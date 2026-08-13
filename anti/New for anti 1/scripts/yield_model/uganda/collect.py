"""Build the causal Uganda green-coffee yield training table."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .climate import collect_seasonal
from .labels import load_labels
from .regions import BELT_KEY, RAW_FEATURES

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"


def add_causal_anomalies(frame: pd.DataFrame, window: int = 20, min_prior: int = 10) -> pd.DataFrame:
    result = frame.sort_values("year").copy()
    for column in RAW_FEATURES:
        anomalies = []
        for _, row in result.iterrows():
            prior = result[(result.year < row.year) & (result.year >= row.year - window)][column].dropna()
            if len(prior) < min_prior or prior.std(ddof=1) == 0:
                anomalies.append(np.nan)
            else:
                anomalies.append((row[column] - prior.mean()) / prior.std(ddof=1))
        result[f"{column}_z"] = anomalies
    return result


def build(refresh: bool = False, end_year: int = None) -> pd.DataFrame:
    climate = add_causal_anomalies(collect_seasonal(end_year=end_year, refresh=refresh))
    frame = climate.merge(load_labels(refresh=refresh), on="year", how="left")
    frame["target_status"] = frame["target_status"].fillna("missing")
    TRAINING.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TRAINING / f"{BELT_KEY}.csv", index=False)
    return frame


if __name__ == "__main__":
    print(build().tail(12).to_string(index=False))
