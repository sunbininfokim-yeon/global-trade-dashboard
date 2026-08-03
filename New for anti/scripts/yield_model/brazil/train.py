"""
Train and honestly validate every region-crop model.

Usage: python3 -m brazil.train [region_key ...]

Same strictness as the US Corn Belt model, but the target is built the way the
guides specify rather than the way the US model does it.

The US model detrends linearly on absolute bushels. That is wrong here.
Brazilian state yields have roughly quadrupled since 1977, and 마투그로수/대두
§3A writes its panel regression on log(Y) while 남부지방/대두 §3A asks for a
quadratic trend and a *relative* anomaly, (Y - Y_hat)/Y_hat. Both are pointing
at the same thing: the weather shock is multiplicative. A 10% drought cost
~100 kg/ha in 1980 and ~370 kg/ha today, so fitting absolute residuals makes
the model chase recent seasons and dismiss forty years of earlier ones as
quiet.

So: the trend is fitted on log(yield), the model predicts the log deviation,
and the forecast is exponentiated back. Trend degree (linear vs quadratic) is
chosen by the same forward-chaining test that chooses the feature set, refit
inside every fold, rather than assumed.

Validation:
  - Forward chaining (train on years < Y, predict Y) with the trend refit
    inside every fold. This is the only number that answers "would this have
    helped me forecast?", and it is what selects the feature set.
  - Leave-one-out as a secondary read on stability.
  - A trend-only baseline throughout. Where the weather features cannot beat
    "assume the trend", the model says so and the report records it. Several
    of these nine are expected to fail that test, and a guide's methodology
    being sound does not guarantee it survives at state-level annual
    resolution with ~45 rows.

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

# Minimum training years before forward chaining will make a call.
MIN_TRAIN = 22

# Features that are not weather. They are legitimate predictors -- coffee's
# biennial cycle and a cane plantation's ratoon age are real and forecastable
# -- but crediting them to a climate model would overstate what the weather
# explains, so skill is reported against a trend+lags baseline as well as
# against trend alone.
NON_WEATHER_FEATURES = {"lag1", "lag2"}

# Folds counted when choosing between trend forms and feature sets. Scoring on
# the whole forward-chaining history would keep rewarding a trend that fitted
# the 1990s and has since drifted off the crop's actual level.
RECENT_FOLDS = 10


def log(msg):
    print(f"[train] {msg}", flush=True)


# Trend forms tried for every config, as (label, polynomial degree, window).
# A window of None fits the whole record.
#
# "recent20" exists because a log-linear fit over the full record extrapolates
# a finished boom. MATOPIBA cotton went from 435 to ~4,500 kg/ha between 1984
# and 2015 and has been flat since; fitted over all 41 years it predicts 6,339
# for 2024 against an actual of 4,320, a 47% overshoot. Relative skill hides
# this completely -- a biased trend inflates the model and its own baseline by
# the same amount -- which is why selection below is on absolute error.
#
# Cotton also forces the shorter recent10 window. Its series booms then
# plateaus, and averaged over all folds a full-record fit still wins, because
# the early folds sit inside the boom where a trailing window lags. What
# matters for forecasting the next season is how a form has done lately, so
# selection uses RMSE over the most recent folds (see RECENT_FOLDS).
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


def window_rows(years, mask, degree, window):
    """
    Narrow a training mask to the rows the trend was actually fitted to.

    A trailing-window trend describes only its own window. Computing residuals
    against it over the whole record leaves them with a large non-zero mean --
    older seasons sit far off a line fitted to recent ones -- and RidgeCV's
    intercept then absorbs that mean as a free level correction, which scores
    as model skill against a baseline that never received it. São Paulo oranges
    made this unmissable: alpha pinned at its 10,000 ceiling, every coefficient
    driven to ~1e-5 so the model used no weather whatsoever, and still +26.3%
    "skill" -- all of it the intercept.
    """
    if not window:
        return mask
    cutoff = years[mask].max() - window + 1
    narrowed = mask & (years >= cutoff)
    # Fall back to the full mask if the window is too thin to regress on.
    return narrowed if narrowed.sum() >= max(degree + 2, 8) else mask


def prepare(df, features, years, trend):
    """
    Feature matrix with lag features expressed as log deviations from trend.

    A raw lagged yield carries the technology level, which the trend already
    explains; feeding it in raw would have the model rediscover the trend
    through the back door and inflate its apparent skill. Converting to "last
    year's departure from trend" leaves only the biennial signal coffee needs,
    in the same log units as the target.
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

    # R2 measured on the detrended target, which is what the model actually
    # predicts. Against raw yield this number would be ~0.9 for every config
    # here purely from the trend.
    dev_true = y_true - baseline
    dev_pred = y_pred - baseline
    ss_res = float(np.sum((dev_true - dev_pred) ** 2))
    ss_tot = float(np.sum((dev_true - np.mean(dev_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    recent_rmse = float(np.sqrt(np.mean(resid[recent] ** 2)))
    recent_base = float(np.sqrt(np.mean((y_true[recent] - baseline[recent]) ** 2)))
    # Signed, so a trend sitting permanently above the crop is visible as bias
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

        fit = window_rows(years, train, degree, window)
        resid_train = np.log(yields[fit]) - trend(years[fit])

        scaler = StandardScaler().fit(X[fit])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid_train)
        pred = float(model.predict(scaler.transform(X[i:i + 1]))[0])

        # Back to kg/ha so RMSE is readable and comparable to the trend
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
    # break is not a level shift to be detrended through: the crop, its
    # calendar and its weather sensitivities all change, so the earlier era
    # contributes distorted coefficients rather than extra evidence.
    if cfg.regime_start:
        before = len(df)
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
        log(f"{cfg.key}: regime restriction from {cfg.regime_start} "
            f"({before} -> {len(df)} seasons)")

    min_train = cfg.min_train or MIN_TRAIN

    # Trim the leading seasons that cannot support the guide's own variables,
    # rather than discarding the variables.
    #
    # Coffee is the case that forces this: lag1 and lag2 are undefined for the
    # first two seasons, and dropping any feature with a missing value would
    # throw away the biennial-bearing lags that are the entire method in
    # 상파울루/커피 §3A. Losing two rows of forty-one is the cheaper trade by far.
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 5:
            df = df[keep].reset_index(drop=True)
            log(f"{cfg.key}: trimmed {trimmed} leading season(s) so the core "
                f"features survive")

    # Past that, a feature is usable only if it is present in every remaining
    # season; imputing a missing onset or frost count would invent weather.
    candidates = [c for c in df.columns
                  if c not in DROP and df[c].notna().all() and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} usable seasons, skipped")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} usable features ({len(core)} core)")

    dropped = [c for c in cfg.core if c not in candidates]
    if dropped:
        log(f"  core features unusable (missing or constant): {', '.join(dropped)}")

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
    # independently.
    #
    # The model is whichever combination forecasts best. The baseline is the
    # best any trend form manages on its own. They need not share a trend
    # form, and forcing them to share one is wrong in both directions: scoring
    # a model against its own trend rewards picking a bad trend and then
    # correcting it (São Paulo cane scored +61.5% for undoing a baseline that
    # ran 4,038 kg/ha high), while pinning the model to the best baseline's
    # trend throws away the better forecaster (Paraná corn's best model scores
    # RMSE 804 on a recent20 trend, beating every trend-only baseline, but was
    # being forced onto recent10 where it scores 1,470).
    best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
    best_baseline = min(v["baseline_rmse"] for v in fwd.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in fwd.values())
    baseline_form = min(fwd.values(), key=lambda v: v["baseline_rmse"])["trend_form"]
    log(f"  best trend-only baseline: {baseline_form}, RMSE {best_baseline:.0f} "
        "(the bar the weather features have to clear)")
    best = results[best_key]
    best_feats = best["features"]
    degree, window = best["degree"], best["window"]

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

    # Isolate the weather contribution. Where the model also carries lags, a
    # trend-only baseline flatters it twice over: the lags both add real
    # information and quietly correct a mis-specified trend. Re-running with
    # the non-weather features alone gives the fair comparison, and the
    # difference is what the weather is actually worth.
    nw_feats = [f for f in best_feats if f in NON_WEATHER_FEATURES]
    weather_skill, nw_rmse = recent_skill, None
    if nw_feats:
        nw = run_cv(df, nw_feats, "forward", degree, window, min_train)
        if nw is not None:
            nw_eval = evaluate(nw[0], nw[1], nw[2])
            nw_rmse = nw_eval["recent_rmse"]
            nw_rmse = min(nw_rmse, best_baseline_recent)
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
            log("  NOT A WEATHER PROBLEM: " + cfg.non_weather_drivers.split(".")[0]
                + ".")
    else:
        log(f"  VERDICT: beats the best trend baseline by {full_skill:.1%} "
            f"over all folds, {recent_skill:.1%} over the last "
            f"{RECENT_FOLDS} ({best_key.split('_')[0]} features).")

    # Final fit on every season, for forecasting the live one.
    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    fit = window_rows(years, np.ones(len(years), dtype=bool), degree, window)
    scaler = StandardScaler().fit(X[fit])
    resid = np.log(df.yield_kg_ha.values[fit]) - trend(years[fit])
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid)

    # Uncertainty from out-of-sample error, never in-sample. Where the model
    # loses to the trend, the honest band is the trend's own error.
    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    # Coefficients are log-space effects of a one-standard-deviation move in
    # the feature; exp() - 1 turns them into the percentage yield change,
    # which is the form the guides state their thresholds in.
    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in ranked))
    log("")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "crop": cfg.crop,
        "states": cfg.states,
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
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
        # Skill attributable to the weather features alone. Equal to
        # recent_skill_vs_trend when the model has no non-weather features.
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
    with open(os.path.join(MODELS, f"{cfg.key}.json"), "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    return artifact


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL

    built = [a for a in (train_one(c) for c in configs) if a]

    log("=" * 78)
    log(f"{'region-crop':26} {'seasons':>7} {'vs trend':>10} "
        f"{'weather only':>13} {'sigma':>8}  verdict")
    log("-" * 78)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        wonly = a["weather_skill"]
        tag = ("usable" if a["beats_trend"] else "no skill - use trend")
        if a["non_weather_features"] and wonly <= 0:
            tag = "skill is non-weather (" + ",".join(a["non_weather_features"]) + ")"
        log(f"{a['key']:26} {a['n_seasons']:7d} "
            f"{a['recent_skill_vs_trend']:+9.1%} {wonly:+12.1%} "
            f"{a['uncertainty']['sigma_kg_ha']:8.0f}  {tag}")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
