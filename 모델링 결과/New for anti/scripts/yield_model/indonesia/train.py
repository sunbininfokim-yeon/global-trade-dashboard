"""Train yield, area and production models for each Indonesian crop."""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

from .model import train_target
from .regions import ALL, BY_KEY


HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")


def log(message):
    print("[indonesia:train] " + message, flush=True)


def anomaly_features(cfg, frame):
    all_features = [column for column in frame if column.endswith("_anom")]
    if "oni_season" in frame and frame.oni_season.notna().all():
        all_features.append("oni_season")
    core = [name + "_anom" for name in cfg.core
            if name + "_anom" in all_features]
    if "oni_season" in all_features:
        core.append("oni_season")
    area = [name + "_anom" for name in cfg.area_core
            if name + "_anom" in all_features]
    if area and "oni_season" in all_features:
        area.append("oni_season")
    return core, all_features, area


def train_crop(cfg):
    path = os.path.join(TRAINING, cfg.key + ".csv")
    if not os.path.exists(path):
        log(cfg.key + ": missing training table")
        return None
    frame = pd.read_csv(path)
    core, all_features, area = anomaly_features(cfg, frame)
    targets = {}
    targets["yield"] = train_target(
        frame, "yield_kg_ha",
        {"trend_only": [], "core": core, "all": all_features}, min_train=10)
    targets["production"] = train_target(
        frame, "production_tonnes",
        {"trend_only": [], "core": core, "all": all_features}, min_train=10)
    targets["area"] = train_target(
        frame, "area_ha", {"trend_only": [], "weather": area}, min_train=10)
    targets = {name: value for name, value in targets.items() if value is not None}
    if not targets:
        log(cfg.key + ": no target had enough complete seasons")
        return None

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key": cfg.key, "label": cfg.label, "label_ko": cfg.label_ko,
        "faostat_item": cfg.faostat_item, "doc": cfg.doc,
        "caveat": cfg.caveat, "non_weather_drivers": cfg.non_weather_drivers,
        "anomaly": {"window_years": 20, "uses_only_prior_years": True},
        "points": cfg.points,
        "targets": targets,
    }
    os.makedirs(MODELS, exist_ok=True)
    output = os.path.join(MODELS, cfg.key + ".json")
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    log(cfg.label)
    for name, target in targets.items():
        score = target["validation"][target["configuration"]]
        gate = target["climate_gate"]
        candidate_skill = gate["candidate_skill_vs_trend"]
        skill_text = "n/a" if candidate_skill is None else "{:+.1%}".format(candidate_skill)
        log("  {:10} climate {}, {} seasons (need {}), {}, trend {}, forecast {}".format(
            name, skill_text, gate["available_seasons"], gate["required_seasons"],
            gate["status"], target["trend"]["name"],
            target["forecast_gate"]["status"]))
    return payload


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[key] for key in keys] if keys else ALL
    for cfg in configs:
        train_crop(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
