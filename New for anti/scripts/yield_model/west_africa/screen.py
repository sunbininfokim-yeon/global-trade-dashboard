"""Forward-validation screen for whether climate adds information beyond trend.

This is a feasibility experiment, not the final operational model. It reports all
predeclared feature groups and deliberately does not publish a live forecast.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
MODELS = HERE / "models"
ALPHAS = np.logspace(-2, 4, 40)
FEATURE_SETS = {
    "water_balance": [
        "cocoa_year_rain_mm", "cocoa_year_root_wetness",
        "max_dry_spell_days", "harmattan_vpd_mean",
    ],
    "harmattan": [
        "harmattan_rain_mm", "harmattan_rh_mean", "harmattan_vpd_mean",
        "harmattan_wind_mean", "harmattan_root_wetness",
    ],
    "wet_disease_weather_proxy": [
        "wet_season_rain_mm", "wet_days_ge_10mm", "humid_wet_days_proxy",
        "wet_season_root_wetness",
    ],
    "combined_minimal": [
        "harmattan_vpd_mean", "harmattan_root_wetness",
        "wet_season_rain_mm", "humid_wet_days_proxy",
    ],
}


def fit_trend(years, target):
    return np.poly1d(np.polyfit(years, np.log(target), 1))


def fit_scaler(matrix):
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=0)
    return mean, np.where(scale > 0, scale, 1.0)


def fit_ridge_cv(matrix, target):
    design = np.column_stack([np.ones(len(matrix)), matrix])
    gram = design.T @ design
    rhs = design.T @ target
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0
    best = None
    for alpha in ALPHAS:
        inverse = np.linalg.pinv(gram + alpha * penalty)
        beta = inverse @ rhs
        fitted = design @ beta
        leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
        loo = (target - fitted) / np.clip(1 - leverage, 1e-8, None)
        score = float(np.mean(loo ** 2))
        if best is None or score < best[0]:
            best = (score, float(alpha), beta)
    return best[1], best[2]


def metrics(truth, prediction, baseline, recent_folds=8):
    truth = np.asarray(truth)
    prediction = np.asarray(prediction)
    baseline = np.asarray(baseline)
    recent = slice(-min(recent_folds, len(truth)), None)
    rmse = float(np.sqrt(np.mean((truth - prediction) ** 2)))
    base = float(np.sqrt(np.mean((truth - baseline) ** 2)))
    recent_rmse = float(np.sqrt(np.mean((truth[recent] - prediction[recent]) ** 2)))
    recent_base = float(np.sqrt(np.mean((truth[recent] - baseline[recent]) ** 2)))
    return {
        "rmse": rmse,
        "trend_rmse": base,
        "skill_vs_trend": 1 - rmse / base if base else None,
        "recent_rmse": recent_rmse,
        "recent_trend_rmse": recent_base,
        "recent_skill_vs_trend": 1 - recent_rmse / recent_base if recent_base else None,
    }


def forward_screen(frame, target_name, features, min_train=20):
    clean = frame.dropna(subset=[target_name] + features).sort_values("year")
    years = clean.year.to_numpy(dtype=float)
    target = clean[target_name].to_numpy(dtype=float)
    matrix = clean[features].to_numpy(dtype=float)
    truth, prediction, baseline, fold_years = [], [], [], []
    for index, year in enumerate(years):
        train = years < year
        if train.sum() < min_train:
            continue
        trend = fit_trend(years[train], target[train])
        mean, scale = fit_scaler(matrix[train])
        scaled = (matrix[train] - mean) / scale
        residual = np.log(target[train]) - trend(years[train])
        _, beta = fit_ridge_cv(scaled, residual)
        current = (matrix[index] - mean) / scale
        weather = float(beta[0] + current @ beta[1:])
        truth.append(float(target[index]))
        baseline.append(float(np.exp(trend(year))))
        prediction.append(float(np.exp(trend(year) + weather)))
        fold_years.append(int(year))
    result = metrics(truth, prediction, baseline)
    result["fold_years"] = fold_years
    result["features"] = features
    result["n_complete_seasons"] = int(len(clean))
    return result


def screen_table(path, country, target_name, label):
    frame = pd.read_csv(path)
    frame = frame[frame.country.eq(country)].copy()
    runs = {
        name: forward_screen(frame, target_name, features)
        for name, features in FEATURE_SETS.items()
    }
    passes = [name for name, result in runs.items()
              if result["skill_vs_trend"] is not None
              and result["skill_vs_trend"] >= 0.10
              and result["recent_skill_vs_trend"] >= 0.10]
    status = "robust_candidate" if len(passes) >= 2 else (
        "candidate_signal" if passes else "no_validated_climate_gain")
    return {
        "country": country,
        "target": target_name,
        "label": label,
        "status": status,
        "passing_feature_sets": passes,
        "minimum_skill_gate": 0.10,
        "runs": runs,
        "warning": (
            "Feasibility screen only. Feature groups share reported folds, recent spatial "
            "weights are held fixed, and the final operational model requires nested source, "
            "calendar and satellite-mask validation."
        ),
    }


def forward_panel_screen(frame, features, min_train=20):
    clean = frame.dropna(subset=["purchases_tonnes"] + features).copy()
    clean = clean.sort_values(["year", "region"])
    years = sorted(clean.year.unique())
    truth, prediction, baseline, fold_years = [], [], [], []
    for year in years:
        train = clean[clean.year < year]
        current = clean[clean.year == year]
        counts = train.groupby("region").year.nunique()
        if current.empty or counts.empty or counts.min() < min_train:
            continue
        trends = {}
        residuals = []
        for region, group in train.groupby("region"):
            trend = fit_trend(
                group.year.to_numpy(dtype=float),
                group.purchases_tonnes.to_numpy(dtype=float))
            trends[region] = trend
            values = np.log(group.purchases_tonnes.to_numpy(dtype=float)) - trend(
                group.year.to_numpy(dtype=float))
            residuals.extend(zip(group.index, values))
        train_matrix = train[features].to_numpy(dtype=float)
        mean, scale = fit_scaler(train_matrix)
        residual_map = dict(residuals)
        residual = np.asarray([residual_map[index] for index in train.index])
        _, beta = fit_ridge_cv((train_matrix - mean) / scale, residual)
        observed_total = predicted_total = baseline_total = 0.0
        for _, row in current.iterrows():
            region = row.region
            if region not in trends:
                continue
            trend_value = float(trends[region](year))
            current_features = row[features].to_numpy(dtype=float)
            weather = float(beta[0] + ((current_features - mean) / scale) @ beta[1:])
            observed_total += float(row.purchases_tonnes)
            baseline_total += float(np.exp(trend_value))
            predicted_total += float(np.exp(trend_value + weather))
        if observed_total:
            truth.append(observed_total)
            baseline.append(baseline_total)
            prediction.append(predicted_total)
            fold_years.append(int(year))
    result = metrics(truth, prediction, baseline)
    result["fold_years"] = fold_years
    result["features"] = features
    result["n_region_years"] = int(len(clean))
    result["n_regions"] = int(clean.region.nunique())
    return result


def screen_panel(path):
    frame = pd.read_csv(path)
    runs = {name: forward_panel_screen(frame, features)
            for name, features in FEATURE_SETS.items()}
    passes = [name for name, result in runs.items()
              if result["skill_vs_trend"] is not None
              and result["skill_vs_trend"] >= 0.10
              and result["recent_skill_vs_trend"] >= 0.10]
    status = "robust_candidate" if len(passes) >= 2 else (
        "candidate_signal" if passes else "no_validated_climate_gain")
    return {
        "country": "Ghana", "target": "regional_purchases_tonnes",
        "label": "COCOBOD regional crop-year purchases; yearly predictions summed nationally",
        "status": status, "passing_feature_sets": passes,
        "minimum_skill_gate": 0.10, "runs": runs,
        "warning": (
            "Region-specific trends are fitted inside each year fold. Climate response is pooled; "
            "region definitions and purchases-versus-production semantics still require audit."),
    }


def main():
    results = [
        screen_table(
            TRAINING / "cocoa_faostat_country.csv", "Côte d'Ivoire",
            "production_tonnes", "FAOSTAT national calendar-year production"),
        screen_table(
            TRAINING / "cocoa_faostat_country.csv", "Ghana",
            "production_tonnes", "FAOSTAT national calendar-year production"),
        screen_table(
            TRAINING / "cocoa_faostat_country.csv", "Côte d'Ivoire",
            "yield_kg_ha", "FAOSTAT national calendar-year yield"),
        screen_table(
            TRAINING / "cocoa_faostat_country.csv", "Ghana",
            "yield_kg_ha", "FAOSTAT national calendar-year yield"),
        screen_table(
            TRAINING / "ghana_cocoa_purchases.csv", "Ghana",
            "purchases_tonnes", "COCOBOD crop-year regional purchases summed nationally"),
        screen_panel(TRAINING / "ghana_cocoa_regional_purchases.csv"),
    ]
    MODELS.mkdir(parents=True, exist_ok=True)
    output = MODELS / "feasibility_screen.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print("{} {}: {}".format(result["country"], result["target"], result["status"]))
        for name, run in result["runs"].items():
            print("  {:27} folds={:2d} skill={:+.1%} recent={:+.1%}".format(
                name, len(run["fold_years"]), run["skill_vs_trend"],
                run["recent_skill_vs_trend"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
