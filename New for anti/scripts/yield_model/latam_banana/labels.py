"""
Province banana yield / area labels.

Until CSVs exist, zone targets raise FileNotFoundError and train skips.
Never fall back to FAOSTAT national yield for a zone weather series.
"""

from __future__ import annotations

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
YIELD_CSV = os.path.join(TRAINING, "province_banana_yields.csv")
AREA_CSV = os.path.join(TRAINING, "province_banana_area.csv")

# Canonical province names expected in CSVs (ASCII, no accents).
PROVINCES = {
    "ecuador": ["Los Rios", "Guayas", "El Oro"],
    "guatemala": ["Izabal", "Escuintla"],
    "costa_rica": ["Limon"],
    "honduras": ["Cortes", "Yoro"],
}

ZONE_PROVINCES = {
    "ecuador_coast_banana": ("ecuador", PROVINCES["ecuador"]),
    "guatemala_banana": ("guatemala", PROVINCES["guatemala"]),
    "costa_rica_banana": ("costa_rica", PROVINCES["costa_rica"]),
    "honduras_banana": ("honduras", PROVINCES["honduras"]),
}


def province_available() -> bool:
    return os.path.isfile(YIELD_CSV) and os.path.isfile(AREA_CSV)


def _require_csvs() -> None:
    if not province_available():
        raise FileNotFoundError(
            "Province banana CSVs missing. Drop real files at:\n"
            f"  {YIELD_CSV}\n"
            f"  {AREA_CSV}\n"
            "See labels.md. Templates must not be renamed into place empty."
        )


def _load_yields() -> pd.DataFrame:
    _require_csvs()
    frame = pd.read_csv(YIELD_CSV)
    need = {"year", "country", "province", "yield_kg_ha"}
    missing = need - set(frame.columns)
    if missing:
        raise ValueError(f"yield CSV missing columns: {sorted(missing)}")
    return frame


def _load_area() -> pd.DataFrame:
    _require_csvs()
    frame = pd.read_csv(AREA_CSV)
    need = {"year", "country", "province", "harvested_ha"}
    missing = need - set(frame.columns)
    if missing:
        raise ValueError(f"area CSV missing columns: {sorted(missing)}")
    return frame


def zone_yield_kg_ha(zone_key: str) -> pd.DataFrame:
    """Area-weighted mean yield (kg/ha) for a pre-registered zone."""
    if zone_key not in ZONE_PROVINCES:
        raise KeyError(zone_key)
    country, provinces = ZONE_PROVINCES[zone_key]
    yields = _load_yields()
    area = _load_area()
    y = yields[(yields.country == country) & (yields.province.isin(provinces))]
    a = area[(area.country == country) & (area.province.isin(provinces))]
    merged = y.merge(a, on=["year", "country", "province"], how="inner")
    if merged.empty:
        raise ValueError(f"no overlapping yield/area rows for {zone_key}")

    rows = []
    for year, group in merged.groupby("year"):
        weights = group.harvested_ha.to_numpy(dtype=float)
        vals = group.yield_kg_ha.to_numpy(dtype=float)
        if weights.sum() <= 0:
            continue
        target = float((vals * weights).sum() / weights.sum())
        rows.append({"year": int(year), "target": target,
                     "yield_kg_ha": target})
    out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    if out.empty:
        raise ValueError(f"empty zone panel for {zone_key}")
    return out


def ecuador_yield_kg_ha() -> pd.DataFrame:
    return zone_yield_kg_ha("ecuador_coast_banana")


def guatemala_yield_kg_ha() -> pd.DataFrame:
    return zone_yield_kg_ha("guatemala_banana")


def costa_rica_yield_kg_ha() -> pd.DataFrame:
    return zone_yield_kg_ha("costa_rica_banana")


def honduras_yield_kg_ha() -> pd.DataFrame:
    return zone_yield_kg_ha("honduras_banana")


def refresh_label_resolution(configs: list) -> None:
    """Flip RegionCrop.label_resolution once CSVs exist."""
    state = "province" if province_available() else "blocked"
    for cfg in configs:
        cfg.label_resolution = state
