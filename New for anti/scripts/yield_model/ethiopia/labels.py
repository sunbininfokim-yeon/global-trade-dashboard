"""FAOSTAT Ethiopia coffee yield, production and derived harvested area."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
YIELD_URL = "https://ourworldindata.org/grapher/coffee-yields.csv?v=1&csvType=full&useColumnShortNames=false"
PRODUCTION_URL = "https://ourworldindata.org/grapher/coffee-bean-production.csv?v=1&csvType=full&useColumnShortNames=false"
YIELD_COLUMN = "Green coffee - Yield (tonnes per hectare)"


def _download(url: str, name: str, refresh: bool) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.exists() and not refresh:
        return target
    response = requests.get(url, headers={"User-Agent": "global-trade-dashboard/1.0"}, timeout=90)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def load_labels(refresh: bool = False) -> pd.DataFrame:
    yields = pd.read_csv(_download(YIELD_URL, "faostat_coffee_yields.csv", refresh))
    production = pd.read_csv(_download(PRODUCTION_URL, "faostat_coffee_production.csv", refresh))
    yields = yields[(yields.Code == "ETH") & yields[YIELD_COLUMN].notna()].copy()
    production = production[production.Code == "ETH"].copy()
    production_column = next(column for column in production.columns if column not in {"Entity", "Code", "Year"})
    yields = yields.rename(columns={"Year": "year", YIELD_COLUMN: "yield_t_ha"})
    production = production.rename(columns={"Year": "year", production_column: "production_t"})
    frame = yields[["year", "yield_t_ha"]].merge(production[["year", "production_t"]], on="year", how="inner")
    frame["yield_kg_ha"] = frame.yield_t_ha.astype(float) * 1000.0
    frame["area_ha"] = frame.production_t.astype(float) / frame.yield_t_ha.astype(float)
    frame["area_growth"] = frame.area_ha.pct_change()
    frame["yield_lag2_kg_ha"] = frame.yield_kg_ha.shift(2)
    frame["area_growth_lag2"] = frame.area_growth.shift(2)
    frame["target_status"] = "final"
    return frame[["year", "yield_kg_ha", "production_t", "area_ha", "area_growth", "yield_lag2_kg_ha", "area_growth_lag2", "target_status"]].sort_values("year")


if __name__ == "__main__":
    print(load_labels().tail(12).to_string(index=False))
