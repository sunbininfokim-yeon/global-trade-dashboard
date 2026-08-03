"""
Train and honestly validate every Argentine region-crop model.

Usage: python3 -m argentina.train [region_key ...]

The validation machinery is imported from `brazil.train` rather than
reimplemented -- forward chaining with the trend refit inside every fold, a
log-yield trend whose form is chosen out of sample, model and baseline chosen
independently, uncertainty taken from out-of-sample error only. That code was
written to stop a model flattering itself and none of its reasoning is
Brazil-specific.

Two things are specific to this feed:

**Abandonment is excluded from the features.** MAGyP publishes sown and
harvested area, and their difference is a superb drought signal -- but it is
measured at harvest, exactly when the yield it would predict is also measured.
Feeding it in would post-dict, not forecast. It stays in the training CSV for
diagnostics and is dropped here, along with harvested area for the same reason.

**A drought that destroys a crop hides in the target.** A field written off
before harvest leaves the yield average entirely, so Argentine yield understates
the worst seasons: 2008/09 and 2022/23 abandoned a large share of the soy area
and the surviving fields were the better ones. The weather features see a
disaster the target only partly records, which caps how much skill any of these
models can show. It is a property of the data, not a bug in the fit.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from brazil.train import (ALPHAS, NON_WEATHER_FEATURES, RECENT_FOLDS,
                          TREND_FORMS, evaluate, fit_trend, prepare, run_cv)
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

# year and yield are the index and target. area_ha and abandonment are known
# only once the season is over (see module docstring).
DROP = {"year", "yield_kg_ha", "area_ha", "abandonment"}

MIN_TRAIN = 22


def log(msg):
    print(f"[train] {msg}", flush=True)


def train_one(cfg):
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])

    if cfg.regime_start:
        before = len(df)
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
        log(f"{cfg.key}: regime restriction from {cfg.regime_start} "
            f"({before} -> {len(df)} seasons)")

    min_train = cfg.min_train or MIN_TRAIN

    # Trim leading seasons that cannot support the guide's own variables
    # rather than discarding the variables (cane's lag1 is the case here).
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 5:
            df = df[keep].reset_index(drop=True)
            log(f"{cfg.key}: trimmed {trimmed} leading season(s) so the core "
                f"features survive")

    candidates = [c for c in df.columns
                  if c not in DROP and df[c].notna().all() and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} usable seasons "
            f"(need {min_train + 5}), skipped")
        if cfg.caveat:
            log(f"  why: {cfg.caveat.split('.')[0]}.")
        log("")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} usable features ({len(core)} core)")

    dropped = [c for c in cfg.core if c not in candidates]
    if dropped:
        log(f"  core features unusable (missing or constant): {', '.join(dropped)}")

    results = {}
    sets = [("all", candidates)] + ([("core", core)] if core else [])

    for label, feats in sets:
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv(df, feats, mode, degree, window, min_train)
                if out is None:
                    continue
                truth, pred, base, yrs = out
                key = f"{label}_{tlabel}_{mode}"
                results[key] = evaluate(truth, pred, base)
                results[key].update({"n": len(truth), "years": [yrs[0], yrs[-1]],
                                     "features": feats, "degree": degree,
                                     "window": window, "trend_form": tlabel})

    fwd = {k: v for k, v in results.items() if k.endswith("_forward")}
    if not fwd:
        log("  no forward-chaining fold had enough history\n")
        return None

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

    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    scaler = StandardScaler().fit(X)
    resid = np.log(df.yield_kg_ha.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)

    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in ranked))

    # How much of the worst seasons never reached the yield average at all.
    if "abandonment" in df.columns and df.abandonment.notna().any():
        worst = df.nsmallest(3, "yield_kg_ha")
        log("  worst seasons: " + ", ".join(
            f"{int(r.year)} {r.yield_kg_ha:.0f} kg/ha "
            f"({r.abandonment * 100:.0f}% abandoned)"
            for _, r in worst.iterrows()))
    log("")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "crop": cfg.crop,
        "provinces": cfg.provinces,
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "regime_start": cfg.regime_start or None,
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
        "mean_abandonment": (float(df.abandonment.mean())
                             if "abandonment" in df.columns else None),
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
        tag = "usable" if a["beats_trend"] else "no skill - use trend"
        if a["non_weather_features"] and wonly <= 0:
            tag = "skill is non-weather (" + ",".join(a["non_weather_features"]) + ")"
        log(f"{a['key']:26} {a['n_seasons']:7d} "
            f"{a['recent_skill_vs_trend']:+9.1%} {wonly:+12.1%} "
            f"{a['uncertainty']['sigma_kg_ha']:8.0f}  {tag}")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
