"""
Apply the MODIS NDVI correction to a live forecast, where the backtest earned it.

Same rule as argentina.ndvi_blend: ndvi_backtest decides per region and
window (the full NDVI window or its first half) whether the correction is on
and stores the slope it fitted. This only looks the decision up and applies
it: the season's production-weighted NDVI, standardised against the fitting
seasons, times the slope, as a log adjustment. Nothing is applied before half
the window has been observed, or for a window the backtest left off.
"""

import json
import os

import numpy as np
import pandas as pd

from .ndvi_backtest import COL, COND, season_ndvi


def _load():
    try:
        with open(os.path.join(COND, "ndvi_backtest.json")) as f:
            report = json.load(f)
        nd = pd.read_csv(os.path.join(COND, "ndvi_points.csv"),
                         parse_dates=["date"])
    except (OSError, ValueError):
        return None, None
    return report, nd


def adjustment(cfg, season):
    """{window, ndvi, z, adjustment_pct, ...} for the season, or None."""
    report, nd = _load()
    live = (report or {}).get(cfg.key, {}).get("live", {})
    for win, half in (("full", False), ("half", True)):
        e = live.get(win)
        if not e or not e.get("enabled"):
            continue
        value = season_ndvi(nd, cfg, half, COL).get(season)
        if value is None:
            continue
        z = (value - e["mean"]) / e["sd"]
        adj = e["slope"] * z
        return {"window": win, "ndvi": round(float(value), 4), "z": round(float(z), 2),
                "log_adjustment": adj,
                "adjustment_pct": round(float(np.exp(adj) - 1) * 100, 2),
                "backtest_skill": round(e["skill_vs_base"], 3),
                "fit_years": e["fit_years"]}
    return None
