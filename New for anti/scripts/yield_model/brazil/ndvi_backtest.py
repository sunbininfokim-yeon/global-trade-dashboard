"""
Does MODIS NDVI improve the Brazilian yield forecasts? Same test as
argentina.ndvi_backtest, on the Brazilian models.

Usage: python3 -m brazil.ndvi_backtest

Each region's saved model is run in forward chaining over the full record
(the trend itself where the model does not beat it, as in production), and
the log error of that forecast is corrected with the season's NDVI using only
earlier seasons. Shrinkage, minimum history and the switch-on rule are
argentina.ndvi_backtest's, unchanged: a window goes live only when the
correction beats the forecast by at least 5% with both the 75th-percentile and
the median pixel summary.

Windows are not chosen here. Each is the first unbroken run of months in the
region's own critical_window (regions.py), fixed before any NDVI was looked
at; the first run, because two of them (cotton, coffee) also list harvest or
flowering months later in the season, where the canopy says little about
yield:

  mato_grosso_soja   Nov-Feb     parana_trigo      Aug-Nov
  mato_grosso_milho  Mar-Jun     matopiba_soja     Dec-Feb
  parana_soja        Dec-Feb     matopiba_algodao  Feb-Apr
  parana_milho       Nov-Jan     sp_cana           Oct-Mar
  sp_cafe            Sep-Oct     sp_laranja        Sep-Feb

"half" is the first half of that window, what a live forecast has seen by
mid-season.

Writes condition/ndvi_backtest.json, including each site's mean window
greenness, so a sampling site that missed the fields can be spotted.
"""

import calendar
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "condition")
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")
COL = "ndvi_p75"


def log(msg):
    print(f"[br-ndvi-bt] {msg}", flush=True)


def first_block(critical_window):
    """First unbroken run of (month, year_offset) entries."""
    block = [critical_window[0]]
    for m, o in critical_window[1:]:
        pm, po = block[-1]
        if (o * 12 + m) - (po * 12 + pm) != 1:
            break
        block.append((m, o))
    return block


def window(cfg):
    """((month, day, year_offset) start, (...) end) relative to the harvest year."""
    block = first_block(cfg.critical_window)
    (m0, o0), (m1, o1) = block[0], block[-1]
    return (m0, 1, o0), (m1, calendar.monthrange(2001, m1)[1], o1)


def window_months(cfg):
    return {m for m, _ in first_block(cfg.critical_window)}


def season_ndvi(nd, cfg, half=False, col=COL):
    """Production-weighted mean NDVI over the window, per harvest year."""
    (m0, d0, o0), (m1, d1, o1) = window(cfg)
    w = {p["name"]: p["weight"] for p in cfg.points}
    nd = nd[nd.point.isin(w)].dropna(subset=[col])
    out = {}
    if nd.empty:
        return out
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
    from .train import MIN_TRAIN, TREND_FORMS, run_cv

    art = json.load(open(os.path.join(MODELS, f"{cfg.key}.json")))
    df = (pd.read_csv(os.path.join(TRAINING, f"{cfg.key}.csv"))
            .sort_values("year").dropna(subset=["yield_kg_ha"])
            .reset_index(drop=True))
    if cfg.regime_start:
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
    _, degree, win = next(t for t in TREND_FORMS if t[0] == art["trend_form"])
    feats = [f for f in art["features"] if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)
    truth, pred, base, years = run_cv(df, feats, "forward", degree, win,
                                      cfg.min_train or MIN_TRAIN)
    use = pred if art.get("beats_trend") else base
    return {int(y): (t, p) for y, t, p in zip(years, truth, use)}, art.get("beats_trend")


def site_greenness(nd, cfg):
    """Per site: mean window NDVI (p75 and median) and seasons seen."""
    out = {}
    for p in cfg.points:
        one = nd[nd.point == p["name"]]
        p75 = season_ndvi(one, _single(cfg, p["name"]), col="ndvi_p75")
        med = season_ndvi(one, _single(cfg, p["name"]), col="ndvi_median")
        if p75:
            out[p["name"]] = {"seasons": len(p75),
                              "mean_p75": round(float(np.mean(list(p75.values()))), 3),
                              "mean_median": round(float(np.mean(list(med.values()))), 3),
                              "sd_p75": round(float(np.std(list(p75.values()))), 3)}
    return out


class _single:
    """A region config narrowed to one site, for per-site window means."""

    def __init__(self, cfg, name):
        self.critical_window = cfg.critical_window
        self.points = [{"name": name, "weight": 1.0}]


def score(cfg, nd):
    from argentina.ndvi_backtest import MIN_SKILL, correct, fit, rmse

    base, beats = base_forecasts(cfg)
    (m0, _, o0), (m1, _, o1) = window(cfg)
    entry = {"base": "model" if beats else "trend",
             "window": f"{calendar.month_abbr[m0]}({o0:+d})-{calendar.month_abbr[m1]}({o1:+d})"}
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
        log(f"{cfg.key:18} {entry['base']:5} {label:12} n={len(ys):2d} "
            f"{int(ys[0])}-{int(ys[-1])}  base={r0:7.0f}  +ndvi={r1:7.0f}  "
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
    entry["sites"] = site_greenness(nd, cfg)
    log(f"{cfg.key:18} live windows: "
        f"{', '.join(w for w, e in entry['live'].items() if e['enabled']) or 'none'}")
    return entry


def main():
    from argentina.ndvi_backtest import MIN_PRIOR, MIN_SKILL
    from .regions import ALL

    nd = pd.read_csv(os.path.join(COND, "ndvi_points.csv"), parse_dates=["date"])
    report = {}
    for cfg in ALL:
        if not os.path.exists(os.path.join(MODELS, f"{cfg.key}.json")):
            log(f"{cfg.key}: no model, skipped")
            continue
        report[cfg.key] = score(cfg, nd)
    report["_rule"] = (f"window live when the forward correction beats the "
                       f"forecast by >= {MIN_SKILL:.0%} with both p75 and median "
                       f"(min {MIN_PRIOR} prior seasons)")
    with open(os.path.join(COND, "ndvi_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
