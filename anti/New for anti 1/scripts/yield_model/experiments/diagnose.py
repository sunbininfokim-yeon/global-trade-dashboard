"""
Diagnose where the remaining error comes from: too little data, the wrong
model, or the genuine ceiling of what weather can explain.

Three tests:

  1. Learning curve. Train on the most recent N seasons and forecast forward.
     If skill is still climbing with N, more history would help. If it has
     flattened, extra seasons buy nothing.

  2. In-sample vs out-of-sample gap. A wide gap means the model is fitting
     noise -- too many parameters for the sample. A narrow gap with poor
     absolute skill means the signal simply is not there.

  3. Residual structure. If what is left correlates with anything, or with
     itself year to year, there is signal still on the table. If it looks
     like white noise, the model has taken what weather has to give.
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

ALPHAS = np.logspace(-2, 4, 40)
CORE = ["july_edd_anom", "julaug_edd_anom", "julaug_vpd_anom",
        "julaug_precip_anom", "preseason_precip_anom", "julaug_soil_anom",
        "oni_growing"]


def load(crop):
    df = pd.read_csv(f"us_{crop}_training.csv").sort_values("year").reset_index(drop=True)
    feats = [c for c in CORE if c in df.columns and df[c].notna().all()]
    return df.dropna(subset=["yield"]), feats


def forward(df, feats, min_train, window=None):
    """Forward-chaining; `window` caps how many past seasons are used."""
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    truth, pred, base = [], [], []
    for i, ty in enumerate(years):
        mask = years < ty
        if window:
            mask &= years >= ty - window
        if mask.sum() < min_train:
            continue
        k, b = np.polyfit(years[mask], ys[mask], 1)
        sc = StandardScaler().fit(X[mask])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[mask]), ys[mask] - (k * years[mask] + b))
        t = k * ty + b
        truth.append(ys[i]); base.append(t)
        pred.append(t + float(m.predict(sc.transform(X[i:i + 1]))[0]))
    return map(np.array, (truth, pred, base))


def metrics(truth, pred, base):
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dt, dp = truth - base, pred - base
    r2 = 1 - np.sum((dt - dp) ** 2) / np.sum((dt - dt.mean()) ** 2)
    return rmse, 1 - rmse / brmse, r2


def run(crop):
    df, feats = load(crop)
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    print(f"=== {crop.upper()}  ({len(df)} seasons, {len(feats)} features) ===")

    # ---- 1. learning curve -------------------------------------------------
    print("  [1] 학습곡선 — 학습에 쓰는 과거 시즌 수를 늘리면 좋아지는가")
    for w in (12, 16, 20, 24, None):
        try:
            t, p, b = forward(df, feats, min_train=min(w or 20, 20), window=w)
            if len(t) < 8:
                continue
            rmse, skill, r2 = metrics(t, p, b)
            label = f"최근 {w}년" if w else "전체 과거"
            print(f"      {label:9} 검증 {len(t):2}회  RMSE={rmse:6.2f}  skill={skill:+6.1%}")
        except Exception as e:  # noqa: BLE001
            print(f"      {w}: {e}")

    # ---- 2. in-sample vs out-of-sample ------------------------------------
    k, b = np.polyfit(years, ys, 1)
    resid = ys - (k * years + b)
    sc = StandardScaler().fit(X)
    m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X), resid)
    in_rmse = float(np.sqrt(np.mean((resid - m.predict(sc.transform(X))) ** 2)))

    t, p, b2 = forward(df, feats, min_train=20)
    out_rmse, skill, r2 = metrics(t, p, b2)
    sd = float(np.std(resid))

    print("  [2] 과적합 진단")
    print(f"      추세잔차 표준편차          {sd:6.2f}")
    print(f"      인샘플 RMSE               {in_rmse:6.2f}  (설명률 {1 - (in_rmse / sd) ** 2:+.1%})")
    print(f"      아웃샘플 RMSE             {out_rmse:6.2f}  (설명률 {r2:+.1%})")
    gap = out_rmse / in_rmse
    print(f"      격차 배율                 {gap:6.2f}x  "
          f"{'← 과적합 신호' if gap > 1.6 else '← 과적합 아님'}")

    # ---- 3. residual structure --------------------------------------------
    err = np.array(t) - np.array(p)
    print("  [3] 남은 오차에 구조가 있는가")
    if len(err) > 3:
        ac = float(np.corrcoef(err[:-1], err[1:])[0, 1])
        print(f"      연도간 자기상관            {ac:+.3f}  "
              f"{'← 구조 남음' if abs(ac) > 0.4 else '← 백색잡음에 가까움'}")
    # does the leftover still track any candidate feature?
    test_years = [int(y) for y in years if y >= years[20]][:len(err)]
    sub = df[df.year.isin(test_years)]
    worst = []
    for c in df.columns:
        if c in ("year", "yield") or not df[c].notna().all():
            continue
        if len(sub) == len(err):
            r = float(np.corrcoef(sub[c].values, err)[0, 1])
            worst.append((abs(r), c, r))
    worst.sort(reverse=True)
    for a, c, r in worst[:3]:
        flag = "← 미포착 신호" if a > 0.5 else ""
        print(f"      잔차 vs {c:24} r={r:+.3f} {flag}")
    print()


if __name__ == "__main__":
    for c in ("corn", "soybeans"):
        run(c)
