"""
Does MODIS NDVI improve the Argentine yield forecasts? Measured, not assumed.

Usage: python3 -m argentina.ndvi_backtest

NDVI starts in 2000, the yield record in the 1980s. Rather than retrain every
model on the satellite era alone (and score a shorter record as if it were
NDVI's fault), NDVI is tested as a correction on top of what the pipeline
already forecasts:

  1. The region's model -- its saved feature set and trend form -- is run in
     forward chaining over the full record, giving an out-of-sample forecast
     for every season from 2007. Where the model does not beat the trend, the
     trend itself is the forecast, as in production.
  2. For each season, the log error of that forecast is regressed on the
     season's NDVI using only earlier seasons, and the fitted correction is
     applied to the season being scored.

Both arms are scored on the same seasons, so the difference is NDVI's alone.
Two windows are tested per crop: the full critical window (what is known at
harvest) and its first half (what is known mid-season). The second is the one
that matters for a live forecast.

Writes condition/ndvi_backtest.json.
"""

import json
import os

import numpy as np
import pandas as pd

from brazil.train import TREND_FORMS, run_cv
from .regions import BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "condition")
TRAINING = os.path.join(HERE, "training")
# AR_MODELS lets the backtest score against models from another branch.
MODELS = os.environ.get("AR_MODELS") or os.path.join(HERE, "models")

# Critical window per region as (start (month, day, year_offset), end (...)),
# year_offset relative to the harvest year. Grain fill for the summer crops,
# heading for wheat -- the stretch where canopy greenness carries yield.
WINDOWS = {
    "pampas_soja":   ((1, 1, 0),   (3, 31, 0)),
    "pampas_maiz":   ((12, 1, -1), (2, 28, 0)),
    "pampas_trigo":  ((8, 15, 0),  (10, 31, 0)),
    "norte_soja":    ((2, 1, 0),   (4, 15, 0)),
    "chaco_algodon": ((1, 1, 0),   (3, 31, 0)),
}
MIN_TRAIN = 22          # same as argentina.train
MIN_PRIOR = 6           # earlier seasons needed before NDVI may correct one
RIDGE = 1.0             # shrinkage on the standardised NDVI slope


def log(msg):
    print(f"[ndvi-bt] {msg}", flush=True)


def season_ndvi(nd, cfg, half=False, col="ndvi_p75"):
    """Production-weighted mean NDVI over the window, per harvest year."""
    (m0, d0, o0), (m1, d1, o1) = WINDOWS[cfg.key]
    w = {p["name"]: p["weight"] for p in cfg.points}
    nd = nd[nd.point.isin(w)].dropna(subset=[col])
    out = {}
    for y in range(2001, nd.date.dt.year.max() + 2):
        a = pd.Timestamp(y + o0, m0, d0)
        b = pd.Timestamp(y + o1, m1, d1)
        if half:
            b = a + (b - a) / 2
        s = nd[(nd.date >= a) & (nd.date <= b)]
        if s.empty or s.date.max() < b - pd.Timedelta(days=20):
            continue
        per = s.groupby("point")[col].mean()
        ww = pd.Series({k: w[k] for k in per.index})
        if ww.sum() < 0.6:          # most of the production weight missing
            continue
        out[y] = float((per * ww).sum() / ww.sum())
    return out


def base_forecasts(cfg):
    art = json.load(open(os.path.join(MODELS, f"{cfg.key}.json")))
    df = (pd.read_csv(os.path.join(TRAINING, f"{cfg.key}.csv"))
            .sort_values("year").dropna(subset=["yield_kg_ha"])
            .reset_index(drop=True))
    if cfg.regime_start:
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
    form = art["trend_form"]
    _, degree, window = next(t for t in TREND_FORMS if t[0] == form)
    feats = [f for f in art["features"] if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)
    res = run_cv(df, feats, "forward", degree, window,
                 cfg.min_train or MIN_TRAIN)
    truth, pred, base, years = res
    use = pred if art.get("beats_trend") else base
    return {y: (t, p) for y, t, p in zip(years, truth, use)}, art.get("beats_trend")


def correct(base, ndvi):
    years = sorted(y for y in base if y in ndvi)
    rows = []
    for j, y in enumerate(years):
        prior = years[:j]
        if len(prior) < MIN_PRIOR:
            continue
        x = np.array([ndvi[p] for p in prior])
        r = np.array([np.log(base[p][0] / base[p][1]) for p in prior])
        mu, sd = x.mean(), x.std() or 1.0
        z = (x - mu) / sd
        slope = (z * (r - r.mean())).sum() / ((z ** 2).sum() + RIDGE)
        adj = r.mean() + slope * (ndvi[y] - mu) / sd
        t, p = base[y]
        rows.append((y, t, p, p * np.exp(adj)))
    return rows


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def main():
    nd = pd.read_csv(os.path.join(COND, "ndvi_points.csv"), parse_dates=["date"])
    report = {}
    for key in WINDOWS:
        cfg = BY_KEY[key]
        if not os.path.exists(os.path.join(MODELS, f"{key}.json")):
            log(f"{key}: no model, skipped")
            continue
        base, beats = base_forecasts(cfg)
        report[key] = {"base": "model" if beats else "trend"}
        for label, half, col in (("full", False, "ndvi_p75"),
                                 ("half", True, "ndvi_p75"),
                                 ("full_median", False, "ndvi_median"),
                                 ("half_median", True, "ndvi_median")):
            ndvi = season_ndvi(nd, cfg, half, col)
            rows = correct(base, ndvi)
            if len(rows) < 5:
                continue
            ys, t, p, c = map(np.array, zip(*rows))
            r0, r1 = rmse(t, p), rmse(t, c)
            # Correlation of the season's NDVI with the forecast's log error,
            # over every scored season -- descriptive, not used for selection.
            corr = float(np.corrcoef([ndvi[y] for y in ys], np.log(t / p))[0, 1])
            report[key][label] = {
                "n": int(len(ys)), "years": [int(ys[0]), int(ys[-1])],
                "rmse_base": r0, "rmse_ndvi": r1,
                "skill_vs_base": 1 - r1 / r0, "corr_ndvi_error": corr,
            }
            log(f"{key:14} {report[key]['base']:5} {label:12} n={len(ys):2d} "
                f"{int(ys[0])}-{int(ys[-1])}  base={r0:6.0f}  +ndvi={r1:6.0f}  "
                f"skill={1 - r1 / r0:+6.1%}  corr={corr:+.2f}")
    with open(os.path.join(COND, "ndvi_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
