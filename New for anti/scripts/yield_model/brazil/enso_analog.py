"""
ENSO-conditioned climatology for the weather a Brazilian season has not yet had.

Usage: python3 -m brazil.enso_analog     # backtest -> condition/enso_analog_backtest.json

Same method as argentina/enso_analog.py (copied, not imported, so each
country's model stays in its own folder). Before the critical window opens,
predict.py fills every unobserved feature -- including the growing-season
ONI, which is most of the models' ENSO signal -- from past seasons, evenly.
In November 2026 that meant a strong El Nino (Nino3.4 +2.6 C at sowing) was
being forecast as an average year.

The filled scenarios are weighted by how close each past season's Nino3.4 in
August-September (before the summer harvest year) was to this one's, with a
0.5 C Gaussian kernel. Switched on only where the pre-season backtest beats
the even fill by more than 3% of trend-only RMSE over all folds and over the
last ten. Wheat (sown in autumn) and the perennials (cane, coffee, oranges)
are left out.

That fill only reshuffles the ridge's scenarios, and a ridge that loses to
the trend out of sample is not allowed to move the published number at all
-- so Mato Grosso soy, whose ridge loses (-7.8%), published the plain trend
in a strong El Nino even though the fill had earned its switch.

The direct adjustment below needs no ridge. It shifts the trend by the
Nino3.4-weighted mean of past seasons' departures from it (minus their plain
mean, so it is zero in an average year). Rule set before the first run
(2026-11-23): on for a region only if, in forward chaining against the same
recent-20-year trend, it cuts RMSE by more than 3% over all folds and over
the last ten. Result: Mato Grosso soy +5.1% / +10.1% (on); Parana soy
-0.3% / +0.7% and MATOPIBA soy +1.8% / -2.2% (off). Kernel width 0.35-0.75 C
and a full-record trend keep MT soy between +3.5% and +5.5% over all folds.
MT safrinha corn also clears the bar (+4.5% / +4.4%) but not at the 0.75 C
kernel (+0.6% last ten), so it is not in this backtest yet.
"""

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SST_FILE = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "sst_regions_v1.json"))
OUT = os.path.join(HERE, "condition", "enso_analog_backtest.json")

BANDWIDTH = 0.5
SUMMER_CROPS = {"soja", "milho", "algodao"}
SOWING_MONTHS = (8, 9)          # of the year before the summer harvest year
ON = {"mato_grosso_soja"}   # the only one the backtest below earns (+4.8% all folds, +6.7% last ten)
MIN_GAIN = 0.03
DIRECT_ON = {"mato_grosso_soja"}
DIRECT_TREND_WINDOW = 20
DIRECT_MIN_PAST = 15


def load_nino34(path=SST_FILE):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    region = next(r for r in payload["regions"] if r["id"] == "nino34")
    return {month: float(v) for month, v in region["series"]}


def sowing_nino34(series, harvest_year, crop):
    """Niño3.4 at sowing. Summer crops: Aug-Sep of the year before harvest."""
    if crop not in SUMMER_CROPS:
        return None
    vals = [series.get(f"{harvest_year - 1}-{m:02d}") for m in SOWING_MONTHS]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if len(vals) == len(SOWING_MONTHS) else None


def weights(past, now, bandwidth=BANDWIDTH):
    past = np.asarray(past, dtype=float)
    return np.exp(-0.5 * ((past - now) / bandwidth) ** 2)


def effective_n(w):
    w = np.asarray(w, dtype=float)
    return float(w.sum() ** 2 / (w ** 2).sum()) if w.sum() > 0 else 0.0


def direct_adjust(years, yields, n34, now):
    """Log shift for this season from past seasons' trend departures.

    years/yields/n34 are past seasons only. Returns (log_shift, info) or
    (None, None) when too few seasons carry a sowing Nino3.4.
    """
    from brazil.train import fit_trend

    years = np.asarray(years, dtype=float)
    yields = np.asarray(yields, dtype=float)
    n34 = np.asarray(n34, dtype=float)
    ok = ~np.isnan(n34) & ~np.isnan(yields)
    if now is None or ok.sum() < DIRECT_MIN_PAST:
        return None, None
    years, yields, n34 = years[ok], yields[ok], n34[ok]
    trend = fit_trend(years, yields, 1, DIRECT_TREND_WINDOW)
    res = np.log(yields) - trend(years)
    w = weights(n34, now)
    if w.sum() <= 0:
        return None, None
    shift = float(np.sum(w * res) / w.sum() - res.mean())
    order = np.argsort(-w)[:4]
    info = {
        "nino34_sowing": round(float(now), 2),
        "effective_seasons": round(effective_n(w), 1),
        "analogs": [{"year": int(years[j]), "weight": round(float(w[j] / w.sum()), 3),
                     "departure_pct": round(float((np.exp(res[j]) - 1) * 100), 1)}
                    for j in order],
    }
    return shift, info


def direct_backtest(keys=("mato_grosso_soja", "parana_soja", "matopiba_soja")):
    """Forward chaining: trend alone vs trend + direct ENSO shift, same trend."""
    from brazil.train import fit_trend

    series = load_nino34()
    out = {}
    for key in keys:
        df = pd.read_csv(os.path.join(HERE, "training", f"{key}.csv"))
        df = df.dropna(subset=["yield_kg_ha"])
        crop = key.rsplit("_", 1)[-1]
        df["n34"] = [sowing_nino34(series, int(y), crop) for y in df.year]
        df = df.dropna(subset=["n34"]).reset_index(drop=True)
        y = df.year.values.astype(float)
        Y = df.yield_kg_ha.values.astype(float)
        truth, base, adj, used = [], [], [], []
        for i, t in enumerate(y):
            tr = y < t
            if tr.sum() < DIRECT_MIN_PAST:
                continue
            shift, _ = direct_adjust(y[tr], Y[tr], df.n34.values[tr], df.n34.values[i])
            b = float(np.exp(fit_trend(y[tr], Y[tr], 1, DIRECT_TREND_WINDOW)(t)))
            truth.append(Y[i]); base.append(b); adj.append(b * np.exp(shift)); used.append(int(t))
        truth, base, adj = map(np.array, (truth, base, adj))

        def skill(sl=slice(None)):
            return float(1 - np.sqrt(np.mean((truth[sl] - adj[sl]) ** 2))
                         / np.sqrt(np.mean((truth[sl] - base[sl]) ** 2)))

        s_all, s_recent = skill(), skill(slice(-10, None))
        out[key] = {"seasons_scored": used, "skill_vs_trend": round(s_all, 4),
                    "skill_vs_trend_last10": round(s_recent, 4),
                    "rmse_kg_ha": round(float(np.sqrt(np.mean((truth - adj) ** 2))), 1),
                    "trend_rmse_kg_ha": round(float(np.sqrt(np.mean((truth - base) ** 2))), 1),
                    "earns_switch": bool(s_all > MIN_GAIN and s_recent > MIN_GAIN),
                    "switched_on": key in DIRECT_ON}
    return out


def backtest():
    """
    Pre-season forward chaining: for each target season, refit the trend and
    the ridge on earlier seasons only, then score the forecast made with every
    weather feature unknown -- even fill vs ENSO-weighted fill vs trend.
    """
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    from brazil.train import ALPHAS, fit_trend, prepare, window_rows

    series = load_nino34()
    models_dir = os.path.join(HERE, "models")
    results = {}
    for name in sorted(os.listdir(models_dir)):
        with open(os.path.join(models_dir, name), encoding="utf-8") as f:
            model = json.load(f)
        key, crop = model["key"], model["crop"]
        if crop not in SUMMER_CROPS:
            continue
        feats = model["features"]
        degree, window = model["trend"]["degree"], model["trend"]["window"]
        df = pd.read_csv(os.path.join(HERE, "training", f"{key}.csv"))
        df = df.dropna(subset=["yield_kg_ha"] + feats)
        df["n34"] = [sowing_nino34(series, int(y), crop) for y in df.year]
        df = df.dropna(subset=["n34"]).reset_index(drop=True)
        years = df.year.values.astype(float)
        yields = df.yield_kg_ha.values.astype(float)

        truth, even, analog, used = [], [], [], []
        for i, target in enumerate(years):
            train = years < target
            if train.sum() < 15:
                continue
            trend = fit_trend(years[train], yields[train], degree, window)
            X = prepare(df, feats, years, trend)
            fit = window_rows(years, train, degree, window)
            resid = np.log(yields[fit]) - trend(years[fit])
            scaler = StandardScaler().fit(X[fit])
            ridge = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid)
            scen = ridge.predict(scaler.transform(X[fit]))
            w = weights(df.n34.values[fit], df.n34.values[i])
            truth.append(np.log(yields[i]) - trend(target))
            even.append(scen.mean())
            analog.append(float(np.sum(w * scen) / w.sum()))
            used.append(int(target))

        truth, even, analog = map(np.array, (truth, even, analog))

        def skill(pred, sl=slice(None)):
            base = np.sqrt(np.mean(truth[sl] ** 2))
            return float(1 - np.sqrt(np.mean((truth[sl] - pred[sl]) ** 2)) / base)

        recent = slice(-10, None)
        gain_all = skill(analog) - skill(even)
        gain_recent = skill(analog, recent) - skill(even, recent)
        results[key] = {
            "seasons_scored": used,
            "skill_even_fill": round(skill(even), 4),
            "skill_enso_fill": round(skill(analog), 4),
            "skill_even_fill_last10": round(skill(even, recent), 4),
            "skill_enso_fill_last10": round(skill(analog, recent), 4),
            "earns_switch": bool(gain_all > MIN_GAIN and gain_recent > MIN_GAIN),
            "switched_on": key in ON,
        }
    return results


def main():
    results = backtest()
    direct = direct_backtest()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"bandwidth_c": BANDWIDTH, "sowing_months": SOWING_MONTHS,
                   "min_gain": MIN_GAIN, "regions": results,
                   "direct": {"trend_window": DIRECT_TREND_WINDOW, "regions": direct}},
                  f, ensure_ascii=False, indent=1)
    for key, r in direct.items():
        print(f"direct {key:18} all {r['skill_vs_trend']:+.3f} last10 {r['skill_vs_trend_last10']:+.3f}"
              f"  earns={r['earns_switch']} on={r['switched_on']}")
    for key, r in results.items():
        print(f"{key:15} even {r['skill_even_fill']:+.3f}  enso {r['skill_enso_fill']:+.3f}"
              f"  last10 {r['skill_even_fill_last10']:+.3f} -> {r['skill_enso_fill_last10']:+.3f}"
              f"  earns={r['earns_switch']} on={r['switched_on']}")
    stale = [k for k, r in results.items() if r["earns_switch"] != r["switched_on"]]
    stale += [f"direct {k}" for k, r in direct.items() if r["earns_switch"] != r["switched_on"]]
    if stale:
        raise SystemExit(f"ON set disagrees with the backtest for: {', '.join(stale)}")


if __name__ == "__main__":
    main()
