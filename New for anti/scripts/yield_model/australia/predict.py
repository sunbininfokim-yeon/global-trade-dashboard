"""Issue leakage-safe in-season Australian forecasts from trained artifacts."""

from __future__ import annotations

import json
import os
from datetime import date

import numpy as np
import pandas as pd

from .collect import load_dmi, load_oni, load_sam, point_weather


HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")


def _scenario_daily(daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                    lag: int) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Fill each missing day from one intact historical-year weather path."""
    current = daily[(daily.date >= start) & (daily.date <= end)].copy()
    observed_through = current.date.max() if not current.empty else None
    columns = ["tmax", "tmin", "tmean", "precip", "gwetroot", "tdew", "solar"]
    lookup = daily.set_index("date")[columns]
    rows = []
    for target_date in pd.date_range(start, end, freq="D"):
        source_date = target_date if target_date in lookup.index else None
        if source_date is None:
            try:
                source_date = target_date.replace(year=target_date.year - lag)
            except ValueError:  # 29 February in a non-leap scenario year
                source_date = target_date.replace(year=target_date.year - lag, day=28)
        if source_date not in lookup.index:
            raise ValueError(f"missing scenario weather for {source_date.date()}")
        values = lookup.loc[source_date]
        rows.append({"date": target_date,
                     **{column: float(values[column]) for column in columns}})
    return pd.DataFrame(rows), observed_through


def _blend_scenario(cfg, year: int, lag: int) -> tuple[dict, pd.Timestamp | None]:
    sums, weights = {}, {}
    observed_dates = []
    for point in cfg.points:
        if cfg.harvest_rule == "winter":
            start, end = pd.Timestamp(year, 1, 1), pd.Timestamp(year, 11, 30)
        else:
            start, end = pd.Timestamp(year - 1, 9, 1), pd.Timestamp(year, 5, 31)
        full, observed = _scenario_daily(point_weather(point), start, end, lag)
        if observed is not None:
            observed_dates.append(observed)
        features = cfg.build(full, year)
        for key, value in features.items():
            if pd.isna(value):
                continue
            sums[key] = sums.get(key, 0.0) + float(value) * point["weight"]
            weights[key] = weights.get(key, 0.0) + point["weight"]
    blended = {key: sums[key] / weights[key] for key in sums if weights[key]}
    return blended, min(observed_dates) if observed_dates else None


def _scenario_monthly(frame: pd.DataFrame, year: int, months: list[int],
                      lag: int) -> float:
    values = []
    for month in months:
        current = frame[(frame.year == year) & (frame.month == month)].value
        if not current.empty:
            values.append(float(current.iloc[-1]))
            continue
        history = frame[(frame.year == year - lag)
                        & (frame.month == month)].value
        if not history.empty:
            values.append(float(history.mean()))
    return float(np.mean(values)) if values else float("nan")


def _scenario_oni(oni: pd.DataFrame, year: int, seasons: list[str],
                  lag: int) -> float:
    values = []
    for season in seasons:
        current = oni[(oni.year == year) & (oni.season == season)].value
        if not current.empty:
            values.append(float(current.iloc[-1]))
            continue
        history = oni[(oni.year == year - lag)
                      & (oni.season == season)].value
        if not history.empty:
            values.append(float(history.mean()))
    return float(np.mean(values)) if values else float("nan")


def _anomalies(raw: dict, history: pd.DataFrame,
               selected: list[str], year: int) -> dict:
    out = {}
    prior = history[history.year < year].sort_values("year").tail(20)
    for name in selected:
        if not name.endswith("_z20"):
            raise ValueError(f"live feature is not a causal anomaly: {name}")
        source = name[:-4]
        values = prior[source].dropna()
        if len(values) < 10 or values.std(ddof=1) == 0:
            raise ValueError(f"not enough anomaly history for {source}")
        out[name] = (float(raw[source]) - float(values.mean())) / float(values.std(ddof=1))
    return out


def current_season(cfg, today: date | None = None) -> int | None:
    today = today or date.today()
    if cfg.harvest_rule == "winter":
        return today.year
    # Do not forecast next summer cotton before its Sep-Oct pre-sowing window.
    return today.year + 1 if today.month >= 9 else None


def predict_one(cfg, today: date | None = None) -> dict:
    today = today or date.today()
    season = current_season(cfg, today)
    if season is None:
        return {"error": "next summer-crop season has no observed pre-sowing weather yet"}

    model_path = os.path.join(MODELS, f"{cfg.key}.json")
    training_path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(model_path) or not os.path.exists(training_path):
        return {"error": "model or training table missing"}
    with open(model_path, "r", encoding="utf-8") as handle:
        artifact = json.load(handle)
    history = pd.read_csv(training_path)

    selected = artifact["selected_features"]
    mean = np.asarray(artifact["scaler"]["mean"], dtype=float)
    scale = np.asarray(artifact["scaler"]["scale"], dtype=float)
    coef = np.asarray(artifact["ridge"]["coef"], dtype=float)
    trend = float(np.exp(np.polyval(artifact["trend"]["log_poly_coef"], season)))
    dmi, sam, oni = load_dmi(), load_sam(), load_oni()

    vectors, weather_points, observed_dates = [], [], []
    for lag in range(1, 21):
        raw, observed = _blend_scenario(cfg, season, lag)
        if observed is not None:
            observed_dates.append(observed)
        if cfg.harvest_rule == "winter":
            raw.update({
                "iod_winter_spring": _scenario_monthly(
                    dmi, season, [6, 7, 8, 9, 10, 11], lag),
                "sam_winter_spring": _scenario_monthly(
                    sam, season, [6, 7, 8, 9, 10, 11], lag),
                "oni_winter_spring": _scenario_oni(
                    oni, season, ["MJJ", "JJA", "JAS", "ASO", "SON"], lag),
            })
        features = _anomalies(raw, history, selected, season)
        vector = np.asarray([features[name] for name in selected], dtype=float)
        weather_log = (float(artifact["ridge"]["intercept"])
                       + float(((vector - mean) / scale) @ coef))
        vectors.append(vector)
        weather_points.append(float(np.exp(np.log(trend) + weather_log)))

    vectors = np.asarray(vectors)
    vector = np.median(vectors, axis=0)
    weather_points = np.asarray(weather_points)
    weather_point = float(np.median(weather_points))
    observed_through = min(observed_dates) if observed_dates else None
    point = weather_point if artifact["operational_choice"] == "ridge_weather" else trend

    critical_start = pd.Timestamp(season, 4, 1)
    critical_end = pd.Timestamp(season, 11, 30)
    if observed_through is None:
        observed_share = 0.0
    else:
        observed_days = max(0, min((observed_through - critical_start).days + 1,
                                   (critical_end - critical_start).days + 1))
        observed_share = observed_days / ((critical_end - critical_start).days + 1)
    q68 = artifact["uncertainty"]["absolute_error_q68_kg_ha"]
    q95 = artifact["uncertainty"]["absolute_error_q95_kg_ha"]
    scenario_points = (weather_points if artifact["operational_choice"] == "ridge_weather"
                       else np.full(20, trend))
    scenario_q16, scenario_q84 = np.quantile(scenario_points, [0.16, 0.84])
    scenario_q025, scenario_q975 = np.quantile(scenario_points, [0.025, 0.975])

    labelled = history.dropna(subset=["yield_kg_ha"]).sort_values("year")
    last = labelled.iloc[-1]
    contributions = [
        {"feature": name,
         "anomaly": round(float(value), 3),
         "log_contribution": round(float((value - mean[i]) / scale[i] * coef[i]), 4)}
        for i, (name, value) in enumerate(zip(selected, vector))
    ]
    return {
        "season": season,
        "unit": "kg/ha",
        "point": point,
        "range_68": [max(0.0, float(scenario_q16) - q68),
                     float(scenario_q84) + q68],
        "range_95": [max(0.0, float(scenario_q025) - q95),
                     float(scenario_q975) + q95],
        "trend": trend,
        "weather_model_point": weather_point,
        "weather_effect_pct": (weather_point / trend - 1.0) * 100.0,
        "operational_choice": artifact["operational_choice"],
        "low_confidence": artifact["low_confidence"],
        "last_actual": {
            "year": int(last.year), "yield": float(last.yield_kg_ha),
            "status": last.target_status,
        },
        "season_progress": {
            "observed_through": (observed_through.date().isoformat()
                                 if observed_through is not None else None),
            "critical_window_observed": observed_share,
            "future_weather_fill": "20-member historical-year weather ensemble",
            "weather_scenario_count": 20,
            "weather_scenario_p16_p84": [float(scenario_q16), float(scenario_q84)],
            "access_s_integrated": False,
        },
        "features": contributions,
        "skill": artifact["validation"][artifact["selected_feature_set"]],
        "provenance": {
            "target": artifact["target"], "guide": artifact["doc"],
            "caveat": artifact["caveat"],
        },
    }
