"""
Does Random Forest / XGBoost beat ridge regression on the MATOPIBA data we
already have? No new data collection -- reuses the state-level
training/matopiba_soja.csv and the four municipality CSVs already sitting on
disk from the GWETROOT and municipality-split experiments.

Motivation: Barbosa dos Santos et al. (2022, J. Sci. Food Agric. 102(9):
3665-3672) predicted MATOPIBA soybean yield from NASA POWER weather + SIDRA
yield -- the same two data sources this package already uses -- and reported
Random Forest as their best model (R2 0.81, RMSE 176.93 kg/ha), beating
linear/polynomial regression. If that holds up under this package's own
validation discipline, it is a real, cheap win: no satellite pixel data, no
new API integration, just a different regressor on data already in hand.

It is tested under exactly the discipline the rest of this package uses --
forward chaining with the trend refit inside every fold, plus a 5-year
holdout -- because the EU JRC's own finding (Meroni et al. 2021, Agric. For.
Meteorol. 308-309:108555) is that ML's apparent edge over simple regression
routinely does not survive honest small-sample validation. Whether Barbosa
dos Santos's R2=0.81 used a comparably strict split is not visible from the
abstract alone, so this is the check rather than taking the number on faith.

Trees cannot extrapolate a trend (a RandomForestRegressor's prediction is
bounded by the range of its training labels), so exactly like the ridge
models elsewhere in this package, RF/XGBoost here predict the *residual*
from the same fitted log-yield trend, never raw yield.
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .train import MIN_TRAIN, RECENT_FOLDS, TREND_FORMS, evaluate, fit_trend, prepare, window_rows

try:
    from xgboost import XGBRegressor
    HAVE_XGB = True
except ImportError:
    HAVE_XGB = False

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_TABLE = os.path.join(HERE, "training", "matopiba_soja.csv")
MUNI_DIR = os.path.join(HERE, "training_muni")

# Deliberately shallow/conservative: ~20-40 rows total, ~15-25 usable in any
# forward-chaining fold. A deep, many-tree forest would just memorise noise.
MODEL_FACTORIES = {
    "rf": lambda: RandomForestRegressor(
        n_estimators=200, max_depth=3, min_samples_leaf=3, random_state=42),
}
if HAVE_XGB:
    MODEL_FACTORIES["xgb"] = lambda: XGBRegressor(
        n_estimators=100, max_depth=2, learning_rate=0.1,
        min_child_weight=3, random_state=42, verbosity=0)


def log(msg):
    print(f"[ml] {msg}", flush=True)


def run_cv_ml(df, features, mode, degree, window, min_train, model_name):
    """Same fold structure as train.py's run_cv, swapping RidgeCV for an
    arbitrary sklearn-API regressor. No StandardScaler: tree splits are scale
    invariant, and standardising would only add a step that changes nothing."""
    years = df.year.values.astype(float)
    yields = df.yield_kg_ha.values.astype(float)

    preds, bases, truth, used = [], [], [], []

    for i, target in enumerate(years):
        if mode == "loo":
            train = np.arange(len(years)) != i
        else:
            train = years < target
            if train.sum() < min_train:
                continue

        trend = fit_trend(years[train], yields[train], degree, window)
        X = prepare(df, features, years, trend)

        fit = window_rows(years, train, degree, window)
        resid_train = np.log(yields[fit]) - trend(years[fit])

        model = MODEL_FACTORIES[model_name]()
        model.fit(X[fit], resid_train)
        pred_resid = float(model.predict(X[i:i + 1])[0])

        preds.append(float(np.exp(trend(target) + pred_resid)))
        bases.append(float(np.exp(trend(target))))
        truth.append(yields[i])
        used.append(int(target))

    if not truth:
        return None
    return (np.array(truth), np.array(preds), np.array(bases), used)


def evaluate_dataset(name, path):
    if not os.path.exists(path):
        log(f"{name}: no training table at {path}, skipped")
        return

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])

    weather_cols = [c for c in df.columns if c not in {"year", "yield_kg_ha"}]
    complete = df[weather_cols].notna().all(axis=1)
    trimmed = int((~complete).sum())
    if trimmed and trimmed <= 5:
        df = df[complete].reset_index(drop=True)

    candidates = [c for c in df.columns
                  if c not in {"year", "yield_kg_ha"}
                  and df[c].notna().all() and df[c].std() > 0]

    if len(df) < MIN_TRAIN + 5:
        log(f"{name}: only {len(df)} usable seasons, skipped")
        return

    log(f"{name}: {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} features: {candidates}")

    for model_name in MODEL_FACTORIES:
        results = {}
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv_ml(df, candidates, mode, degree, window,
                                MIN_TRAIN, model_name)
                if out is None:
                    continue
                truth, pred, base, yrs = out
                rkey = f"{tlabel}_{mode}"
                results[rkey] = evaluate(truth, pred, base)
                results[rkey]["n"] = len(truth)

        fwd = {k: v for k, v in results.items() if k.endswith("_forward")}
        if not fwd:
            log(f"  {model_name}: no forward-chaining fold had enough history")
            continue

        best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
        best = fwd[best_key]
        log(f"  {model_name:4} best={best_key:16} n={best['n']:3d} "
            f"RMSE={best['rmse']:7.1f}  recent{RECENT_FOLDS}={best['recent_rmse']:7.1f}  "
            f"vs-trend(full)={best['skill_vs_trend']:+7.1%}")


def main():
    log(f"xgboost available: {HAVE_XGB}")
    log("")
    evaluate_dataset("state-level matopiba_soja", STATE_TABLE)
    log("")
    if os.path.isdir(MUNI_DIR):
        for fname in sorted(os.listdir(MUNI_DIR)):
            if fname.endswith(".csv"):
                evaluate_dataset(fname[:-4], os.path.join(MUNI_DIR, fname))
                log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
