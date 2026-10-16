"""
Train Thailand region-crop models (ridge on log-yield residual vs trend).

Usage: PYTHONPATH=. python3 -m thailand.train [region_key ...]
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from brazil.train import (ALPHAS, NON_WEATHER_FEATURES, RECENT_FOLDS,
                          TREND_FORMS, evaluate, fit_trend, nested_selection,
                          prepare, run_cv)
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

DROP = {"year", "yield_kg_ha", "label_source", "label_note", "role_upstream",
        "onset_doy"}
MIN_TRAIN = 18


def log(msg):
    print(f"[train] {msg}", flush=True)


def _is_provisional(label_sources):
    return (not label_sources
            or all(s.startswith("provisional") for s in label_sources))


def train_one(cfg):
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])
    if df.empty:
        log(f"{cfg.key}: empty yields, skipped")
        return None

    label_source = "unknown"
    label_sources = []
    if "label_source" in df.columns and df.label_source.notna().any():
        label_sources = sorted({str(s) for s in df.label_source.dropna().unique()})
        recent = df.dropna(subset=["label_source"]).sort_values("year")
        label_source = str(recent.label_source.iloc[-1])
        if len(label_sources) > 1:
            label_source = (
                f"{label_source} (+{len(label_sources) - 1} other sources; "
                f"see training CSV)")

    if cfg.regime_start:
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)

    min_train = cfg.min_train or MIN_TRAIN
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 8:
            df = df[keep].reset_index(drop=True)

    candidates = [c for c in df.columns
                  if c not in DROP
                  and df[c].notna().all()
                  and pd.api.types.is_numeric_dtype(df[c])
                  and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} seasons "
            f"(need {min_train + 5}), skipped")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  labels: {label_source}")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} features ({len(core)} core)")
    if getattr(cfg, "sources", None):
        for s in cfg.sources[:3]:
            log(f"  ref: {s}")

    results = {}
    paths = {}   # forward key -> {year: (truth, pred, trend)}
    sets = [("all", candidates)] + ([("core", core)] if core else [])
    for label, feats in sets:
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv(df, feats, mode, degree, window, min_train)
                if out is None:
                    continue
                truth, pred, base, yrs = out
                key = f"{label}_{tlabel}_{mode}"
                if mode == "forward":
                    paths[key] = {y: (t, pr, b) for y, t, pr, b
                                  in zip(yrs, truth, pred, base)}
                results[key] = evaluate(truth, pred, base)
                results[key]["n"] = len(truth)
                results[key]["years"] = [yrs[0], yrs[-1]]
                results[key]["features"] = feats
                results[key]["degree"] = degree
                results[key]["window"] = window
                results[key]["trend_form"] = tlabel

    fwd = {k: v for k, v in results.items() if k.endswith("_forward")}
    if not fwd:
        log("  no forward folds\n")
        return None

    best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
    best_baseline = min(v["baseline_rmse"] for v in fwd.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in fwd.values())
    best = results[best_key]
    best_feats = best["features"]
    degree, window = best["degree"], best["window"]
    n_folds = best["n"]

    for k in sorted(results):
        r = results[k]
        mark = " <-" if k == best_key else ""
        log(f"    {k:26} n={r['n']:3d}  RMSE={r['rmse']:7.1f}  "
            f"vs trend={r['skill_vs_trend']:+7.1%}{mark}")

    trend = fit_trend(df.year.values, df.yield_kg_ha.values, degree, window)
    # Skill from nested selection (see brazil/train.py): each season is
    # forecast by the combination that scored best on the seasons before it,
    # so picking the winner on the test years no longer inflates the number.
    in_sample = {
        "full_skill": float(1 - best["rmse"] / best_baseline
                            if best_baseline > 0 else float("nan")),
        "recent_skill": float(1 - best["recent_rmse"] / best_baseline_recent
                              if best_baseline_recent > 0 else float("nan")),
    }
    baseline_form = min(fwd.values(), key=lambda v: v["baseline_rmse"])["trend_form"]
    nested = nested_selection(paths, baseline_form)
    if nested is not None:
        honest = evaluate(*nested["arrays"])
        full_skill = 1 - honest["rmse"] / honest["baseline_rmse"]
        recent_skill = 1 - honest["recent_rmse"] / honest["recent_baseline_rmse"]
        best_baseline_recent = honest["recent_baseline_rmse"]
        model_recent_rmse = honest["recent_rmse"]
        log(f"  nested selection over {len(nested['years'])} seasons: "
            f"{full_skill:+.1%} all, {recent_skill:+.1%} recent "
            f"(in-sample pick: {in_sample['full_skill']:+.1%}, "
            f"{in_sample['recent_skill']:+.1%})")
    else:
        full_skill, recent_skill = in_sample["full_skill"], in_sample["recent_skill"]
        model_recent_rmse = best["recent_rmse"]
    beats_trend = full_skill > 0 and recent_skill > 0

    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    scaler = StandardScaler().fit(X)
    resid = np.log(df.yield_kg_ha.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)
    sigma = model_recent_rmse if beats_trend else best_baseline_recent

    provisional = _is_provisional(label_sources)
    season_imperfect = any(
        "faostat" in s or "national" in s or "scaled" in s
        for s in label_sources)
    # Off-season rice + national FAOSTAT rice is always season-imperfect
    if cfg.key == "chao_phraya_rice_off":
        season_imperfect = True

    if not beats_trend:
        log("  VERDICT: does not beat trend-only.")
    else:
        tag = "provisional labels only" if provisional else "on wired labels"
        log(f"  VERDICT: beats trend by {full_skill:.1%} full / "
            f"{recent_skill:.1%} recent — {tag}.")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "crop": cfg.crop,
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "sources": list(getattr(cfg, "sources", []) or []),
        "label_source": label_source,
        "label_sources": label_sources,
        "labels_provisional": provisional,
        "labels_season_imperfect": season_imperfect,
        "dam_storage_is_proxy": cfg.key == "chao_phraya_rice_off",
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "n_forward_folds": int(n_folds),
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
        "skill_basis": "nested" if nested is not None else "in_sample",
        "nested": (None if nested is None else {
            "n": len(nested["years"]),
            "years": [nested["years"][0], nested["years"][-1]],
            "picks": nested["picks"],
        }),
        "skill_in_sample": in_sample,
        "weather_skill": float(recent_skill),
        "non_weather_features": [f for f in best_feats
                                 if f in NON_WEATHER_FEATURES],
        "recent_folds": RECENT_FOLDS,
        "uncertainty": {
            "sigma_kg_ha": float(sigma),
            "basis": ("out-of-sample RMSE recent folds" if beats_trend else
                      "trend-only baseline (no skill)"),
        },
        "validation": {k: {kk: vv for kk, vv in v.items() if kk != "features"}
                       for k, v in results.items()},
        "forward": {kk: vv for kk, vv in best.items() if kk != "features"},
        "gee_used": False,
        "rid_dam_wired": False,
    }

    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, f"{cfg.key}.json"), "w",
              encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    log("")
    return artifact


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else list(ALL)
    built = [a for a in (train_one(c) for c in configs) if a]

    log("=" * 78)
    log(f"{'region-crop':28} {'n':>4} {'vs trend':>10} {'sigma':>8}  notes")
    log("-" * 78)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        note = "provisional" if a["labels_provisional"] else "FAOSTAT/official"
        if a.get("labels_season_imperfect"):
            note += "; season imperfect"
        if a.get("dam_storage_is_proxy"):
            note += "; dam PROXY"
        tag = "beats trend" if a["beats_trend"] else "use trend"
        log(f"{a['key']:28} {a['n_seasons']:4d} "
            f"{a['recent_skill_vs_trend']:+9.1%} "
            f"{a['uncertainty']['sigma_kg_ha']:8.0f}  {tag}; {note}")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
