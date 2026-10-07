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
collect_us_cornbelt.py. Both candidate sets are month-separable: every feature
belongs to one calendar month (or to the pre-season), so the in-season engine
can take the months that have happened as observed and fill the rest from
each past year in turn (see us_scenarios.py). The CORE set is the subset the
literature points to -- monthly heat (extreme degree days), vapour pressure
deficit, rain and soil moisture, plus Thompson's pre-season recharge. ALL adds
monthly mean temperature and June soil moisture.

The growing-season ONI is no longer a feature. It is not known until the
season is over, so it cannot enter a forecast made in June, and dropping it
did not lower forward skill for either crop (model-eval, 2026-10-07).
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from us_scenarios import CUTOFFS, FORECAST_SKILL, MONTHS, feature_month

HERE = os.path.dirname(os.path.abspath(__file__))
ALPHAS = np.logspace(-2, 4, 40)

CORE = (["preseason_precip_anom"]
        + [f"june_{v}_anom" for v in ("edd", "precip", "vpd")]
        + [f"{m}_{v}_anom" for m in ("july", "august")
           for v in ("edd", "precip", "vpd", "soil")])

ALL = (["preseason_precip_anom"]
       + [f"{m}_{v}_anom" for m in MONTHS
          for v in ("edd", "precip", "vpd", "soil", "tmean")])


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


def inseason_backtest(df, features, min_train=20):
    """Skill of the scenario engine at fixed dates in the season.

    Forward-chaining as in run_cv. For each test year the months not yet
    known at the cutoff are replaced, one past year at a time, by that past
    year's values; the mean of those predictions is the forecast. Coverage
    checks whether the truth falls inside the 68% / 90% bands built the way
    predict_us.py builds them (scenario spread plus model error).
    """
    from us_scenarios import mixture_quantiles

    years = df.year.values
    yields = df["yield"].values
    X = df[features].astype(float).values
    month_of = np.array([feature_month(f) for f in features])

    rows = {label: {"pred": [], "in68": [], "in90": []} for label, _ in CUTOFFS}
    truth, base = [], []
    for i, ty in enumerate(years):
        tr = years < ty
        if tr.sum() < min_train:
            continue
        slope, intercept = fit_trend(years[tr], yields[tr])
        resid_tr = yields[tr] - (slope * years[tr] + intercept)
        trend_t = slope * ty + intercept
        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), resid_tr)
        # Training-fold error, inflated: the in-sample residual understates
        # out-of-sample error and there are too few years for an inner CV.
        sigma = float(np.std(resid_tr - m.predict(sc.transform(X[tr])))) * 1.25

        truth.append(yields[i])
        base.append(trend_t)
        for label, known in CUTOFFS:
            unknown = ~np.isin(month_of, known)
            Xs = np.repeat(X[i:i + 1], tr.sum(), axis=0)
            Xs[:, unknown] = X[tr][:, unknown]
            preds = trend_t + m.predict(sc.transform(Xs))
            q05, q16, q84, q95 = mixture_quantiles(preds, sigma, (0.05, 0.16, 0.84, 0.95))
            rows[label]["pred"].append(float(preds.mean()))
            rows[label]["in68"].append(q16 <= yields[i] <= q84)
            rows[label]["in90"].append(q05 <= yields[i] <= q95)

    truth, base = np.array(truth), np.array(base)
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    out = {}
    for label, _ in CUTOFFS:
        r = rows[label]
        rmse = float(np.sqrt(np.mean((truth - np.array(r["pred"])) ** 2)))
        skill = 1 - rmse / brmse
        out[label] = {"skill_vs_trend": skill, "rmse": rmse,
                      "coverage_68": float(np.mean(r["in68"])),
                      "coverage_90": float(np.mean(r["in90"]))}
        log(f"  in-season {label}: skill={skill:+6.1%}  RMSE={rmse:6.2f}  "
            f"68%-cover={out[label]['coverage_68']:.2f}  90%-cover={out[label]['coverage_90']:.2f}")
    return {
        "method": "forward-chaining; months after the cutoff filled from every "
                  "earlier year in turn, mean of scenarios scored against trend-only",
        "forecast_skill_threshold": FORECAST_SKILL,
        "n_test": int(len(truth)),
        "cutoffs": out,
    }


def train(crop):
    path = os.path.join(HERE, f"us_{crop}_training.csv")
    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield"])

    allf = [c for c in ALL if c in df.columns and df[c].notna().all()]
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

    inseason = inseason_backtest(df, feats)

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
        "selected": best,
        "features": feats,
        "feature_months": {f: feature_month(f) for f in feats},
        "scaler": {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_), "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "uncertainty": {"sigma": fwd["rmse"], "basis": "out-of-sample forward-chaining RMSE"},
        "validation": results,
        "inseason": inseason,
        "methodology": {
            "trend": "Thompson (1969, 1986) via FAO review: regression on time absorbs "
                     "technology (genetics, management, fertiliser); weather is related to "
                     "deviations from that trend.",
            "heat": "Schlenker & Roberts (2009): nonlinear damage, entered as extreme "
                    "degree days above the crop threshold rather than counts of hot days.",
            "vpd": "Urban et al. (2015), Roberts et al. (2012), Lobell et al. (2014): "
                   "vapour pressure deficit as a combined heat/dryness predictor.",
            "inseason": "UNL Yield Forecasting Center approach (Hybrid-Maize on "
                        "historical weather): observed weather to date, a short-range "
                        "forecast, then each past year's weather for the rest of the "
                        "season; the spread of outcomes is the forecast range.",
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
