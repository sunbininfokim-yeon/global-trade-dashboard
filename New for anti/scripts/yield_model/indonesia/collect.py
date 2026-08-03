"""Build leak-free annual training tables for Indonesia crop models."""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import climate as C
from .data import faostat_indonesia, load_oni, oni_for, point_weather
from .regions import ALL, BY_KEY


HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
FIRST_FEATURE_YEAR = 1986  # POWER begins 1984; palm reaches back two dry seasons.
LAST_COMPLETE_YEAR = date.today().year - 1


def log(message):
    print("[indonesia:collect] " + message, flush=True)


def blend_features(cfg, dailies, year):
    """Derive point features first, then production-weight the scalars."""
    totals, weights = {}, {}
    for point in cfg.points:
        features = cfg.build(dailies[point["name"]], year)
        for name, value in features.items():
            if value is None or pd.isna(value):
                continue
            totals[name] = totals.get(name, 0.0) + float(value) * point["weight"]
            weights[name] = weights.get(name, 0.0) + point["weight"]
    return {name: totals[name] / weights[name]
            for name in totals if weights.get(name, 0) > 0}


def build_crop(cfg, labels, oni):
    log("{}: {}".format(cfg.key, cfg.label))
    dailies = {point["name"]: point_weather(point) for point in cfg.points}
    rows = []
    for year in range(FIRST_FEATURE_YEAR, LAST_COMPLETE_YEAR + 1):
        row = blend_features(cfg, dailies, year)
        row["year"] = year
        row["oni_season"] = oni_for(oni, year)
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)

    raw_features = [column for column in frame.columns
                    if column not in {"year", "oni_season"}]
    frame = C.trailing_anomalies(frame, raw_features, window=20, min_history=20)
    crop_labels = labels[labels.item.eq(cfg.faostat_item)].drop(columns="item")
    frame = frame.merge(crop_labels, on="year", how="left")

    os.makedirs(TRAINING, exist_ok=True)
    output = os.path.join(TRAINING, cfg.key + ".csv")
    frame.to_csv(output, index=False)
    usable = frame.dropna(subset=["yield_kg_ha"])
    anomalous = [c for c in frame if c.endswith("_anom")]
    complete = usable.dropna(subset=anomalous + ["oni_season"])
    log("  wrote {} seasons; {} labelled; {} with 20-year anomalies -> {}".format(
        len(frame), len(usable), len(complete), output))
    if len(usable):
        last = usable.iloc[-1]
        log("  latest {}: yield {:,.1f} kg/ha, production {:,.0f} t [{}]".format(
            int(last.year), last.yield_kg_ha, last.production_tonnes,
            last.get("production_flag", "")))
    return frame


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[key] for key in keys] if keys else ALL
    labels = faostat_indonesia([cfg.faostat_item for cfg in configs])
    oni = load_oni()
    for cfg in configs:
        build_crop(cfg, labels, oni)
    return 0


if __name__ == "__main__":
    sys.exit(main())

