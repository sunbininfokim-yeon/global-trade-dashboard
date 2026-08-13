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

# Features derived from NOAA's climate indices rather than from local weather.
ENSO_FEATURES = {"oni_lag", "iod_spring", "climate_shock"}

# Features derived from POWER's GWETROOT root-zone wetness -- the 0803
# 작업지시서's soil-moisture channel.
#
# `smi_*` is deliberately NOT in this set. Those come from this pipeline's own
# single-layer bucket balance, which is a local water accounting built out of
# rainfall and ET0 that the model would have anyway. The question the sheet
# asks is whether an independent land-surface soil-moisture field adds
# anything on top of that, so only the `sm_*` family and the thresholds built
# on it count as "soil".
SOIL_FEATURES = {
    "sm_summer", "sm_silking", "sm_spring", "sm_rep_obs", "sm_flowering_obs",
    "autumn_recharge", "heat_x_drought", "dry_spell", "harvest_wet_days",
}


def log(msg):
    print(f"[train] {msg}", flush=True)


def nested_sets(candidates):
    """
    The three cumulative feed sets, as (name, features), smallest first.

    These are also offered to model selection, not only to the ablation report.
    An ablation that finds a better feature set than the selector can choose is
    a broken selector: Pampas corn scored +38.6% on local weather alone and
    +30.1% once the soil features were bolted on, and the run had no way to
    pick the first. Adding three physically-motivated nested sets to the
    existing "all"/"core" choice widens selection multiplicity a little, which
    is a real cost -- but nested-by-data-feed is a principled ordering, not a
    search over arbitrary subsets.
    """
    soil = [c for c in candidates if c in SOIL_FEATURES]
    enso = [c for c in candidates if c in ENSO_FEATURES]
    weather = [c for c in candidates if c not in SOIL_FEATURES
               and c not in ENSO_FEATURES]
    return [("weather", weather),
            ("enso", weather + enso),
            ("soil", weather + enso + soil)]


def ablation(df, candidates, degree, window, min_train, baseline_rmse):
    """
    The 0803 작업지시서's results table, computed rather than asserted.

    Four cumulative rungs, each scored by the same forward chaining and against
    the same trend baseline:

      trend          the technology trend alone -- no features at all
      weather        local weather only (rainfall, heat, the water balance)
      +enso          add ONI and the dipole
      +soil          add the GWETROOT root-zone features

    Cumulative rather than leave-one-out, because the sheet's question is an
    ordering question -- "is it worth adding this feed?" -- and the answer to
    that depends on what is already in the model. A soil-moisture field that
    duplicates information the rainfall features already carry should score
    zero here, and that is the correct answer, not a bug.

    The rungs all share one trend form so the comparison is between feature
    sets and not between baselines.
    """
    rungs = nested_sets(candidates)

    mean_yield = float(df.yield_kg_ha.tail(10).mean())
    out = {"trend": {"features": [], "n_features": 0,
                     "rmse": baseline_rmse,
                     "mape_pct": baseline_rmse / mean_yield * 100,
                     "skill_vs_trend": 0.0}}

    for name, feats in rungs:
        if not feats:
            continue
        res = run_cv(df, feats, "forward", degree, window, min_train)
        if res is None:
            continue
        truth, pred, base, _ = res
        ev = evaluate(truth, pred, base)
        out[name] = {
            "features": feats,
            "n_features": len(feats),
            "rmse": ev["rmse"],
            "mape_pct": ev["rmse"] / mean_yield * 100,
            "skill_vs_trend": (1 - ev["rmse"] / baseline_rmse
                               if baseline_rmse > 0 else float("nan")),
        }

    # What each feed bought on top of the rung below it.
    for lower, upper in (("weather", "enso"), ("enso", "soil")):
        if lower in out and upper in out and out[lower]["rmse"] > 0:
            out[upper]["marginal_gain"] = (
                1 - out[upper]["rmse"] / out[lower]["rmse"])

    return out


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
    # Plus the nested data-feed sets, so the selector can reach the answer the
    # ablation finds rather than only choosing between "everything" and "the
    # guide's own variables".
    sets += [(name, feats) for name, feats in nested_sets(candidates) if feats]

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

    # The 0803 작업지시서's results table.
    abl = ablation(df, candidates, degree, window, min_train, best_baseline)
    log("  feed ablation (forward chaining, one shared trend form):")
    for rung in ("trend", "weather", "enso", "soil"):
        if rung not in abl:
            continue
        a = abl[rung]
        marginal = (f"  marginal {a['marginal_gain']:+6.1%}"
                    if "marginal_gain" in a else "")
        log(f"    {rung:8} {a['n_features']:2d} feats  RMSE {a['rmse']:7.1f}  "
            f"MAPE {a['mape_pct']:5.1f}%  vs trend {a['skill_vs_trend']:+6.1%}"
            f"{marginal}")

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
        # Cumulative feed ablation: trend -> weather -> +ENSO -> +GWETROOT
        "ablation": abl,
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
