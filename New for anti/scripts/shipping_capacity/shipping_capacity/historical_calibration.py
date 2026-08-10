"""Historical event calibration for PortWatch chokepoint trade-volume signals.

The adapter calibrates observed throughput severity, duration and recovery.  A
single chokepoint series cannot identify whether missing flow rerouted, waited,
was cancelled, or lost insurance, so those behavioral states remain explicitly
partially identified.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from shipping_capacity.portwatch import CAPACITY_FIELDS, PortWatchClient, _iso_date


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _moving_block_sample(values: list[float], rng: random.Random) -> list[float]:
    if len(values) <= 1:
        return list(values)
    block_size = min(7, max(2, len(values) // 3))
    maximum_start = max(0, len(values) - block_size)
    sampled: list[float] = []
    while len(sampled) < len(values):
        start = rng.randint(0, maximum_start)
        sampled.extend(values[start : start + block_size])
    return sampled[: len(values)]


def _bootstrap_ratio_interval(
    baseline: list[float],
    event: list[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    if not baseline or not event or statistics.fmean(baseline) == 0:
        return {"status": "insufficient_data"}
    rng = random.Random(seed)
    ratios = []
    for _ in range(iterations):
        sampled_baseline = _moving_block_sample(baseline, rng)
        sampled_event = _moving_block_sample(event, rng)
        baseline_mean = statistics.fmean(sampled_baseline)
        if baseline_mean:
            ratios.append(statistics.fmean(sampled_event) / baseline_mean)
    return {
        "status": "available" if ratios else "insufficient_data",
        "method": "deterministic moving-block bootstrap",
        "iterations": len(ratios),
        "block_days_max": 7,
        "ratio_ci_95_low": _quantile(ratios, 0.025),
        "ratio_ci_95_high": _quantile(ratios, 0.975),
        "shortfall_ci_95_low": (
            max(0.0, 1.0 - _quantile(ratios, 0.975)) if ratios else None
        ),
        "shortfall_ci_95_high": (
            max(0.0, 1.0 - _quantile(ratios, 0.025)) if ratios else None
        ),
    }


def _placebo_test(
    observations: list[tuple[date, float]],
    *,
    event_start: date,
    event_count: int,
    baseline_days: int,
    lookback_days: int,
    observed_shortfall: float,
) -> dict[str, Any]:
    prior = [row for row in observations if 0 < (event_start - row[0]).days <= lookback_days]
    placebo_shortfalls = []
    for stop in range(baseline_days, len(prior) - event_count + 1):
        baseline = [value for _, value in prior[stop - baseline_days : stop]]
        candidate = [value for _, value in prior[stop : stop + event_count]]
        baseline_mean = statistics.fmean(baseline)
        if baseline_mean:
            placebo_shortfalls.append(1.0 - statistics.fmean(candidate) / baseline_mean)
    if not placebo_shortfalls:
        return {"status": "insufficient_history", "sample_count": 0}
    exceedances = sum(value >= observed_shortfall for value in placebo_shortfalls)
    percentile = sum(value <= observed_shortfall for value in placebo_shortfalls) / len(
        placebo_shortfalls
    )
    return {
        "status": "available",
        "method": "rolling pre-event windows with the same observation count",
        "lookback_days": lookback_days,
        "sample_count": len(placebo_shortfalls),
        "event_shortfall_percentile": percentile,
        "one_sided_empirical_p_value": (exceedances + 1) / (len(placebo_shortfalls) + 1),
        "placebo_shortfall_median": statistics.median(placebo_shortfalls),
        "placebo_shortfall_p95": _quantile(placebo_shortfalls, 0.95),
        "warning": (
            "Overlapping rolling windows are dependent; this is an empirical rarity "
            "diagnostic, not a formal independent-sample causal p-value."
        ),
    }


def _recovery_days(
    observations: list[tuple[date, float]],
    *,
    event_end: date,
    baseline_mean: float,
    threshold: float = 0.90,
    rolling_days: int = 7,
    confirmation_days: int = 3,
) -> int | None:
    post = [row for row in observations if row[0] > event_end]
    qualifying_dates = []
    for stop in range(rolling_days, len(post) + 1):
        window = [value for _, value in post[stop - rolling_days : stop]]
        if statistics.fmean(window) >= baseline_mean * threshold:
            qualifying_dates.append(post[stop - 1][0])
        else:
            qualifying_dates.clear()
        if len(qualifying_dates) >= confirmation_days:
            return (qualifying_dates[0] - event_end).days
    return None


def calibrate_metric(
    rows: list[dict[str, Any]],
    event: dict[str, Any],
    metric: str,
    *,
    baseline_days: int,
    placebo_lookback_days: int,
    bootstrap_iterations: int,
) -> dict[str, Any]:
    field = CAPACITY_FIELDS[metric]
    start = date.fromisoformat(event["start_date"])
    end = date.fromisoformat(event["end_date"])
    observations = []
    vessel_observations = []
    for row in rows:
        iso = _iso_date(row.get("date"))
        value = row.get(field)
        if iso and isinstance(value, (int, float)):
            observations.append((date.fromisoformat(iso), float(value)))
        vessels = row.get("n_total")
        if iso and isinstance(vessels, (int, float)):
            vessel_observations.append((date.fromisoformat(iso), float(vessels)))
    observations.sort()
    vessel_observations.sort()
    baseline_rows = [row for row in observations if row[0] < start][-baseline_days:]
    event_rows = [row for row in observations if start <= row[0] <= end]
    expected_event_days = (end - start).days + 1
    if len(baseline_rows) < min(14, baseline_days) or not event_rows:
        return {
            "status": "insufficient_data",
            "metric": metric,
            "field": field,
            "baseline_observation_count": len(baseline_rows),
            "event_observation_count": len(event_rows),
        }
    baseline_values = [value for _, value in baseline_rows]
    event_values = [value for _, value in event_rows]
    baseline_mean = statistics.fmean(baseline_values)
    event_mean = statistics.fmean(event_values)
    ratio = event_mean / baseline_mean if baseline_mean else 0.0
    signed_shortfall = 1.0 - ratio

    rolling_shortfalls = []
    for stop in range(min(7, len(event_values)), len(event_values) + 1):
        window = event_values[max(0, stop - 7) : stop]
        rolling_shortfalls.append(1.0 - statistics.fmean(window) / baseline_mean)

    baseline_vessels = [value for when, value in vessel_observations if when < start][
        -baseline_days:
    ]
    event_vessels = [value for when, value in vessel_observations if start <= when <= end]
    vessel_ratio = None
    if baseline_vessels and event_vessels and statistics.fmean(baseline_vessels):
        vessel_ratio = statistics.fmean(event_vessels) / statistics.fmean(baseline_vessels)

    bootstrap = _bootstrap_ratio_interval(
        baseline_values,
        event_values,
        iterations=bootstrap_iterations,
        seed=sum(ord(char) for char in f"{event['event_id']}:{metric}"),
    )
    placebo = _placebo_test(
        observations,
        event_start=start,
        event_count=len(event_values),
        baseline_days=baseline_days,
        lookback_days=placebo_lookback_days,
        observed_shortfall=signed_shortfall,
    )
    recovery = None
    if event.get("window_end_is_resolution"):
        recovery = _recovery_days(
            observations,
            event_end=end,
            baseline_mean=baseline_mean,
        )
    p_value = placebo.get("one_sided_empirical_p_value")
    evidence = (
        "strong_event_signal"
        if signed_shortfall >= 0.10 and p_value is not None and p_value <= 0.05
        else "moderate_event_signal"
        if signed_shortfall >= 0.05
        else "weak_or_no_shortfall_signal"
    )
    return {
        "status": "calibrated_observed_throughput",
        "metric": metric,
        "field": field,
        "unit": "estimated_trade_tonnes_per_day",
        "baseline_start_date": baseline_rows[0][0].isoformat(),
        "baseline_end_date": baseline_rows[-1][0].isoformat(),
        "baseline_observation_count": len(baseline_rows),
        "event_observation_count": len(event_rows),
        "event_expected_calendar_days": expected_event_days,
        "event_coverage_ratio": len(event_rows) / expected_event_days,
        "baseline_mean_estimated_trade_tonnes": baseline_mean,
        "event_mean_estimated_trade_tonnes": event_mean,
        "observed_event_to_baseline_ratio": ratio,
        "observed_mean_shortfall_fraction": signed_shortfall,
        "observed_peak_7d_shortfall_fraction": max(rolling_shortfalls),
        "observed_vessel_count_ratio": vessel_ratio,
        "trade_volume_vs_vessel_ratio_gap": ratio - vessel_ratio if vessel_ratio is not None else None,
        "bootstrap": bootstrap,
        "placebo_test": placebo,
        "recovery_definition": "first 7d mean at or above 90% of baseline, confirmed for 3 days",
        "recovery_days_after_window_end": recovery,
        "evidence_grade": evidence,
    }


def calibrate_event(
    rows: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    baseline_days: int = 28,
    placebo_lookback_days: int = 365,
    bootstrap_iterations: int = 2000,
) -> dict[str, Any]:
    metrics = {
        metric: calibrate_metric(
            rows,
            event,
            metric,
            baseline_days=baseline_days,
            placebo_lookback_days=placebo_lookback_days,
            bootstrap_iterations=bootstrap_iterations,
        )
        for metric in event.get("metrics", [event.get("primary_metric", "all")])
    }
    primary_metric = event.get("primary_metric", "all")
    return {
        **event,
        "duration_calendar_days": (
            date.fromisoformat(event["end_date"])
            - date.fromisoformat(event["start_date"])
        ).days
        + 1,
        "primary_metric": primary_metric,
        "primary_result": metrics.get(primary_metric),
        "metrics": metrics,
        "throughput_calibration_status": metrics.get(primary_metric, {}).get("status"),
        "behavior_partition_status": "not_identified_by_single_chokepoint_throughput",
        "behavior_partition_warning": (
            "PortWatch observes passage trade volume and vessel count, but cannot uniquely "
            "separate rerouting, waiting, cancellation, or insurance exclusion."
        ),
    }


def build_profile_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event["event_type"]].append(event)
    output = {}
    for event_type, rows in grouped.items():
        usable = [
            row["primary_result"]
            for row in rows
            if row.get("primary_result", {}).get("status") == "calibrated_observed_throughput"
        ]
        shortfalls = [row["observed_mean_shortfall_fraction"] for row in usable]
        output[event_type] = {
            "event_count": len(rows),
            "calibrated_event_count": len(usable),
            "event_ids": [row["event_id"] for row in rows],
            "mean_shortfall_range": (
                {"minimum": min(shortfalls), "maximum": max(shortfalls)}
                if shortfalls
                else None
            ),
            "evidence_grade": "single_event_reference" if len(usable) == 1 else "multi_event_reference",
            "throughput_severity_status": "empirically_calibrated" if usable else "not_available",
            "behavior_multiplier_status": "prior_not_numerically_identified",
        }
    return output


def build_calibration(
    config: dict[str, Any],
    series_by_portwatch_id: dict[str, list[dict[str, Any]]],
    fetch_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    calibrated = []
    for event in config["events"]:
        rows = series_by_portwatch_id.get(event["portwatch_id"], [])
        calibrated.append(
            calibrate_event(
                rows,
                event,
                baseline_days=int(config.get("baseline_days", 28)),
                placebo_lookback_days=int(config.get("placebo_lookback_days", 365)),
                bootstrap_iterations=int(config.get("bootstrap_iterations", 2000)),
            )
        )
    return {
        "status": (
            "throughput_calibrated_behavior_partition_partially_identified"
            if any(row.get("throughput_calibration_status") == "calibrated_observed_throughput" for row in calibrated)
            else "calibration_unavailable"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "IMF PortWatch daily chokepoint estimated trade volume and official event windows",
        "method": {
            "baseline": "28 observations immediately before each event window",
            "uncertainty": "moving-block bootstrap 95% interval",
            "rarity": "same-length rolling placebo windows in the preceding year",
            "rarity_warning": (
                "overlapping placebo windows are dependent and the empirical p-value is diagnostic"
            ),
            "recovery": "first post-resolution 7d mean >=90% of baseline for 3 consecutive days",
        },
        "identification_boundary": (
            "Observed throughput severity, duration and recovery are calibrated. "
            "Reroute/wait/cancel/insurance shares are not uniquely identifiable from a single passage series."
        ),
        "fetch_errors": fetch_errors or [],
        "events": calibrated,
        "profile_evidence": build_profile_evidence(calibrated),
    }


def preserve_failed_event_calibrations(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Keep the last valid event result when a PortWatch refresh is unavailable."""

    if not previous or not current.get("fetch_errors"):
        return current
    failed_ids = {row["portwatch_id"] for row in current["fetch_errors"]}
    previous_by_event = {row["event_id"]: row for row in previous.get("events", [])}
    preserved = []
    events = []
    for event in current.get("events", []):
        old = previous_by_event.get(event["event_id"])
        if event.get("portwatch_id") in failed_ids and old:
            events.append(
                {
                    **old,
                    "refresh_status": "previous_calibration_preserved_after_fetch_error",
                    "refresh_attempted_at": current["generated_at"],
                }
            )
            preserved.append(event["event_id"])
        else:
            events.append(event)
    merged = {**current, "events": events}
    merged["profile_evidence"] = build_profile_evidence(events)
    merged["preserved_previous_event_ids"] = preserved
    if events:
        merged["status"] = "throughput_calibrated_behavior_partition_partially_identified"
    return merged


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "historical_events.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "config" / "event_calibration.json",
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    client = PortWatchClient(timeout_seconds=90)
    record_count = int(config.get("record_count_per_chokepoint", 4000))
    series_by_id = {}
    fetch_errors = []
    for portwatch_id in sorted({row["portwatch_id"] for row in config["events"]}):
        try:
            series_by_id[portwatch_id] = client.fetch_series(
                portwatch_id,
                record_count=record_count,
            )
            print(
                f"[historical_calibration] {portwatch_id} rows={len(series_by_id[portwatch_id])}",
                flush=True,
            )
        except Exception as exc:
            fetch_errors.append({"portwatch_id": portwatch_id, "error": str(exc)})
    result = build_calibration(config, series_by_id, fetch_errors)
    previous = None
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
    result = preserve_failed_event_calibrations(previous, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} ({len(result['events'])} events)")


if __name__ == "__main__":
    main()
