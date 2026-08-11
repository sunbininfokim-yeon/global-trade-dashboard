"""
Experiment: does crop phenology improve the US yield model?

Three additions are tested against the current feature set, all on the same
34 seasons so nothing is lost to a shorter record:

  P1  planting-delay anomaly   -- how late 50% planting ran vs that state's
                                  own normal. Thompson ties wet springs to
                                  delayed planting and lower yield.
  P2  silking-aligned windows  -- heat/VPD/rain/soil measured over 50% silking
                                  +/- 14 days instead of fixed July. Silking
                                  dates move +/- 6-8 days between years, so a
                                  fixed month samples a different growth stage
                                  depending on the season.
  P3  both

Scored the same way as everything else: forward-chaining, trend refit inside
each fold, error on the production-weighted aggregate.
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

MODEL_DIR = "/Users/yeoninair/Documents/New for anti/New for anti/scripts/yield_model"
sys.path.insert(0, MODEL_DIR)
os.chdir(MODEL_DIR)

from collect_us_cornbelt import (  # noqa: E402
    CLIMATOLOGY_YEARS, CROPS, END_YEAR, START_YEAR, STATES,
    growing_season_oni, load_oni, nass_yields, power_weather,
    season_features, to_anomalies,
)
from phenology import stage_dates  # noqa: E402

ALPHAS = np.logspace(-2, 4, 40)

BASE = ["july_edd_anom", "julaug_edd_anom", "julaug_vpd_anom",
        "julaug_precip_anom", "preseason_precip_anom", "julaug_soil_anom",
        "oni_growing"]

PLANT = ["plant_delay_anom"]
SILK = ["silk_edd_anom", "silk_vpd_anom", "silk_precip_anom", "silk_soil_anom"]


def silk_window_features(wx, year, centre_doy, spec, half=14):
    """Weather over the pollination window, dated from NASS progress."""
    start = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=centre_doy - half - 1)
    end = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=centre_doy + half - 1)
    w = wx[(wx.date >= start) & (wx.date <= end)]
    if w.empty or w.tmax.isna().all():
        return None
    return {
        "silk_edd": (w.tmax - spec["edd_threshold"]).clip(lower=0).sum(),
        "silk_vpd": w.vpd.mean(),
        "silk_precip": w.precip.sum(),
        "silk_soil": w.soil.mean(),
    }


def build(crop):
    spec = CROPS[crop]
    oni = load_oni()
    rows = []

    for st in STATES:
        wx = power_weather(st)
        dates = stage_dates(crop, st)
        ys = nass_yields(crop, st).set_index("year")["yield"].to_dict()

        raw_cal, raw_silk, plant_doy = {}, {}, {}
        for y in range(START_YEAR, END_YEAR + 1):
            f = season_features(wx, y, spec)
            if f:
                raw_cal[y] = f
            rec = dates.get(y, {})
            centre = rec.get("critical_doy")
            if centre is None or pd.isna(centre):
                p = rec.get("planted_doy")
                centre = (p + 90) if p is not None and not pd.isna(p) else None
            if centre is not None and not pd.isna(centre):
                s = silk_window_features(wx, y, centre, spec)
                if s:
                    raw_silk[y] = s
            if not pd.isna(rec.get("planted_doy", np.nan)):
                plant_doy[y] = rec["planted_doy"]

        anom_cal = to_anomalies(raw_cal)
        anom_silk = to_anomalies(raw_silk)

        for y, a in anom_cal.items():
            if y not in ys:
                continue
            r = {k: v for k, v in a.items() if k != "year"}
            r.update(anom_silk.get(y, {}))
            r.pop("year", None)

            # Planting delay vs that state's own trailing normal.
            hist = [plant_doy[yy] for yy in plant_doy
                    if y - CLIMATOLOGY_YEARS <= yy < y]
            if y in plant_doy and len(hist) >= 10:
                mu, sd = np.mean(hist), np.std(hist)
                r["plant_delay_anom"] = (plant_doy[y] - mu) / sd if sd > 0 else 0.0

            r.update({"year": y, "state": st["code"], "weight": st["weight"],
                      "yield": ys[y], "oni_growing": growing_season_oni(oni, y)})
            rows.append(r)

    return pd.DataFrame(rows)


def aggregate(panel, feats):
    """Collapse the state panel to one production-weighted row per year."""
    keep = panel.dropna(subset=feats + ["yield"])
    out = []
    for y, d in keep.groupby("year"):
        row = {f: np.average(d[f], weights=d.weight) for f in feats}
        row["year"] = y
        row["yield"] = np.average(d["yield"], weights=d.weight)
        out.append(row)
    return pd.DataFrame(out).sort_values("year").reset_index(drop=True)


def evaluate(df, feats, min_train=20):
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    truth, pred, base = [], [], []
    for i, ty in enumerate(years):
        tr = years < ty
        if tr.sum() < min_train:
            continue
        k, b = np.polyfit(years[tr], ys[tr], 1)
        resid = ys[tr] - (k * years[tr] + b)
        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), resid)
        t = k * ty + b
        truth.append(ys[i]); base.append(t)
        pred.append(t + float(m.predict(sc.transform(X[i:i + 1]))[0]))

    truth, pred, base = map(np.array, (truth, pred, base))
    rmse = np.sqrt(np.mean((truth - pred) ** 2))
    brmse = np.sqrt(np.mean((truth - base) ** 2))
    dt, dp = truth - base, pred - base
    r2 = 1 - np.sum((dt - dp) ** 2) / np.sum((dt - dt.mean()) ** 2)
    return rmse, 1 - rmse / brmse, r2, len(truth)


def run(crop):
    panel = build(crop)
    print(f"=== {crop.upper()} ===")

    variants = {
        "base (현재)": BASE,
        "+ 파종지연": BASE + PLANT,
        "+ 수분기창": BASE + SILK,
        "+ 둘다": BASE + PLANT + SILK,
    }

    for name, feats in variants.items():
        feats = [f for f in feats if f in panel.columns]
        agg = aggregate(panel, feats)
        if len(agg) < 25:
            print(f"  {name:14} 표본 부족 ({len(agg)})")
            continue
        rmse, skill, r2, n = evaluate(agg, feats)
        print(f"  {name:14} n={len(agg)} 시즌, 검증 {n}  "
              f"RMSE={rmse:6.2f}  skill={skill:+6.1%}  detrended R2={r2:+.3f}")
    print()


if __name__ == "__main__":
    for c in ("corn", "soybeans"):
        run(c)
