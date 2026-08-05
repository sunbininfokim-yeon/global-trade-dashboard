"""
Hold out the last N seasons and forecast them against published actuals.

Usage: python3 -m brazil.backtest [--years 5] [region_key ...]

IBGE has not published 2025 yet, so a genuine unseen-season test has to come
from the recent past instead. For each held-out year the trend and the
regression are refit on that year's predecessors only -- the same discipline
as the forward-chaining inside train.py, but reported season by season so the
misses are visible individually rather than averaged into one RMSE.

The feature set and trend form are taken from the saved model artifact, which
means they were selected using folds that include these years. That is a real
caveat and it is stated in the output: this measures whether the chosen
configuration forecasts, not whether the selection procedure itself is clean.
The forward-chaining figures in train.py remain the primary evidence.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

from .train import (
    ALPHAS,
    TREND_FORMS,
    fit_trend,
    prepare,
)
from .regions import ALL, BY_KEY

from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")


def log(msg):
    print(f"[backtest] {msg}", flush=True)


def backtest_one(cfg, n_years):
    mpath = os.path.join(MODELS, f"{cfg.key}.json")
    tpath = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not (os.path.exists(mpath) and os.path.exists(tpath)):
        return None

    with open(mpath, encoding="utf-8") as f:
        model = json.load(f)

    df = pd.read_csv(tpath).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])
    if cfg.regime_start:
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)

    feats = [f for f in model["features"] if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)

    form = model["trend"].get("form", "deg1")
    degree, window = next(((d, w) for lbl, d, w in TREND_FORMS if lbl == form),
                          (model["trend"]["degree"], model["trend"].get("window")))

    years = df.year.values.astype(float)
    yields = df.yield_kg_ha.values.astype(float)
    targets = years[-n_years:]

    rows = []
    for target in targets:
        train = years < target
        if train.sum() < 12:
            continue

        trend = fit_trend(years[train], yields[train], degree, window)
        X = prepare(df, feats, years, trend)
        resid = np.log(yields[train]) - trend(years[train])

        scaler = StandardScaler().fit(X[train])
        ridge = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[train]), resid)

        i = int(np.where(years == target)[0][0])
        pred_resid = float(ridge.predict(scaler.transform(X[i:i + 1]))[0])

        base = float(np.exp(trend(target)))
        pred = float(np.exp(trend(target) + pred_resid))
        actual = float(yields[i])

        rows.append({
            "year": int(target), "actual": actual, "predicted": pred,
            "trend_only": base,
            "err_pct": (pred - actual) / actual * 100,
            "trend_err_pct": (base - actual) / actual * 100,
        })

    if not rows:
        return None
    return pd.DataFrame(rows), model


def main():
    args = list(sys.argv[1:])
    n_years = 5
    if "--years" in args:
        i = args.index("--years")
        n_years = int(args[i + 1])
        del args[i:i + 2]

    configs = [BY_KEY[k] for k in args] if args else ALL

    log(f"holding out the last {n_years} published seasons; trend and "
        "regression refit on earlier years only")
    log("(feature set and trend form come from the saved model, which was "
        "selected on folds including these years -- see module docstring)")
    log("")

    summary = []
    for cfg in configs:
        out = backtest_one(cfg, n_years)
        if out is None:
            log(f"{cfg.key}: skipped")
            continue
        bt, model = out

        mape = float(np.mean(np.abs(bt.err_pct)))
        tmape = float(np.mean(np.abs(bt.trend_err_pct)))
        rmse = float(np.sqrt(np.mean((bt.predicted - bt.actual) ** 2)))
        trmse = float(np.sqrt(np.mean((bt.trend_only - bt.actual) ** 2)))

        log(f"{cfg.label}  [{'weather beats trend' if model['beats_trend'] else 'no weather skill'}]")
        log(f"  {'year':>6} {'actual':>9} {'model':>9} {'err%':>7} "
            f"{'trend':>9} {'err%':>7}")
        for _, r in bt.iterrows():
            log(f"  {int(r.year):>6} {r.actual:9,.0f} {r.predicted:9,.0f} "
                f"{r.err_pct:+7.1f} {r.trend_only:9,.0f} {r.trend_err_pct:+7.1f}")
        log(f"  MAPE model {mape:.1f}%  vs trend {tmape:.1f}%   "
            f"RMSE model {rmse:,.0f}  vs trend {trmse:,.0f}")
        log("")

        summary.append({"key": cfg.key, "mape": mape, "tmape": tmape,
                        "rmse": rmse, "trmse": trmse,
                        "beats": model["beats_trend"]})

    log("=" * 74)
    log(f"{'region-crop':26} {'model MAPE':>11} {'trend MAPE':>11} "
        f"{'improvement':>12}")
    log("-" * 74)
    for s in sorted(summary, key=lambda x: x["mape"] - x["tmape"]):
        gain = s["tmape"] - s["mape"]
        log(f"{s['key']:26} {s['mape']:10.1f}% {s['tmape']:10.1f}% "
            f"{gain:+11.1f}pp")
    log("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
