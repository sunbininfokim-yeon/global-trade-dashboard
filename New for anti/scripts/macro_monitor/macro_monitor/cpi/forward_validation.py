"""Fixed-cutoff, latest-vintage replay for existing US CPI candidate paths."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

import numpy as np


def shift(month: str, offset: int) -> str:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise ValueError(f"invalid reference month: {month}")
    serial = int(month[:4]) * 12 + int(month[5:]) - 1 + offset
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def monthly_changes(points: Iterable[tuple[str, float | None]]) -> dict[str, float]:
    levels: dict[str, float] = {}
    for month, value in points:
        shift(month, 0)
        if value is not None and math.isfinite(value) and value > 0:
            levels[month] = value
    return {
        month: (levels[month] / levels[prev] - 1) * 100
        for month in sorted(levels)
        if (prev := shift(month, -1)) in levels
    }


def candidate_specs(vehicle: Mapping, external: Mapping, structure: Mapping) -> list[dict[str, Any]]:
    types = {row["id"]: row["type"] for row in structure["relationships"]}
    specs: list[dict[str, Any]] = []
    for config in (vehicle, external):
        for row in config["relationships"]:
            map_id = row["relationship_map_id"]
            if map_id is not None and (map_id not in types or types[map_id] == "measurement_link"):
                raise ValueError(f"not a predictive candidate: {map_id}")
            sources = row["external_inputs"] if "external_inputs" in row else [row["source"]]
            # Same-release CPI and reference-month PPI cannot be assumed available
            # ahead of target CPI. Same-reference-month EIA is a nowcast only.
            allowed_nowcast = set(external["sources"]["eia"]["series"])
            terms = [
                (name, lag) for name in sources for lag in row["lag_grid_months"]
                if lag > 0 or (lag == 0 and name in allowed_nowcast)
            ]
            if any(not any(key == name for key, _ in terms) for name in sources):
                raise ValueError(f"no eligible lags: {row['id']}")
            specs.append({
                "id": row["id"], "relationship_map_id": map_id, "target": row["target"],
                "controls": [(name, 1) for name in row["controls"]], "terms": terms,
                "calendar_effects": "external_inputs" in row,
                "minimum_train": config["sample"]["minimum_train_months"],
                "mode": "includes_lag_zero_nowcast" if any(lag == 0 for _, lag in terms) else "lagged_inputs_only",
            })
    return specs


def metrics(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    result: dict[str, Any] = {"n": n, "baseline_rmse_pp": None, "extended_rmse_pp": None,
                              "baseline_mae_pp": None, "extended_mae_pp": None, "rmse_improvement_pct": None}
    if n:
        for model in ("baseline", "extended"):
            errors = np.array([row[model] - row["actual"] for row in rows])
            result[f"{model}_rmse_pp"] = float(np.sqrt(np.mean(errors ** 2)))
            result[f"{model}_mae_pp"] = float(np.mean(np.abs(errors)))
        if n >= 3 and result["baseline_rmse_pp"] > 0:
            result["rmse_improvement_pct"] = 100 * (1 - result["extended_rmse_pp"] / result["baseline_rmse_pp"])
    return result


def _fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    coef, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        raise ValueError("rank_deficient_design")
    return coef


def evaluate(spec: Mapping[str, Any], series: Mapping[str, Mapping[str, float]], *,
             cutoff: str, through: str) -> dict[str, Any]:
    if shift(through, 0) <= shift(cutoff, 0):
        raise ValueError("through must be later than cutoff")
    target = spec["target"]
    base_terms = [(target, 1), *spec["controls"]]
    terms = base_terms + spec["terms"]
    keys = sorted({name for name, _ in terms})
    coverage = {}
    for name in keys:
        months = [m for m, value in series.get(name, {}).items() if m <= through and math.isfinite(value)]
        coverage[name] = {"first": min(months, default=None), "last": max(months, default=None), "months": len(months)}
    out: dict[str, Any] = {
        "id": spec["id"], "relationship_map_id": spec["relationship_map_id"],
        "target": target, "mode": spec["mode"], "baseline_terms": base_terms,
        "added_terms": spec["terms"], "calendar_effects": spec["calendar_effects"],
        "activation": "disabled",
        "coverage": coverage,
    }
    missing = [name for name in keys if not out["coverage"][name]["months"]]
    if missing:
        return {**out, "status": "source_unavailable", "unavailable_series": missing}

    def regressors(month: str) -> tuple[list[float], list[float]] | None:
        values = [series[name].get(shift(month, -lag), math.nan) for name, lag in terms]
        if not all(math.isfinite(value) for value in values):
            return None
        base = [1.0, *values[:len(base_terms)]]
        if spec["calendar_effects"]:
            base.extend(float(int(month[5:]) == i) for i in range(2, 13))
        return base, base + values[len(base_terms):]

    train = [(m, row, value) for m, value in sorted(series[target].items())
             if m <= cutoff and math.isfinite(value) and (row := regressors(m)) is not None]
    out["training"] = {"first": train[0][0] if train else None, "last": train[-1][0] if train else None,
                       "n": len(train)}
    if len(train) < spec["minimum_train"]:
        return {**out, "status": "insufficient_training"}
    try:
        y = np.array([value for _, _, value in train])
        base_coef = _fit(np.array([row[0] for _, row, _ in train]), y)
        ext_coef = _fit(np.array([row[1] for _, row, _ in train]), y)
    except ValueError as exc:
        return {**out, "status": str(exc)}

    scores = []
    unscored = {}
    month = shift(cutoff, 1)
    while month <= through:
        actual = series[target].get(month)
        design = regressors(month)
        if actual is None or not math.isfinite(actual):
            unscored[month] = "missing_target_mom"
        elif design is None:
            unscored[month] = {"missing_inputs": [
                {"series": name, "month": ref, "lag": lag}
                for name, lag in terms if not math.isfinite(series[name].get(ref := shift(month, -lag), math.nan))
            ]}
        else:
            base, ext = design
            scores.append({"month": month, "actual": actual, "baseline": float(base_coef @ base),
                           "extended": float(ext_coef @ ext)})
        month = shift(month, 1)
    return {**out, "status": "scored" if scores else "no_aligned_holdout",
            "holdout": metrics(scores), "monthly_replay": scores, "unscored_months": unscored}
