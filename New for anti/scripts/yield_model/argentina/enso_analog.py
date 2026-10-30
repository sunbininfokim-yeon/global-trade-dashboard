"""
ENSO-conditioned climatology for the weather a season has not yet had.

Usage: python3 -m argentina.enso_analog     # backtest -> condition/enso_analog_backtest.json

Before the critical window opens, predict.py fills every unobserved feature
from past seasons, one scenario per season, and averages them. Averaged
evenly that is the climatology, so the pre-season number collapses onto the
trend -- even in a year like 2026, when Niño3.4 is already near +2.6 °C at
sowing and the record says Pampas summer crops do well in El Niño years
(+9% soy, +9% maize against trend on average; 1997/98 and 2015/16 both
finished well above).

So the scenarios are weighted by how close each past season's Niño3.4 at
sowing was to this one's, with a Gaussian kernel of 0.5 °C (one ONI class
width, fixed before the backtest was run). The weather itself still comes
from real past seasons through the model's own coefficients; only which
seasons count as "likely this year" changes. As the window fills, observed
features replace the filled ones and the weighting stops mattering.

Niño3.4 is read from public/data/sst_regions_v1.json (OISST v2.1, refreshed
weekly by sst_refresh.yml) rather than CPC's ONI: at the late-October
publication the ONI for the sowing months is not out yet, and the backtest
and the live run must read the same series. August-September is used
because it is the latest pair reliably published by then.

Switched on only where the pre-season backtest beat the even climatology by
more than 3% of trend-only RMSE, both over all folds and over the last ten:
Pampas soy and Pampas maize. Chaco cotton, northern soy and wheat lose
slightly and stay on the even fill.
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
SOWING_MONTHS = (8, 9)          # of the year before the summer harvest year
ON = {"pampas_soja", "pampas_maiz"}
MIN_GAIN = 0.03


def load_nino34(path=SST_FILE):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    region = next(r for r in payload["regions"] if r["id"] == "nino34")
    return {month: float(v) for month, v in region["series"]}


def sowing_nino34(series, harvest_year, crop):
    """Niño3.4 at sowing. Summer crops: Aug-Sep of the year before harvest."""
    if crop == "trigo":
        return None             # not switched on; wheat is sown in May-June
    vals = [series.get(f"{harvest_year - 1}-{m:02d}") for m in SOWING_MONTHS]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if len(vals) == len(SOWING_MONTHS) else None


def weights(past, now, bandwidth=BANDWIDTH):
    past = np.asarray(past, dtype=float)
    return np.exp(-0.5 * ((past - now) / bandwidth) ** 2)


def effective_n(w):
    w = np.asarray(w, dtype=float)
    return float(w.sum() ** 2 / (w ** 2).sum()) if w.sum() > 0 else 0.0


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
        if crop == "trigo":
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
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"bandwidth_c": BANDWIDTH, "sowing_months": SOWING_MONTHS,
                   "min_gain": MIN_GAIN, "regions": results},
                  f, ensure_ascii=False, indent=1)
    for key, r in results.items():
        print(f"{key:15} even {r['skill_even_fill']:+.3f}  enso {r['skill_enso_fill']:+.3f}"
              f"  last10 {r['skill_even_fill_last10']:+.3f} -> {r['skill_enso_fill_last10']:+.3f}"
              f"  earns={r['earns_switch']} on={r['switched_on']}")
    stale = [k for k, r in results.items() if r["earns_switch"] != r["switched_on"]]
    if stale:
        raise SystemExit(f"ON set disagrees with the backtest for: {', '.join(stale)}")


if __name__ == "__main__":
    main()
