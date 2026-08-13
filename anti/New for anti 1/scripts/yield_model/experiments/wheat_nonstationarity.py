"""
Two experiments on the wheat models.

A) Spring wheat and non-stationarity.
   Lanning et al. (2010) found Montana spring wheat has been escaping July
   heat over time -- earlier planting as springs warmed, plus breeding for
   earlier heading. If the heat-yield relationship itself has been weakening,
   a model with fixed coefficients fitted across 34 seasons is estimating an
   average of two different regimes, which is a good explanation for strong
   single correlations paired with a forward-chaining collapse.

   A full time-varying-parameter model (state space / Kalman) is not viable
   at n=34. The practical equivalents are:
     - rolling window: refit on only the most recent N seasons
     - exponential weighting: keep all seasons but downweight old ones
   Both let the coefficients drift. Tested here against the fixed-window model.

B) Winter wheat and wind.
   Kansas State work frames the damaging event as "hot, dry and windy".
   VPD already carries hot-and-dry, so wind may be a third component or may
   be redundant. Given that NDVI, silking windows and planting dates were all
   rejected today for exactly that redundancy, this is tested, not assumed.
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.preprocessing import StandardScaler

MODEL_DIR = "/Users/yeoninair/Documents/New for anti/New for anti/scripts/yield_model"
sys.path.insert(0, MODEL_DIR)
os.chdir(MODEL_DIR)

ALPHAS = np.logspace(-2, 4, 40)

CORE = {
    "winter_wheat": ["spring_soil_anom", "winter_soil_anom", "heading_soil_anom",
                     "spring_precip_anom", "fall_precip_anom", "heading_edd_anom",
                     "heading_vpd_anom", "winter_chill_anom", "heading_frost_anom",
                     "oni_season"],
    "spring_wheat": ["flowering_edd_anom", "vegetative_edd_anom", "flowering_vpd_anom",
                     "grainfill_edd_anom", "preseason_precip_anom",
                     "flowering_precip_anom", "grainfill_soil_anom", "oni_season"],
}


def evaluate(df, feats, window=None, halflife=None, min_train=15):
    """
    Forward-chaining. `window` restricts training to the last N seasons;
    `halflife` instead keeps everything with exponentially decaying weights.
    Either one lets the fitted relationship move over time.
    """
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    truth, pred, base = [], [], []

    for i, ty in enumerate(years):
        mask = years < ty
        if window:
            mask = mask & (years >= ty - window)
        if mask.sum() < min_train:
            continue

        yr_tr, y_tr, X_tr = years[mask], ys[mask], X[mask]

        if halflife:
            w = 0.5 ** ((ty - yr_tr) / halflife)
        else:
            w = np.ones(len(yr_tr))

        # Trend fitted with the same weights, so the technology baseline also
        # tracks the recent record rather than the whole history.
        k, b = np.polyfit(yr_tr, y_tr, 1, w=np.sqrt(w))
        resid = y_tr - (k * yr_tr + b)

        sc = StandardScaler().fit(X_tr)
        Z = sc.transform(X_tr)
        if halflife:
            # RidgeCV has no sample_weight in cross-validation, so pick alpha
            # unweighted then refit weighted.
            alpha = RidgeCV(alphas=ALPHAS).fit(Z, resid).alpha_
            m = Ridge(alpha=alpha).fit(Z, resid, sample_weight=w)
        else:
            m = RidgeCV(alphas=ALPHAS).fit(Z, resid)

        t = k * ty + b
        truth.append(ys[i]); base.append(t)
        pred.append(t + float(m.predict(sc.transform(X[i:i + 1]))[0]))

    truth, pred, base = map(np.array, (truth, pred, base))
    if len(truth) < 5:
        return None
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dt, dp = truth - base, pred - base
    r2 = 1 - np.sum((dt - dp) ** 2) / np.sum((dt - dt.mean()) ** 2)
    return rmse, 1 - rmse / brmse, r2, len(truth)


def show(label, res):
    if res is None:
        print(f"  {label:26} 표본 부족")
        return None
    rmse, skill, r2, n = res
    print(f"  {label:26} 검증 {n:2}  RMSE={rmse:6.2f}  skill={skill:+6.1%}  R2={r2:+.3f}")
    return rmse


def experiment_a():
    print("=== A. 봄밀 — 비정상성 대응 ===")
    df = pd.read_csv("us_spring_wheat_training.csv").sort_values("year").reset_index(drop=True)
    feats = [c for c in CORE["spring_wheat"] if c in df.columns and df[c].notna().all()]

    show("고정 (전체 과거)", evaluate(df, feats))
    print("  -- 이동창 (최근 N년만 학습) --")
    for w in (15, 20, 25):
        show(f"최근 {w}년", evaluate(df, feats, window=w))
    print("  -- 지수가중 (반감기 N년) --")
    for h in (5, 8, 12):
        show(f"반감기 {h}년", evaluate(df, feats, halflife=h))
    print()


def experiment_b():
    print("=== B. 겨울밀 — 풍속이 새 정보인가 ===")
    df = pd.read_csv("us_winter_wheat_training.csv").sort_values("year").reset_index(drop=True)
    feats = [c for c in CORE["winter_wheat"] if c in df.columns and df[c].notna().all()]

    base_rmse = show("base (풍속 없음)", evaluate(df, feats, min_train=20))

    wind = [c for c in df.columns if "wind" in c and df[c].notna().all()]
    if not wind:
        print("  풍속 변수 없음 — 수집 필요 (NASA POWER WS2M)")
        print()
        return

    show("+ 풍속", evaluate(df, feats + wind, min_train=20))

    # Is wind even independent of what VPD already measures?
    print("  풍속과 기존 변수의 상관:")
    for w in wind:
        for c in ("heading_vpd_anom", "heading_edd_anom", "spring_soil_anom"):
            if c in df.columns:
                print(f"    {w} vs {c:22} r={df[w].corr(df[c]):+.3f}")
    print()


if __name__ == "__main__":
    experiment_a()
    experiment_b()
