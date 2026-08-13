"""Regulated boosted-tree challenger; never selected on the holdout."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from .regions import BELT_KEY, FEATURE_SETS
from .train import DEVELOPMENT_END, HOLDOUT_START, MIN_TRAIN, _trend

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
MODELS = HERE / "models"


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
        estimator = GradientBoostingRegressor(**params)
        estimator.fit(matrix[indices], target)
        weather = float(estimator.predict(matrix[i : i + 1])[0])
        rows.append(
            {
                "year": int(year),
                "truth": float(yields[i]),
                "baseline": float(np.exp(trend(year))),
                "prediction": float(np.exp(trend(year) + weather)),
            }
        )
    return pd.DataFrame(rows)


def _score(frame):
    rmse = float(np.sqrt(np.mean((frame.truth - frame.prediction) ** 2)))
    baseline = float(np.sqrt(np.mean((frame.truth - frame.baseline) ** 2)))
    return {
        "n_folds": int(len(frame)),
        "rmse_kg_ha": rmse,
        "baseline_rmse_kg_ha": baseline,
        "skill_vs_trend": 1 - rmse / baseline,
    }


def evaluate():
    frame = pd.read_csv(TRAINING / f"{BELT_KEY}.csv")
    all_features = sorted(set().union(*FEATURE_SETS.values()))
    frame = frame[frame.target_status == "final"].dropna(
        subset=["yield_kg_ha"] + all_features
    ).sort_values("year")
    feature_choices = {
        "selected_water_demand": FEATURE_SETS["water_demand"],
        "all_weather": all_features,
    }
    shapes = [
        {"max_depth": 1, "n_estimators": 30, "learning_rate": 0.03, "min_samples_leaf": 4},
        {"max_depth": 1, "n_estimators": 60, "learning_rate": 0.03, "min_samples_leaf": 4},
        {"max_depth": 2, "n_estimators": 30, "learning_rate": 0.03, "min_samples_leaf": 4},
        {"max_depth": 1, "n_estimators": 40, "learning_rate": 0.05, "min_samples_leaf": 5},
    ]
    runs = {}
    for feature_name, features in feature_choices.items():
        for shape in shapes:
            name = (
                f"{feature_name}_d{shape['max_depth']}_n{shape['n_estimators']}_"
                f"lr{shape['learning_rate']}"
            )
            params = {
                **shape,
                "subsample": 0.8,
                "loss": "huber",
                "random_state": 42,
            }
            full = _forward(frame, features, params, window=None)
            rolling = _forward(frame, features, params, window=20)
            ensemble = full.merge(
                rolling, on=["year", "truth"], suffixes=("_full", "_rolling")
            )
            ensemble["baseline"] = (
                ensemble.baseline_full + ensemble.baseline_rolling
            ) / 2
            ensemble["prediction"] = (
                ensemble.prediction_full + ensemble.prediction_rolling
            ) / 2
            development = ensemble[ensemble.year <= DEVELOPMENT_END]
            holdout = ensemble[ensemble.year >= HOLDOUT_START]
            runs[name] = {
                "features": features,
                "params": params,
                "development": _score(development),
                "holdout": _score(holdout),
            }

    # Hyperparameters are selected without seeing 2016-2025.
    selected = min(runs, key=lambda name: runs[name]["development"]["rmse_kg_ha"])
    chosen = runs[selected]
    main_path = MODELS / f"{BELT_KEY}.json"
    operational = json.loads(main_path.read_text(encoding="utf-8"))
    ridge_rmse = float(operational["skill"]["rmse_kg_ha"])
    adopted = bool(
        chosen["holdout"]["skill_vs_trend"] >= 0.10
        and chosen["holdout"]["rmse_kg_ha"] <= 0.95 * ridge_rmse
    )
    report = {
        "model": "sklearn GradientBoostingRegressor",
        "role": "XGBoost-family nonlinear challenger; not labelled as XGBoost",
        "selection_period": "2007-2015 forward folds",
        "untouched_holdout": "2016-2025",
        "selected_candidate": selected,
        "selected_result": chosen,
        "operational_ridge_holdout_rmse_kg_ha": ridge_rmse,
        "adoption_rule": "holdout skill >=10% and RMSE at least 5% below Ridge",
        "adopted": adopted,
        "decision": "adopt" if adopted else "reject_overfit",
        "all_candidates": runs,
    }
    (MODELS / "boosted_tree_challenger.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    operational["challengers"] = {
        "boosted_tree": {
            key: report[key]
            for key in (
                "model",
                "selected_candidate",
                "selected_result",
                "operational_ridge_holdout_rmse_kg_ha",
                "adoption_rule",
                "adopted",
                "decision",
            )
        }
    }
    main_path.write_text(
        json.dumps(operational, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[challenger] selected={selected} holdout_skill="
        f"{chosen['holdout']['skill_vs_trend']:+.1%} "
        f"RMSE={chosen['holdout']['rmse_kg_ha']:,.0f}; decision={report['decision']}"
    )
    return report


if __name__ == "__main__":
    evaluate()
