"""
El Nino analog shift for Indian regions whose weather model loses to the trend.

Usage: python3 -m india.enso_direct      # backtest -> enso_direct_backtest.json

Same method as brazil/enso_analog.py's direct shift (copied, not imported, so
each country's model stays in its own folder): the published trend moves by
the Nino3.4-weighted mean of past seasons' departures from that trend, minus
their plain mean, so an average year moves nothing.

Rule set before the first run (2026-11-27): the Nino3.4 window comes from the
crop calendar (kharif: Jun-Aug of the season; rabi wheat: Oct-Nov before
sowing), the kernel is 0.5 C, the trend is the one the region publishes, and a
region is switched on only if forward chaining cuts RMSE by more than 3% over
all folds and over the last ten, and stays positive at 0.35 and 0.75 C.

Result (14 Asian regions tested the same day, India, Thailand, Vietnam,
Indonesia): only eastern kharif rice passes among regions whose model loses
to the trend -- +6.8% / +6.8% (0.35 C +5.3/+4.0, 0.75 C +4.9/+5.1).
MP soybean, Vidarbha cotton and Punjab wheat fail and stay on trend.
"""

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SST_FILE = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "sst_regions_v1.json"))
OUT = os.path.join(HERE, "enso_direct_backtest.json")

BANDWIDTH = 0.5
CHECK_BANDWIDTHS = (0.35, 0.75)
MIN_GAIN = 0.03
MIN_PAST = 15
# key -> (Nino3.4 months, year offset from the season year)
WINDOWS = {"east_rice": ((6, 7, 8), 0), "mp_soybean": ((6, 7, 8), 0),
           "vidarbha_cotton": ((6, 7, 8), 0), "punjab_wheat": ((10, 11), -1)}
ON = {"east_rice"}


def load_nino34(path=SST_FILE):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    region = next(r for r in payload["regions"] if r["id"] == "nino34")
    return {month: float(v) for month, v in region["series"]}


def nino34_for(series, key, year):
    months, off = WINDOWS[key]
    vals = [series.get(f"{year + off}-{m:02d}") for m in months]
    return float(np.mean(vals)) if all(v is not None for v in vals) else None


def model_trend(key):
    with open(os.path.join(HERE, "models", f"{key}.json"), encoding="utf-8") as f:
        t = json.load(f)["trend"]
    return t["degree"], t.get("window")


def _trend(years, yields, degree, window):
    if window:
        m = years >= years.max() - window + 1
        if m.sum() >= max(degree + 2, 8):
            years, yields = years[m], yields[m]
    return np.poly1d(np.polyfit(years, np.log(yields), degree))


def weights(past, now, bandwidth=BANDWIDTH):
    return np.exp(-0.5 * ((np.asarray(past, dtype=float) - now) / bandwidth) ** 2)


def shift(years, yields, n34, now, degree, window, bandwidth=BANDWIDTH):
    """(log shift, info) from past seasons, or (None, None)."""
    years, yields, n34 = (np.asarray(a, dtype=float) for a in (years, yields, n34))
    ok = ~np.isnan(n34) & ~np.isnan(yields)
    if now is None or ok.sum() < MIN_PAST:
        return None, None
    years, yields, n34 = years[ok], yields[ok], n34[ok]
    res = np.log(yields) - _trend(years, yields, degree, window)(years)
    w = weights(n34, now, bandwidth)
    if w.sum() <= 0:
        return None, None
    s = float(np.sum(w * res) / w.sum() - res.mean())
    order = np.argsort(-w)[:4]
    return s, {
        "nino34_sowing": round(float(now), 2),
        "effective_seasons": round(float(w.sum() ** 2 / (w ** 2).sum()), 1),
        "beyond_record": bool(now > n34.max() + 0.5 or now < n34.min() - 0.5),
        "analogs": [{"year": int(years[j]), "weight": round(float(w[j] / w.sum()), 3),
                     "departure_pct": round(float((np.exp(res[j]) - 1) * 100), 1)}
                    for j in order]}


def _table(key, series):
    df = pd.read_csv(os.path.join(HERE, "training", f"{key}.csv"))
    df = df[["year", "yield_kg_ha"]].dropna()
    df = df[df.yield_kg_ha > 0].copy()
    df["n34"] = [nino34_for(series, key, int(y)) for y in df.year]
    return df.dropna().reset_index(drop=True)


def backtest():
    series = load_nino34()
    out = {}
    for key in WINDOWS:
        df = _table(key, series)
        degree, window = model_trend(key)
        y, Y, n = df.year.values.astype(float), df.yield_kg_ha.values.astype(float), df.n34.values
        scores = {}
        for bw in (BANDWIDTH,) + CHECK_BANDWIDTHS:
            truth, base, adj = [], [], []
            for i, t in enumerate(y):
                tr = y < t
                if tr.sum() < MIN_PAST:
                    continue
                s, _ = shift(y[tr], Y[tr], n[tr], n[i], degree, window, bw)
                b = float(np.exp(_trend(y[tr], Y[tr], degree, window)(t)))
                truth.append(Y[i]); base.append(b); adj.append(b * np.exp(s))
            truth, base, adj = map(np.array, (truth, base, adj))

            def sk(sl=slice(None)):
                return float(1 - np.sqrt(np.mean((truth[sl] - adj[sl]) ** 2))
                             / np.sqrt(np.mean((truth[sl] - base[sl]) ** 2)))
            scores[bw] = (round(sk(), 4), round(sk(slice(-10, None)), 4), len(truth))
        main = scores[BANDWIDTH]
        earns = (main[0] > MIN_GAIN and main[1] > MIN_GAIN
                 and all(scores[b][0] > 0 and scores[b][1] > 0 for b in CHECK_BANDWIDTHS))
        out[key] = {"seasons_scored": main[2], "skill_vs_trend": main[0],
                    "skill_vs_trend_last10": main[1],
                    "kernel_checks": {str(b): scores[b][:2] for b in CHECK_BANDWIDTHS},
                    "earns_switch": bool(earns), "switched_on": key in ON}
    return out


def direct_fill(key, year, history):
    """Shift for this season where switched on, or None."""
    if key not in ON:
        return None
    try:
        series = load_nino34()
    except (OSError, ValueError, StopIteration):
        return None
    past = history[["year", "yield_kg_ha"]].dropna()
    past = past[(past.year < year) & (past.yield_kg_ha > 0)]
    n34 = np.array([nino34_for(series, key, int(y)) or np.nan for y in past.year], dtype=float)
    s, info = shift(past.year.values, past.yield_kg_ha.values, n34,
                    nino34_for(series, key, year), *model_trend(key))
    if s is None:
        return None
    bt = {}
    try:
        with open(OUT, encoding="utf-8") as f:
            bt = json.load(f).get(key, {})
    except (OSError, ValueError):
        pass
    months, off = WINDOWS[key]
    return {"log": s, "shift_pct": round(float((np.exp(s) - 1) * 100), 2),
            "window": [f"{year + off}-{m:02d}" for m in months],
            "backtest_skill": bt.get("skill_vs_trend"),
            "backtest_skill_last10": bt.get("skill_vs_trend_last10"), **info}


def main():
    results = backtest()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
        f.write("\n")
    for k, r in results.items():
        print(f"{k:16} all {r['skill_vs_trend']:+.3f} last10 {r['skill_vs_trend_last10']:+.3f} "
              f"checks {r['kernel_checks']} earns={r['earns_switch']} on={r['switched_on']}")
    stale = [k for k, r in results.items() if r["earns_switch"] != r["switched_on"]]
    if stale:
        raise SystemExit(f"ON set disagrees with the backtest for: {', '.join(stale)}")


if __name__ == "__main__":
    main()
