"""
Does MODIS NDVI improve the Vietnamese yield forecasts? Same test as
thailand.ndvi_backtest (and argentina.ndvi_backtest before it).

Usage: python3 -m vietnam.ndvi_backtest

Each region's saved model is run in forward chaining over the full record
(the trend itself where the model does not beat it, as in production), and
the log error of that forecast is corrected with the season's NDVI using only
earlier seasons. Shrinkage, minimum history and the switch-on rule are
argentina.ndvi_backtest's, unchanged. Regions without a model are skipped.

Windows were fixed before looking at results, from the region configs' crop
calendars:

  mekong_rice_ws            Jan-Feb, heading and grain fill of the
                            winter-spring (Dong Xuan) crop harvested Feb-Mar
  central_highlands_coffee  May-Aug, cherry development after the Feb-Apr
                            flowering the config's weather window covers

Writes condition/ndvi_backtest.json.
"""

import json
import os

import numpy as np
import pandas as pd

from argentina.ndvi_backtest import COL, MIN_PRIOR, MIN_SKILL, correct, fit, rmse
from brazil.train import TREND_FORMS, run_cv
from .regions import BY_KEY
from .train import MIN_TRAIN

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "condition")
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

WINDOWS = {
    "mekong_rice_ws":           ((1, 1, 0), (2, 28, 0)),
    "central_highlands_coffee": ((5, 1, 0), (8, 31, 0)),
}


def log(msg):
    print(f"[vn-ndvi-bt] {msg}", flush=True)


def season_ndvi(nd, cfg, half=False, col=COL):
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
        if ww.sum() < 0.6 * sum(w.values()):
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
    _, degree, window = next(t for t in TREND_FORMS if t[0] == art["trend_form"])
    feats = [f for f in art["features"] if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)
    truth, pred, base, years = run_cv(df, feats, "forward", degree, window,
                                      cfg.min_train or MIN_TRAIN)
    use = pred if art.get("beats_trend") else base
    return {y: (t, p) for y, t, p in zip(years, truth, use)}, art.get("beats_trend")


def main():
    nd = pd.read_csv(os.path.join(COND, "ndvi_points.csv"), parse_dates=["date"])
    report = {}
    for key in WINDOWS:
        cfg = BY_KEY[key]
        if not os.path.exists(os.path.join(MODELS, f"{key}.json")):
            log(f"{key}: no model, skipped")
            continue
        base, beats = base_forecasts(cfg)
        entry = {"base": "model" if beats else "trend"}
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
            corr = float(np.corrcoef([ndvi[y] for y in ys], np.log(t / p))[0, 1])
            entry[label] = {"n": int(len(ys)), "years": [int(ys[0]), int(ys[-1])],
                            "rmse_base": r0, "rmse_ndvi": r1,
                            "skill_vs_base": 1 - r1 / r0, "corr_ndvi_error": corr}
            log(f"{key:22} {entry['base']:5} {label:12} n={len(ys):2d} "
                f"{int(ys[0])}-{int(ys[-1])}  base={r0:6.0f}  +ndvi={r1:6.0f}  "
                f"skill={1 - r1 / r0:+6.1%}  corr={corr:+.2f}")
        entry["live"] = {}
        for win, half in (("full", False), ("half", True)):
            a, b = entry.get(win), entry.get(f"{win}_median")
            on = bool(a and b and a["skill_vs_base"] >= MIN_SKILL
                      and b["skill_vs_base"] >= MIN_SKILL)
            live = {"enabled": on}
            if on:
                ndvi = season_ndvi(nd, cfg, half, COL)
                years = sorted(y for y in base if y in ndvi)
                slope, mu, sd = fit(base, ndvi, years)
                live.update({"slope": slope, "mean": mu, "sd": sd,
                             "fit_years": [years[0], years[-1]],
                             "skill_vs_base": a["skill_vs_base"]})
            entry["live"][win] = live
        log(f"{key:22} live windows: "
            f"{', '.join(w for w, e in entry['live'].items() if e['enabled']) or 'none'}")
        report[key] = entry
    report["_rule"] = (f"window live when the forward correction beats the "
                       f"forecast by >= {MIN_SKILL:.0%} with both p75 and median "
                       f"(min {MIN_PRIOR} prior seasons)")
    with open(os.path.join(COND, "ndvi_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
