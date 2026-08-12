#!/usr/bin/env python3
"""Generate a local simulator-grid and PortWatch backtest validation report."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shipping_capacity.validation import (
    run_temporary_environment_grid,
    run_temporary_scenario_grid,
)
from shipping_capacity.comtrade_routes import apply_route_flows


ROOT = Path(__file__).resolve().parent


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_portwatch_backtests(snapshot: dict[str, Any]) -> dict[str, Any]:
    results = []
    for chokepoint_id, status in snapshot.get("chokepoints_live", {}).items():
        metric = status.get("multi_model_primary_metric")
        analysis = status.get("multi_model_analysis", {}).get(metric, {})
        if not analysis:
            continue
        selected_name = analysis.get("selected_model")
        selected_backtest = next(
            (
                row
                for row in analysis.get("walk_forward_backtest", {}).get("models", [])
                if row.get("model") == selected_name
            ),
            None,
        )
        results.append(
            {
                "chokepoint_id": chokepoint_id,
                "metric": metric,
                "latest_date": status.get("latest_date"),
                "selected_model": selected_name,
                "forecast_use": analysis.get("forecast_use"),
                "published_next_7d_shortfall_fraction": analysis.get(
                    "published_next_7d_shortfall_fraction"
                ),
                "holdout_beats_best_simple_baseline_by_5pct": analysis.get(
                    "beats_best_simple_baseline_by_5pct"
                ),
                "walk_forward_beats_best_simple_baseline_by_5pct": analysis.get(
                    "backtest_beats_best_simple_baseline_by_5pct"
                ),
                "walk_forward_positive_r2": analysis.get("backtest_positive_r2"),
                "walk_forward_selected_model_metrics": selected_backtest,
                "walk_forward_method": analysis.get("walk_forward_backtest", {}).get(
                    "method"
                ),
            }
        )
    return {
        "status": "available" if results else "not_available",
        "chokepoint_count": len(results),
        "results": results,
    }


def validate_historical_event_calibration(snapshot: dict[str, Any]) -> dict[str, Any]:
    calibration = snapshot.get("historical_event_calibration", {})
    failures = []
    summaries = []
    for event in calibration.get("events", []):
        primary = event.get("primary_result") or {}
        ratio = primary.get("observed_event_to_baseline_ratio")
        shortfall = primary.get("observed_mean_shortfall_fraction")
        bootstrap = primary.get("bootstrap", {})
        placebo = primary.get("placebo_test", {})
        checks = {
            "primary_throughput_is_calibrated": (
                primary.get("status") == "calibrated_observed_throughput"
            ),
            "ratio_and_shortfall_are_complements": (
                isinstance(ratio, (int, float))
                and isinstance(shortfall, (int, float))
                and math.isclose(ratio + shortfall, 1.0, abs_tol=1e-8)
            ),
            "event_coverage_is_at_least_80pct": (
                primary.get("event_coverage_ratio", 0) >= 0.80
            ),
            "bootstrap_interval_is_ordered": (
                bootstrap.get("ratio_ci_95_low") is not None
                and bootstrap.get("ratio_ci_95_high") is not None
                and bootstrap["ratio_ci_95_low"] <= bootstrap["ratio_ci_95_high"]
            ),
            "placebo_p_value_is_valid": (
                isinstance(placebo.get("one_sided_empirical_p_value"), (int, float))
                and 0 <= placebo["one_sided_empirical_p_value"] <= 1
            ),
            "behavior_partition_is_not_overclaimed": (
                event.get("behavior_partition_status")
                == "not_identified_by_single_chokepoint_throughput"
            ),
        }
        failures.extend(
            {"event_id": event.get("event_id"), "check": name}
            for name, passed in checks.items()
            if not passed
        )
        summaries.append(
            {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "metric": event.get("primary_metric"),
                "mean_shortfall_fraction": shortfall,
                "peak_7d_shortfall_fraction": primary.get(
                    "observed_peak_7d_shortfall_fraction"
                ),
                "shortfall_ci_95": [
                    bootstrap.get("shortfall_ci_95_low"),
                    bootstrap.get("shortfall_ci_95_high"),
                ],
                "placebo_p_value": placebo.get("one_sided_empirical_p_value"),
                "recovery_days_after_window_end": primary.get(
                    "recovery_days_after_window_end"
                ),
                "behavior_partition_status": event.get("behavior_partition_status"),
            }
        )
    return {
        "status": "passed" if summaries and not failures else "failed",
        "event_count": len(summaries),
        "failure_count": len(failures),
        "failures": failures,
        "identification_boundary": calibration.get("identification_boundary"),
        "events": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT.parent.parent / "public" / "data" / "shipping_capacity_v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "generated" / "validation_report.json",
    )
    args = parser.parse_args()

    fleet = load_json(ROOT / "config" / "fleet_2025.json")
    routes = load_json(ROOT / "config" / "routes.json")
    comtrade_path = ROOT / "config" / "comtrade_route_flows.json"
    routes = apply_route_flows(
        routes,
        load_json(comtrade_path) if comtrade_path.exists() else None,
    )
    fleet_by_type = {row["ship_type"]: row["dwt"] for row in fleet["fleet_by_type"]}
    snapshot = load_json(args.snapshot) if args.snapshot.exists() else {}
    diagnostics_path = args.snapshot.parent / "shipping_capacity_diagnostics_v1.json"
    backtests_path = args.snapshot.parent / "shipping_capacity_backtests_v1.json"
    diagnostics = load_json(diagnostics_path) if diagnostics_path.exists() else {}
    backtests = load_json(backtests_path) if backtests_path.exists() else {}
    validation_snapshot = {**snapshot, **diagnostics, **backtests}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_model_version": snapshot.get("model", {}).get("version"),
        "snapshot_generated_at": snapshot.get("generated_at"),
        "simulator_validation": run_temporary_scenario_grid(routes, fleet_by_type),
        "environment_simulator_validation": run_temporary_environment_grid(
            routes, fleet_by_type
        ),
        "portwatch_backtests": extract_portwatch_backtests(validation_snapshot),
        "historical_event_calibration_validation": (
            validate_historical_event_calibration(validation_snapshot)
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
