"""Leakage-resistant nonlinear challenger for Ethiopia coffee."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from .regions import BELT_KEY, FEATURE_SETS
from .train import DEVELOPMENT_END, HOLDOUT_START, MIN_TRAIN, ROLLING_WINDOW, _prepare, _score, _trend

HERE = Path(__file__).resolve().parent
CANDIDATES = [
    {"max_depth": 1, "n_estimators": 30, "learning_rate": 0.03},
    {"max_depth": 1, "n_estimators": 60, "learning_rate": 0.03},
    {"max_depth": 2, "n_estimators": 30, "learning_rate": 0.03},
    {"max_depth": 2, "n_estimators": 60, "learning_rate": 0.03},
    {"max_depth": 1, "n_estimators": 60, "learning_rate": 0.05},
]


def _forward(frame, features, params, window=None):
    years = frame.year.to_numpy(float); yields = frame.yield_kg_ha.to_numpy(float); rows = []
    for i, year in enumerate(years):
        indices = np.where(years < year)[0]
        if len(indices) < MIN_TRAIN: continue
        if window is not None: indices = indices[-window:]
        trend = _trend(years[indices], yields[indices]); matrix = _prepare(frame, features, years, trend)
        target = np.log(yields[indices]) - trend(years[indices])
        fit = GradientBoostingRegressor(loss="huber", random_state=42, **params).fit(matrix[indices], target)
        residual = float(fit.predict(matrix[i].reshape(1, -1))[0])
        rows.append({"year": int(year), "truth": float(yields[i]), "baseline": float(np.exp(trend(year))), "prediction": float(np.exp(trend(year) + residual))})
    return pd.DataFrame(rows)


def _ensemble(frame, features, params):
    full, rolling = _forward(frame, features, params), _forward(frame, features, params, ROLLING_WINDOW)
    out = full.merge(rolling, on=["year", "truth"], suffixes=("_full", "_rolling"))
    out["baseline"] = (out.baseline_full + out.baseline_rolling) / 2; out["prediction"] = (out.prediction_full + out.prediction_rolling) / 2
    return out[["year", "truth", "baseline", "prediction"]]


def run():
    raw = pd.read_csv(HERE / "training" / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = raw[raw.target_status == "final"].dropna(subset=["yield_kg_ha"] + all_features).sort_values("year").reset_index(drop=True)
    choices = []
    for name, features in FEATURE_SETS.items():
        for params in CANDIDATES:
            pred = _ensemble(frame, features, params); dev = _score(pred[pred.year <= DEVELOPMENT_END])
            choices.append({"feature_set": name, "features": features, "params": params, "development": dev})
    selected = min(choices, key=lambda x: x["development"]["rmse_kg_ha"])
    pred = _ensemble(frame, selected["features"], selected["params"]); holdout = _score(pred[pred.year >= HOLDOUT_START])
    ridge = json.loads((HERE / "models" / f"{BELT_KEY}.json").read_text(encoding="utf-8"))
    ridge_holdout = ridge["selected_validation"]["holdout_2015_2024"]
    adopted = bool(holdout["skill_vs_trend"] >= .10 and holdout["rmse_kg_ha"] <= ridge_holdout["rmse_kg_ha"] * .95)
    artifact = {"model_family": "sklearn GradientBoostingRegressor (XGBoost-like challenger; not XGBoost)", "selection_protocol": "feature/hyperparameter selection through 2014; 2015-2024 opened once", "selected": selected, "holdout_2015_2024": holdout, "ridge_holdout_2015_2024": ridge_holdout, "adoption_rule": "holdout skill >=10% and >=5% RMSE gain versus Ridge", "adopted": adopted, "decision": "adopt" if adopted else "reject_overfit_or_no_gain"}
    (HERE / "models" / "boosted_tree_challenger.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[challenger] dev_skill={selected['development']['skill_vs_trend']:+.1%} holdout_skill={holdout['skill_vs_trend']:+.1%} RMSE={holdout['rmse_kg_ha']:.1f}; {artifact['decision']}")
    return artifact


if __name__ == "__main__": run()
