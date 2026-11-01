"""
MODIS NDVI correction for the Australian state models (and, through
canada/ndvi.py, the Canadian ones) -- the channel Argentina and Brazil use.

Usage: python3 -m australia.ndvi [--full] [--shard K --shards N --out FILE]
       python3 -m australia.ndvi merge FILE [FILE ...]
       python3 -m australia.ndvi backtest

Collection is brazil.ndvi's (ORNL DAAC MOD13Q1, a +-4 km box per site, median
and 75th percentile, only the composites the NDVI window needs, sharded for
the first backfill). The test is argentina.ndvi_backtest's, unchanged: each
region's own forward-chained forecast (the weather model where it is
operational, the trend where it is not) has its log error regressed on the
season's standardised NDVI, using earlier seasons only; a window goes live
only if that beats the forecast by at least 5% with both the p75 and the
median summary. A half window also needs the full window not to make the
forecast worse, because once the window has filled in the half correction
is the one still applied.

The window is fixed here, before any NDVI was read: July-September of the
harvest year, when the winter crop is in stem elongation to grain fill
across the southern belt ("half" is July to mid-August). Sites are the
weather points, except two that sit where a 250 m box would not read crop:
Esperance is on the coast (half the box would be sea) and moves to the
cropping country north of it at Scaddan; Loxton is irrigated Murray
horticulture and moves into the dryland mallee west of the river.

Writes condition/ndvi_points.csv and condition/ndvi_backtest.json.
"""

import argparse
import calendar
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from argentina import ndvi as A
from brazil import ndvi as B

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "condition")
COL = "ndvi_p75"

# ((month, day) start, (month, day) end) within the harvest year.
WINDOW = ((7, 1), (9, 30))

SITES = {
    "Esperance": (-33.44, 121.72),
    "Loxton": (-34.60, 140.30),
}


def log(msg):
    print(f"[ndvi] {msg}", flush=True)


class Country:
    """What differs between the countries that share this module."""

    def __init__(self, package, configs, sites, window):
        self.package = package
        self.configs = configs
        self.site_overrides = sites
        self.window = window
        self.cond = os.path.join(os.path.dirname(HERE), package, "condition")
        self.out = os.path.join(self.cond, "ndvi_points.csv")

    def months(self):
        (m0, _), (m1, _) = self.window
        return frozenset(range(m0, m1 + 1))

    def sites(self):
        out = {}
        for cfg in self.configs:
            for p in cfg.points:
                lat, lon = self.site_overrides.get(p["name"], (p["lat"], p["lon"]))
                out[p["name"]] = (lat, lon, self.months())
        return out


def australia():
    from .regions import ALL
    return Country("australia", ALL, SITES, WINDOW)


# --- collection ------------------------------------------------------------

def collect(country, full=False, shard=0, shards=1, out=None):
    A.BOX_KM = B.A.BOX_KM = 4
    old = pd.DataFrame() if full else B.load(country.out)
    todo = sorted(country.sites().items())[shard::shards]
    log(f"{country.package} shard {shard + 1}/{shards}: {len(todo)} sites")

    def job(item):
        name, (lat, lon, months) = item
        have = set()
        if len(old):
            mine = old[(old.point == name) & (old.lat.round(2) == round(lat, 2))
                       & (old.lon.round(2) == round(lon, 2))]
            have = set(mine.modis_date)
        return B.collect_site(name, lat, lon, months, have)

    with ThreadPoolExecutor(B.WORKERS) as ex:
        new = pd.DataFrame([r for rows in ex.map(job, todo) for r in rows],
                           columns=B.COLUMNS)
    if out:
        new.to_csv(out, index=False)
        log(f"wrote {len(new)} new rows -> {out}")
    else:
        B.save(pd.concat([old, new], ignore_index=True), country.out)


def merge(country, paths):
    parts = [B.load(country.out)] + [pd.read_csv(p, dtype={"modis_date": str}) for p in paths]
    frame = pd.concat([p for p in parts if len(p)] or [pd.DataFrame(columns=B.COLUMNS)],
                      ignore_index=True)
    here = country.sites()
    keep = np.array([r.point in here
                     and round(r.lat, 2) == round(here[r.point][0], 2)
                     and round(r.lon, 2) == round(here[r.point][1], 2)
                     for r in frame.itertuples()], dtype=bool)
    frame = B.save(frame[keep], country.out)
    log(f"merged {len(paths)} shard files -> {len(frame)} rows, {frame.point.nunique()} sites")


# --- backtest --------------------------------------------------------------

def season_ndvi(nd, cfg, window, half=False, col=COL):
    """Point-weighted mean NDVI over the window, per harvest year."""
    (m0, d0), (m1, d1) = window
    w = {p["name"]: p["weight"] for p in cfg.points}
    nd = nd[nd.point.isin(w)].dropna(subset=[col])
    out = {}
    if nd.empty:
        return out
    for y in range(2001, nd.date.dt.year.max() + 1):
        a, b = pd.Timestamp(y, m0, d0), pd.Timestamp(y, m1, d1)
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


def base_forecasts(country, cfg):
    """year -> (truth, the forecast production would have made), forward-chained."""
    import importlib
    train = importlib.import_module(f"{country.package}.train")
    with open(os.path.join(train.MODELS, f"{cfg.key}.json"), encoding="utf-8") as f:
        art = json.load(f)
    frame = pd.read_csv(os.path.join(train.TRAINING, f"{cfg.key}.csv")).sort_values("year")
    all_features = sorted(set().union(*cfg.feature_sets.values()))
    frame = frame.dropna(subset=["yield_kg_ha"] + all_features).reset_index(drop=True)
    run = train.forward_cv(frame, art["selected_features"], cfg.min_train)
    operational = art["operational_choice"] == "ridge_weather"
    use = run["prediction"] if operational else run["baseline"]
    return ({int(y): (float(t), float(p)) for y, t, p in zip(run["years"], run["truth"], use)},
            operational)


def switched_on(entry, win, min_skill):
    """argentina's rule (p75 and median both beat the forecast by min_skill),
    plus: the half-window correction stays on after the window has filled
    in, so it may not run where the whole window made the forecast worse --
    a gain in the first weeks that the rest of the window erases is noise."""
    a, b = entry.get(win), entry.get(f"{win}_median")
    on = bool(a and b and a["skill_vs_base"] >= min_skill
              and b["skill_vs_base"] >= min_skill)
    if win == "half" and entry.get("full", {}).get("skill_vs_base", 0.0) < 0:
        on = False
    return on


def score(country, cfg, nd):
    from argentina.ndvi_backtest import MIN_SKILL, correct, fit, rmse

    base, operational = base_forecasts(country, cfg)
    entry = {"base": "model" if operational else "trend"}
    for label, half, col in (("full", False, "ndvi_p75"), ("half", True, "ndvi_p75"),
                             ("full_median", False, "ndvi_median"),
                             ("half_median", True, "ndvi_median")):
        ndvi = season_ndvi(nd, cfg, country.window, half, col)
        rows = correct(base, ndvi)
        if len(rows) < 5:
            continue
        ys, t, p, c = map(np.array, zip(*rows))
        r0, r1 = rmse(t, p), rmse(t, c)
        corr = float(np.corrcoef([ndvi[y] for y in ys], np.log(t / p))[0, 1])
        entry[label] = {"n": int(len(ys)), "years": [int(ys[0]), int(ys[-1])],
                        "rmse_base": r0, "rmse_ndvi": r1,
                        "skill_vs_base": 1 - r1 / r0, "corr_ndvi_error": corr}
    entry["live"] = {}
    for win, half in (("full", False), ("half", True)):
        on = switched_on(entry, win, MIN_SKILL)
        live = {"enabled": on}
        if on:
            ndvi = season_ndvi(nd, cfg, country.window, half, COL)
            years = sorted(y for y in base if y in ndvi)
            slope, mu, sd = fit(base, ndvi, years)
            live.update({"slope": slope, "mean": mu, "sd": sd,
                         "fit_years": [years[0], years[-1]],
                         "skill_vs_base": entry[win]["skill_vs_base"]})
        entry["live"][win] = live
    entry["sites"] = {}
    for p in cfg.points:
        one = nd[nd.point == p["name"]]
        single = type("one", (), {"points": [{"name": p["name"], "weight": 1.0}]})
        v = season_ndvi(one, single, country.window)
        if v:
            entry["sites"][p["name"]] = {"seasons": len(v),
                                         "mean_p75": round(float(np.mean(list(v.values()))), 3)}
    full = entry.get("full", {})
    log(f"{cfg.key:24} {entry['base']:5} full skill "
        f"{full.get('skill_vs_base', float('nan')):+.1%} corr {full.get('corr_ndvi_error', float('nan')):+.2f}"
        f"  live: {', '.join(w for w, e in entry['live'].items() if e['enabled']) or 'none'}")
    return entry


def backtest(country):
    import importlib
    from argentina.ndvi_backtest import MIN_PRIOR, MIN_SKILL
    train = importlib.import_module(f"{country.package}.train")

    nd = pd.read_csv(country.out, parse_dates=["date"])
    report = {}
    for cfg in country.configs:
        if not os.path.exists(os.path.join(train.MODELS, f"{cfg.key}.json")):
            continue
        report[cfg.key] = score(country, cfg, nd)
    (m0, d0), (m1, d1) = country.window
    report["_rule"] = (f"window {calendar.month_abbr[m0]} {d0}-{calendar.month_abbr[m1]} {d1}; "
                       f"live when the forward correction beats the forecast by "
                       f">= {MIN_SKILL:.0%} with both p75 and median (min {MIN_PRIOR} prior seasons)")
    with open(os.path.join(country.cond, "ndvi_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)


def adjustment(country, cfg, season):
    """The live correction for the season, or None (see brazil.ndvi_blend)."""
    try:
        with open(os.path.join(country.cond, "ndvi_backtest.json")) as f:
            report = json.load(f)
        nd = pd.read_csv(country.out, parse_dates=["date"])
    except (OSError, ValueError):
        return None
    live = report.get(cfg.key, {}).get("live", {})
    for win, half in (("full", False), ("half", True)):
        e = live.get(win)
        if not e or not e.get("enabled"):
            continue
        value = season_ndvi(nd, cfg, country.window, half, COL).get(season)
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


def apply(row, adj):
    """Fold a live correction into a forecast row's point and ranges."""
    if not adj:
        return row
    factor = float(np.exp(adj["log_adjustment"]))
    for key in ("point", "weather_model_point"):
        if isinstance(row.get(key), (int, float)):
            row[key] = row[key] * factor
    for key in ("range_68", "range_95"):
        if isinstance(row.get(key), list):
            row[key] = [v * factor for v in row[key]]
    row["ndvi"] = adj
    return row


def cli(country):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="collect")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    os.makedirs(country.cond, exist_ok=True)
    if args.command == "merge":
        merge(country, args.files)
    elif args.command == "backtest":
        backtest(country)
    else:
        collect(country, args.full, args.shard, args.shards, args.out)


if __name__ == "__main__":
    cli(australia())
