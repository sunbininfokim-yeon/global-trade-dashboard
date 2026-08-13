"""Leakage-safe Ridge vs XGBoost vs two-layer MLP sorghum experiment."""

from __future__ import annotations

import json
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import TimeSeriesSplit
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

from australia.train import evaluate, fit_ridge_cv, fit_scaler, fit_trend, transform


HERE = Path(__file__).resolve().parents[1]
FEATURES = [
    "rain_preseason_z20", "rain_growing_z20", "harvest_rain_z20",
    "sm_preseason_z20", "sm_flowering_z20", "terminal_dryness_z20",
    "heat_excess_flowering_z20", "heat_dry_flowering_z20",
    "oni_flowering_z20",
]
MIN_TRAIN = 20
SEEDS = [11, 29, 47, 71, 97]

XGB_GRID = [
    {"n_estimators": 30, "max_depth": 1, "learning_rate": 0.05, "reg_lambda": 10.0},
    {"n_estimators": 60, "max_depth": 1, "learning_rate": 0.05, "reg_lambda": 10.0},
    {"n_estimators": 40, "max_depth": 2, "learning_rate": 0.03, "reg_lambda": 10.0},
    {"n_estimators": 80, "max_depth": 2, "learning_rate": 0.03, "reg_lambda": 10.0},
    {"n_estimators": 40, "max_depth": 2, "learning_rate": 0.05, "reg_lambda": 20.0},
    {"n_estimators": 80, "max_depth": 2, "learning_rate": 0.05, "reg_lambda": 20.0},
]
MLP_GRID = [
    {"hidden_layer_sizes": (8, 4), "alpha": 0.1},
    {"hidden_layer_sizes": (8, 4), "alpha": 1.0},
    {"hidden_layer_sizes": (16, 8), "alpha": 1.0},
    {"hidden_layer_sizes": (16, 8), "alpha": 10.0},
]


def scaled(train_x: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean, scale = fit_scaler(train_x)
    return transform(train_x, mean, scale), transform(test_x, mean, scale)


def inner_splits(n: int):
    return TimeSeriesSplit(n_splits=3).split(np.arange(n))


def xgb_model(params: dict) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror", min_child_weight=3,
        subsample=0.85, colsample_bytree=0.85, random_state=2026,
        n_jobs=1, verbosity=0, **params,
    )


def choose_xgb(x: np.ndarray, y: np.ndarray) -> dict:
    scored = []
    for params in XGB_GRID:
        errors = []
        for train_i, valid_i in inner_splits(len(y)):
            train_x, valid_x = scaled(x[train_i], x[valid_i])
            model = xgb_model(params)
            model.fit(train_x, y[train_i])
            errors.extend((y[valid_i] - model.predict(valid_x)).tolist())
        scored.append((float(np.sqrt(np.mean(np.square(errors)))), params))
    return min(scored, key=lambda row: row[0])[1]


def mlp_model(params: dict, seed: int) -> MLPRegressor:
    return MLPRegressor(
        activation="relu", solver="lbfgs", max_iter=3000,
        random_state=seed, tol=1e-7, **params,
    )


def choose_mlp(x: np.ndarray, y: np.ndarray) -> dict:
    scored = []
    for params in MLP_GRID:
        errors = []
        for train_i, valid_i in inner_splits(len(y)):
            train_x, valid_x = scaled(x[train_i], x[valid_i])
            model = mlp_model(params, SEEDS[0])
            model.fit(train_x, y[train_i])
            errors.extend((y[valid_i] - model.predict(valid_x)).tolist())
        scored.append((float(np.sqrt(np.mean(np.square(errors)))), params))
    return min(scored, key=lambda row: row[0])[1]


def run_region(key: str) -> dict:
    frame = pd.read_csv(HERE / "training" / f"{key}.csv")
    frame = frame.dropna(subset=["yield_kg_ha"] + FEATURES).sort_values("year")
    years = frame.year.to_numpy(float)
    yields = frame.yield_kg_ha.to_numpy(float)
    matrix = frame[FEATURES].to_numpy(float)
    truth, baseline = [], []
    predictions = {"ridge": [], "xgboost": [], "mlp_2layer": []}
    selected_xgb, selected_mlp, fold_years = [], [], []

    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    for i, year in enumerate(years):
        mask = years < year
        if mask.sum() < MIN_TRAIN:
            continue
        train_x, test_x = scaled(matrix[mask], matrix[i:i + 1])
        trend = fit_trend(years[mask], yields[mask])
        residual = np.log(yields[mask]) - trend(years[mask])
        base = float(np.exp(trend(year)))

        ridge = fit_ridge_cv(train_x, residual)
        ridge_residual = float(ridge["intercept"] + test_x[0] @ ridge["coef"])

        xgb_params = choose_xgb(matrix[mask], residual)
        xgb = xgb_model(xgb_params)
        xgb.fit(train_x, residual)
        xgb_residual = float(xgb.predict(test_x)[0])

        mlp_params = choose_mlp(matrix[mask], residual)
        mlp_residuals = []
        for seed in SEEDS:
            mlp = mlp_model(mlp_params, seed)
            mlp.fit(train_x, residual)
            mlp_residuals.append(float(mlp.predict(test_x)[0]))
        mlp_residual = float(np.mean(mlp_residuals))

        truth.append(float(yields[i]))
        baseline.append(base)
        fold_years.append(int(year))
        predictions["ridge"].append(float(np.exp(np.log(base) + ridge_residual)))
        predictions["xgboost"].append(float(np.exp(np.log(base) + xgb_residual)))
        predictions["mlp_2layer"].append(float(np.exp(np.log(base) + mlp_residual)))
        selected_xgb.append(json.dumps(xgb_params, sort_keys=True))
        selected_mlp.append(json.dumps(mlp_params, sort_keys=True))

    truth_a, baseline_a = np.asarray(truth), np.asarray(baseline)
    metrics = {
        name: evaluate(truth_a, np.asarray(values), baseline_a)
        for name, values in predictions.items()
    }
    for name, values in predictions.items():
        metrics[name]["wins_vs_trend"] = int(np.sum(
            np.abs(truth_a - np.asarray(values)) < np.abs(truth_a - baseline_a)))
    return {
        "region": key, "fold_years": fold_years,
        "n_complete_seasons": int(len(frame)), "n_forward_folds": len(fold_years),
        "features": FEATURES, "metrics": metrics,
        "xgb_choices": Counter(selected_xgb).most_common(),
        "mlp_choices": Counter(selected_mlp).most_common(),
    }


def main() -> int:
    results = [run_region(key) for key in ("nsw_sorghum", "qld_sorghum")]
    for result in results:
        print(f"\n{result['region']} ({result['n_forward_folds']} forward folds)")
        for name, metric in result["metrics"].items():
            print(
                f"  {name:12} RMSE={metric['rmse']:7.1f} "
                f"MAE={metric['mae']:7.1f} full={metric['skill_vs_trend']:+7.1%} "
                f"recent={metric['recent_skill_vs_trend']:+7.1%} "
                f"wins={metric['wins_vs_trend']}/{result['n_forward_folds']}"
            )
        print("  XGB choices", result["xgb_choices"])
        print("  MLP choices", result["mlp_choices"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
