"""FAOSTAT green-coffee yield labels, distributed through OWID's data API."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
URL = (
    "https://ourworldindata.org/grapher/coffee-yields.csv?"
    "v=1&csvType=full&useColumnShortNames=false"
)
COLUMN = "Green coffee - Yield (tonnes per hectare)"


def download(refresh: bool = False) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / "faostat_owid_coffee_yields.csv"
    if target.exists() and not refresh:
        return target
    response = requests.get(
        URL,
        headers={"User-Agent": "global-trade-dashboard/1.0"},
        timeout=90,
    )
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def load_labels(refresh: bool = False) -> pd.DataFrame:
    raw = pd.read_csv(download(refresh=refresh))
    frame = raw[(raw["Code"] == "UGA") & raw[COLUMN].notna()].copy()
    frame = frame.rename(columns={"Year": "year"})
    frame["yield_kg_ha"] = frame[COLUMN].astype(float) * 1000.0
    frame["target_status"] = "final"
    return frame[["year", "yield_kg_ha", "target_status"]].sort_values("year")


if __name__ == "__main__":
    print(load_labels().tail(12).to_string(index=False))
