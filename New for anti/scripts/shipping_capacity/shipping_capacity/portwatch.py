"""Keyless IMF PortWatch ArcGIS client and baseline anomaly calculation."""

from __future__ import annotations

import copy
import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from shipping_capacity.ml_validation import analyze_capacity_series


PORTWATCH_QUERY_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
PORTWATCH_PORTS_QUERY_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Ports_Data/FeatureServer/0/query"
)

CAPACITY_FIELDS = {
    "container": "capacity_container",
    "dry_bulk": "capacity_dry_bulk",
    "general_cargo": "capacity_general_cargo",
    "tanker": "capacity_tanker",
    "all": "capacity",
}

ML_PRIMARY_METRIC = {
    "chokepoint6": "tanker",
}

PORTWATCH_METRIC_UNIT = "estimated_trade_tonnes_per_day"
PORTWATCH_METRIC_DEFINITION = (
    "PortWatch estimated daily trade volume in metric tonnes, derived from vessel DWT "
    "and estimated payload/utilization; not observed vessel DWT."
)


def _date_key(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("-inf")
    return float("-inf")


def _iso_date(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).date().isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return statistics.fmean(values) if values else None


def _daily_average_window(
    history: list[dict[str, Any]],
    *,
    required_observations: int,
    label_ko: str,
) -> dict[str, Any]:
    """Publish a transparent average of observed daily records only.

    PortWatch normally provides one observation per day, but upstream revisions
    or AIS coverage can leave gaps.  This helper never fills those gaps or
    converts an observation count into a fabricated calendar-day value.
    """

    points = history[-required_observations:]
    if len(points) < required_observations:
        return {
            "label_ko": label_ko,
            "status": "insufficient_observed_days",
            "value": None,
            "observation_count": len(points),
            "required_observation_count": required_observations,
            "start_date": points[0]["date"] if points else None,
            "end_date": points[-1]["date"] if points else None,
            "calculation": "mean_of_observed_daily_values_no_imputation",
        }
    return {
        "label_ko": label_ko,
        "status": "observed_daily_average",
        "value": statistics.fmean(float(point["value"]) for point in points),
        "observation_count": len(points),
        "required_observation_count": required_observations,
        "start_date": points[0]["date"],
        "end_date": points[-1]["date"],
        "calculation": "mean_of_observed_daily_values_no_imputation",
    }


def _prior_daily_average_window(
    history: list[dict[str, Any]],
    *,
    current_observations: int,
    required_observations: int,
    label_ko: str,
) -> dict[str, Any]:
    """Average the 28 observations immediately before the current seven."""

    if len(history) < current_observations + required_observations:
        return _daily_average_window(
            [],
            required_observations=required_observations,
            label_ko=label_ko,
        )
    return _daily_average_window(
        history[-(current_observations + required_observations) : -current_observations],
        required_observations=required_observations,
        label_ko=label_ko,
    )


def _daily_averages_contract(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the UI-ready daily observation and rolling-average contract."""

    latest = history[-1] if history else None
    return {
        "status": (
            "observed_daily_estimated_trade_volume"
            if history
            else "unavailable_cached_summary_only"
        ),
        "unit": PORTWATCH_METRIC_UNIT,
        "definition": PORTWATCH_METRIC_DEFINITION,
        "latest_daily_observation": (
            {"date": latest["date"], "value": latest["value"]}
            if latest
            else None
        ),
        "trailing_7d_average": _daily_average_window(
            history,
            required_observations=7,
            label_ko="최근 7일 일평균",
        ),
        "prior_28d_average": _prior_daily_average_window(
            history,
            current_observations=7,
            required_observations=28,
            label_ko="직전 28일 일평균",
        ),
        "warning_ko": (
            "PortWatch의 일별 추정 교역량 관측치를 평균한 값입니다. 결측일은 보간하지 "
            "않으며, 실제 화물 명세·통항 DWT·물리적 봉쇄율을 뜻하지 않습니다."
        ),
    }


def _metric_history_contract(
    valid_rows: list[dict[str, Any]],
    *,
    metric_key: str,
    field: str,
) -> dict[str, Any]:
    """Publish one observed daily PortWatch series for a displayed ship type.

    ``metrics`` holds the 7-day / prior-28-day summaries.  It is not enough to
    draw a daily container or tanker chart, so this companion contract keeps
    the original daily values separate and never asks the browser to infer
    them from averages.
    """

    history = [
        {"date": _iso_date(row.get("date")), "value": float(row[field])}
        for row in valid_rows
        if _iso_date(row.get("date")) is not None
        and isinstance(row.get(field), (int, float))
    ]
    return {
        "metric_key": metric_key,
        "field": field,
        "unit": PORTWATCH_METRIC_UNIT,
        "definition": PORTWATCH_METRIC_DEFINITION,
        "history": history,
        "history_point_count": len(history),
        "history_status": (
            "observed_daily_estimated_trade_volume"
            if history
            else "unavailable_cached_summary_only"
        ),
        "daily_averages": _daily_averages_contract(history),
    }


def _normalize_metric_history_contract(
    raw: Any,
    *,
    metric_key: str,
) -> dict[str, Any] | None:
    """Make cached metric histories safe without inventing missing days."""

    if not isinstance(raw, dict):
        return None
    history = raw.get("history")
    if not isinstance(history, list):
        history = []
    field = raw.get("field", CAPACITY_FIELDS.get(metric_key, CAPACITY_FIELDS["all"]))
    daily_averages = raw.get("daily_averages")
    if not isinstance(daily_averages, dict):
        daily_averages = _daily_averages_contract(history)
    return {
        **raw,
        "metric_key": metric_key,
        "field": field,
        "unit": PORTWATCH_METRIC_UNIT,
        "definition": PORTWATCH_METRIC_DEFINITION,
        "history": history,
        "history_point_count": len(history),
        "history_status": raw.get(
            "history_status",
            "observed_daily_estimated_trade_volume"
            if history
            else "unavailable_cached_summary_only",
        ),
        "daily_averages": daily_averages,
    }


def _mae(actual: list[float], predicted: list[float]) -> float:
    return statistics.fmean(abs(a - p) for a, p in zip(actual, predicted))


def _r_squared(actual: list[float], predicted: list[float]) -> float | None:
    mean_actual = statistics.fmean(actual)
    denominator = sum((value - mean_actual) ** 2 for value in actual)
    if denominator == 0:
        return None
    numerator = sum((value - estimate) ** 2 for value, estimate in zip(actual, predicted))
    return 1.0 - numerator / denominator


def validate_7d_28d_signal(
    rows: list[dict[str, Any]],
    field: str,
    *,
    current_window: int = 7,
    baseline_window: int = 28,
    forward_window: int = 7,
) -> dict[str, Any]:
    """Walk-forward OLS check for persistence of the 7d-vs-28d trade-volume signal.

    The feature is the signed gap between the current seven observations and
    the preceding 28.  The target is the signed gap of the following seven
    observations against the same preceding baseline.  This is a diagnostic
    for signal persistence, not a closure-probability forecast.
    """

    values = [
        float(row[field])
        for row in sorted(rows, key=lambda row: _date_key(row.get("date")))
        if _date_key(row.get("date")) != float("-inf")
        and isinstance(row.get(field), (int, float))
    ]
    history = baseline_window + current_window
    pairs: list[tuple[float, float]] = []
    for stop in range(history, len(values) - forward_window + 1):
        baseline = values[stop - history : stop - current_window]
        current = values[stop - current_window : stop]
        future = values[stop : stop + forward_window]
        baseline_mean = statistics.fmean(baseline)
        if baseline_mean == 0:
            continue
        feature = 1.0 - statistics.fmean(current) / baseline_mean
        target = 1.0 - statistics.fmean(future) / baseline_mean
        pairs.append((feature, target))

    if len(pairs) < 30:
        return {
            "status": "insufficient_history",
            "sample_count": len(pairs),
            "minimum_sample_count": 30,
        }

    split = max(20, int(len(pairs) * 0.8))
    split = min(split, len(pairs) - 7)
    train = pairs[:split]
    test = pairs[split:]
    train_x = [pair[0] for pair in train]
    train_y = [pair[1] for pair in train]
    mean_x = statistics.fmean(train_x)
    mean_y = statistics.fmean(train_y)
    variance_x = sum((value - mean_x) ** 2 for value in train_x)
    slope = (
        sum((x - mean_x) * (y - mean_y) for x, y in train) / variance_x
        if variance_x
        else 0.0
    )
    intercept = mean_y - slope * mean_x

    test_x = [pair[0] for pair in test]
    test_y = [pair[1] for pair in test]
    predictions = [intercept + slope * value for value in test_x]
    persistence_predictions = test_x
    test_mae = _mae(test_y, predictions)
    persistence_mae = _mae(test_y, persistence_predictions)
    test_r2 = _r_squared(test_y, predictions)
    beats_persistence = test_mae < persistence_mae
    has_positive_skill = test_r2 is not None and test_r2 > 0 and beats_persistence
    return {
        "status": "exploratory_positive_skill" if has_positive_skill else "exploratory_no_proven_skill",
        "forecast_use": "eligible_for_exploratory_forecast" if has_positive_skill else "descriptive_only",
        "sample_count": len(pairs),
        "train_count": len(train),
        "test_count": len(test),
        "feature": "signed current 7-observation estimated trade-volume gap vs preceding 28",
        "target": "signed next 7-observation estimated trade-volume gap vs same preceding 28",
        "ols_intercept": intercept,
        "ols_slope": slope,
        "test_r2": test_r2,
        "test_mae_fraction": test_mae,
        "persistence_mae_fraction": persistence_mae,
        "beats_persistence": beats_persistence,
        "warning": "Exploratory chronological validation; not a causal model or closure probability.",
    }


class PortWatchClient:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_series(self, portwatch_id: str, record_count: int = 730) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        page_size = min(1000, record_count)
        while len(rows) < record_count:
            requested = min(page_size, record_count - len(rows))
            params = {
                "where": f"portid='{portwatch_id}'",
                "outFields": "date,portid,portname,n_total,capacity,capacity_container,capacity_dry_bulk,capacity_general_cargo,capacity_tanker",
                "returnGeometry": "false",
                "orderByFields": "date DESC",
                "resultOffset": str(offset),
                "resultRecordCount": str(requested),
                "f": "json",
            }
            url = PORTWATCH_QUERY_URL + "?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "global-trade-dashboard/1.0"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
            if "error" in payload:
                raise RuntimeError(f"PortWatch API error: {payload['error']}")
            page = [feature["attributes"] for feature in payload.get("features", [])]
            rows.extend(page)
            if len(page) < requested:
                break
            offset += len(page)

        # Pagination can occasionally repeat a boundary row while the upstream
        # layer is being revised.  Keep one observation per port/date.
        deduplicated: dict[tuple[Any, Any], dict[str, Any]] = {}
        for row in rows:
            deduplicated[(row.get("portid"), row.get("date"))] = row
        rows = list(deduplicated.values())
        rows.sort(key=lambda row: _date_key(row.get("date")))
        return rows

    def fetch_status(self, portwatch_id: str) -> dict[str, Any]:
        return summarize_series(self.fetch_series(portwatch_id), portwatch_id)


class PortWatchPortClient:
    """Read public PortWatch port-call observations for a configured country group.

    The public Daily_Ports_Data layer exposes calls and estimated import/export
    volume, but no anchorage count, berth queue, or vessel waiting-time field.
    This client keeps that boundary explicit rather than converting port calls
    into a fabricated waiting-vessel count.
    """

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_country_group_series(
        self, iso3_codes: list[str], *, record_count: int = 730
    ) -> list[dict[str, Any]]:
        if not iso3_codes:
            raise ValueError("at least one ISO3 code is required")
        safe_codes = [code.strip().upper() for code in iso3_codes if code.strip().isalpha()]
        if len(safe_codes) != len(iso3_codes):
            raise ValueError("ISO3 codes must contain letters only")
        # ArcGIS SQL values are supplied from a checked ISO3-only list.
        where = "ISO3 IN (" + ",".join(f"'{code}'" for code in safe_codes) + ")"
        params = {
            "where": where,
            "outStatistics": json.dumps(
                [
                    {"statisticType": "sum", "onStatisticField": field, "outStatisticFieldName": field}
                    for field in (
                        "portcalls",
                        "portcalls_container",
                        "portcalls_dry_bulk",
                        "portcalls_tanker",
                        "import",
                        "export",
                        "import_container",
                        "export_container",
                        "import_dry_bulk",
                        "export_dry_bulk",
                        "import_tanker",
                        "export_tanker",
                    )
                ]
            ),
            "groupByFieldsForStatistics": "date",
            "orderByFields": "date DESC",
            "returnGeometry": "false",
            "resultRecordCount": str(min(1000, record_count)),
            "f": "json",
        }
        request = urllib.request.Request(
            PORTWATCH_PORTS_QUERY_URL + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": "global-trade-dashboard/1.0"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(f"PortWatch ports API error: {payload['error']}")
        rows = [feature["attributes"] for feature in payload.get("features", [])]
        rows.sort(key=lambda row: _date_key(row.get("date")))
        return rows

    def fetch_group_status(self, group: dict[str, Any]) -> dict[str, Any]:
        rows = self.fetch_country_group_series(
            list(group.get("iso3_codes", [])),
            record_count=int(group.get("record_count", 365)),
        )
        return summarize_port_context(rows, group)


def summarize_port_context(rows: list[dict[str, Any]], group: dict[str, Any]) -> dict[str, Any]:
    """Summarize port-call and estimated cargo anomalies without relabeling them.

    A falling port-call count can be useful corroborating context for a route
    disruption. It is not a direct backlog measure, and no output from this
    function enters scenario behavior shares.
    """

    valid = [row for row in rows if _date_key(row.get("date")) != float("-inf")]
    valid.sort(key=lambda row: _date_key(row.get("date")))
    metrics: dict[str, Any] = {}
    current = valid[-7:]
    baseline = valid[-35:-7] if len(valid) >= 35 else valid[:-7]
    field_by_ship_type = {
        "container": ("portcalls_container", "import_container", "export_container"),
        "dry_bulk": ("portcalls_dry_bulk", "import_dry_bulk", "export_dry_bulk"),
        "tanker": ("portcalls_tanker", "import_tanker", "export_tanker"),
        "all": ("portcalls", "import", "export"),
    }
    for ship_type, fields in field_by_ship_type.items():
        calls_current = _mean(current, fields[0])
        calls_baseline = _mean(baseline, fields[0])
        imports_current = _mean(current, fields[1])
        exports_current = _mean(current, fields[2])
        if calls_current is None or calls_baseline in (None, 0):
            continue
        ratio = calls_current / calls_baseline
        metrics[ship_type] = {
            "portcalls_field": fields[0],
            "current_7d_mean_port_calls": calls_current,
            "prior_28d_mean_port_calls": calls_baseline,
            "port_call_ratio": ratio,
            "port_call_shortfall_fraction": max(0.0, min(1.0, 1.0 - ratio)),
            "current_7d_mean_estimated_import_tonnes": imports_current,
            "current_7d_mean_estimated_export_tonnes": exports_current,
        }
    return {
        "group_id": group.get("id"),
        "name_ko": group.get("name_ko"),
        "iso3_codes": group.get("iso3_codes", []),
        "source_url": PORTWATCH_PORTS_QUERY_URL,
        "latest_date": _iso_date(valid[-1].get("date")) if valid else None,
        "observation_count": len(valid),
        "status": "observed_port_calls_and_estimated_trade_volume" if metrics else "insufficient_history",
        "waiting_anchorage_status": "not_published_in_public_portwatch_daily_ports_layer",
        "waiting_anchorage_warning_ko": "공개 PortWatch Daily_Ports_Data에는 정박 대수·대기시간 필드가 없어, 입항량을 대기·백로그로 환산하지 않습니다.",
        "use_in_model": "diagnostic_context_only_not_behavior_calibration",
        "metrics": metrics,
    }


def normalize_status_contract(status: dict[str, Any]) -> dict[str, Any]:
    """Migrate a cached PortWatch status away from the former DWT mislabel.

    Older snapshots named PortWatch ``capacity_*`` values as DWT even though the
    upstream definition is estimated trade volume in metric tonnes.  Fallback
    snapshots pass through this function so an upstream outage cannot revive
    the incorrect public contract.
    """

    normalized = copy.deepcopy(status)
    for metric in normalized.get("metrics", {}).values():
        current = metric.pop(
            "current_7d_mean_dwt",
            metric.get("current_7d_mean_estimated_trade_tonnes"),
        )
        baseline = metric.pop(
            "prior_28d_mean_dwt",
            metric.get("prior_28d_mean_estimated_trade_tonnes"),
        )
        ratio = metric.pop(
            "capacity_ratio",
            metric.get("estimated_trade_volume_ratio"),
        )
        shortfall = metric.pop(
            "observed_shortfall_fraction",
            metric.get("observed_trade_volume_shortfall_fraction"),
        )
        if shortfall is None:
            shortfall = metric.pop("effective_blockage_fraction", None)
        else:
            metric.pop("effective_blockage_fraction", None)
        remaining = metric.pop(
            "residual_throughput_rate",
            metric.get("remaining_trade_volume_ratio"),
        )
        if current is not None:
            metric["current_7d_mean_estimated_trade_tonnes"] = current
        if baseline is not None:
            metric["prior_28d_mean_estimated_trade_tonnes"] = baseline
        if ratio is not None:
            metric["estimated_trade_volume_ratio"] = ratio
        if shortfall is not None:
            metric["observed_trade_volume_shortfall_fraction"] = shortfall
        if remaining is None and shortfall is not None:
            remaining = 1.0 - shortfall
        if remaining is not None:
            metric["remaining_trade_volume_ratio"] = remaining
        metric["unit"] = PORTWATCH_METRIC_UNIT
        metric["definition"] = PORTWATCH_METRIC_DEFINITION

    for validation in normalized.get("signal_validation", {}).values():
        if validation.get("feature"):
            validation["feature"] = (
                "signed current 7-observation estimated trade-volume gap vs preceding 28"
            )
        if validation.get("target"):
            validation["target"] = (
                "signed next 7-observation estimated trade-volume gap vs same preceding 28"
            )

    history = normalized.get("history")
    if not isinstance(history, list):
        history = []
    normalized["history"] = history
    inferred_metric_key = (
        "tanker"
        if "tanker" in normalized.get("metrics", {})
        and "all" not in normalized.get("metrics", {})
        else "all"
    )
    history_metric_key = normalized.get("history_metric_key", inferred_metric_key)
    normalized["history_metric_key"] = history_metric_key
    normalized["history_field"] = normalized.get(
        "history_field",
        CAPACITY_FIELDS.get(history_metric_key, CAPACITY_FIELDS["all"]),
    )
    normalized["history_unit"] = PORTWATCH_METRIC_UNIT
    normalized["history_point_count"] = len(history)
    normalized["history_status"] = normalized.get(
        "history_status",
        (
            "observed_daily_estimated_trade_volume"
            if history
            else "unavailable_cached_summary_only"
        ),
    )
    daily_averages = normalized.get("daily_averages")
    if not isinstance(daily_averages, dict):
        # An older cache may have only 7d/28d summaries.  Publish unavailable
        # daily values rather than reconstructing a time series from them.
        daily_averages = _daily_averages_contract(history)
    normalized["daily_averages"] = daily_averages

    # A legacy cache has only one representative history.  Do not copy that
    # into every ship type: it would turn an all-vessel series into false
    # container/bulk/tanker observations.
    raw_metric_histories = normalized.get("metric_histories", {})
    metric_histories: dict[str, Any] = {}
    if isinstance(raw_metric_histories, dict):
        for metric_key, raw_history in raw_metric_histories.items():
            if metric_key not in CAPACITY_FIELDS:
                continue
            history_contract = _normalize_metric_history_contract(
                raw_history, metric_key=metric_key
            )
            if history_contract is not None:
                metric_histories[metric_key] = history_contract
    normalized["metric_histories"] = metric_histories

    normalized["quality"] = "observed_estimated_trade_volume_shortfall_7d_vs_prior_28d"
    normalized["metric_unit"] = PORTWATCH_METRIC_UNIT
    normalized["metric_definition"] = PORTWATCH_METRIC_DEFINITION
    normalized["interpretation"] = (
        "Short-term estimated trade-volume anomaly used as a disruption signal; "
        "not observed DWT and not proof of literal physical closure."
    )
    return normalized


def summarize_series(rows: list[dict[str, Any]], portwatch_id: str) -> dict[str, Any]:
    """Compare latest seven observations with the preceding 28 observations."""

    valid = [row for row in rows if _date_key(row.get("date")) != float("-inf")]
    valid.sort(key=lambda row: _date_key(row.get("date")))
    history_metric_key = ML_PRIMARY_METRIC.get(portwatch_id, "all")
    history_field = CAPACITY_FIELDS[history_metric_key]
    metric_histories = {
        metric_key: _metric_history_contract(
            valid, metric_key=metric_key, field=field
        )
        for metric_key, field in CAPACITY_FIELDS.items()
    }
    history = metric_histories[history_metric_key]["history"]
    if len(valid) < 14:
        return {
            "portwatch_id": portwatch_id,
            "quality": "insufficient_history",
            "observation_count": len(valid),
            "metrics": {},
            "history": history,
            "history_metric_key": history_metric_key,
            "history_field": history_field,
            "history_unit": PORTWATCH_METRIC_UNIT,
            "history_point_count": len(history),
            "history_status": "observed_daily_estimated_trade_volume",
            "daily_averages": _daily_averages_contract(history),
            "metric_histories": metric_histories,
        }
    current = valid[-7:]
    baseline = valid[-35:-7] if len(valid) >= 35 else valid[:-7]
    metrics: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    multi_model_analysis: dict[str, Any] = {}
    for ship_type, field in CAPACITY_FIELDS.items():
        current_mean = _mean(current, field)
        baseline_mean = _mean(baseline, field)
        if current_mean is None or baseline_mean in (None, 0):
            continue
        ratio = current_mean / baseline_mean
        trade_volume_shortfall = max(0.0, min(1.0, 1.0 - ratio))
        metrics[ship_type] = {
            "field": field,
            "unit": PORTWATCH_METRIC_UNIT,
            "definition": PORTWATCH_METRIC_DEFINITION,
            "current_7d_mean_estimated_trade_tonnes": current_mean,
            "prior_28d_mean_estimated_trade_tonnes": baseline_mean,
            "estimated_trade_volume_ratio": ratio,
            "observed_trade_volume_shortfall_fraction": trade_volume_shortfall,
            "remaining_trade_volume_ratio": 1.0 - trade_volume_shortfall,
            "change_pct": (ratio - 1.0) * 100.0,
        }
        validation[ship_type] = validate_7d_28d_signal(valid, field)
        primary_ml_metric = ML_PRIMARY_METRIC.get(portwatch_id, "all")
        if ship_type == primary_ml_metric:
            field_values = [
                float(row[field])
                for row in valid
                if isinstance(row.get(field), (int, float))
            ]
            multi_model_analysis[ship_type] = analyze_capacity_series(field_values)
    latest_date = _iso_date(valid[-1]["date"])
    return {
        "portwatch_id": portwatch_id,
        "portname": valid[-1].get("portname"),
        "latest_date": latest_date,
        "quality": "observed_estimated_trade_volume_shortfall_7d_vs_prior_28d",
        "current_window_days": 7,
        "baseline_window_days": 28,
        "metric_unit": PORTWATCH_METRIC_UNIT,
        "metric_definition": PORTWATCH_METRIC_DEFINITION,
        "interpretation": (
            "Short-term estimated trade-volume anomaly used as a disruption signal; "
            "not observed DWT and not proof of literal physical closure."
        ),
        "observation_count": len(valid),
        "history": history,
        "history_metric_key": history_metric_key,
        "history_field": history_field,
        "history_unit": PORTWATCH_METRIC_UNIT,
        "history_point_count": len(history),
        "history_status": "observed_daily_estimated_trade_volume",
        "daily_averages": _daily_averages_contract(history),
        "metric_histories": metric_histories,
        "history_warning": (
            "Daily PortWatch transit-volume estimate in metric tonnes; subject to "
            "AIS coverage and upstream revisions, and not observed DWT."
        ),
        "metrics": metrics,
        "signal_validation": validation,
        "multi_model_analysis": multi_model_analysis,
        "multi_model_primary_metric": history_metric_key,
    }
