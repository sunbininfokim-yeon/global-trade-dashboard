"""
Train Vietnam region-crop models (ridge on log-yield residual vs trend).

Usage: python3 -m vietnam.train [region_key ...]
       python3 -m vietnam.train --ablation-official mekong_rice_ws

Reuses brazil.train validation (forward chaining, trend refit per fold).
Skills on provisional_synthetic labels measure consistency of the feature
scaffold, **not** production forecast skill against GSO. Mekong WS uses
labels_official (GSO Yearbook / MTN Đông Xuân + FAOSTAT prior) — read
`labels_season_imperfect` on the artifact when pre-2017 FAOSTAT is included.

Mekong: optional sample_weight (official 2017+ ×3) and exploratory
2017–2024-only ablation (thin n — reported separately, not production).
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
                          TREND_FORMS, evaluate, fit_trend, prepare,
                          window_rows)
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

DROP = {"year", "yield_kg_ha", "label_source", "label_note", "coast_km",
        "irrig_fraction", "ec_proxy_hydro", "y_rel_salt_hydro",
        "salt_water_index", "sample_weight", "q_wet_pakse",
        "precip_dry_tanchau", "q_sm_tanchau", "label_note"}
MIN_TRAIN = 18
# Official-only ablation is n≈8; lower gate so forward folds exist at all.
MIN_TRAIN_OFFICIAL_ABLATION = 4


def log(msg):
    print(f"[train] {msg}", flush=True)


def _is_provisional(label_sources):
    return (not label_sources
            or all(s.startswith("provisional") for s in label_sources))


def run_cv(df, features, mode, degree, window, min_train, weights=None):
    """Forward / LOO CV with optional sample weights (official-year emphasis)."""
    years = df.year.values.astype(float)
    yields = df.yield_kg_ha.values.astype(float)
    w_all = (weights if weights is not None
             else np.ones(len(years), dtype=float))

    preds, bases, truth, used = [], [], [], []

    for i, target in enumerate(years):
        if mode == "loo":
            train = np.arange(len(years)) != i
        else:
            train = years < target
            if train.sum() < min_train:
                continue

        trend = fit_trend(years[train], yields[train], degree, window)
        X = prepare(df, features, years, trend)

        fit = window_rows(years, train, degree, window)
        resid_train = np.log(yields[fit]) - trend(years[fit])

        scaler = StandardScaler().fit(X[fit])
        model = RidgeCV(alphas=ALPHAS).fit(
            scaler.transform(X[fit]), resid_train,
            sample_weight=w_all[fit])
        pred = float(model.predict(scaler.transform(X[i:i + 1]))[0])

        preds.append(float(np.exp(trend(target) + pred)))
        bases.append(float(np.exp(trend(target))))
        truth.append(yields[i])
        used.append(int(target))

    if not truth:
        return None
    return (np.array(truth), np.array(preds), np.array(bases), used)


def train_one(cfg, *, ablation_official=False, use_weights=True):
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None
    if cfg.stub and not os.path.exists(path):
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

    if ablation_official:
        df = df[df.year >= 2017].reset_index(drop=True)
        log(f"{cfg.key}: ABLATION official WS years only "
            f"({int(df.year.min())}-{int(df.year.max())}, n={len(df)})")
    elif cfg.regime_start:
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)

    min_train = (MIN_TRAIN_OFFICIAL_ABLATION if ablation_official
                 else (cfg.min_train or MIN_TRAIN))
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 5:
            df = df[keep].reset_index(drop=True)

    candidates = [c for c in df.columns
                  if c not in DROP
                  and df[c].notna().all()
                  and pd.api.types.is_numeric_dtype(df[c])
                  and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 2 or not candidates:
        log(f"{cfg.key}: only {len(df)} seasons "
            f"(need {min_train + 2}), skipped")
        return None

    weights = None
    if (use_weights and not ablation_official
            and "sample_weight" in df.columns
            and cfg.key == "mekong_rice_ws"):
        weights = df.sample_weight.values.astype(float)
        log(f"  sample_weight: official years ×"
            f"{float(weights.max()):.0f} "
            f"(mean={weights.mean():.2f})")

    tag = " [ablation official2017+]" if ablation_official else ""
    log(f"{cfg.key}{tag}  ({cfg.label})")
    log(f"  labels: {label_source}")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} features ({len(core)} core)")

    results = {}
    sets = [("all", candidates)] + ([("core", core)] if core else [])
    for label, feats in sets:
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv(df, feats, mode, degree, window, min_train,
                             weights=weights)
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
    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    full_skill = (1 - best["rmse"] / best_baseline
                  if best_baseline > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    scaler = StandardScaler().fit(X)
    resid = np.log(df.yield_kg_ha.values) - trend(years)
    w_fit = (weights if weights is not None
             else np.ones(len(years), dtype=float))
    final = RidgeCV(alphas=ALPHAS).fit(
        scaler.transform(X), resid, sample_weight=w_fit)
    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    provisional = _is_provisional(label_sources)
    if not beats_trend:
        log("  VERDICT: does not beat trend-only.")
    else:
        tag2 = "provisional labels only" if provisional else "on wired labels"
        log(f"  VERDICT: beats trend by {full_skill:.1%} full / "
            f"{recent_skill:.1%} recent — {tag2}.")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "crop": cfg.crop,
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
        "label_source": label_source,
        "label_sources": label_sources,
        "labels_provisional": provisional,
        "labels_season_imperfect": any(
            "faostat" in s or "scaled" in s for s in label_sources),
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_seasons": int(len(df)),
        "n_forward_folds": int(n_folds),
        "ablation_official_2017": bool(ablation_official),
        "sample_weights_used": bool(weights is not None),
        "methodology_features_20260805": [
            "spei4_ws_min", "spi_ws", "oni_lag2", "q_upstream_proxy",
            "salt_x_coast", "salt_coastal_belt",
        ],
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
        "salinity_is_proxy": True,
        "mrc_discharge_used": False,
        "q_upstream_is_power_proxy": True,
    }

    os.makedirs(MODELS, exist_ok=True)
    out_name = (f"{cfg.key}_ablation_official2017.json" if ablation_official
                else f"{cfg.key}.json")
    with open(os.path.join(MODELS, out_name), "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    log(f"  wrote models/{out_name}\n")
    return artifact


def main():
    args = list(sys.argv[1:])
    do_ablation = False
    if "--ablation-official" in args:
        do_ablation = True
        args.remove("--ablation-official")

    keys = args
    configs = [BY_KEY[k] for k in keys] if keys else list(ALL)
    built = [a for a in (train_one(c) for c in configs) if a]

    if do_ablation or any(c.key == "mekong_rice_ws" for c in configs):
        # Always run thin official-year ablation alongside Mekong production train
        if any(c.key == "mekong_rice_ws" for c in configs):
            ab = train_one(BY_KEY["mekong_rice_ws"], ablation_official=True,
                           use_weights=False)
            if ab:
                built.append(ab)

    log("=" * 78)
    log(f"{'region-crop':36} {'n':>4} {'vs trend':>10} {'sigma':>8}  notes")
    log("-" * 78)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        note = "provisional labels" if a["labels_provisional"] else "real/best-effort"
        if a.get("labels_season_imperfect"):
            note += "; season imperfect"
        if a.get("ablation_official_2017"):
            note = "ABLATION 2017+ only; " + note
        if a.get("sample_weights_used"):
            note += "; w×official"
        tag = "beats trend" if a["beats_trend"] else "use trend"
        name = a["key"] + ("_ablation2017" if a.get("ablation_official_2017") else "")
        log(f"{name:36} {a['n_seasons']:4d} "
            f"{a['recent_skill_vs_trend']:+9.1%} "
            f"{a['uncertainty']['sigma_kg_ha']:8.0f}  {tag}; {note}")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
