"""
Experiment: does MODIS NDVI improve the US yield model?

The comparison has to be like-for-like. NDVI starts in 2000, so the baseline
is re-measured on the same 2000-2025 window rather than compared against its
34-season score -- otherwise the shorter record would be scored as if it were
NDVI's fault, or its benefit.

NDVI features are built the same way as the weather ones: anomalies against a
trailing climatology, so a long-run greening trend (rising CO2, changing
varieties, land-use shift) is absorbed by the moving baseline instead of being
read as a yield signal.
"""

import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

MODEL_DIR = "/Users/yeoninair/Documents/New for anti/New for anti/scripts/yield_model"
sys.path.insert(0, MODEL_DIR)
os.chdir(MODEL_DIR)

from collect_us_cornbelt import CLIMATOLOGY_YEARS, STATES  # noqa: E402

ALPHAS = np.logspace(-2, 4, 40)
CORE = ["july_edd_anom", "julaug_edd_anom", "julaug_vpd_anom",
        "julaug_precip_anom", "preseason_precip_anom", "julaug_soil_anom",
        "oni_growing"]

NDVI_SETS = {
    "+ NDVI(7-8월 평균)": ["ndvi_julaug_anom"],
    "+ NDVI(최대값)": ["ndvi_peak_anom"],
    "+ NDVI(전체 3개)": ["ndvi_julaug_anom", "ndvi_peak_anom", "ndvi_aug_anom"],
}


def ndvi_year_features():
    """Production-weighted NDVI summaries per year, then anomalised."""
    per_state_raw = {}
    for st in STATES:
        f = f"cache/ndvi_{st['code']}.csv"
        if not os.path.exists(f):
            continue
        d = pd.read_csv(f, parse_dates=["date"])
        d["year"] = d.date.dt.year
        d["month"] = d.date.dt.month
        raw = {}
        for y, g in d.groupby("year"):
            ja = g[g.month.isin([7, 8])]
            au = g[g.month == 8]
            if ja.empty:
                continue
            raw[int(y)] = {
                "ndvi_julaug": ja.ndvi.mean(),
                "ndvi_peak": g.ndvi.max(),
                "ndvi_aug": au.ndvi.mean() if not au.empty else ja.ndvi.mean(),
            }
        per_state_raw[st["code"]] = raw

    # Anomalise per state against its own trailing climatology, then blend.
    blended = {}
    for st in STATES:
        raw = per_state_raw.get(st["code"])
        if not raw:
            continue
        years = sorted(raw)
        for i, y in enumerate(years):
            base = [yy for yy in years[:i] if yy >= y - CLIMATOLOGY_YEARS]
            if len(base) < 5:   # NDVI record is short; accept a smaller normal
                continue
            row = blended.setdefault(y, {"w": 0.0})
            for k in ("ndvi_julaug", "ndvi_peak", "ndvi_aug"):
                hist = [raw[b][k] for b in base]
                mu, sd = np.mean(hist), np.std(hist)
                z = (raw[y][k] - mu) / sd if sd > 0 else 0.0
                row[f"{k}_anom"] = row.get(f"{k}_anom", 0.0) + z * st["weight"]
            row["w"] += st["weight"]

    out = []
    for y, r in blended.items():
        if r["w"] == 0:
            continue
        rec = {k: v / r["w"] for k, v in r.items() if k != "w"}
        rec["year"] = y
        out.append(rec)
    return pd.DataFrame(out).sort_values("year").reset_index(drop=True)


def forward(df, feats, min_train=10):
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    truth, pred, base = [], [], []
    for i, ty in enumerate(years):
        tr = years < ty
        if tr.sum() < min_train:
            continue
        k, b = np.polyfit(years[tr], ys[tr], 1)
        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), ys[tr] - (k * years[tr] + b))
        t = k * ty + b
        truth.append(ys[i]); base.append(t)
        pred.append(t + float(m.predict(sc.transform(X[i:i + 1]))[0]))
    truth, pred, base = map(np.array, (truth, pred, base))
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dt, dp = truth - base, pred - base
    r2 = 1 - np.sum((dt - dp) ** 2) / np.sum((dt - dt.mean()) ** 2)
    return rmse, 1 - rmse / brmse, r2, len(truth)


def run(crop, nd):
    df = pd.read_csv(f"us_{crop}_training.csv")
    merged = df.merge(nd, on="year", how="inner").dropna()
    core = [c for c in CORE if c in merged.columns]

    print(f"=== {crop.upper()} — NDVI 사용 가능 구간 {merged.year.min()}-{merged.year.max()} "
          f"({len(merged)}시즌) ===")

    rmse, skill, r2, n = forward(merged, core)
    print(f"  {'base (동일구간)':22} 검증 {n:2}  RMSE={rmse:6.2f}  skill={skill:+6.1%}  R2={r2:+.3f}")
    best = rmse

    for name, extra in NDVI_SETS.items():
        feats = core + [e for e in extra if e in merged.columns]
        if len(feats) == len(core):
            continue
        rmse2, skill2, r22, n2 = forward(merged, feats)
        mark = "  ← 개선" if rmse2 < best else ""
        print(f"  {name:22} 검증 {n2:2}  RMSE={rmse2:6.2f}  skill={skill2:+6.1%}  R2={r22:+.3f}{mark}")

    # Is NDVI even correlated with what the weather model misses?
    years, ys = merged.year.values, merged["yield"].values
    k, b = np.polyfit(years, ys, 1)
    resid = ys - (k * years + b)
    print("  NDVI 단독 상관 (추세잔차 대비):")
    for c in ("ndvi_julaug_anom", "ndvi_peak_anom", "ndvi_aug_anom"):
        if c in merged.columns:
            print(f"      {c:20} r={np.corrcoef(merged[c], resid)[0, 1]:+.3f}")
    print()


if __name__ == "__main__":
    nd = ndvi_year_features()
    print(f"NDVI 연도별 피처: {len(nd)}년 ({nd.year.min()}-{nd.year.max()})\n")
    for c in ("corn", "soybeans"):
        run(c, nd)
