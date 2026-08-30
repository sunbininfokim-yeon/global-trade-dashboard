"""BLS-only, independent tests for the candidate CPI vehicle chain.

All four CPI components are published in the same release. Consequently, this
module never treats a contemporaneous (lag 0) component as an advance signal.
It reports conditional predictive diagnostics only, not a causal chain.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import statsmodels.api as sm
from scipy.stats import norm

from .api import fetch_series


class VehicleBacktestError(RuntimeError):
    """Raised when a requested vehicle path cannot be evaluated."""


def bls_monthly_mom(response: Mapping[str, Any], series_id: str) -> dict[str, float]:
    """Convert the published BLS SA index level into an SA MoM change."""
    values: dict[str, float] = {}
    for row in response[series_id].get("data", []):
        period = str(row.get("period", ""))
        if not (period.startswith("M") and period[1:].isdigit() and 1 <= int(period[1:]) <= 12):
            continue
        try:
            values[f"{row['year']}-{int(period[1:]):02d}"] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
    output: dict[str, float] = {}
    previous_month: str | None = None
    for month in sorted(values):
        if previous_month is not None and values[previous_month] and values[month] > 0:
            output[month] = round((values[month] / values[previous_month] - 1) * 100.0, 10)
        previous_month = month
    return output


def _lag(month: str, amount: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    serial = year * 12 + number - 1 - amount
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def _design(
    target: Mapping[str, float],
    source: Mapping[str, float],
    controls: Mapping[str, Mapping[str, float]],
    lag_grid: list[int],
) -> tuple[list[str], np.ndarray, np.ndarray, list[str]]:
    labels = ["target_lag_1"] + [f"source_lag_{lag}" for lag in lag_grid] + [f"{name}_lag_1" for name in controls]
    months: list[str] = []
    x_rows: list[list[float]] = []
    y_rows: list[float] = []
    for month in sorted(target):
        values = [target.get(_lag(month, 1), float("nan"))]
        values.extend(source.get(_lag(month, lag), float("nan")) for lag in lag_grid)
        values.extend(values_by_month.get(_lag(month, 1), float("nan")) for values_by_month in controls.values())
        outcome = target[month]
        if math.isfinite(outcome) and all(math.isfinite(value) for value in values):
            months.append(month)
            x_rows.append(values)
            y_rows.append(outcome)
    return months, np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float), labels


def _fit_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> float:
    fit = sm.OLS(train_y, sm.add_constant(train_x, has_constant="add")).fit()
    return float(fit.predict(sm.add_constant(test_x.reshape(1, -1), has_constant="add"))[0])


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int | None]:
    errors = actual - predicted
    return {
        "observations": int(len(actual)),
        "rmse": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
        "mae": float(np.mean(np.abs(errors))) if len(errors) else None,
        "direction_hit_rate": float(np.mean(np.sign(actual) == np.sign(predicted))) if len(errors) else None,
    }


def _dm_test(baseline_errors: np.ndarray, extended_errors: np.ndarray) -> dict[str, float | None]:
    differential = baseline_errors**2 - extended_errors**2
    if len(differential) < 12 or np.std(differential) == 0:
        return {"statistic": None, "pvalue": None}
    centered = differential - differential.mean()
    max_lag = min(6, len(centered) - 1)
    long_run_variance = float(np.mean(centered * centered))
    for lag in range(1, max_lag + 1):
        covariance = float(np.mean(centered[lag:] * centered[:-lag]))
        long_run_variance += 2.0 * (1.0 - lag / (max_lag + 1)) * covariance
    if long_run_variance <= 0:
        return {"statistic": None, "pvalue": None}
    statistic = float(differential.mean() / math.sqrt(long_run_variance / len(differential)))
    return {"statistic": statistic, "pvalue": float(2 * norm.sf(abs(statistic)))}


def _expanding_oos(
    x: np.ndarray,
    y: np.ndarray,
    *,
    baseline_columns: list[int],
    minimum_train_months: int,
) -> dict[str, Any]:
    actual: list[float] = []
    baseline_predictions: list[float] = []
    extended_predictions: list[float] = []
    for position in range(minimum_train_months, len(y)):
        try:
            baseline_predictions.append(_fit_predict(x[:position, baseline_columns], y[:position], x[position, baseline_columns]))
            extended_predictions.append(_fit_predict(x[:position], y[:position], x[position]))
            actual.append(float(y[position]))
        except np.linalg.LinAlgError:
            continue
    actual_array = np.asarray(actual)
    baseline_array = np.asarray(baseline_predictions)
    extended_array = np.asarray(extended_predictions)
    baseline = _metrics(actual_array, baseline_array)
    extended = _metrics(actual_array, extended_array)
    return {
        "baseline": baseline,
        "extended": extended,
        "rmse_improvement_pct": (
            float((baseline["rmse"] - extended["rmse"]) / baseline["rmse"] * 100)
            if baseline["rmse"] and extended["rmse"] is not None else None
        ),
        "mae_improvement_pct": (
            float((baseline["mae"] - extended["mae"]) / baseline["mae"] * 100)
            if baseline["mae"] and extended["mae"] is not None else None
        ),
        "diebold_mariano": _dm_test(actual_array - baseline_array, actual_array - extended_array),
    }


def _single_lag_oos(
    x: np.ndarray,
    y: np.ndarray,
    *,
    lag_grid: list[int],
    baseline_columns: list[int],
    minimum_train_months: int,
) -> list[dict[str, Any]]:
    base = x[:, baseline_columns]
    rows = []
    for offset, lag in enumerate(lag_grid):
        candidate = np.column_stack([base, x[:, 1 + offset]])
        rows.append({
            "lag_months": lag,
            **_expanding_oos(
                candidate,
                y,
                baseline_columns=list(range(base.shape[1])),
                minimum_train_months=minimum_train_months,
            ),
        })
    return rows


def _joint_hac_wald(fit: Any, *, source_lag_count: int) -> dict[str, Any]:
    restriction = np.zeros((source_lag_count, len(fit.params)))
    for position in range(source_lag_count):
        restriction[position, 1 + position] = 1.0
    try:
        result = fit.wald_test(restriction, scalar=True)
        return {
            "statistic": float(result.statistic),
            "pvalue": float(result.pvalue),
            "degrees_of_freedom": source_lag_count,
            "interpretation": "joint HAC conditional predictive test, not causality",
        }
    except Exception as exc:  # noqa: BLE001
        return {"pvalue": None, "interpretation": f"test_unavailable:{type(exc).__name__}"}


def _fdr(rows: list[dict[str, Any]]) -> None:
    valid = [(index, row["conditional_predictive_test"].get("pvalue")) for index, row in enumerate(rows)]
    valid = [(index, value) for index, value in valid if value is not None]
    for row in rows:
        row["conditional_predictive_test"]["fdr_qvalue"] = None
    previous = 1.0
    for rank, (index, value) in reversed(list(enumerate(sorted(valid, key=lambda item: item[1]), start=1))):
        adjusted = min(previous, value * len(valid) / rank)
        rows[index]["conditional_predictive_test"]["fdr_qvalue"] = float(adjusted)
        previous = adjusted


def run_relationship(spec: Mapping[str, Any], *, series: Mapping[str, Mapping[str, float]], minimum_train_months: int) -> dict[str, Any]:
    target = series[spec["target"]]
    source = series[spec["source"]]
    controls = {name: series[name] for name in spec["controls"]}
    months, x, y, labels = _design(target, source, controls, list(spec["lag_grid_months"]))
    if len(y) <= minimum_train_months + 12:
        raise VehicleBacktestError(f"insufficient aligned coverage for {spec['id']}")
    baseline_columns = [0] + list(range(1 + len(spec["lag_grid_months"]), x.shape[1]))
    oos = _expanding_oos(x, y, baseline_columns=baseline_columns, minimum_train_months=minimum_train_months)
    single_lag = _single_lag_oos(x, y, lag_grid=list(spec["lag_grid_months"]), baseline_columns=baseline_columns, minimum_train_months=minimum_train_months)
    full = sm.OLS(y, sm.add_constant(x, has_constant="add")).fit(cov_type="HAC", cov_kwds={"maxlags": min(12, len(y) // 4)})
    best_lag = min(single_lag, key=lambda row: row["extended"]["rmse"] if row["extended"]["rmse"] is not None else float("inf"))
    return {
        "id": spec["id"],
        "relationship_map_id": spec.get("relationship_map_id"),
        "classification": spec["classification"],
        "coverage": {"first_month": months[0], "last_month": months[-1], "aligned_months": len(months), "oos_months": oos["extended"]["observations"]},
        "specification": {
            "source": spec["source"], "target": spec["target"], "controls": [f"{name}_lag_1" for name in controls],
            "lag_grid_months": spec["lag_grid_months"], "availability_rule": spec["availability_rule"],
            "baseline": "target AR(1) plus lagged controls", "extended": "baseline plus all pre-specified source lags"
        },
        "best_lag_out_of_sample_exploratory": best_lag,
        "out_of_sample": oos,
        "conditional_predictive_test": _joint_hac_wald(full, source_lag_count=len(spec["lag_grid_months"])),
        "activation": {
            "status": "not_activated",
            "reasons": [
                "Current BLS revised histories are not a release-vintage reconstruction.",
                "The test measures conditional predictive content, not a causal chain.",
                "Vehicle supply, financing, fleet age, claims, regulation, medical costs and reinsurance are not fully controlled."
            ]
        }
    }


def build_snapshot(config: Mapping[str, Any], *, bls_api_key: str, retrieved_at: str | None = None) -> dict[str, Any]:
    start_year = int(config["sample"]["start_year"])
    raw = fetch_series(
        list(config["source"]["series"].values()),
        registration_key=bls_api_key,
        start_year=start_year,
        end_year=datetime.now(timezone.utc).year,
    )
    series = {name: bls_monthly_mom(raw, series_id) for name, series_id in config["source"]["series"].items()}
    rows = [run_relationship(spec, series=series, minimum_train_months=config["sample"]["minimum_train_months"]) for spec in config["relationships"]]
    _fdr(rows)
    return {
        "schema_version": config["schema_version"],
        "model": "us_cpi_vehicle_chain_backtest",
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "data_status": "official_observed_current_vintage",
        "scope": "Minimal result report only. Raw BLS histories are not stored. This is separate from the CPI contribution and UI data flow.",
        "sample": config["sample"],
        "source": config["source"],
        "relationships": rows,
        "activation_policy": config["activation_policy"],
    }
