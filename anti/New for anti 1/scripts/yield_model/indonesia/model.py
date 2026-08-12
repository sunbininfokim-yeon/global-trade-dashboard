"""Numpy-only trend + weather ridge model with strict forward validation."""

import math

import numpy as np


ALPHAS = np.logspace(-2, 4, 24)
RECENT_FOLDS = 5
MIN_OPERATIONAL_SKILL = 0.10
MIN_WEATHER_SEASONS = 25
SEASONS_PER_WEATHER_PARAMETER = 5
MAX_PUBLISH_MAPE = 0.15
TREND_FORMS = {
    "full_linear": {"degree": 1, "window": None},
    "full_quadratic": {"degree": 2, "window": None},
    "recent_20_linear": {"degree": 1, "window": 20},
    "recent_15_linear": {"degree": 1, "window": 15},
    "recent_10_linear": {"degree": 1, "window": 10},
}


def _tail(years, values, window=None, x=None):
    start = max(0, len(years) - window) if window else 0
    result = (np.asarray(years, float)[start:], np.asarray(values, float)[start:])
    if x is None:
        return result
    return result + (np.asarray(x, float)[start:],)


def fit_trend(years, values, degree=1, window=None):
    years, values = _tail(years, values, window)
    return np.poly1d(np.polyfit(years, np.log(values), degree))


def _ridge_fit(x, y, alpha):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    y_mean = float(y.mean())
    lhs = z.T @ z + float(alpha) * np.eye(z.shape[1])
    coef = np.linalg.solve(lhs, z.T @ (y - y_mean))
    return {"mean": mean, "scale": scale, "coef": coef,
            "intercept": y_mean, "alpha": float(alpha)}


def _ridge_predict(model, x):
    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    z = (x - model["mean"]) / model["scale"]
    return model["intercept"] + z @ model["coef"]


def select_alpha(x, y):
    """Choose ridge strength by leave-one-out inside the training fold."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(y) < 6:
        return 10.0
    scores = []
    for alpha in ALPHAS:
        errors = []
        for i in range(len(y)):
            train = np.arange(len(y)) != i
            fitted = _ridge_fit(x[train], y[train], alpha)
            pred = float(_ridge_predict(fitted, x[i])[0])
            errors.append((pred - y[i]) ** 2)
        scores.append(float(np.mean(errors)))
    return float(ALPHAS[int(np.argmin(scores))])


def evaluate(truth, predicted, baseline, years):
    truth = np.asarray(truth, float)
    predicted = np.asarray(predicted, float)
    baseline = np.asarray(baseline, float)
    recent_n = min(RECENT_FOLDS, len(truth))
    recent = slice(-recent_n, None)
    rmse = float(np.sqrt(np.mean((truth - predicted) ** 2)))
    base_rmse = float(np.sqrt(np.mean((truth - baseline) ** 2)))
    recent_rmse = float(np.sqrt(np.mean((truth[recent] - predicted[recent]) ** 2)))
    recent_base = float(np.sqrt(np.mean((truth[recent] - baseline[recent]) ** 2)))
    mape = float(np.mean(np.abs((truth - predicted) / truth)))
    base_mape = float(np.mean(np.abs((truth - baseline) / truth)))
    recent_mape = float(np.mean(np.abs((truth[recent] - predicted[recent]) / truth[recent])))
    recent_base_mape = float(np.mean(np.abs((truth[recent] - baseline[recent]) / truth[recent])))
    latest_ape = float(abs(predicted[-1] - truth[-1]) / truth[-1])
    latest_base_ape = float(abs(baseline[-1] - truth[-1]) / truth[-1])
    skill = 1 - recent_rmse / recent_base if recent_base > 0 else float("nan")
    deviations = truth - baseline
    explained = predicted - baseline
    ss_res = float(np.sum((deviations - explained) ** 2))
    ss_tot = float(np.sum((deviations - deviations.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "rmse": rmse, "baseline_rmse": base_rmse,
        "recent_rmse": recent_rmse, "recent_baseline_rmse": recent_base,
        "mape": mape, "baseline_mape": base_mape,
        "recent_mape": recent_mape,
        "recent_baseline_mape": recent_base_mape,
        "latest_ape": latest_ape,
        "latest_baseline_ape": latest_base_ape,
        "skill_vs_trend": skill, "detrended_r2": r2,
        "n_folds": len(truth), "recent_folds": recent_n,
        "years": [int(min(years)), int(max(years))],
    }


def forward_validate(frame, target, features, min_train=10, degree=1, window=None):
    years = frame.year.to_numpy(dtype=float)
    values = frame[target].to_numpy(dtype=float)
    x = frame[features].to_numpy(dtype=float) if features else None
    truth, predicted, baseline, used = [], [], [], []
    for i in range(min_train, len(frame)):
        trend = fit_trend(years[:i], values[:i], degree=degree, window=window)
        base = float(np.exp(trend(years[i])))
        if features:
            fit_years, fit_values, fit_x = _tail(
                years[:i], values[:i], window=window, x=x[:i])
            residual = np.log(fit_values) - trend(fit_years)
            alpha = select_alpha(fit_x, residual)
            ridge = _ridge_fit(fit_x, residual, alpha)
            shock = float(_ridge_predict(ridge, x[i])[0])
            pred = float(np.exp(trend(years[i]) + shock))
        else:
            pred = base
        truth.append(values[i])
        predicted.append(pred)
        baseline.append(base)
        used.append(int(years[i]))
    if not truth:
        return None
    return evaluate(truth, predicted, baseline, used)


def train_target(frame, target, feature_sets, min_train=10):
    feature_sets = dict(feature_sets)
    feature_sets.setdefault("trend_only", [])
    required = sorted(set(sum(feature_sets.values(), [])))
    trend_usable = frame.dropna(subset=[target]).sort_values("year").reset_index(drop=True)
    weather_usable = frame.dropna(
        subset=[target] + required).sort_values("year").reset_index(drop=True)
    if len(trend_usable) < min_train + 5:
        return None

    validation = {}
    configurations = {}
    for feature_name, features in feature_sets.items():
        usable = weather_usable if features else trend_usable
        if len(usable) < min_train + 5:
            continue
        for trend_name, trend_form in TREND_FORMS.items():
            name = feature_name + "__" + trend_name
            result = forward_validate(
                usable, target, features, min_train=min_train, **trend_form)
            if result is not None:
                validation[name] = result
                configurations[name] = {
                    "feature_set": feature_name, "features": features,
                    "trend_name": trend_name, **trend_form,
                }
    if not validation:
        return None

    trend_names = [name for name, config in configurations.items()
                   if not config["features"]]
    weather_names = [name for name, config in configurations.items()
                     if config["features"]]
    best_trend_name = min(
        trend_names, key=lambda name: validation[name]["recent_rmse"])
    best_weather_name = (min(
        weather_names, key=lambda name: validation[name]["recent_rmse"])
        if weather_names else None)
    candidate = configurations[best_weather_name] if best_weather_name else None
    candidate_score = validation[best_weather_name] if best_weather_name else None
    required_weather_seasons = (
        max(MIN_WEATHER_SEASONS,
            SEASONS_PER_WEATHER_PARAMETER * (len(candidate["features"]) + 1))
        if candidate else None)
    enough_weather_data = bool(
        candidate and len(weather_usable) >= required_weather_seasons)
    enough_weather_skill = bool(
        candidate_score and
        candidate_score["skill_vs_trend"] >= MIN_OPERATIONAL_SKILL)
    beats_trend = bool(enough_weather_data and enough_weather_skill)
    best_name = best_weather_name if beats_trend else best_trend_name
    selected = configurations[best_name]
    best_features = selected["features"]
    best = validation[best_name]
    usable = weather_usable if beats_trend else trend_usable

    if not candidate:
        climate_status = "not_evaluated_no_weather_features"
    elif not enough_weather_data:
        climate_status = "stopped_insufficient_sample"
    elif not enough_weather_skill:
        climate_status = "stopped_no_incremental_skill"
    else:
        climate_status = "weather_adjustment_validated"

    years = usable.year.to_numpy(dtype=float)
    values = usable[target].to_numpy(dtype=float)
    fit_years, fit_values = _tail(years, values, selected["window"])
    trend = fit_trend(
        years, values, degree=selected["degree"], window=selected["window"])
    ridge_payload = None
    if beats_trend and best_features:
        x = usable[best_features].to_numpy(dtype=float)
        _, _, fit_x = _tail(years, values, selected["window"], x=x)
        residual = np.log(fit_values) - trend(fit_years)
        alpha = select_alpha(fit_x, residual)
        ridge = _ridge_fit(fit_x, residual, alpha)
        ridge_payload = {
            "alpha": ridge["alpha"],
            "mean": ridge["mean"].tolist(),
            "scale": ridge["scale"].tolist(),
            "coef": ridge["coef"].tolist(),
            "intercept": ridge["intercept"],
            "effect_per_scaled_sd_pct": [
                (math.exp(float(value)) - 1) * 100 for value in ridge["coef"]
            ],
        }

    sigma = (best["recent_rmse"] if beats_trend
             else best["recent_baseline_rmse"])
    operational_mape = (
        best["recent_mape"] if beats_trend else best["recent_baseline_mape"])
    operational_latest_ape = (
        best["latest_ape"] if beats_trend else best["latest_baseline_ape"])
    publishable = bool(
        best["recent_folds"] >= 5 and
        operational_mape <= MAX_PUBLISH_MAPE and
        operational_latest_ape <= MAX_PUBLISH_MAPE)
    return {
        "target": target,
        "trained_years": [int(years.min()), int(years.max())],
        "n_seasons": len(usable),
        "fit_years": [int(fit_years.min()), int(fit_years.max())],
        "trend": {
            "name": selected["trend_name"],
            "degree": selected["degree"],
            "window": selected["window"],
            "log_poly_coef": trend.coefficients.tolist(),
        },
        "configuration": best_name,
        "feature_set": selected["feature_set"],
        "features": best_features,
        "ridge": ridge_payload,
        "beats_trend": beats_trend,
        "minimum_operational_skill": MIN_OPERATIONAL_SKILL,
        "climate_gate": {
            "status": climate_status,
            "candidate_configuration": best_weather_name,
            "candidate_features": candidate["features"] if candidate else [],
            "available_seasons": len(weather_usable),
            "required_seasons": required_weather_seasons,
            "candidate_skill_vs_trend": (
                candidate_score["skill_vs_trend"] if candidate_score else None),
        },
        "forecast_gate": {
            "publishable": publishable,
            "recent_operational_mape": operational_mape,
            "latest_operational_ape": operational_latest_ape,
            "maximum_publish_mape": MAX_PUBLISH_MAPE,
            "status": ("publishable_baseline" if publishable
                       else "stopped_poor_recent_backtest"),
        },
        "validation": validation,
        "uncertainty": {
            "sigma": float(sigma),
            "basis": ("recent forward-chaining model RMSE" if beats_trend
                      else "recent forward-chaining trend-only RMSE"),
        },
    }


def predict_target(model, year, feature_values):
    coefficients = model["trend"].get(
        "log_poly_coef", model["trend"].get("log_linear_coef"))
    trend = np.poly1d(coefficients)
    trend_value = float(np.exp(trend(year)))
    candidate_shock = 0.0
    if model["features"] and model["ridge"]:
        ridge = model["ridge"]
        fitted = {
            "mean": np.asarray(ridge["mean"], float),
            "scale": np.asarray(ridge["scale"], float),
            "coef": np.asarray(ridge["coef"], float),
            "intercept": float(ridge["intercept"]),
        }
        row = np.asarray([feature_values[name] for name in model["features"]], float)
        candidate_shock = float(_ridge_predict(fitted, row)[0])
    applied_shock = candidate_shock if model["beats_trend"] else 0.0
    point = float(np.exp(trend(year) + applied_shock))
    sigma = float(model["uncertainty"]["sigma"])
    return {
        "point": point, "trend": trend_value,
        "weather_effect": point - trend_value,
        "candidate_weather_effect": float(np.exp(trend(year) + candidate_shock) - trend_value),
        "sigma": sigma,
        "range_68": [max(0.0, point - sigma), point + sigma],
        "range_95": [max(0.0, point - 1.96 * sigma), point + 1.96 * sigma],
    }
