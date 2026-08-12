"""
Train and honestly validate every India region-crop model.

Usage: python3 -m india.train [region_key ...]

The target is log(yield). Indian yields have not merely drifted -- Punjab wheat
roughly trebled between the early Green Revolution and today, and Madhya
Pradesh soybean went from a crop that barely existed to five million hectares.
A weather shock is multiplicative against that: the same 10% drought costs a
few hundred kg/ha now and a fraction of that in 1985. Fitting absolute
residuals would make the model chase recent seasons and treat three decades of
earlier ones as quiet.

So the technology trend is fitted on log(yield), the model predicts the log
deviation, and the forecast is exponentiated back. Which trend form to use is
chosen by the same forward-chaining test that chooses the feature set, refit
inside every fold, rather than assumed.

Validation:
  - Forward chaining (train on years < Y, predict Y) with the trend refit
    inside every fold. This is the only number that answers "would this have
    helped me forecast?", and it selects the feature set.
  - Leave-one-out as a secondary read on stability.
  - A trend-only baseline throughout. Where the weather features cannot beat
    "assume the trend", the model says so and the artifact records it.

That last point is not a formality. These three guides are well argued, but a
sound methodology at field scale does not have to survive at regional annual
resolution with thirty-odd rows, and if it does not, the honest output is a
negative result rather than a tuned one.

Writes models/<region_key>.json and prints a comparison table.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

ALPHAS = np.logspace(-2, 4, 40)

DROP = {"year", "yield_kg_ha"}

# Minimum training years before forward chaining will make a call. Lower than
# the Brazilian package's 22 because NASA POWER's radiation record starts in
# 1984 and the ICRISAT yield series ends well before the present, so the
# labelled span here is roughly a decade shorter than Brazil's.
MIN_TRAIN = 18

# Features that are not weather. None of the three India configs currently
# carries one -- there is no biennial crop in this set -- but the machinery is
# kept so that any future lag feature is reported separately rather than
# credited to the climate signal.
NON_WEATHER_FEATURES = {"lag1", "lag2"}

# Folds counted when choosing between trend forms and feature sets. Scoring on
# the whole forward-chaining history keeps rewarding a trend that fitted the
# 1990s and has since drifted off the crop's actual level.
RECENT_FOLDS = 8


def log(msg):
    print(f"[train] {msg}", flush=True)


# Trend forms tried for every config, as (label, polynomial degree, window).
# A window of None fits the whole record.
#
# The trailing-window forms matter here for a specific Indian reason: Punjab
# wheat yield growth flattened sharply once the canal-and-fertiliser package
# was fully deployed, so a log-linear fit over the whole record extrapolates a
# finished boom and runs high on recent seasons. Selection below is on absolute
# error rather than relative skill, because a biased trend inflates a model and
# its own baseline by the same amount and relative skill hides it completely.
TREND_FORMS = [("deg1", 1, None), ("deg2", 2, None),
               ("recent20", 1, 20), ("recent10", 1, 10)]


def fit_trend(years, yields, degree, window=None):
    """
    Technology trend in log space. Returns a poly1d over the year.

    With a window, only the most recent `window` years of the data handed in
    are used -- inside a fold that means the most recent years of the training
    set, never anything at or beyond the target.
    """
    if window:
        mask = years >= years.max() - window + 1
        if mask.sum() >= max(degree + 2, 8):
            years, yields = years[mask], yields[mask]
    return np.poly1d(np.polyfit(years, np.log(yields), degree))


def prepare(df, features, years, trend):
    """
    Feature matrix, with any lag feature expressed as a log deviation from
    trend rather than as a raw yield.

    A raw lagged yield carries the technology level, which the trend already
    explains; feeding it in raw would have the model rediscover the trend
    through the back door and inflate its apparent skill.
    """
    X = df[features].astype(float).copy()
    for f, lag in (("lag1", 1), ("lag2", 2)):
        if f in features:
            prior = X[f].clip(lower=1.0)
            X[f] = np.log(prior) - trend(years - lag)
    return X.values


def evaluate(y_true, y_pred, baseline):
    resid = y_true - y_pred
    recent = slice(-min(RECENT_FOLDS, len(y_true)), None)
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    mae = float(np.mean(np.abs(resid)))

    base_rmse = float(np.sqrt(np.mean((y_true - baseline) ** 2)))
    skill = 1 - rmse / base_rmse if base_rmse > 0 else float("nan")

    # R2 on the detrended target, which is what the model actually predicts.
    # Against raw yield this would be ~0.9 for every config here purely from
    # the trend, and would mean nothing.
    dev_true = y_true - baseline
    dev_pred = y_pred - baseline
    ss_res = float(np.sum((dev_true - dev_pred) ** 2))
    ss_tot = float(np.sum((dev_true - np.mean(dev_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    recent_rmse = float(np.sqrt(np.mean(resid[recent] ** 2)))
    recent_base = float(np.sqrt(np.mean((y_true[recent] - baseline[recent]) ** 2)))
    # Signed, so a trend sitting permanently above the crop shows as bias
    # rather than averaging away against its own scatter.
    trend_bias = float(np.mean(baseline[recent] - y_true[recent]))

    return {"rmse": rmse, "mae": mae, "detrended_r2": r2,
            "skill_vs_trend": skill, "baseline_rmse": base_rmse,
            "recent_rmse": recent_rmse, "recent_baseline_rmse": recent_base,
            "recent_trend_bias": trend_bias}


def run_cv(df, features, mode, degree, window, min_train):
    years = df.year.values.astype(float)
    yields = df.yield_kg_ha.values.astype(float)

    preds, bases, truth, used = [], [], [], []

    for i, target in enumerate(years):
        if mode == "loo":
            train = np.arange(len(years)) != i
        else:
            train = years < target
            if train.sum() < min_train:
                continue

        # Refit inside the fold: fitting the trend once on all years and then
        # cross-validating leaks the future into every training set.
        trend = fit_trend(years[train], yields[train], degree, window)
        X = prepare(df, features, years, trend)

        resid_train = np.log(yields[train]) - trend(years[train])

        scaler = StandardScaler().fit(X[train])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[train]), resid_train)
        pred = float(model.predict(scaler.transform(X[i:i + 1]))[0])

        preds.append(float(np.exp(trend(target) + pred)))
        bases.append(float(np.exp(trend(target))))
        truth.append(yields[i])
        used.append(int(target))

    if not truth:
        return None
    return (np.array(truth), np.array(preds), np.array(bases), used)


def train_one(cfg):
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])

    # Drop seasons from before a structural break in the farming system. A
    # break is not a level shift to be detrended through: the crop, its inputs
    # and its weather sensitivities all change, so the earlier era contributes
    # distorted coefficients rather than extra evidence.
    if cfg.regime_start:
        before = len(df)
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
        log(f"{cfg.key}: regime restriction from {cfg.regime_start} "
            f"({before} -> {len(df)} seasons)")

    min_train = cfg.min_train or MIN_TRAIN

    # Trim leading seasons that cannot support the guide's own variables,
    # rather than discarding the variables.
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 5:
            df = df[keep].reset_index(drop=True)
            log(f"{cfg.key}: trimmed {trimmed} leading season(s) so the core "
                f"features survive")

    # Past that, a feature is usable only if present in every remaining
    # season. Imputing a missing monsoon onset would invent weather.
    candidates = [c for c in df.columns
                  if c not in DROP and df[c].notna().all() and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} usable seasons "
            f"(need {min_train + 5}), skipped")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} usable features ({len(core)} core)")

    dropped = [c for c in cfg.core if c not in candidates]
    if dropped:
        log(f"  core features unusable (missing or constant): "
            f"{', '.join(dropped)}")

    results = {}
    sets = [("all", candidates)]
    if core:
        sets.append(("core", core))

    for label, feats in sets:
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv(df, feats, mode, degree, window, min_train)
                if out is None:
                    continue
                truth, pred, base, yrs = out
                key = f"{label}_{tlabel}_{mode}"
                results[key] = evaluate(truth, pred, base)
                results[key]["n"] = len(truth)
                results[key]["years"] = [yrs[0], yrs[-1]]
                results[key]["features"] = feats
                results[key]["degree"] = degree
                results[key]["window"] = window
                results[key]["trend_form"] = tlabel

    fwd = {k: v for k, v in results.items() if k.endswith("_forward")}
    if not fwd:
        log("  no forward-chaining fold had enough history\n")
        return None

    # Best available model against best available baseline, chosen
    # independently. Scoring a model against its own trend rewards picking a
    # bad trend and then correcting it; pinning the model to the best
    # baseline's trend throws away the better forecaster.
    best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
    best_baseline = min(v["baseline_rmse"] for v in fwd.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in fwd.values())
    baseline_form = min(fwd.values(),
                        key=lambda v: v["baseline_rmse"])["trend_form"]
    log(f"  best trend-only baseline: {baseline_form}, RMSE "
        f"{best_baseline:.0f} (the bar the weather features have to clear)")

    best = results[best_key]
    best_feats = best["features"]
    degree, window = best["degree"], best["window"]

    n_folds = best["n"]
    if n_folds < RECENT_FOLDS:
        log(f"  WARNING: only {n_folds} forward-chaining folds. Any skill "
            "figure below rests on too few unseen seasons to be relied on.")

    for k in sorted(results):
        r = results[k]
        mark = " <-" if k == best_key else ""
        log(f"    {k:26} n={r['n']:3d}  RMSE={r['rmse']:7.1f}  "
            f"recent={r['recent_rmse']:7.1f}  "
            f"trend bias={r['recent_trend_bias']:+7.0f}  "
            f"vs trend={r['skill_vs_trend']:+7.1%}{mark}")

    trend = fit_trend(df.year.values, df.yield_kg_ha.values, degree, window)

    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    full_skill = (1 - best["rmse"] / best_baseline
                  if best_baseline > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    # Isolate the weather contribution where non-weather features are present.
    nw_feats = [f for f in best_feats if f in NON_WEATHER_FEATURES]
    weather_skill, nw_rmse = recent_skill, None
    if nw_feats:
        nw = run_cv(df, nw_feats, "forward", degree, window, min_train)
        if nw is not None:
            nw_eval = evaluate(nw[0], nw[1], nw[2])
            nw_rmse = min(nw_eval["recent_rmse"], best_baseline_recent)
            weather_skill = (1 - best["recent_rmse"] / nw_rmse
                             if nw_rmse > 0 else float("nan"))
            log(f"  vs trend+lags baseline (weather's own contribution): "
                f"{weather_skill:+.1%}")

    log(f"  trend form {best['trend_form']}, recent bias "
        f"{best['recent_trend_bias']:+.0f} kg/ha over the last "
        f"{RECENT_FOLDS} seasons")
    bias_pct = (best["recent_trend_bias"]
                / float(df.yield_kg_ha.tail(10).mean()) * 100)
    if abs(bias_pct) > 3:
        log(f"  WARNING: even the best trend form runs {bias_pct:+.1f}% off "
            "recent yield; treat the level with caution.")

    if not beats_trend:
        log("  VERDICT: does not beat a trend-only baseline out of sample.")
        if cfg.non_weather_drivers:
            log("  NOT A WEATHER PROBLEM: "
                + cfg.non_weather_drivers.split(".")[0] + ".")
    else:
        log(f"  VERDICT: beats the best trend baseline by {full_skill:.1%} "
            f"over all folds, {recent_skill:.1%} over the last "
            f"{RECENT_FOLDS} ({best_key.split('_')[0]} features).")

    # Final fit on every season, for forecasting the live one.
    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    scaler = StandardScaler().fit(X)
    resid = np.log(df.yield_kg_ha.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)

    # Uncertainty from out-of-sample error, never in-sample. Where the model
    # loses to the trend, the honest band is the trend's own error.
    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    # Coefficients are log-space effects of a one-standard-deviation move;
    # exp() - 1 turns them into the percentage yield change, which is the form
    # the guides state their thresholds in.
    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in ranked))
    log("")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "crop": cfg.crop,
        "selector": [[s, d] for s, d in cfg.selector],
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "n_forward_folds": int(n_folds),
        "regime_start": cfg.regime_start or None,
        # log(yield) = poly(year); coefficients highest-power first, as numpy
        # returns them. The forecast exponentiates poly(year) + weather term.
        "trend": {"log_poly_coef": [float(c) for c in trend.coefficients],
                  "degree": int(degree),
                  "form": best["trend_form"],
                  "window": window,
                  "space": "log(kg/ha)"},
        "features": best_feats,
        "feature_set": best_key.split("_")[0],
        "trend_form": best["trend_form"],
        "scaler": {"mean": scaler.mean_.tolist(),
                   "scale": scaler.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_),
                  "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "beats_trend": bool(beats_trend),
        "recent_skill_vs_trend": float(recent_skill),
        "skill_vs_best_trend": float(full_skill),
        "best_trend_baseline_rmse": float(best_baseline),
        "weather_skill": float(weather_skill),
        "non_weather_features": nw_feats,
        "trend_plus_lags_rmse": nw_rmse,
        "recent_trend_bias_kg_ha": float(best["recent_trend_bias"]),
        "recent_folds": RECENT_FOLDS,
        "uncertainty": {
            "sigma_kg_ha": float(sigma),
            "basis": (f"out-of-sample RMSE over the last {RECENT_FOLDS} "
                      "forward-chaining folds" if beats_trend else
                      f"trend-only baseline RMSE over the last {RECENT_FOLDS} "
                      "folds (model showed no skill)"),
        },
        "validation": {k: {kk: vv for kk, vv in v.items() if kk != "features"}
                       for k, v in results.items()},
        "forward": {kk: vv for kk, vv in best.items() if kk != "features"},
    }

    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, f"{cfg.key}.json"), "w",
              encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    return artifact


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL

    built = [a for a in (train_one(c) for c in configs) if a]

    log("=" * 82)
    log(f"{'region-crop':22} {'seasons':>7} {'folds':>6} {'vs trend':>10} "
        f"{'weather only':>13} {'sigma':>8}  verdict")
    log("-" * 82)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        wonly = a["weather_skill"]
        tag = "usable" if a["beats_trend"] else "no skill - use trend"
        if a["non_weather_features"] and wonly <= 0:
            tag = "skill is non-weather (" + ",".join(
                a["non_weather_features"]) + ")"
        if a["n_forward_folds"] < RECENT_FOLDS:
            tag += f" [only {a['n_forward_folds']} folds]"
        log(f"{a['key']:22} {a['n_seasons']:7d} {a['n_forward_folds']:6d} "
            f"{a['recent_skill_vs_trend']:+9.1%} {wonly:+12.1%} "
            f"{a['uncertainty']['sigma_kg_ha']:8.0f}  {tag}")
    log("=" * 82)
    return 0


if __name__ == "__main__":
    sys.exit(main())
