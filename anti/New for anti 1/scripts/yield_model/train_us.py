"""
Train and validate the US Corn Belt yield model.

Usage: python3 train_us.py [corn|soybeans ...]

Same discipline as the Brazil pilot: yield = technology trend + weather
deviation, the model only ever predicts the deviation, and every skill number
is measured out of sample.

  - The trend is refit inside each CV fold. Fitting it once over all years and
    then cross-validating leaks the future into every training set.
  - Forward-chaining (train on years < Y, predict Y) is the number to trust;
    it is the honest analogue of forecasting a season in progress.
  - A trend-only baseline is always reported. If weather cannot beat "assume
    trend", it has earned nothing and the script says so.

Features are anomalies against a trailing climatology, built in
collect_us_cornbelt.py. The CORE set is the subset the literature points to:
July and July-August heat (extreme degree days), vapour pressure deficit, and
Thompson's pre-season moisture recharge.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
ALPHAS = np.logspace(-2, 4, 40)

CORE = [
    "july_edd_anom",
    "julaug_edd_anom",
    "julaug_vpd_anom",
    "julaug_precip_anom",
    "preseason_precip_anom",
    "julaug_soil_anom",
    "oni_growing",
]

DROP = {"year", "yield"}


def log(msg):
    print(f"[train-us] {msg}", flush=True)


def fit_trend(years, y):
    return np.polyfit(years, y, 1)


def run_cv(df, features, mode, min_train=20):
    years = df.year.values
    yields = df["yield"].values
    X = df[features].values

    truth, pred, base, used = [], [], [], []
    for i, ty in enumerate(years):
        if mode == "loo":
            tr = np.arange(len(years)) != i
        else:
            tr = years < ty
            if tr.sum() < min_train:
                continue

        slope, intercept = fit_trend(years[tr], yields[tr])
        resid_tr = yields[tr] - (slope * years[tr] + intercept)
        trend_t = slope * ty + intercept

        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), resid_tr)
        r = float(m.predict(sc.transform(X[i:i + 1]))[0])

        truth.append(yields[i])
        pred.append(trend_t + r)
        base.append(trend_t)
        used.append(int(ty))

    return np.array(truth), np.array(pred), np.array(base), used


def score(name, truth, pred, base):
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    skill = 1 - rmse / brmse if brmse else float("nan")

    # Skill on the detrended series is the number comparable to the published
    # "weather explains X% of yield variability" figures; R2 against raw yield
    # would mostly be measuring the trend.
    dt_t, dt_p = truth - base, pred - base
    ss_res = float(np.sum((dt_t - dt_p) ** 2))
    ss_tot = float(np.sum((dt_t - dt_t.mean()) ** 2))
    r2_dt = 1 - ss_res / ss_tot if ss_tot else float("nan")
    r = float(np.corrcoef(dt_t, dt_p)[0, 1]) if len(dt_t) > 2 else float("nan")

    log(f"  {name:18} RMSE={rmse:6.2f} (trend {brmse:6.2f})  skill={skill:+6.1%}  "
        f"detrended R2={r2_dt:+.3f}  r={r:+.3f}")
    return {"rmse": rmse, "baseline_rmse": brmse, "skill_vs_trend": skill,
            "detrended_r2": r2_dt, "detrended_r": r, "n": len(truth)}


def train(crop):
    path = os.path.join(HERE, f"us_{crop}_training.csv")
    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield"])

    allf = [c for c in df.columns if c not in DROP and df[c].notna().all()]
    core = [c for c in CORE if c in df.columns and df[c].notna().all()]

    log(f"{crop}: {len(df)} seasons ({df.year.min()}-{df.year.max()}), "
        f"{len(allf)} features, core {len(core)}")

    results = {}
    for label, feats in (("all", allf), ("core", core)):
        log(f" {label} ({len(feats)}):")
        for mode, pretty in (("loo", "leave-one-out"), ("forward", "forward-chaining")):
            t, p, b, yrs = run_cv(df, feats, mode)
            if len(t) == 0:
                continue
            results[f"{label}_{mode}"] = score(pretty, t, p, b)
            if mode == "forward":
                results[f"{label}_{mode}"]["years"] = [yrs[0], yrs[-1]]

    best = max(("all", "core"),
               key=lambda k: results.get(f"{k}_forward", {}).get("skill_vs_trend", -9))
    feats = allf if best == "all" else core
    fwd = results[f"{best}_forward"]
    log(f" selected: {best} (forward skill {fwd['skill_vs_trend']:+.1%})")

    slope, intercept = fit_trend(df.year.values, df["yield"].values)
    sc = StandardScaler().fit(df[feats].values)
    resid = df["yield"].values - (slope * df.year.values + intercept)
    final = RidgeCV(alphas=ALPHAS).fit(sc.transform(df[feats].values), resid)

    artifact = {
        "crop": crop,
        "region": "US Corn Belt (8 states, production-weighted)",
        "unit": "bu/acre",
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "trend": {"slope_per_year": float(slope), "intercept": float(intercept)},
        "features": feats,
        "scaler": {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_), "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "uncertainty": {"sigma": fwd["rmse"], "basis": "out-of-sample forward-chaining RMSE"},
        "validation": results,
        "methodology": {
            "trend": "Thompson (1969, 1986) via FAO review: regression on time absorbs "
                     "technology (genetics, management, fertiliser); weather is related to "
                     "deviations from that trend.",
            "heat": "Schlenker & Roberts (2009): nonlinear damage, entered as extreme "
                    "degree days above the crop threshold rather than counts of hot days.",
            "vpd": "Urban et al. (2015), Roberts et al. (2012), Lobell et al. (2014): "
                   "vapour pressure deficit as a combined heat/dryness predictor.",
            "anomalies": "All weather features are anomalies against a trailing 20-year "
                         "climatology, so multi-decade climate drift is not read as a "
                         "yield signal.",
        },
        "sources": {"yield": "USDA NASS Quick Stats (state, SURVEY, annual)",
                    "weather": "NASA POWER daily, 1981-",
                    "enso": "NOAA CPC ONI"},
    }

    out = os.path.join(HERE, f"us_{crop}_model.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    log(f" wrote {out}  sigma=+/-{fwd['rmse']:.2f} bu/acre")
    log("")
    return artifact


def main():
    for crop in (sys.argv[1:] or ["corn", "soybeans"]):
        train(crop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
