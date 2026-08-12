"""Causal validation of Ethiopia coffee climate plus structural-cycle model."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .regions import BELT_KEY, FEATURE_SETS, FULL_FEATURE_SETS

HERE = Path(__file__).resolve().parent
ALPHAS = np.logspace(-2, 4, 40)
MIN_TRAIN = 12
DEVELOPMENT_END = 2014
HOLDOUT_START = 2015
ROLLING_WINDOW = 20


def _trend(years, yields):
    return np.poly1d(np.polyfit(years, np.log(yields), 1))


def _prepare(frame, features, years, trend):
    matrix = frame[features].astype(float).copy()
    if "yield_lag2_kg_ha" in features:
        matrix["yield_lag2_kg_ha"] = np.log(matrix["yield_lag2_kg_ha"].clip(lower=1)) - trend(years - 2)
    return matrix.to_numpy(float)


def _ridge(matrix, target):
    mean = matrix.mean(axis=0); scale = np.where(matrix.std(axis=0) > 0, matrix.std(axis=0), 1)
    x = (matrix - mean) / scale
    design = np.column_stack([np.ones(len(x)), x]); gram, rhs = design.T @ design, design.T @ target
    penalty = np.eye(design.shape[1]); penalty[0, 0] = 0
    best = None
    for alpha in ALPHAS:
        inverse = np.linalg.pinv(gram + alpha * penalty); beta = inverse @ rhs
        fitted = design @ beta; leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
        loo = np.mean(((target - fitted) / np.clip(1 - leverage, 1e-8, None)) ** 2)
        if best is None or loo < best[0]: best = (float(loo), float(alpha), beta)
    return mean, scale, best[1], float(best[2][0]), np.asarray(best[2][1:])


def _score(frame):
    truth, pred, base = (frame[name].to_numpy(float) for name in ("truth", "prediction", "baseline"))
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2))); brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dev_true, dev_pred = truth - base, pred - base; denom = float(np.sum((dev_true - dev_true.mean()) ** 2))
    return {"n_folds": int(len(frame)), "rmse_kg_ha": rmse, "baseline_rmse_kg_ha": brmse, "skill_vs_trend": 1 - rmse / brmse, "detrended_r2": 1 - float(np.sum((dev_true - dev_pred) ** 2)) / denom if denom else float("nan")}


def _forward(frame, features, window=None):
    years = frame.year.to_numpy(float); yields = frame.yield_kg_ha.to_numpy(float); rows = []
    for i, year in enumerate(years):
        indices = np.where(years < year)[0]
        if len(indices) < MIN_TRAIN: continue
        if window is not None: indices = indices[-window:]
        trend = _trend(years[indices], yields[indices]); matrix = _prepare(frame, features, years, trend)
        mean, scale, _, intercept, coef = _ridge(matrix[indices], np.log(yields[indices]) - trend(years[indices]))
        weather = intercept + ((matrix[i] - mean) / scale) @ coef
        rows.append({"year": int(year), "truth": float(yields[i]), "baseline": float(np.exp(trend(year))), "prediction": float(np.exp(trend(year) + weather))})
    return pd.DataFrame(rows)


def _ensemble(frame, features):
    full, rolling = _forward(frame, features), _forward(frame, features, ROLLING_WINDOW)
    out = full.merge(rolling, on=["year", "truth"], suffixes=("_full", "_rolling"))
    out["baseline"] = (out.baseline_full + out.baseline_rolling) / 2; out["prediction"] = (out.prediction_full + out.prediction_rolling) / 2
    return out[["year", "truth", "baseline", "prediction"]]


def _fit_component(frame, features, name, window=None):
    if window is not None: frame = frame.tail(window)
    years = frame.year.to_numpy(float); yields = frame.yield_kg_ha.to_numpy(float); trend = _trend(years, yields)
    matrix = _prepare(frame, features, years, trend); mean, scale, alpha, intercept, coef = _ridge(matrix, np.log(yields) - trend(years))
    return {"name": name, "train_window_years": window, "trained_years": [int(years.min()), int(years.max())], "trend": {"log_poly_coef": trend.coefficients.tolist()}, "scaler": {"mean": mean.tolist(), "scale": scale.tolist()}, "ridge": {"alpha": alpha, "intercept": intercept, "coef": coef.tolist()}}


def _split(pred):
    return {"development_2007_2014": _score(pred[pred.year <= DEVELOPMENT_END]), "holdout_2015_2024": _score(pred[pred.year >= HOLDOUT_START]), "all": _score(pred)}


def train():
    raw = pd.read_csv(HERE / "training" / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = raw[raw.target_status == "final"].dropna(subset=["yield_kg_ha"] + all_features).sort_values("year").reset_index(drop=True)
    runs, preds = {}, {}
    for name, features in FEATURE_SETS.items():
        preds[name] = _ensemble(frame, features); runs[name] = _split(preds[name])
    selected = min(FULL_FEATURE_SETS, key=lambda name: runs[name]["development_2007_2014"]["rmse_kg_ha"])
    selected_pred = preds[selected]; cycle_pred = preds["cycle_only"]
    selected_scores, cycle_scores = runs[selected], runs["cycle_only"]
    holdout, dev = selected_scores["holdout_2015_2024"], selected_scores["development_2007_2014"]
    cycle_holdout = cycle_scores["holdout_2015_2024"]
    weather_incremental = 1 - holdout["rmse_kg_ha"] / cycle_holdout["rmse_kg_ha"]
    accepted = bool(dev["skill_vs_trend"] >= 0.10 and holdout["skill_vs_trend"] >= 0.10 and weather_incremental >= 0.02)
    operational = selected_pred if accepted else cycle_pred
    operational_holdout = operational[operational.year >= HOLDOUT_START]
    operational_errors = np.abs(operational_holdout.truth - (operational_holdout.prediction if accepted else operational_holdout.baseline)).to_numpy()
    artifact = {
        "key": BELT_KEY, "crop": "coffee", "target": {"variable": "FAOSTAT_green_coffee_yield_kg_ha", "source": "FAOSTAT QCL via OWID", "spatial_scale": "Ethiopia national yield; ECTA regional climate proxy"},
        "trained_years": [int(frame.year.min()), int(frame.year.max())], "n_seasons": int(len(frame)),
        "selection_protocol": {"feature_selection": "forward folds ending 2014", "untouched_holdout": "2015-2024", "baseline": "refitted log trend", "incremental_gate": "weather+cycle must improve holdout RMSE >=2% versus cycle-only"},
        "feature_sets": FEATURE_SETS, "validation_runs": runs, "selected_full_model": selected, "selected_features": FEATURE_SETS[selected],
        "selected_validation": selected_scores, "cycle_only_validation": cycle_scores, "weather_incremental_skill_vs_cycle_holdout": weather_incremental,
        "accepted_weather_forecast": accepted, "operational_choice": "weather_plus_cycle" if accepted else "no_forecast_reference",
        "low_confidence": not accepted or holdout["skill_vs_trend"] < 0.20,
        "components": [_fit_component(frame, FEATURE_SETS[selected], "full_history"), _fit_component(frame, FEATURE_SETS[selected], "rolling_20", ROLLING_WINDOW)],
        "uncertainty": {"basis": "absolute 2015-2024 errors; trend fallback if weather model rejected", "q68_kg_ha": float(np.quantile(operational_errors, .68, method="higher")), "q95_kg_ha": float(np.quantile(operational_errors, .95, method="higher"))},
        "structural_context_not_fitted": {"source": "USDA/FAS ET2026-0005 citing ECTA", "old_tree_share_approx": 0.70, "stumped_area_share_2025_26": 0.15, "regional_stumping_rates": {"Oromia": 0.19, "South Ethiopia": 0.14, "Sidama": 0.13}, "reason_not_fitted": "one recent snapshot, no causal annual regional history"},
        "warnings": ["FAOSTAT calendar-year yield and Ethiopia's Oct-Sep marketing year are not perfectly aligned.", "Lag-2 yield and area growth are proxies for bearing cycle and structural change, not observed tree age.", "Stumping rates are scenario context only and never multiplied into the forecast.", "Regional climate weights are recent three-year average production shares, not annual historical weights."],
    }
    (HERE / "models").mkdir(parents=True, exist_ok=True)
    (HERE / "models" / f"{BELT_KEY}.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[train] selected={selected} holdout_skill={holdout['skill_vs_trend']:+.1%} incremental_vs_cycle={weather_incremental:+.1%} accepted={accepted}")
    return artifact


if __name__ == "__main__": train()
