"""
Train and honestly validate every China region-crop model.

Usage: python3 -m china.train [region_key ...]

The validation skeleton is brazil.train's, unchanged in substance because it is
the part of this repository worth keeping identical across countries: forward
chaining with the technology trend refit *inside every fold*, a log-space
target, and model and baseline trend forms chosen independently so a model
cannot score well by correcting a trend it picked badly on purpose.

Three things differ, all forced by what China's data looks like.

The target column is `target` rather than `yield_kg_ha`. Five configs are
yields; south_china_rice_area is harvested area in 1000 ha, because the
question its guide asks -- did farmers plant the second rice crop the state
told them to? -- is invisible in yield per harvested hectare and visible in
area. Sigma is therefore published in the config's own unit rather than
labelled kg/ha.

`region_share` is written into every artifact. Five of the six targets are
national series answering a provincial question, and the share of the national
total that the modelled region actually produces is the ceiling on how much of
the target these features could explain even if every formula were perfect.
That belongs in the published record next to the skill score, not only in a
source comment.

Robust weighting is deliberately not implemented. 동북3성 §4 and 허난 §4 both ask
for a loss that down-weights seasons where the official Chinese yield diverges
from USDA's estimate and from the satellite record. That instruction presumes
the NBS series is the label. Here USDA *is* the label -- data.stats.gov.cn is
unreachable, see labels.py -- so there is no divergence left to down-weight.
The guides' intent is satisfied by the choice of source rather than by a loss
function, and adding a robust loss on top would be theatre.

Expect several of these six to lose to a trend-only baseline. Chinese yields
have roughly doubled since 1982 on breeding, fertiliser and irrigation, so the
trend is enormous and the weather residual it leaves is small and nationally
averaged. A model that cannot beat the trend says so and the report records it.

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

DROP = {"year", "target"}

MIN_TRAIN = 22

# Features that are real predictors but are not weather. No China config uses
# lags today; the machinery stays so that adding one later cannot quietly
# credit biological memory to the climate model.
NON_WEATHER_FEATURES = {"lag1", "lag2"}

RECENT_FOLDS = 10

TREND_FORMS = [("deg1", 1, None), ("deg2", 2, None),
               ("recent20", 1, 20), ("recent10", 1, 10)]


def log(msg):
    print(f"[train] {msg}", flush=True)


def fit_trend(years, values, degree, window=None):
    """Technology trend in log space. Returns a poly1d over the year."""
    if window:
        mask = years >= years.max() - window + 1
        if mask.sum() >= max(degree + 2, 8):
            years, values = years[mask], values[mask]
    return np.poly1d(np.polyfit(years, np.log(values), degree))


def prepare(df, features, years, trend):
    """
    Feature matrix, with any lag features expressed as log deviations from
    trend so a lagged target cannot smuggle the technology level back in.
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
    # Against the raw series this would read ~0.95 for every config here on the
    # strength of the trend alone.
    dev_true = y_true - baseline
    dev_pred = y_pred - baseline
    ss_res = float(np.sum((dev_true - dev_pred) ** 2))
    ss_tot = float(np.sum((dev_true - np.mean(dev_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    recent_rmse = float(np.sqrt(np.mean(resid[recent] ** 2)))
    recent_base = float(np.sqrt(np.mean((y_true[recent] - baseline[recent]) ** 2)))
    trend_bias = float(np.mean(baseline[recent] - y_true[recent]))

    return {"rmse": rmse, "mae": mae, "detrended_r2": r2,
            "skill_vs_trend": skill, "baseline_rmse": base_rmse,
            "recent_rmse": recent_rmse, "recent_baseline_rmse": recent_base,
            "recent_trend_bias": trend_bias}


def run_cv(df, features, mode, degree, window, min_train):
    years = df.year.values.astype(float)
    values = df.target.values.astype(float)

    preds, bases, truth, used = [], [], [], []

    for i, target_year in enumerate(years):
        if mode == "loo":
            train = np.arange(len(years)) != i
        else:
            train = years < target_year
            if train.sum() < min_train:
                continue

        # Refit inside the fold. Fitting the trend once on all years and then
        # cross-validating leaks the future into every training set.
        trend = fit_trend(years[train], values[train], degree, window)
        X = prepare(df, features, years, trend)

        resid_train = np.log(values[train]) - trend(years[train])

        scaler = StandardScaler().fit(X[train])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[train]), resid_train)
        pred = float(model.predict(scaler.transform(X[i:i + 1]))[0])

        preds.append(float(np.exp(trend(target_year) + pred)))
        bases.append(float(np.exp(trend(target_year))))
        truth.append(values[i])
        used.append(int(target_year))

    if not truth:
        return None
    return (np.array(truth), np.array(preds), np.array(bases), used)


def train_one(cfg):
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["target"])

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

    # Past that, a feature is usable only if present in every remaining season.
    # Imputing a missing frost count or radiation total would invent weather.
    candidates = [c for c in df.columns
                  if c not in DROP and df[c].notna().all() and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} usable seasons, skipped")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} usable features ({len(core)} core)")
    log(f"  target: {cfg.target_label} in {cfg.target_unit} "
        f"[{cfg.label_source}]")

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
    # independently. Scoring a model against its own trend rewards picking a
    # bad trend and then correcting it; pinning the model to the best
    # baseline's trend throws away the better forecaster.
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
        log(f"    {k:26} n={r['n']:3d}  RMSE={r['rmse']:8.1f}  "
            f"recent={r['recent_rmse']:8.1f}  "
            f"trend bias={r['recent_trend_bias']:+8.0f}  "
            f"vs trend={r['skill_vs_trend']:+7.1%}{mark}")

    trend = fit_trend(df.year.values, df.target.values, degree, window)

    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    full_skill = (1 - best["rmse"] / best_baseline
                  if best_baseline > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    # Isolate the weather contribution where the model carries non-weather
    # features. No China config does yet, so this is normally a no-op.
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
        f"{best['recent_trend_bias']:+.0f} {cfg.target_unit} over the last "
        f"{RECENT_FOLDS} seasons")
    bias_pct = (best["recent_trend_bias"]
                / float(df.target.tail(10).mean()) * 100)
    if abs(bias_pct) > 3:
        log(f"  WARNING: even the best trend form runs {bias_pct:+.1f}% off "
            "the recent level; treat the absolute number with caution.")
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
    resid = np.log(df.target.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)

    # Uncertainty from out-of-sample error, never in-sample. Where the model
    # loses to the trend, the honest band is the trend's own error.
    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in ranked))
    log("")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "doc": cfg.doc,
        "target_label": cfg.target_label,
        "target_unit": cfg.target_unit,
        "label_source": cfg.label_source,
        # The ceiling on this model: how much of the national target the
        # modelled region actually produces.
        "region_share": cfg.region_share,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "regime_start": cfg.regime_start or None,
        "trend": {"log_poly_coef": [float(c) for c in trend.coefficients],
                  "degree": int(degree),
                  "form": best["trend_form"],
                  "window": window,
                  "space": f"log({cfg.target_unit})"},
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
        "recent_trend_bias": float(best["recent_trend_bias"]),
        "recent_folds": RECENT_FOLDS,
        "uncertainty": {
            "sigma": float(sigma),
            "unit": cfg.target_unit,
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

    log("=" * 84)
    log(f"{'region-crop':24} {'seasons':>7} {'vs trend':>10} "
        f"{'weather only':>13} {'sigma':>10} {'unit':>9}  verdict")
    log("-" * 84)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        wonly = a["weather_skill"]
        tag = "usable" if a["beats_trend"] else "no skill - use trend"
        if a["non_weather_features"] and wonly <= 0:
            tag = "skill is non-weather (" + ",".join(a["non_weather_features"]) + ")"
        log(f"{a['key']:24} {a['n_seasons']:7d} "
            f"{a['recent_skill_vs_trend']:+9.1%} {wonly:+12.1%} "
            f"{a['uncertainty']['sigma']:10.0f} {a['target_unit']:>9}  {tag}")
    log("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
