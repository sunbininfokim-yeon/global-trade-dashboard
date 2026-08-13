"""Leakage-resistant validation for Uganda national green-coffee yield."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .regions import BELT_KEY, FEATURE_SETS

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
MODELS = HERE / "models"
ALPHAS = np.logspace(-2, 4, 40)
MIN_TRAIN = 12
DEVELOPMENT_END = 2014
HOLDOUT_START = 2015
ROLLING_WINDOW = 20
MIN_OPERATIONAL_SKILL = 0.10


def _trend(years, yields):
    return np.poly1d(np.polyfit(years, np.log(yields), 1))


def _scale(matrix):
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=0)
    return mean, np.where(scale > 0, scale, 1.0)


def _ridge(matrix, target):
    design = np.column_stack([np.ones(len(matrix)), matrix])
    gram, rhs = design.T @ design, design.T @ target
    penalty = np.eye(design.shape[1]); penalty[0, 0] = 0
    best = None
    for alpha in ALPHAS:
        inverse = np.linalg.pinv(gram + alpha * penalty)
        beta = inverse @ rhs
        fitted = design @ beta
        leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
        loo = np.mean(((target - fitted) / np.clip(1 - leverage, 1e-8, None)) ** 2)
        if best is None or loo < best[0]:
            best = (float(loo), float(alpha), beta)
    return best[1], float(best[2][0]), np.asarray(best[2][1:])


def _score(frame):
    truth, prediction, baseline = (frame[name].to_numpy(float) for name in ("truth", "prediction", "baseline"))
    rmse = float(np.sqrt(np.mean((truth - prediction) ** 2)))
    base_rmse = float(np.sqrt(np.mean((truth - baseline) ** 2)))
    dev_true, dev_pred = truth - baseline, prediction - baseline
    denom = float(np.sum((dev_true - dev_true.mean()) ** 2))
    return {
        "n_folds": int(len(frame)),
        "rmse_kg_ha": rmse,
        "baseline_rmse_kg_ha": base_rmse,
        "skill_vs_trend": 1 - rmse / base_rmse,
        "detrended_r2": 1 - float(np.sum((dev_true - dev_pred) ** 2)) / denom if denom else float("nan"),
    }


def _split_scores(predictions):
    return {
        "all": _score(predictions),
        "development_2004_2014": _score(predictions[predictions.year <= DEVELOPMENT_END]),
        "holdout_2015_2024": _score(predictions[predictions.year >= HOLDOUT_START]),
    }


def _forward(frame, features, window=None):
    years = frame.year.to_numpy(float); yields = frame.yield_kg_ha.to_numpy(float)
    matrix = frame[features].to_numpy(float); rows = []
    for i, year in enumerate(years):
        indices = np.where(years < year)[0]
        if len(indices) < MIN_TRAIN:
            continue
        if window is not None:
            indices = indices[-window:]
        trend = _trend(years[indices], yields[indices])
        mean, scale = _scale(matrix[indices])
        _, intercept, coef = _ridge((matrix[indices] - mean) / scale, np.log(yields[indices]) - trend(years[indices]))
        weather = intercept + ((matrix[i] - mean) / scale) @ coef
        rows.append({"year": int(year), "truth": float(yields[i]), "baseline": float(np.exp(trend(year))), "prediction": float(np.exp(trend(year) + weather))})
    return pd.DataFrame(rows)


def _fit_component(frame, features, name, window=None):
    if window is not None:
        frame = frame.tail(window)
    years = frame.year.to_numpy(float); yields = frame.yield_kg_ha.to_numpy(float)
    matrix = frame[features].to_numpy(float); trend = _trend(years, yields)
    mean, scale = _scale(matrix)
    alpha, intercept, coef = _ridge((matrix - mean) / scale, np.log(yields) - trend(years))
    return {"name": name, "train_window_years": window, "trained_years": [int(years.min()), int(years.max())], "n_seasons": int(len(frame)), "trend": {"form": "log_linear", "log_poly_coef": trend.coefficients.tolist()}, "scaler": {"mean": mean.tolist(), "scale": scale.tolist()}, "ridge": {"alpha": alpha, "intercept": intercept, "coef": coef.tolist()}}


def train():
    raw = pd.read_csv(TRAINING / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = raw[raw.target_status == "final"].dropna(subset=["yield_kg_ha"] + all_features).sort_values("year")
    runs, predictions = {}, {}
    for name, features in FEATURE_SETS.items():
        predictions[name] = _forward(frame, features)
        runs[name] = _split_scores(predictions[name])
    selected = min(runs, key=lambda name: runs[name]["development_2004_2014"]["rmse_kg_ha"])
    features = FEATURE_SETS[selected]
    full = predictions[selected]; rolling = _forward(frame, features, window=ROLLING_WINDOW)
    ensemble = full.merge(rolling, on=["year", "truth"], suffixes=("_full", "_rolling"))
    ensemble["baseline"] = (ensemble.baseline_full + ensemble.baseline_rolling) / 2
    ensemble["prediction"] = (ensemble.prediction_full + ensemble.prediction_rolling) / 2
    ensemble = ensemble[["year", "truth", "baseline", "prediction"]]
    scores = _split_scores(ensemble); holdout = scores["holdout_2015_2024"]; development = scores["development_2004_2014"]
    beats_trend = bool(holdout["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL and development["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL)
    holdout_rows = ensemble[ensemble.year >= HOLDOUT_START]
    operational_prediction = (
        holdout_rows.prediction if beats_trend else holdout_rows.baseline
    )
    errors = np.abs(holdout_rows.truth - operational_prediction).to_numpy()
    warnings = [
        "The target is national FAOSTAT yield; regional climate weights are fixed species proxies, not annual district production weights.",
        "Uganda has two harvest cycles and FAOSTAT calendar-year labels do not align perfectly with either marketing season.",
        "Management, tree age, disease and expansion of improved seedlings are not observed by the model.",
        "The untouched evaluation set contains only ten seasons (2015-2024).",
    ]
    artifact = {
        "key": BELT_KEY,
        "crop": "coffee",
        "target": {"variable": "green_coffee_yield_kg_ha", "source": "FAOSTAT QCL via Our World in Data", "spatial_scale": "Uganda national yield, climate proxied by seven coffee-belt locations", "area_basis": "harvested area"},
        "trained_years": [int(frame.year.min()), int(frame.year.max())],
        "n_seasons": int(len(frame)),
        "selection_protocol": {"feature_selection_years": "2004-2014 forward folds only", "untouched_holdout_years": "2015-2024", "trend_ensemble": "equal weight: full-history + rolling 20-season log trends"},
        "feature_sets": FEATURE_SETS,
        "development_validation_runs": runs,
        "selected_feature_set": selected,
        "selected_features": features,
        "ensemble_validation": scores,
        "operational_choice": "trend_ensemble_ridge_weather" if beats_trend else "trend_ensemble_only",
        "beats_trend": beats_trend,
        "low_confidence": holdout["skill_vs_trend"] < 0.20,
        "skill": {**holdout, "evaluation_period": "untouched holdout 2015-2024"},
        "components": [_fit_component(frame, features, "full_history"), _fit_component(frame, features, "rolling_20", ROLLING_WINDOW)],
        "uncertainty": {"basis": f"absolute errors on untouched 2015-2024 holdout using {'weather model' if beats_trend else 'trend fallback'}", "q68_kg_ha": float(np.quantile(errors, 0.68, method="higher")), "q95_kg_ha": float(np.quantile(errors, 0.95, method="higher"))},
        "anomaly": {"window_years": 20, "minimum_prior_years": 10},
        "model_warnings": warnings,
        "caveats": warnings,
    }
    MODELS.mkdir(parents=True, exist_ok=True)
    with (MODELS / f"{BELT_KEY}.json").open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
    print(f"[train] selected={selected} holdout_skill={holdout['skill_vs_trend']:+.1%} holdout_rmse={holdout['rmse_kg_ha']:,.0f} kg/ha operational={artifact['operational_choice']}")
    return artifact


if __name__ == "__main__":
    train()
