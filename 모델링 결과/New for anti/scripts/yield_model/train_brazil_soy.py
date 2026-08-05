"""
Train and honestly validate the Brazil soybean yield model.

Structure follows standard crop-forecast practice: yield is split into a
technology trend (seed genetics, fertiliser, mechanisation) plus a weather
deviation from that trend. The model predicts the deviation, never the raw
yield -- a linear trend alone already explains R2=0.90 of the level, so
reporting R2 against raw yield would flatter the model enormously.

Validation is deliberately strict, because with 44 seasons and 24 candidate
features it would be very easy to produce an impressive-looking fit that
forecasts nothing:

  - Leave-one-out CV, with the trend refit inside every fold. Fitting the
    trend once on all years and then cross-validating leaks future
    information into every training set.
  - Forward-chaining (expanding window): train only on years < Y, predict Y.
    This is the honest analogue of forecasting the current season, and it is
    the number to trust.
  - A trend-only baseline. If weather features cannot beat "assume trend",
    they are not earning their place and the script says so.

Outputs brazil_soy_model.json: coefficients, feature list and measured skill.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "brazil_soy_training.csv")
OUT = os.path.join(HERE, "brazil_soy_model.json")

# Ridge penalties searched inside each fold.
ALPHAS = np.logspace(-2, 4, 40)

# Agronomically motivated subset, used as a guard against the full 24-feature
# model simply memorising 44 rows. Pod fill is the water-stress-critical
# window for soybeans; ONI carries the El Nino / La Nina signal.
CORE_FEATURES = [
    "podfill_soil",
    "vegetative_soil",
    "podfill_hotdays",
    "vegetative_hotdays",
    "podfill_wbal",
    "oni_season",
]

DROP = {"year", "yield_kg_ha", "Unit"}


def log(msg):
    print(f"[train] {msg}", flush=True)


def fit_trend(years, yields):
    """Linear technology trend. Returns (slope, intercept)."""
    return np.polyfit(years, yields, 1)


def evaluate(name, y_true, y_pred, baseline_pred):
    """Skill of a prediction against truth and against the trend-only baseline."""
    resid = y_true - y_pred
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    mae = float(np.mean(np.abs(resid)))

    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    base_rmse = float(np.sqrt(np.mean((y_true - baseline_pred) ** 2)))
    skill = 1 - rmse / base_rmse if base_rmse > 0 else float("nan")

    log(f"  {name:22} RMSE={rmse:6.1f}  MAE={mae:6.1f}  R2={r2:+.3f}  "
        f"vs trend-only={skill:+.1%}")
    return {"rmse": rmse, "mae": mae, "r2": r2, "skill_vs_trend": skill,
            "baseline_rmse": base_rmse}


def run_cv(df, features, mode):
    """
    mode='loo'     -> leave-one-out
    mode='forward' -> expanding window, train strictly on earlier years
    """
    years = df.year.values
    yields = df.yield_kg_ha.values
    X_all = df[features].values

    preds, bases, truth, used_years = [], [], [], []

    for i, target_year in enumerate(years):
        if mode == "loo":
            train = np.arange(len(years)) != i
        else:
            train = years < target_year
            # Need enough history for a trend plus a regression.
            if train.sum() < 20:
                continue

        # Trend fit on training years ONLY -- this is the leakage guard.
        slope, intercept = fit_trend(years[train], yields[train])
        trend_train = slope * years[train] + intercept
        trend_target = slope * target_year + intercept

        resid_train = yields[train] - trend_train

        scaler = StandardScaler().fit(X_all[train])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X_all[train]), resid_train)

        pred_resid = float(model.predict(scaler.transform(X_all[i:i + 1]))[0])

        preds.append(trend_target + pred_resid)
        bases.append(trend_target)          # trend-only baseline
        truth.append(yields[i])
        used_years.append(int(target_year))

    return (np.array(truth), np.array(preds), np.array(bases), used_years)


def main():
    df = pd.read_csv(TRAINING).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])

    all_features = [c for c in df.columns if c not in DROP and df[c].notna().all()]
    log(f"{len(df)} seasons ({df.year.min()}-{df.year.max()}), "
        f"{len(all_features)} candidate features")

    slope, intercept = fit_trend(df.year.values, df.yield_kg_ha.values)
    log(f"technology trend: {slope:+.1f} kg/ha per year")
    log("")

    results = {}
    for label, feats in (("all features", all_features), ("core features", CORE_FEATURES)):
        feats = [f for f in feats if f in df.columns]
        log(f"{label} ({len(feats)}):")
        for mode, pretty in (("loo", "leave-one-out"), ("forward", "forward-chaining")):
            truth, pred, base, yrs = run_cv(df, feats, mode)
            key = f"{label.split()[0]}_{mode}"
            results[key] = evaluate(pretty, truth, pred, base)
            results[key]["n"] = len(truth)
            if mode == "forward":
                results[key]["years"] = [yrs[0], yrs[-1]]
        log("")

    # Pick whichever feature set forecasts better under the strict test.
    best_label, best_feats = max(
        (("all", all_features), ("core", CORE_FEATURES)),
        key=lambda kv: results[f"{kv[0]}_forward"]["skill_vs_trend"],
    )
    log(f"selected feature set: {best_label} "
        f"(forward-chaining skill {results[f'{best_label}_forward']['skill_vs_trend']:+.1%})")

    best_feats = [f for f in best_feats if f in df.columns]

    # Final model on every season, for use on the current year.
    scaler = StandardScaler().fit(df[best_feats].values)
    resid = df.yield_kg_ha.values - (slope * df.year.values + intercept)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(df[best_feats].values), resid)

    # Prediction interval from out-of-sample errors, not in-sample ones --
    # in-sample residuals would understate real forecast uncertainty.
    fwd = results[f"{best_label}_forward"]
    sigma = fwd["rmse"]

    artifact = {
        "crop": "soybeans",
        "region": "Brazil (national)",
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "trend": {"slope_kg_ha_per_year": float(slope), "intercept": float(intercept)},
        "features": best_feats,
        "scaler": {
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "ridge": {
            "alpha": float(final.alpha_),
            "coef": final.coef_.tolist(),
            "intercept": float(final.intercept_),
        },
        "uncertainty": {
            "sigma_kg_ha": sigma,
            "interval_68": [-sigma, sigma],
            "interval_95": [-1.96 * sigma, 1.96 * sigma],
            "basis": "out-of-sample forward-chaining RMSE",
        },
        "validation": results,
        "sources": {
            "yield": "FAOSTAT (Production_Crops_Livestock, Brazil, Soya beans, Yield)",
            "weather": "Open-Meteo ERA5 archive, 6 producing states, production-weighted",
            "enso": "NOAA CPC ONI",
        },
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    log("")
    log(f"wrote {OUT}")
    log(f"forecast uncertainty: +/-{sigma:.0f} kg/ha (68%), "
        f"+/-{1.96 * sigma:.0f} kg/ha (95%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
