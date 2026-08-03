"""Assemble observed/forecast/climatology weather and predict a season."""

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import climate as C
from .collect import blend_features
from .data import load_oni, oni_for, point_forecast, point_weather
from .model import predict_target
from .regions import ALL, BY_KEY


HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")


def log(message):
    print("[indonesia:predict] " + message, flush=True)


def live_daily(point, year):
    history = point_weather(point)
    try:
        forecast = point_forecast(point)
    except Exception as exc:
        log("{} forecast unavailable; climatology used ({})".format(point["name"], exc))
        forecast = None
    return C.fill_calendar(history, year, forecast)


def anomaly_row(cfg, year, live_raw, oni):
    training = pd.read_csv(os.path.join(TRAINING, cfg.key + ".csv"))
    result = {}
    for name, value in live_raw.items():
        if name not in training:
            continue
        prior = training[training.year < year].sort_values("year").tail(20)[name].dropna()
        if len(prior) < 20 or prior.std(ddof=1) == 0:
            result[name + "_anom"] = np.nan
        else:
            result[name + "_anom"] = float((value - prior.mean()) / prior.std(ddof=1))
    result["oni_season"] = oni_for(oni, year)
    return result, training


def _inflate_ranges(result, observed_share):
    factor = 1 + 0.5 * (1 - observed_share)
    sigma = result["sigma"] * factor
    point = result["point"]
    result["base_sigma"] = result["sigma"]
    result["sigma"] = sigma
    result["range_68"] = [max(0.0, point - sigma), point + sigma]
    result["range_95"] = [max(0.0, point - 1.96 * sigma), point + 1.96 * sigma]
    return result


def predict_crop(cfg, year):
    model_path = os.path.join(MODELS, cfg.key + ".json")
    if not os.path.exists(model_path):
        return {"key": cfg.key, "error": "model artifact missing"}
    with open(model_path, encoding="utf-8") as handle:
        artifact = json.load(handle)

    weather_applied = any(
        target["beats_trend"] for target in artifact["targets"].values())
    if weather_applied:
        dailies = {point["name"]: live_daily(point, year) for point in cfg.points}
        raw = blend_features(cfg, dailies, year)
        features, training = anomaly_row(cfg, year, raw, load_oni())
        counts, observed_share = C.critical_progress(
            next(iter(dailies.values())), year, cfg.critical_window)
        latest_observed = max(
            daily.loc[daily.source.eq("observed"), "date"].max()
            for daily in dailies.values())
    else:
        # A rejected climate model must not trigger a live-weather adjustment.
        dailies, raw, features = {}, {}, {}
        training = pd.read_csv(os.path.join(TRAINING, cfg.key + ".csv"))
        counts = {"observed": 0, "forecast": 0, "climatology": 0}
        observed_share = 1.0
        latest_observed = pd.NaT

    missing = sorted({name for target in artifact["targets"].values()
                      for name in target["features"]
                      if name not in features or pd.isna(features[name])})
    if missing:
        return {"key": cfg.key, "error": "missing live features: " + ", ".join(missing)}

    predictions = {}
    for name, target_model in artifact["targets"].items():
        prediction = _inflate_ranges(
            predict_target(target_model, year, features), observed_share)
        prediction["forecast_gate"] = target_model["forecast_gate"]
        prediction["climate_gate"] = target_model["climate_gate"]
        predictions[name] = prediction

    labelled = training.dropna(subset=["yield_kg_ha"]).sort_values("year")
    last = labelled.iloc[-1]
    crosscheck = None
    if ("yield" in predictions and "area" in predictions and
            predictions["yield"]["forecast_gate"]["publishable"] and
            predictions["area"]["forecast_gate"]["publishable"]):
        crosscheck = predictions["yield"]["point"] * predictions["area"]["point"] / 1000.0

    return {
        "key": cfg.key, "label": cfg.label, "label_ko": cfg.label_ko,
        "season": year, "unit": "kg/ha", "features": features,
        "raw_features": raw, "targets": predictions,
        "production_crosscheck_tonnes": crosscheck,
        "last_actual": {
            "year": int(last.year), "yield_kg_ha": float(last.yield_kg_ha),
            "area_ha": float(last.area_ha),
            "production_tonnes": float(last.production_tonnes),
            "flags": {"yield": last.get("yield_flag"), "area": last.get("area_flag"),
                      "production": last.get("production_flag")},
        },
        "season_progress": {"critical_days": counts, "observed_share": observed_share},
        "weather_through": (latest_observed.date().isoformat()
                            if pd.notna(latest_observed) else None),
        "doc": cfg.doc, "caveat": cfg.caveat,
        "non_weather_drivers": cfg.non_weather_drivers,
    }


def main():
    args = list(sys.argv[1:])
    year = date.today().year
    if "--year" in args:
        index = args.index("--year")
        year = int(args[index + 1])
        del args[index:index + 2]
    configs = [BY_KEY[key] for key in args] if args else ALL
    for cfg in configs:
        result = predict_crop(cfg, year)
        if "error" in result:
            log("{}: {}".format(cfg.key, result["error"]))
            continue
        production = result["targets"]["production"]
        yield_result = result["targets"]["yield"]
        log("{}: {:,.0f} t ({:,.0f}-{:,.0f}), yield {:,.0f} kg/ha".format(
            cfg.label, production["point"], production["range_68"][0],
            production["range_68"][1], yield_result["point"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
