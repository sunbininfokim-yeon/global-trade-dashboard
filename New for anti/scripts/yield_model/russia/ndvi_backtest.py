"""
Does MODIS NDVI improve the Russian forecasts? Same test as argentina's.

Usage: python3 -m russia.ndvi_backtest

The method, the live rule and the correction are argentina.ndvi_backtest's
(see that docstring). Russia differs in the base forecast: no Russian model
beats its trend at present, so production publishes the trend, and the trend
is what NDVI has to improve. A trend needs far fewer seasons than a weather
model, so the base is a forward trend from TREND_MIN_PRIOR seasons on, which
leaves enough scored seasons on a record that only starts in 2000 and has a
2022-2023 gap. Where a model does beat the trend, its own forward forecasts
are the base instead, as in Argentina.

Barley is left out: its label is national PSD (interim), which the point
NDVI cannot speak for.

Writes condition/ndvi_backtest.json.
"""

import json
import os

import numpy as np
import pandas as pd

from argentina.ndvi_backtest import RULE, score_region
from .regions import BY_KEY
from .train import TREND_FORMS, fit_trend, run_cv

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "condition")
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

# Heading through grain fill for winter wheat (earlier in the South),
# flowering through seed fill for sunflower. Harvest year = calendar year.
WINDOWS = {
    "southern_winter_wheat": ((5, 1, 0),  (6, 20, 0)),
    "cbe_winter_wheat":      ((5, 15, 0), (7, 5, 0)),
    "volga_winter_wheat":    ((5, 15, 0), (7, 5, 0)),
    "russia_winter_wheat":   ((5, 1, 0),  (6, 30, 0)),
    "southern_sunflower":    ((7, 1, 0),  (8, 20, 0)),
    "cbe_sunflower":         ((7, 1, 0),  (8, 20, 0)),
    "volga_sunflower":       ((7, 1, 0),  (8, 20, 0)),
    "russia_sunflower":      ((7, 1, 0),  (8, 20, 0)),
}
TREND_MIN_PRIOR = 8


def log(msg):
    print(f"[ru-ndvi-bt] {msg}", flush=True)


def base_forecasts(cfg):
    art = json.load(open(os.path.join(MODELS, f"{cfg.key}.json")))
    df = (pd.read_csv(os.path.join(TRAINING, f"{cfg.key}.csv"))
            .sort_values("year").dropna(subset=["target"]))
    df = df[df.target > 0]
    if cfg.regime_start:
        df = df[df.year >= cfg.regime_start]
    df = df.reset_index(drop=True)
    _, degree, window = next(t for t in TREND_FORMS if t[0] == art["trend_form"])
    if art.get("beats_trend"):
        feats = [f for f in art["features"] if f in df.columns]
        df = df.dropna(subset=feats).reset_index(drop=True)
        truth, pred, _, years = run_cv(df, feats, "forward", degree, window,
                                       cfg.min_train or 18)
        return {y: (t, p) for y, t, p in zip(years, truth, pred)}, True
    years = df.year.values.astype(float)
    vals = df.target.values.astype(float)
    out = {}
    for i, y in enumerate(years):
        prior = years < y
        if prior.sum() < TREND_MIN_PRIOR:
            continue
        trend = fit_trend(years[prior], vals[prior], degree, window)
        out[int(y)] = (vals[i], float(np.exp(trend(y))))
    return out, False


def main():
    nd = pd.read_csv(os.path.join(COND, "ndvi_points.csv"), parse_dates=["date"])
    report = {}
    for key in WINDOWS:
        cfg = BY_KEY[key]
        if not os.path.exists(os.path.join(MODELS, f"{key}.json")):
            log(f"{key}: no model, skipped")
            continue
        base, beats = base_forecasts(cfg)
        report[key] = score_region(nd, cfg, base, beats, WINDOWS)
    report["_rule"] = RULE
    with open(os.path.join(COND, "ndvi_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
