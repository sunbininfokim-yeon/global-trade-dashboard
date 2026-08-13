"""Nonlinear boosted-tree challenger; never adopted from in-sample fit."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from .regions import BELT_KEY, FEATURE_SETS
from .train import DEVELOPMENT_END, HOLDOUT_START, MIN_TRAIN, ROLLING_WINDOW, _score, _trend

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
MODELS = HERE / "models"

CANDIDATES = [
    {"max_depth": 1, "n_estimators": 30, "learning_rate": 0.03},
    {"max_depth": 1, "n_estimators": 60, "learning_rate": 0.03},
    {"max_depth": 2, "n_estimators": 30, "learning_rate": 0.03},
    {"max_depth": 2, "n_estimators": 60, "learning_rate": 0.03},
    {"max_depth": 1, "n_estimators": 60, "learning_rate": 0.05},
]


def _forward(frame, features, params, window=None):
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
        target = np.log(yields[indices]) - trend(years[indices])
        model = GradientBoostingRegressor(loss="huber", random_state=42, **params)
        model.fit(matrix[indices], target)
        weather = float(model.predict(matrix[i].reshape(1, -1))[0])
        rows.append({"year": int(year), "truth": float(yields[i]), "baseline": float(np.exp(trend(year))), "prediction": float(np.exp(trend(year) + weather))})
    return pd.DataFrame(rows)


def _ensemble(frame, features, params):
    full = _forward(frame, features, params)
    rolling = _forward(frame, features, params, ROLLING_WINDOW)
    result = full.merge(rolling, on=["year", "truth"], suffixes=("_full", "_rolling"))
    result["baseline"] = (result.baseline_full + result.baseline_rolling) / 2
    result["prediction"] = (result.prediction_full + result.prediction_rolling) / 2
    return result[["year", "truth", "baseline", "prediction"]]


def run():
    raw = pd.read_csv(TRAINING / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = raw[raw.target_status == "final"].dropna(subset=["yield_kg_ha"] + all_features).sort_values("year")
    candidates = []
    for set_name, features in FEATURE_SETS.items():
        for params in CANDIDATES:
            predictions = _ensemble(frame, features, params)
            dev = _score(predictions[predictions.year <= DEVELOPMENT_END])
            candidates.append({"feature_set": set_name, "features": features, "params": params, "development": dev})
    selected = min(candidates, key=lambda item: item["development"]["rmse_kg_ha"])
    predictions = _ensemble(frame, selected["features"], selected["params"])
    holdout = _score(predictions[predictions.year >= HOLDOUT_START])
    ridge = json.loads((MODELS / f"{BELT_KEY}.json").read_text(encoding="utf-8"))
    ridge_holdout = ridge["skill"]
    adopted = bool(holdout["skill_vs_trend"] >= 0.10 and holdout["rmse_kg_ha"] <= ridge_holdout["rmse_kg_ha"] * 0.95)
    artifact = {
        "model_family": "sklearn GradientBoostingRegressor (XGBoost-like nonlinear challenger; not XGBoost)",
        "selection_protocol": "feature set and hyperparameters selected on forward folds through 2014; 2015-2024 opened once after selection",
        "selected": selected,
        "holdout_2015_2024": holdout,
        "ridge_holdout_2015_2024": {key: ridge_holdout[key] for key in ("n_folds", "rmse_kg_ha", "baseline_rmse_kg_ha", "skill_vs_trend", "detrended_r2")},
        "adoption_rule": "holdout skill >=10% and RMSE at least 5% below Ridge",
        "adopted": adopted,
        "decision": "adopt" if adopted else "reject_overfit_or_no_gain",
    }
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / "boosted_tree_challenger.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[challenger] dev_skill={selected['development']['skill_vs_trend']:+.1%} holdout_skill={holdout['skill_vs_trend']:+.1%} RMSE={holdout['rmse_kg_ha']:.1f}; decision={artifact['decision']}")
    return artifact


if __name__ == "__main__":
    run()
