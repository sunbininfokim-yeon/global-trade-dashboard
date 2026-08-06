"""
Fit LatAm banana ridge residual models (Australia protocol).

Pre-registered feature ablations only. Operational only if skill vs trend
≥ 10% on all and recent folds. Refuses label_resolution=blocked.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

from .labels import province_available, refresh_label_resolution
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")
ALPHAS = np.logspace(-2, 4, 40)
RECENT_FOLDS = 10
MIN_OPERATIONAL_SKILL = 0.10
LOW_CONFIDENCE_SKILL = 0.20


def log(message: str) -> None:
    print(f"[train] {message}", flush=True)


def fit_trend(years: np.ndarray, yields: np.ndarray) -> np.poly1d:
    return np.poly1d(np.polyfit(years, np.log(yields), 1))


def fit_scaler(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=0)
    scale = np.where(scale > 0, scale, 1.0)
    return mean, scale


def transform(matrix: np.ndarray, mean: np.ndarray,
              scale: np.ndarray) -> np.ndarray:
    return (matrix - mean) / scale


def fit_ridge_cv(matrix: np.ndarray, target: np.ndarray) -> dict:
    design = np.column_stack([np.ones(len(matrix)), matrix])
    gram = design.T @ design
    rhs = design.T @ target
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    best = None
    for alpha in ALPHAS:
        inverse = np.linalg.pinv(gram + alpha * penalty)
        beta = inverse @ rhs
        fitted = design @ beta
        leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
        denom = np.clip(1.0 - leverage, 1e-8, None)
        loo_mse = float(np.mean(((target - fitted) / denom) ** 2))
        if best is None or loo_mse < best[0]:
            best = (loo_mse, float(alpha), beta)
    return {
        "alpha": best[1], "intercept": float(best[2][0]),
        "coef": np.asarray(best[2][1:], dtype=float),
    }


def evaluate(truth: np.ndarray, prediction: np.ndarray,
             baseline: np.ndarray) -> dict:
    error = truth - prediction
    base_error = truth - baseline
    recent = slice(-min(RECENT_FOLDS, len(truth)), None)
    rmse = float(np.sqrt(np.mean(error ** 2)))
    base_rmse = float(np.sqrt(np.mean(base_error ** 2)))
    recent_rmse = float(np.sqrt(np.mean(error[recent] ** 2)))
    recent_base = float(np.sqrt(np.mean(base_error[recent] ** 2)))
    dev_true = truth - baseline
    dev_pred = prediction - baseline
    ss_total = float(np.sum((dev_true - dev_true.mean()) ** 2))
    ss_error = float(np.sum((dev_true - dev_pred) ** 2))
    return {
        "rmse": rmse,
        "mae": float(np.mean(np.abs(error))),
        "baseline_rmse": base_rmse,
        "skill_vs_trend": 1 - rmse / base_rmse if base_rmse else float("nan"),
        "recent_rmse": recent_rmse,
        "recent_baseline_rmse": recent_base,
        "recent_skill_vs_trend": (
            1 - recent_rmse / recent_base if recent_base else float("nan")),
        "detrended_r2": 1 - ss_error / ss_total if ss_total else float("nan"),
        "recent_trend_bias": float(np.mean(baseline[recent] - truth[recent])),
    }


def forward_cv(frame: pd.DataFrame, features: list[str], min_train: int) -> dict:
    years = frame.year.to_numpy(dtype=float)
    yields = frame.yield_kg_ha.to_numpy(dtype=float)
    matrix = frame[features].to_numpy(dtype=float)
    truth, prediction, baseline, used = [], [], [], []

    for i, year in enumerate(years):
        train = years < year
        if train.sum() < min_train:
            continue
        trend = fit_trend(years[train], yields[train])
        mean, scale = fit_scaler(matrix[train])
        scaled = transform(matrix[train], mean, scale)
        residual = np.log(yields[train]) - trend(years[train])
        model = fit_ridge_cv(scaled, residual)
        current = transform(matrix[i:i + 1], mean, scale)[0]
        weather = float(model["intercept"] + current @ model["coef"])
        truth.append(yields[i])
        baseline.append(float(np.exp(trend(year))))
        prediction.append(float(np.exp(trend(year) + weather)))
        used.append(int(year))
    if not truth:
        raise ValueError(f"no forward folds after {min_train} training seasons")
    arrays = {
        "truth": np.asarray(truth), "prediction": np.asarray(prediction),
        "baseline": np.asarray(baseline), "years": used,
    }
    arrays["metrics"] = evaluate(
        arrays["truth"], arrays["prediction"], arrays["baseline"])
    return arrays


def train_one(cfg) -> dict | None:
    if cfg.label_resolution == "blocked" or not province_available():
        log(f"{cfg.key}: labels blocked — skip (see labels.md)")
        return None

    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(path):
        log(f"{cfg.key}: no training table, skipped")
        return None

    frame = pd.read_csv(path).sort_values("year")
    all_features = sorted(set().union(*cfg.feature_sets.values()))
    frame = frame.dropna(
        subset=["yield_kg_ha"] + all_features).reset_index(drop=True)
    if len(frame) < cfg.min_train + 5:
        log(f"{cfg.key}: only {len(frame)} complete seasons; need "
            f"{cfg.min_train + 5}, skipped")
        return None

    log(f"{cfg.key}: {cfg.label}; {len(frame)} seasons "
        f"{int(frame.year.min())}-{int(frame.year.max())}")
    runs = {}
    for name, features in cfg.feature_sets.items():
        out = forward_cv(frame, features, cfg.min_train)
        runs[name] = out
        m = out["metrics"]
        log(f"  {name:24} folds={len(out['years']):2d} "
            f"RMSE={m['rmse']:7.1f} recent={m['recent_rmse']:7.1f} "
            f"vs trend={m['skill_vs_trend']:+7.1%} "
            f"recent={m['recent_skill_vs_trend']:+7.1%}")

    eligible = [
        name for name, run in runs.items()
        if run["metrics"]["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL
        and run["metrics"]["recent_skill_vs_trend"] >= MIN_OPERATIONAL_SKILL
    ]
    selection_pool = eligible or list(runs)
    best_name = min(
        selection_pool, key=lambda n: runs[n]["metrics"]["recent_rmse"])
    best = runs[best_name]
    metrics = best["metrics"]
    beats_trend = bool(eligible)

    features = cfg.feature_sets[best_name]
    years = frame.year.to_numpy(dtype=float)
    yields = frame.yield_kg_ha.to_numpy(dtype=float)
    matrix = frame[features].to_numpy(dtype=float)
    trend = fit_trend(years, yields)
    scaler_mean, scaler_scale = fit_scaler(matrix)
    final = fit_ridge_cv(
        transform(matrix, scaler_mean, scaler_scale),
        np.log(yields) - trend(years))

    ranked = sorted(
        zip(features, final["coef"]), key=lambda item: -abs(item[1]))
    residual_abs = np.abs(best["truth"] - best["prediction"])
    q68 = float(np.quantile(residual_abs, 0.68, method="higher"))
    q95 = float(np.quantile(residual_abs, 0.95, method="higher"))

    artifact = {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "crop": "banana",
        "country": cfg.country,
        "doc": cfg.doc,
        "caveat": cfg.caveat,
        "hurricane_prone": cfg.hurricane_prone,
        "target": {
            "variable": "yield_kg_ha",
            "source": "province statistical offices (area-weighted)",
        },
        "trained_years": [int(years.min()), int(years.max())],
        "n_seasons": int(len(frame)),
        "feature_sets": cfg.feature_sets,
        "selected_feature_set": best_name,
        "selected_features": features,
        "minimum_operational_skill": MIN_OPERATIONAL_SKILL,
        "operational_choice": "ridge_weather" if beats_trend else "trend_only",
        "beats_trend": bool(beats_trend),
        "low_confidence": bool(
            metrics["recent_skill_vs_trend"] < LOW_CONFIDENCE_SKILL),
        "trend": {
            "form": "log_linear",
            "log_poly_coef": [float(v) for v in trend.coefficients],
        },
        "scaler": {
            "mean": scaler_mean.tolist(),
            "scale": scaler_scale.tolist(),
        },
        "ridge": {
            "alpha": final["alpha"],
            "coef": final["coef"].tolist(),
            "intercept": final["intercept"],
        },
        "top_effects": [
            {"feature": name,
             "effect_pct_per_sd": round((np.exp(value) - 1) * 100, 2)}
            for name, value in ranked
        ],
        "uncertainty": {
            "basis": "absolute errors from forward-chaining predictions",
            "absolute_error_q68_kg_ha": q68,
            "absolute_error_q95_kg_ha": q95,
            "n_forward_errors": len(residual_abs),
        },
        "validation": {
            name: {**run["metrics"], "features": cfg.feature_sets[name],
                   "fold_years": run["years"]}
            for name, run in runs.items()
        },
    }

    os.makedirs(MODELS, exist_ok=True)
    model_path = os.path.join(MODELS, f"{cfg.key}.json")
    with open(model_path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
    verdict = "usable weather challenger" if beats_trend else "trend only"
    log(f"  selected={best_name}; verdict={verdict}; wrote {model_path}")
    return artifact


def main() -> int:
    keys = sys.argv[1:]
    unknown = [key for key in keys if key not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown config(s): {', '.join(unknown)}")
    configs = [BY_KEY[key] for key in keys] if keys else ALL
    refresh_label_resolution(configs)
    built = [a for a in (train_one(cfg) for cfg in configs) if a is not None]
    log("=" * 72)
    if not built:
        log("no models trained — province CSVs and collect still required")
    for artifact in built:
        selected = artifact["selected_feature_set"]
        score = artifact["validation"][selected]
        log(f"{artifact['key']:28} {artifact['operational_choice']:13} "
            f"recent skill {score['recent_skill_vs_trend']:+.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
