"""Safe collection and first-pass validation for two external CPI pathways.

The module intentionally reports *conditional predictive associations*, never
causal effects or live signals.  It keeps the collection separate from the
Table 6/7 contribution pipeline and does not mutate the dashboard data pack.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from scipy.stats import norm
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, kpss

from .api import fetch_series


EIA_SERIES_ENDPOINT = "https://api.eia.gov/v2/seriesid/"
FRED_OBSERVATIONS_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"


class ExternalBacktestError(RuntimeError):
    """Raised for a failed source response without revealing credentials."""


@dataclass(frozen=True)
class MonthlyPoint:
    month: str
    value: float


def _month(value: str) -> str:
    return value[:7]


def _safe_urlopen(request: Request, *, opener=urlopen, timeout: int = 60) -> Mapping[str, Any]:
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ExternalBacktestError(f"source request failed ({type(exc).__name__})") from exc


def fetch_eia_monthly_series(
    series_id: str,
    *,
    api_key: str,
    opener=urlopen,
) -> list[MonthlyPoint]:
    """Fetch a legacy EIA series through v2 and aggregate daily/weekly values.

    The key is only placed into the request URL because EIA requires it there;
    neither the request nor an error message is logged or persisted.
    """
    if not api_key:
        raise ValueError("EIA_API_KEY is required")
    query = urlencode({"api_key": api_key, "data[]": "value", "length": 5000})
    request = Request(f"{EIA_SERIES_ENDPOINT}{series_id}?{query}", headers={"Accept": "application/json"})
    payload = _safe_urlopen(request, opener=opener)
    rows = payload.get("response", {}).get("data", [])
    if not rows:
        raise ExternalBacktestError(f"EIA returned no observations for configured series {series_id}")
    by_month: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        raw = row.get("value")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and row.get("period"):
            by_month[_month(str(row["period"]))].append(value)
    if not by_month:
        raise ExternalBacktestError(f"EIA returned no numeric observations for configured series {series_id}")
    return [MonthlyPoint(month, float(np.mean(values))) for month, values in sorted(by_month.items())]


def fetch_fred_monthly_series(
    series_id: str,
    *,
    api_key: str,
    start: str,
    opener=urlopen,
) -> list[MonthlyPoint]:
    """Fetch an observed FRED series; release vintages are not substituted."""
    if not api_key:
        raise ValueError("FRED_API_KEY is required")
    query = urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": f"{start}-01",
    })
    request = Request(f"{FRED_OBSERVATIONS_ENDPOINT}?{query}", headers={"Accept": "application/json"})
    payload = _safe_urlopen(request, opener=opener)
    points: list[MonthlyPoint] = []
    for row in payload.get("observations", []):
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            points.append(MonthlyPoint(_month(str(row["date"])), value))
    if not points:
        raise ExternalBacktestError(f"FRED returned no numeric observations for configured series {series_id}")
    return points


def bls_monthly_series(
    response: Mapping[str, Any],
    series_id: str,
) -> list[MonthlyPoint]:
    """Normalize BLS index observations returned by the existing BLS client."""
    out: list[MonthlyPoint] = []
    for row in response[series_id].get("data", []):
        period = str(row.get("period", ""))
        if not (period.startswith("M") and period[1:].isdigit() and 1 <= int(period[1:]) <= 12):
            continue
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            out.append(MonthlyPoint(f"{row['year']}-{int(period[1:]):02d}", value))
    points = {point.month: point for point in out}
    return [points[key] for key in sorted(points)]


def mom_pct(points: Iterable[MonthlyPoint]) -> dict[str, float]:
    ordered = sorted(points, key=lambda point: point.month)
    out: dict[str, float] = {}
    previous: MonthlyPoint | None = None
    for point in ordered:
        if previous and previous.value and point.value > 0:
            out[point.month] = round((point.value / previous.value - 1.0) * 100.0, 10)
        previous = point
    return out


def _lag(month: str, amount: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 - amount
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _stationarity(values: list[float]) -> dict[str, Any]:
    if len(values) < 24 or np.std(values) == 0:
        return {"adf_pvalue": None, "kpss_pvalue": None, "interpretation": "insufficient_or_constant"}
    try:
        adf_pvalue = float(adfuller(values, autolag="AIC")[1])
    except Exception:  # noqa: BLE001
        adf_pvalue = None
    try:
        with np.errstate(all="ignore"):
            kpss_pvalue = float(kpss(values, regression="c", nlags="auto")[1])
    except Exception:  # noqa: BLE001
        kpss_pvalue = None
    return {
        "adf_pvalue": adf_pvalue,
        "kpss_pvalue": kpss_pvalue,
        "interpretation": "diagnostic_only; differenced MoM inputs are used regardless of these finite-sample tests",
    }


def _design(
    months: list[str],
    target: Mapping[str, float],
    inputs: Mapping[str, Mapping[str, float]],
    controls: Mapping[str, Mapping[str, float]],
    lags: list[int],
) -> tuple[list[str], np.ndarray, np.ndarray, list[str]]:
    rows: list[list[float]] = []
    ys: list[float] = []
    kept: list[str] = []
    labels = (
        ["target_lag_1"]
        + [f"{source}_lag_{lag}" for source in inputs for lag in lags]
        + [f"{source}_lag_1" for source in controls]
        + [f"calendar_month_{number:02d}" for number in range(2, 13)]
    )
    for month in months:
        values: list[float] = [target.get(_lag(month, 1), float("nan"))]
        for source in inputs.values():
            values.extend(source.get(_lag(month, lag), float("nan")) for lag in lags)
        values.extend(source.get(_lag(month, 1), float("nan")) for source in controls.values())
        values.extend(1.0 if int(month[5:]) == number else 0.0 for number in range(2, 13))
        actual = target.get(month, float("nan"))
        if math.isfinite(actual) and all(math.isfinite(value) for value in values):
            rows.append(values)
            ys.append(actual)
            kept.append(month)
    return kept, np.asarray(rows, dtype=float), np.asarray(ys, dtype=float), labels


def _fit_predict(train_x: np.ndarray, train_y: np.ndarray, next_x: np.ndarray) -> float:
    model = sm.OLS(train_y, sm.add_constant(train_x, has_constant="add")).fit()
    return float(model.predict(sm.add_constant(next_x.reshape(1, -1), has_constant="add"))[0])


def _dm_test(error_baseline: np.ndarray, error_model: np.ndarray) -> dict[str, float | None]:
    differential = error_baseline**2 - error_model**2
    if len(differential) < 12 or np.std(differential) == 0:
        return {"statistic": None, "pvalue": None}
    max_lag = min(6, len(differential) - 1)
    centered = differential - differential.mean()
    variance = float(np.mean(centered * centered))
    for lag in range(1, max_lag + 1):
        covariance = float(np.mean(centered[lag:] * centered[:-lag]))
        variance += 2.0 * (1.0 - lag / (max_lag + 1)) * covariance
    if variance <= 0:
        return {"statistic": None, "pvalue": None}
    statistic = float(differential.mean() / math.sqrt(variance / len(differential)))
    return {"statistic": statistic, "pvalue": float(2 * norm.sf(abs(statistic)))}


def _metrics(actual: np.ndarray, prediction: np.ndarray) -> dict[str, float | int | None]:
    errors = actual - prediction
    direction = (np.sign(actual) == np.sign(prediction))
    return {
        "observations": int(len(actual)),
        "rmse": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
        "mae": float(np.mean(np.abs(errors))) if len(errors) else None,
        "direction_hit_rate": float(np.mean(direction)) if len(direction) else None,
    }


def _expanding_oos(x: np.ndarray, y: np.ndarray, *, baseline_columns: list[int], min_train: int) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    actual: list[float] = []
    baseline_predictions: list[float] = []
    model_predictions: list[float] = []
    for position in range(min_train, len(y)):
        try:
            baseline_predictions.append(_fit_predict(x[:position, baseline_columns], y[:position], x[position, baseline_columns]))
            model_predictions.append(_fit_predict(x[:position], y[:position], x[position]))
            actual.append(float(y[position]))
        except np.linalg.LinAlgError:
            continue
    actual_array = np.asarray(actual)
    baseline_array = np.asarray(baseline_predictions)
    model_array = np.asarray(model_predictions)
    baseline_metrics = _metrics(actual_array, baseline_array)
    model_metrics = _metrics(actual_array, model_array)
    baseline_errors = actual_array - baseline_array
    model_errors = actual_array - model_array
    return {
        "baseline": baseline_metrics,
        "extended": model_metrics,
        "rmse_improvement_pct": (
            float((baseline_metrics["rmse"] - model_metrics["rmse"]) / baseline_metrics["rmse"] * 100)
            if baseline_metrics["rmse"] and model_metrics["rmse"] is not None else None
        ),
        "mae_improvement_pct": (
            float((baseline_metrics["mae"] - model_metrics["mae"]) / baseline_metrics["mae"] * 100)
            if baseline_metrics["mae"] and model_metrics["mae"] is not None else None
        ),
        "diebold_mariano": _dm_test(baseline_errors, model_errors),
    }, baseline_errors, model_errors


def _single_lag_oos(
    x: np.ndarray,
    y: np.ndarray,
    *,
    lag_grid: list[int],
    input_count: int,
    baseline_columns: list[int],
    minimum_train_months: int,
) -> list[dict[str, Any]]:
    """Evaluate one *pre-specified common lag* for each external input.

    The table makes the apparent best lag auditable. It is explicitly
    exploratory because selecting it after looking at OOS metrics is not an
    activation test.
    """
    rows: list[dict[str, Any]] = []
    external_width = len(lag_grid)
    base = x[:, baseline_columns]
    for lag_position, lag in enumerate(lag_grid):
        selected = [1 + source * external_width + lag_position for source in range(input_count)]
        candidate = np.column_stack([base, x[:, selected]])
        oos, _, _ = _expanding_oos(
            candidate,
            y,
            baseline_columns=list(range(base.shape[1])),
            min_train=minimum_train_months,
        )
        rows.append({"lag_months": lag, **oos})
    return rows


def _conditional_predictive_wald(full: Any, *, external_column_count: int) -> dict[str, Any]:
    """Joint HAC Wald test for every pre-specified external lag.

    This is the regression analogue of a conditional Granger-style test: the
    external lag block is jointly zero conditional on target AR, controls and
    calendar effects.  It is deliberately not labelled a causal test.
    """
    if external_column_count <= 0:
        return {"pvalue": None, "interpretation": "no_external_columns"}
    restriction = np.zeros((external_column_count, len(full.params)))
    for position in range(external_column_count):
        restriction[position, 1 + position] = 1.0  # index 0 is the intercept
    try:
        result = full.wald_test(restriction, scalar=True)
        return {
            "statistic": float(result.statistic),
            "pvalue": float(result.pvalue),
            "degrees_of_freedom": int(external_column_count),
            "method": "joint HAC Wald test of external distributed-lag block conditional on AR(1), common-factor control and calendar-month fixed effects",
            "interpretation": "conditional predictive content only; not causality or a forecast signal",
        }
    except Exception as exc:  # noqa: BLE001
        return {"pvalue": None, "interpretation": f"test_unavailable:{type(exc).__name__}"}


def _benjamini_hochberg(rows: list[dict[str, Any]]) -> None:
    valid = [(index, row["conditional_predictive_test"].get("pvalue")) for index, row in enumerate(rows)]
    valid = [(index, pvalue) for index, pvalue in valid if pvalue is not None]
    for row in rows:
        row["conditional_predictive_test"]["fdr_qvalue"] = None
    if not valid:
        return
    ordered = sorted(valid, key=lambda row: row[1])
    adjusted: list[tuple[int, float]] = []
    total = len(ordered)
    previous = 1.0
    for rank, (index, pvalue) in reversed(list(enumerate(ordered, start=1))):
        value = min(previous, pvalue * total / rank)
        adjusted.append((index, value))
        previous = value
    for index, qvalue in adjusted:
        rows[index]["conditional_predictive_test"]["fdr_qvalue"] = float(qvalue)


def run_relationship(
    spec: Mapping[str, Any],
    *,
    series: Mapping[str, Mapping[str, float]],
    minimum_train_months: int,
) -> dict[str, Any]:
    target = series[spec["target"]]
    inputs = {name: series[name] for name in spec["external_inputs"]}
    controls = {name: series[name] for name in spec.get("controls", [])}
    universe = sorted(target)
    months, x, y, labels = _design(universe, target, inputs, controls, list(spec["lag_grid_months"]))
    if len(y) <= minimum_train_months + 12:
        raise ExternalBacktestError(f"{spec['id']} has insufficient aligned monthly coverage")
    baseline_columns = [0] + list(range(1 + len(inputs) * len(spec["lag_grid_months"]), x.shape[1]))
    oos, _, _ = _expanding_oos(x, y, baseline_columns=baseline_columns, min_train=minimum_train_months)
    single_lag_oos = _single_lag_oos(
        x,
        y,
        lag_grid=list(spec["lag_grid_months"]),
        input_count=len(inputs),
        baseline_columns=baseline_columns,
        minimum_train_months=minimum_train_months,
    )
    full = sm.OLS(y, sm.add_constant(x, has_constant="add")).fit(cov_type="HAC", cov_kwds={"maxlags": min(12, len(y) // 4)})
    coefficient_rows = []
    for label, coefficient, pvalue in zip(labels, full.params[1:], full.pvalues[1:]):
        coefficient_rows.append({"term": label, "coefficient": float(coefficient), "hac_pvalue": float(pvalue)})
    external_column_count = len(inputs) * len(spec["lag_grid_months"])
    conditional_test = _conditional_predictive_wald(full, external_column_count=external_column_count)
    lag_coefficients = [row for row in coefficient_rows if row["term"].startswith(f"{spec['external_inputs'][0]}_lag_")]
    best_lag = min(lag_coefficients, key=lambda row: row["hac_pvalue"]) if lag_coefficients else None
    best_oos_lag = min(
        single_lag_oos,
        key=lambda row: row["extended"]["rmse"] if row["extended"]["rmse"] is not None else float("inf"),
    )
    return {
        "id": spec["id"],
        "relationship_map_id": spec["relationship_map_id"],
        "activation": {
            "status": "not_activated",
            "reasons": [
                "This first pass uses current-revised histories, not an archival release-vintage panel.",
                "Conditional predictive tests and OOS comparisons do not establish causality.",
                "Specified demand/capacity/hedging and supply-chain confounders are not fully observed in this first pass."
            ],
        },
        "coverage": {"first_month": months[0], "last_month": months[-1], "aligned_months": len(months), "oos_months": oos["extended"]["observations"]},
        "specification": {
            "target": spec["target"],
            "external_inputs": list(inputs),
            "controls": [f"{name}_lag_1" for name in controls],
            "lag_grid_months": spec["lag_grid_months"],
            "baseline": "target AR(1), lagged common-factor controls and calendar-month fixed effects",
            "extended": "baseline plus all pre-specified external distributed lags",
            "availability_rule": spec["availability_rule"],
        },
        "stationarity": {"target": _stationarity(list(y)), **{name: _stationarity([values[month] for month in months if month in values]) for name, values in inputs.items()}},
        "conditional_predictive_test": conditional_test,
        "lowest_hac_pvalue_lag_exploratory": best_lag,
        "best_lag_out_of_sample_exploratory": best_oos_lag,
        "out_of_sample": oos,
        "limitations": [
            "Model selection across lag candidates can overstate a single best lag; the reported best individual coefficient is exploratory.",
            "CPI is SA, but the two configured industry PPI indexes are NSA; the first pass keeps those inputs as published and absorbs recurring calendar seasonality with month fixed effects. It is not a substitute for an official PPI seasonal adjustment.",
            "COVID-era structural changes, airline hedging, seat capacity, agricultural commodity inputs, retail margins, and revision vintages can change the apparent relationship."
        ],
    }


def build_snapshot(
    config: Mapping[str, Any],
    *,
    bls_api_key: str,
    eia_api_key: str,
    fred_api_key: str,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Collect current official histories and return an external-only report."""
    start_year = int(config["sample"]["start"][:4])
    end_year = datetime.now(timezone.utc).year
    source_spec = config["sources"]
    bls_ids = list(source_spec["bls"]["series"].values())
    bls_response = fetch_series(bls_ids, registration_key=bls_api_key, start_year=start_year, end_year=end_year)
    series: dict[str, dict[str, float]] = {}
    for name, series_id in source_spec["bls"]["series"].items():
        series[name] = mom_pct(bls_monthly_series(bls_response, series_id))
    for name, series_id in source_spec["eia"]["series"].items():
        try:
            series[name] = mom_pct(fetch_eia_monthly_series(series_id, api_key=eia_api_key))
        except ExternalBacktestError as exc:
            # Series IDs are public metadata. Credentials and request URLs are
            # deliberately absent from this diagnostic.
            raise ExternalBacktestError(f"EIA source unavailable for {series_id}: {exc}") from exc
    for name, series_id in source_spec["fred"]["series"].items():
        series[name] = mom_pct(fetch_fred_monthly_series(series_id, api_key=fred_api_key, start=config["sample"]["start"]))
    rows = [run_relationship(spec, series=series, minimum_train_months=config["sample"]["minimum_train_months"]) for spec in config["relationships"]]
    _benjamini_hochberg(rows)
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": config["schema_version"],
        "model": "us_cpi_external_pathway_backtest",
        "retrieved_at": retrieved_at,
        "data_status": "official_observed_current_vintage",
        "scope": "External-input backtest; separate from BLS Table 6/7 contribution accounting and not read by UI.",
        "sample": config["sample"],
        "sources": {
            "bls": {"publisher": "U.S. Bureau of Labor Statistics", "series": source_spec["bls"]["series"]},
            "eia": {"publisher": "U.S. Energy Information Administration", "series": source_spec["eia"]["series"]},
            "fred": {
                "publisher": "Federal Reserve Bank of St. Louis",
                "series": source_spec["fred"]["series"],
                "provenance_note": "PCU311311 and PCU484484 are BLS PPI industry series retrieved through FRED because the BLS Public Data API rejected those configured identifiers on the first live run.",
            },
        },
        "relationships": rows,
        "activation_policy": config["activation_policy"],
        "limitations": [
            "No source credential, raw request URL, or credential-bearing payload is persisted in this snapshot.",
            "Current-vintage source histories do not recreate the exact information set available on each historical release date.",
            "Results are research diagnostics only and must not change the CPI relationship catalog's candidate status."
        ],
    }
