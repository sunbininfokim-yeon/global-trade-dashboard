"""Leakage-resistant validation for South African commercial maize yield."""

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
MIN_TRAIN = 15
DEVELOPMENT_END = 2015
HOLDOUT_START = 2016
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
    gram = design.T @ design
    rhs = design.T @ target
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0
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
    truth = frame.truth.to_numpy(float)
    prediction = frame.prediction.to_numpy(float)
    baseline = frame.baseline.to_numpy(float)
    error = truth - prediction
    base_error = truth - baseline
    rmse = float(np.sqrt(np.mean(error ** 2)))
    base_rmse = float(np.sqrt(np.mean(base_error ** 2)))
    dev_true = truth - baseline
    dev_pred = prediction - baseline
    denom = float(np.sum((dev_true - dev_true.mean()) ** 2))
    return {
        "n_folds": int(len(frame)),
        "rmse_kg_ha": rmse,
        "baseline_rmse_kg_ha": base_rmse,
        "skill_vs_trend": 1 - rmse / base_rmse,
        "detrended_r2": (
            1 - float(np.sum((dev_true - dev_pred) ** 2)) / denom
            if denom
            else float("nan")
        ),
    }


def _split_scores(predictions):
    development = predictions[predictions.year <= DEVELOPMENT_END]
    holdout = predictions[predictions.year >= HOLDOUT_START]
    return {
        "all": _score(predictions),
        "development_2007_2015": _score(development),
        "holdout_2016_2025": _score(holdout),
    }


def _forward(frame, features, window=None):
    years = frame.year.to_numpy(float)
    yields = frame.yield_kg_ha.to_numpy(float)
    matrix = frame[features].to_numpy(float)
    rows = []
    for i, year in enumerate(years):
        indices = np.where(years < year)[0]
        if len(indices) < MIN_TRAIN:
            continue
        if window is not None:
            indices = indices[-window:]
        trend = _trend(years[indices], yields[indices])
        mean, scale = _scale(matrix[indices])
        scaled = (matrix[indices] - mean) / scale
        residual = np.log(yields[indices]) - trend(years[indices])
        _, intercept, coef = _ridge(scaled, residual)
        weather = intercept + ((matrix[i] - mean) / scale) @ coef
        rows.append(
            {
                "year": int(year),
                "truth": float(yields[i]),
                "baseline": float(np.exp(trend(year))),
                "prediction": float(np.exp(trend(year) + weather)),
            }
        )
    return pd.DataFrame(rows)


def _fit_component(frame, features, name, window=None):
    if window is not None:
        frame = frame.tail(window)
    years = frame.year.to_numpy(float)
    yields = frame.yield_kg_ha.to_numpy(float)
    matrix = frame[features].to_numpy(float)
    trend = _trend(years, yields)
    mean, scale = _scale(matrix)
    alpha, intercept, coef = _ridge(
        (matrix - mean) / scale, np.log(yields) - trend(years)
    )
    return {
        "name": name,
        "train_window_years": window,
        "trained_years": [int(years.min()), int(years.max())],
        "n_seasons": int(len(frame)),
        "trend": {"form": "log_linear", "log_poly_coef": trend.coefficients.tolist()},
        "scaler": {"mean": mean.tolist(), "scale": scale.tolist()},
        "ridge": {"alpha": alpha, "intercept": intercept, "coef": coef.tolist()},
    }


def train():
    frame = pd.read_csv(TRAINING / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = frame[frame.target_status == "final"].dropna(
        subset=["yield_kg_ha"] + all_features
    ).sort_values("year")
    if len(frame) < MIN_TRAIN + 5:
        raise ValueError(f"Only {len(frame)} complete final seasons")

    # Feature choice sees only the development folds. The latest ten seasons
    # remain untouched until the feature set is frozen.
    development_runs = {}
    predictions = {}
    for name, features in FEATURE_SETS.items():
        fold_frame = _forward(frame, features, window=None)
        predictions[name] = fold_frame
        development_runs[name] = _split_scores(fold_frame)
    selected = min(
        development_runs,
        key=lambda name: development_runs[name]["development_2007_2015"][
            "rmse_kg_ha"
        ],
    )
    features = FEATURE_SETS[selected]

    full_predictions = predictions[selected]
    rolling_predictions = _forward(frame, features, window=ROLLING_WINDOW)
    ensemble = full_predictions.merge(
        rolling_predictions,
        on=["year", "truth"],
        suffixes=("_full", "_rolling"),
    )
    ensemble["baseline"] = (
        ensemble.baseline_full + ensemble.baseline_rolling
    ) / 2
    ensemble["prediction"] = (
        ensemble.prediction_full + ensemble.prediction_rolling
    ) / 2
    ensemble = ensemble[["year", "truth", "baseline", "prediction"]]
    ensemble_scores = _split_scores(ensemble)
    holdout = ensemble[ensemble.year >= HOLDOUT_START]
    holdout_score = ensemble_scores["holdout_2016_2025"]
    development_score = ensemble_scores["development_2007_2015"]
    beats_trend = bool(
        holdout_score["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL
        and development_score["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL
    )

    components = [
        _fit_component(frame, features, "full_history", window=None),
        _fit_component(frame, features, "rolling_20", window=ROLLING_WINDOW),
    ]
    selected_corr = frame[features].corr().to_numpy()
    upper = (
        np.abs(selected_corr[np.triu_indices(len(features), 1)])
        if len(features) > 1
        else np.asarray([0.0])
    )
    max_abs_correlation = float(upper.max())
    warnings = []
    if max_abs_correlation >= 0.80:
        warnings.append(
            "Selected weather predictors are strongly correlated; coefficient signs are not causal."
        )
    if holdout_score["detrended_r2"] < 0.10:
        warnings.append("Holdout detrended R2 is below 0.10.")
    warnings.append(
        "The untouched evaluation set contains only ten seasons (2016-2025)."
    )
    holdout_errors = np.abs(holdout.truth - holdout.prediction).to_numpy()

    artifact = {
        "key": BELT_KEY,
        "crop": "corn",
        "target": {
            "variable": "commercial_maize_yield_kg_ha",
            "source": "Crop Estimates Committee via SAGIS historic production workbook",
            "spatial_scale": "South Africa commercial maize, climate proxied by core belt",
            "area_basis": "planted area",
        },
        "trained_years": [int(frame.year.min()), int(frame.year.max())],
        "n_seasons": int(len(frame)),
        "selection_protocol": {
            "feature_selection_years": "2007-2015 forward folds only",
            "untouched_holdout_years": "2016-2025",
            "trend_ensemble": "equal weight: full-history + rolling 20-season log trends",
        },
        "feature_sets": FEATURE_SETS,
        "development_validation_runs": development_runs,
        "selected_feature_set": selected,
        "selected_features": features,
        "component_validation": {
            "full_history": _split_scores(full_predictions),
            "rolling_20": _split_scores(rolling_predictions),
        },
        "ensemble_validation": ensemble_scores,
        "operational_choice": "trend_ensemble_ridge_weather" if beats_trend else "trend_ensemble_only",
        "beats_trend": beats_trend,
        "low_confidence": holdout_score["skill_vs_trend"] < 0.20,
        "model_warnings": warnings,
        "selected_feature_max_abs_correlation": max_abs_correlation,
        "skill": {
            "rmse_kg_ha": holdout_score["rmse_kg_ha"],
            "baseline_rmse_kg_ha": holdout_score["baseline_rmse_kg_ha"],
            "skill_vs_trend": holdout_score["skill_vs_trend"],
            "detrended_r2": holdout_score["detrended_r2"],
            "evaluation_period": "untouched holdout 2016-2025",
            "n_folds": holdout_score["n_folds"],
        },
        "components": components,
        "uncertainty": {
            "basis": "absolute errors on untouched 2016-2025 holdout",
            "q68_kg_ha": float(np.quantile(holdout_errors, 0.68, method="higher")),
            "q95_kg_ha": float(np.quantile(holdout_errors, 0.95, method="higher")),
        },
        "anomaly": {"window_years": 20, "minimum_prior_years": 10},
        "caveats": [
            "The target is national commercial maize yield; the three provinces supply only the climate proxy.",
            "The six locations use fixed mean 2023-2025 production weights, not historical annual weights.",
            "Irrigated Northern Cape maize is intentionally excluded from the climate proxy.",
            *warnings,
        ],
    }
    MODELS.mkdir(parents=True, exist_ok=True)
    with (MODELS / f"{BELT_KEY}.json").open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
    print(
        f"[train] selected={selected} holdout_skill="
        f"{holdout_score['skill_vs_trend']:+.1%} holdout_rmse="
        f"{holdout_score['rmse_kg_ha']:,.0f} kg/ha"
    )
    return artifact


if __name__ == "__main__":
    train()
