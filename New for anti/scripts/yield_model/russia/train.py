"""
Train Russia winter-wheat models (ridge residual on log yield trend).

Usage: python3 -m russia.train [region_key ...]

Validation skeleton matches china.train: forward chaining with trend refit
inside each fold; skill_vs_trend; best model vs best independent baseline.
"""

from __future__ import annotations

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
MIN_TRAIN = 18
RECENT_FOLDS = 10
TREND_FORMS = [("deg1", 1, None), ("deg2", 2, None),
               ("recent20", 1, 20), ("recent10", 1, 10)]

# Evidence floor for calling a model usable. Winter wheat has only five
# forward folds (2018-2021, 2024; Rosstat 2022-2023 missing), and a 16-feature
# model on 23 seasons scored +36.6% on those five while scoring +6% under
# leave-one-out. Below these limits a positive score is noise, not skill.
MIN_FORWARD_FOLDS = 8
SEASONS_PER_FEATURE = 5


def log(msg):
    print(f"[train] {msg}", flush=True)


def fit_trend(years, values, degree, window=None):
    if window:
        mask = years >= years.max() - window + 1
        if mask.sum() >= max(degree + 2, 8):
            years, values = years[mask], values[mask]
    return np.poly1d(np.polyfit(years, np.log(values), degree))


def window_rows(years, mask, degree, window):
    """
    Narrow a training mask to the rows the trend was actually fitted to.

    Same fix as brazil.train.window_rows (2026-08-03): residuals against a
    trailing-window trend computed over the whole record carry a non-zero mean,
    and RidgeCV's intercept takes it as a free level correction that scores as
    skill against a baseline that never received it.
    """
    if not window:
        return mask
    cutoff = years[mask].max() - window + 1
    narrowed = mask & (years >= cutoff)
    return narrowed if narrowed.sum() >= max(degree + 2, 8) else mask


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
        fit = window_rows(years, train, degree, window)
        resid_train = np.log(values[fit]) - trend(years[fit])
        scaler = StandardScaler().fit(X[fit])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid_train)
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
    # Drop non-positive yields if any PSD blank
    df = df[df.target > 0].reset_index(drop=True)

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
        log(f"{cfg.key}: only {len(df)} usable seasons, skipped")
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
    raw_beats_trend = bool(beats_trend)
    label_res = getattr(cfg, "label_resolution", "") or ""
    interim_labels = label_res == "national_psd_interim"
    if interim_labels and beats_trend:
        log("  NOTE: numerical skill > 0 but labels are national PSD interim — "
            "refusing usable / beats_trend for forecast (not Track B).")
        beats_trend = False
    elif interim_labels:
        log("  NOTE: national PSD interim labels — not Track B oblast validation.")

    n_folds = int(best["n"])
    max_features = len(df) // SEASONS_PER_FEATURE
    thin_evidence = []
    if n_folds < MIN_FORWARD_FOLDS:
        thin_evidence.append(f"{n_folds} forward folds < {MIN_FORWARD_FOLDS}")
    if len(best_feats) > max_features:
        thin_evidence.append(f"{len(best_feats)} features > {len(df)} seasons / "
                             f"{SEASONS_PER_FEATURE}")
    if thin_evidence and beats_trend:
        log("  NOTE: positive skill on thin evidence ("
            + "; ".join(thin_evidence) + ") — not usable.")
        beats_trend = False

    if not beats_trend:
        if interim_labels and raw_beats_trend:
            log("  VERDICT: INTERIM only — raw skill positive but NOT usable "
                "(national y vs zone weather).")
        else:
            log("  VERDICT: does not beat trend-only out of sample.")
    else:
        log(f"  VERDICT: beats trend by {full_skill:.1%} (all folds), "
            f"{recent_skill:.1%} (recent {RECENT_FOLDS}).")

    years = df.year.values.astype(float)
    X = prepare(df, best_feats, years, trend)
    fit = window_rows(years, np.ones(len(years), dtype=bool), degree, window)
    scaler = StandardScaler().fit(X[fit])
    resid = np.log(df.target.values[fit]) - trend(years[fit])
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid)
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
        "label_resolution": label_res or None,
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
        "raw_beats_trend": raw_beats_trend,
        "thin_evidence": thin_evidence,
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
                (
                    f"INTERIM PSD labels: not usable for zone forecast; "
                    f"raw recent skill={recent_skill:+.1%}, "
                    f"trend-only sigma used"
                    if interim_labels else
                    f"trend-only baseline RMSE over last {RECENT_FOLDS} folds "
                    "(model showed no skill)"
                )
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
    configs = [BY_KEY[k] for k in keys] if keys else ALL
    built = [a for a in (train_one(c) for c in configs) if a]

    log("=" * 84)
    log(f"{'region-crop':28} {'seasons':>7} {'vs trend':>10} "
        f"{'sigma':>10}  verdict")
    log("-" * 84)
    for a in sorted(built, key=lambda x: -x["recent_skill_vs_trend"]):
        if a.get("label_resolution") == "national_psd_interim":
            tag = "INTERIM PSD — not Track B / not usable"
        elif a["beats_trend"]:
            tag = "usable"
        else:
            tag = "no skill - use trend"
        log(f"{a['key']:28} {a['n_seasons']:7d} "
            f"{a['recent_skill_vs_trend']:+9.1%} "
            f"{a['uncertainty']['sigma']:10.0f}  {tag}")
    log("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
