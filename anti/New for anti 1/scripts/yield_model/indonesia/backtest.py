"""Show the last N one-step-ahead forecasts season by season."""

import json
import os
import sys

import numpy as np
import pandas as pd

from .model import _ridge_fit, _ridge_predict, _tail, fit_trend, select_alpha
from .regions import ALL, BY_KEY


HERE = os.path.dirname(os.path.abspath(__file__))


def backtest_target(frame, target_name, target_model, n_years):
    features = target_model["features"]
    frame = frame.dropna(subset=[target_name] + features).sort_values("year").reset_index(drop=True)
    rows = []
    degree = target_model["trend"].get("degree", 1)
    window = target_model["trend"].get("window")
    for i in range(max(10, len(frame) - n_years), len(frame)):
        train = frame.iloc[:i]
        test = frame.iloc[i]
        train_years = train.year.to_numpy(float)
        train_values = train[target_name].to_numpy(float)
        trend = fit_trend(train_years, train_values, degree=degree, window=window)
        base = float(np.exp(trend(test.year)))
        candidate = base
        if features:
            x = train[features].to_numpy(float)
            fit_years, fit_values, fit_x = _tail(
                train_years, train_values, window=window, x=x)
            residual = np.log(fit_values) - trend(fit_years)
            alpha = select_alpha(fit_x, residual)
            ridge = _ridge_fit(fit_x, residual, alpha)
            shock = float(_ridge_predict(ridge, test[features].to_numpy(float))[0])
            candidate = float(np.exp(trend(test.year) + shock))
        prediction = candidate if target_model["beats_trend"] else base
        actual = float(test[target_name])
        rows.append({
            "year": int(test.year), "actual": actual, "predicted": prediction,
            "trend": base, "error_pct": (prediction - actual) / actual * 100,
            "trend_error_pct": (base - actual) / actual * 100,
        })
    return pd.DataFrame(rows)


def main():
    args = list(sys.argv[1:])
    n_years = 5
    if "--years" in args:
        index = args.index("--years")
        n_years = int(args[index + 1])
        del args[index:index + 2]
    configs = [BY_KEY[key] for key in args] if args else ALL
    for cfg in configs:
        model_path = os.path.join(HERE, "models", cfg.key + ".json")
        training_path = os.path.join(HERE, "training", cfg.key + ".csv")
        if not os.path.exists(model_path) or not os.path.exists(training_path):
            continue
        with open(model_path, encoding="utf-8") as handle:
            artifact = json.load(handle)
        frame = pd.read_csv(training_path)
        print("[indonesia:backtest] " + cfg.label)
        for name, column in [("yield", "yield_kg_ha"),
                             ("production", "production_tonnes"),
                             ("area", "area_ha")]:
            if name not in artifact["targets"]:
                continue
            result = backtest_target(frame, column, artifact["targets"][name], n_years)
            mape = float(result.error_pct.abs().mean())
            trend_mape = float(result.trend_error_pct.abs().mean())
            print("  {} MAPE {:.1f}% vs trend {:.1f}%".format(name, mape, trend_mape))
            for _, row in result.iterrows():
                print("    {} actual {:,.1f}, model {:,.1f} ({:+.1f}%), trend {:,.1f}".format(
                    int(row.year), row.actual, row.predicted, row.error_pct, row.trend))
    return 0


if __name__ == "__main__":
    sys.exit(main())
