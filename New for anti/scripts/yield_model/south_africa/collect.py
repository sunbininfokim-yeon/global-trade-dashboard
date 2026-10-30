"""Build the causal year-by-year South African maize training table."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

if os.environ.get("CLIMATE_SOURCE", "power") == "gee":
    from .climate import collect_seasonal
else:
    from .climate_power import collect_seasonal
from .labels import load_labels
from .regions import BELT_KEY, RAW_FEATURES

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"


def add_causal_anomalies(
    frame: pd.DataFrame, window: int = 20, min_prior: int = 10
) -> pd.DataFrame:
    result = frame.sort_values("year").copy()
    for column in RAW_FEATURES:
        values = []
        for _, row in result.iterrows():
            prior = result[
                (result.year < row.year) & (result.year >= row.year - window)
            ][column].dropna()
            if len(prior) < min_prior or prior.std(ddof=1) == 0:
                values.append(np.nan)
            else:
                values.append((row[column] - prior.mean()) / prior.std(ddof=1))
        result[f"{column}_z"] = values
    return result


def build(refresh: bool = False, end_year: int = None) -> pd.DataFrame:
    climate = collect_seasonal(end_year=end_year, refresh=refresh)
    climate = add_causal_anomalies(climate)
    labels = load_labels(refresh=refresh)
    frame = climate.merge(labels, on="year", how="left")
    frame["target_status"] = "missing"
    # The workbook's newest populated summer-crop row is the live CEC
    # estimate; earlier rows are final. This rolls forward without embedding
    # the current calendar year in code.
    latest_label_year = int(labels.year.max())
    frame.loc[
        (frame.year < latest_label_year) & frame.yield_kg_ha.notna(),
        "target_status",
    ] = "final"
    frame.loc[
        (frame.year == latest_label_year) & frame.yield_kg_ha.notna(),
        "target_status",
    ] = "cec_estimate"
    TRAINING.mkdir(parents=True, exist_ok=True)
    target = TRAINING / f"{BELT_KEY}.csv"
    frame.to_csv(target, index=False)
    return frame


if __name__ == "__main__":
    print(build().tail(12).to_string(index=False))
