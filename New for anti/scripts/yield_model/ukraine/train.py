"""
Train Ukraine models (ridge residual on log yield trend).

Usage: python3 -m ukraine.train [region_key ...]

Refuses configs with label_resolution=blocked or missing/empty target series.
Default wheat-only when no keys passed.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from .labels import LABEL_MAX_YEAR
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

ALPHAS = np.logspace(-2, 4, 40)
DROP = {"year", "target"}
MIN_TRAIN = 16
RECENT_FOLDS = 8
TREND_FORMS = [("deg1", 1, None), ("deg2", 2, None),
               ("recent20", 1, 20), ("recent10", 1, 10)]


def log(msg):
    print(f"[train] {msg}", flush=True)


def fit_trend(years, values, degree, window=None):
    if window:
        mask = years >= years.max() - window + 1
        if mask.sum() >= max(degree + 2, 8):
            years, values = years[mask], values[mask]
    return np.poly1d(np.polyfit(years, np.log(values), degree))


def prepare(df, features, years, trend):
    return df[features].astype(float).values


def evaluate(y_true, y_pred, baseline):
    resid = y_true - y_pred
    recent = slice(-min(RECENT_FOLDS, len(y_true)), None)
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    mae = float(np.mean(np.abs(resid)))
    base_rmse = float(np.sqrt(np.mean((y_true - baseline) ** 2)))
    skill = 1 - rmse / base_rmse if base_rmse > 0 else float("nan")
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
    if getattr(cfg, "label_resolution", "") == "blocked":
        log(f"{cfg.key}: label_resolution=blocked — skip "
            f"(need oblast CSV; see labels.md)")
        return None

    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["target"])
    df = df[df.target > 0].reset_index(drop=True)
    # Hard war-year gate even if CSV sneaks in later years.
    df = df[df.year <= LABEL_MAX_YEAR].reset_index(drop=True)

    if cfg.regime_start:
        before = len(df)
        df = df[df.year >= cfg.regime_start].reset_index(drop=True)
        log(f"{cfg.key}: regime from {cfg.regime_start} ({before} -> {len(df)})")

    min_train = cfg.min_train or MIN_TRAIN
    present = [c for c in cfg.core if c in df.columns]
    if present:
        keep = df[present].notna().all(axis=1)
        trimmed = int((~keep).sum())
        if trimmed and trimmed <= 5:
            df = df[keep].reset_index(drop=True)
            log(f"{cfg.key}: trimmed {trimmed} leading incomplete season(s)")

    candidates = [c for c in df.columns
                  if c not in DROP and df[c].notna().all() and df[c].std() > 0]
    core = [c for c in cfg.core if c in candidates]

    if len(df) < min_train + 5 or not candidates:
        log(f"{cfg.key}: only {len(df)} usable seasons (≤{LABEL_MAX_YEAR}), skipped")
        return None

    log(f"{cfg.key}  ({cfg.label})")
    log(f"  {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} features ({len(core)} core)")
    log(f"  target: {cfg.target_label} [{cfg.label_source}]")

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
        log("  no forward-chaining folds\n")
        return None

    best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
    best_baseline = min(v["baseline_rmse"] for v in fwd.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in fwd.values())
    log(f"  best trend-only RMSE {best_baseline:.0f}")
    best = results[best_key]
    best_feats = best["features"]
    degree, window = best["degree"], best["window"]

    for k in sorted(results):
        r = results[k]
        mark = " <-" if k == best_key else ""
        log(f"    {k:26} n={r['n']:3d}  RMSE={r['rmse']:8.1f}  "
            f"recent={r['recent_rmse']:8.1f}  "
            f"vs trend={r['skill_vs_trend']:+7.1%}{mark}")

    trend = fit_trend(df.year.values, df.target.values, degree, window)
    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    full_skill = (1 - best["rmse"] / best_baseline
                  if best_baseline > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    if not beats_trend:
        log("  VERDICT: does not beat trend-only out of sample.")
    else:
        log(f"  VERDICT: beats trend by {full_skill:.1%} (all folds), "
            f"{recent_skill:.1%} (recent {RECENT_FOLDS}).")

    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    scaler = StandardScaler().fit(X)
    resid = np.log(df.target.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)
    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent

    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in ranked))
    log("")

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "doc": cfg.doc,
        "target_label": cfg.target_label,
        "target_unit": cfg.target_unit,
        "label_source": cfg.label_source,
        "label_resolution": getattr(cfg, "label_resolution", None),
        "label_max_year": LABEL_MAX_YEAR,
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
        "weather_skill": float(recent_skill),
        "recent_trend_bias": float(best["recent_trend_bias"]),
        "recent_folds": RECENT_FOLDS,
        "uncertainty": {
            "sigma": float(sigma),
            "unit": cfg.target_unit,
            "basis": (
                f"out-of-sample RMSE over last {RECENT_FOLDS} forward folds"
                if beats_trend else
                f"trend-only baseline RMSE over last {RECENT_FOLDS} folds "
                "(model showed no skill)"
            ),
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
    if keys:
        configs = [BY_KEY[k] for k in keys]
    else:
        configs = [c for c in ALL if "wheat" in c.key]

    built = [a for a in (train_one(c) for c in configs) if a]

    log("=" * 84)
    if not built:
        log("no models trained — drop oblast wheat CSVs (labels.md) first")
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        tag = "usable" if a["beats_trend"] else "no skill - use trend"
        log(f"{a['key']:28} {a['n_seasons']:7d} "
            f"{a['recent_skill_vs_trend']:+9.1%} "
            f"{a['uncertainty']['sigma']:10.0f}  {tag}")
    log("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
