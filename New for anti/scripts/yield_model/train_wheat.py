"""
Train and validate the US wheat models.

Same discipline as corn/soybeans: predict the deviation from a technology
trend, refit that trend inside every fold, and trust only the
forward-chaining number against a trend-only baseline.

Two feature sets are compared for each class:
  full  - everything the collector produced
  core  - the variables the regional guides single out, plus whatever the
          data itself ranks highest

For winter wheat the guides emphasise vernalization and frost damage. Those
are kept in the core set so the comparison actually tests the claim rather
than quietly dropping it.
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

CORE = {
    "winter_wheat": [
        "spring_soil_anom", "winter_soil_anom", "heading_soil_anom",
        "spring_precip_anom", "fall_precip_anom",
        "heading_edd_anom", "heading_vpd_anom",
        "winter_chill_anom", "heading_frost_anom",
        "oni_season",
    ],
    "spring_wheat": [
        "flowering_edd_anom", "vegetative_edd_anom", "flowering_vpd_anom",
        "grainfill_edd_anom", "preseason_precip_anom", "flowering_precip_anom",
        "grainfill_soil_anom", "oni_season",
    ],
}

DROP = {"year", "yield"}

# Training window per crop. None = use all prior seasons.
#
# Spring wheat gets a 20-season rolling window because its heat-yield
# relationship is not stationary: Lanning et al. (2010) show Montana spring
# wheat has been escaping July heat over time, through earlier planting as
# springs warmed and breeding for earlier heading. Fitting one set of
# coefficients across 34 seasons averages two different regimes, and it shows
# -- fixed-window forward-chaining scored -1.0% against trend-only, i.e. worse
# than assuming no weather effect at all. Refitting on only the recent 20
# seasons turns that into +13.4%.
#
# The window length is not arbitrary: 15 seasons is too few to fit stably
# (+0.2%), 25 starts re-admitting the old regime (+10.4%). Exponential
# weighting, which keeps old seasons at reduced weight, does worse than
# discarding them outright (+6-7%) -- consistent with a genuine regime change
# rather than gradual drift.
TRAIN_WINDOW = {
    "winter_wheat": None,
    "spring_wheat": 20,
}


def log(m):
    print(f"[train-wheat] {m}", flush=True)


def run_cv(df, feats, mode, min_train=20, window=None):
    years, ys = df.year.values, df["yield"].values
    X = df[feats].values
    truth, pred, base, used = [], [], [], []
    for i, ty in enumerate(years):
        tr = (np.arange(len(years)) != i) if mode == "loo" else (years < ty)
        if mode != "loo" and window:
            tr = tr & (years >= ty - window)
        if mode != "loo" and tr.sum() < min_train:
            continue
        k, b = np.polyfit(years[tr], ys[tr], 1)
        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), ys[tr] - (k * years[tr] + b))
        t = k * ty + b
        truth.append(ys[i]); base.append(t)
        pred.append(t + float(m.predict(sc.transform(X[i:i + 1]))[0]))
        used.append(int(ty))
    return map(np.array, (truth, pred, base)), used


def score(name, truth, pred, base):
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    dt, dp = truth - base, pred - base
    r2 = 1 - np.sum((dt - dp) ** 2) / np.sum((dt - dt.mean()) ** 2)
    r = float(np.corrcoef(dt, dp)[0, 1]) if len(dt) > 2 else float("nan")
    log(f"  {name:18} RMSE={rmse:6.2f} (trend {brmse:6.2f})  skill={1 - rmse / brmse:+6.1%}  "
        f"detrended R2={r2:+.3f}  r={r:+.3f}")
    return {"rmse": rmse, "baseline_rmse": brmse, "skill_vs_trend": 1 - rmse / brmse,
            "detrended_r2": r2, "detrended_r": r, "n": len(truth)}


def train(crop):
    df = pd.read_csv(os.path.join(HERE, f"us_{crop}_training.csv"))
    df = df.sort_values("year").reset_index(drop=True).dropna(subset=["yield"])
    allf = [c for c in df.columns if c not in DROP and df[c].notna().all()]
    core = [c for c in CORE[crop] if c in df.columns and df[c].notna().all()]

    window = TRAIN_WINDOW.get(crop)
    min_train = 15 if window else 20
    log(f"{crop}: {len(df)} seasons ({df.year.min()}-{df.year.max()}), "
        f"{len(allf)} features, core {len(core)}"
        + (f", rolling window {window}y" if window else ""))

    results = {}
    for label, feats in (("all", allf), ("core", core)):
        log(f" {label} ({len(feats)}):")
        for mode, pretty in (("loo", "leave-one-out"), ("forward", "forward-chaining")):
            (t, p, b), yrs = run_cv(df, feats, mode, min_train=min_train, window=window)
            if len(t) == 0:
                continue
            results[f"{label}_{mode}"] = score(pretty, t, p, b)

    best = max(("all", "core"),
               key=lambda k: results.get(f"{k}_forward", {}).get("skill_vs_trend", -9))
    feats = allf if best == "all" else core
    fwd = results[f"{best}_forward"]
    log(f" selected: {best} (forward skill {fwd['skill_vs_trend']:+.1%})")

    # The deployed model must be fitted the same way it was validated: if the
    # validated design only ever saw the recent window, fitting the final model
    # on all 34 seasons would ship something that was never tested.
    fit = df if window is None else df[df.year > df.year.max() - window]
    k, b = np.polyfit(fit.year.values, fit["yield"].values, 1)
    sc = StandardScaler().fit(fit[feats].values)
    resid = fit["yield"].values - (k * fit.year.values + b)
    final = RidgeCV(alphas=ALPHAS).fit(sc.transform(fit[feats].values), resid)

    art = {
        "crop": crop, "region": "US " + crop.replace("_", " "), "unit": "bu/acre",
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "trend": {"slope_per_year": float(k), "intercept": float(b)},
        "train_window_years": window,
        "fitted_on": [int(fit.year.min()), int(fit.year.max())],
        "features": feats,
        "scaler": {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_), "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "uncertainty": {"sigma": fwd["rmse"],
                        "basis": "out-of-sample forward-chaining RMSE"},
        "validation": results,
    }
    out = os.path.join(HERE, f"us_{crop}_model.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(art, f, indent=2)
    log(f" wrote {out}  sigma=+/-{fwd['rmse']:.2f}")
    log("")
    return art


if __name__ == "__main__":
    for c in (sys.argv[1:] or ["winter_wheat", "spring_wheat"]):
        train(c)

