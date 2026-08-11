"""Official CEC/SAGIS commercial-maize labels.

SAGIS republishes the Crop Estimates Committee historic workbook. The target
is commercial production divided by commercial planted area (columns E:G),
not total maize: non-commercial agriculture has a different spatial footprint
and much lower reported yield.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
LANDING_URL = "https://www.sagis.org.za/non-sagis-historic-info/"
FALLBACK_URL = (
    "https://www.sagis.org.za/wp-content/uploads/2026/08/"
    "Historic_WGO_Production_Info_2026-07-31.xlsx"
)


def _latest_workbook_url(session: requests.Session) -> str:
    response = session.get(LANDING_URL, timeout=45)
    response.raise_for_status()
    matches = re.findall(
        r'https?://[^"\']+Historic[^"\']+Production[^"\']+\.xlsx',
        response.text,
        flags=re.IGNORECASE,
    )
    return matches[0].replace("&amp;", "&") if matches else FALLBACK_URL


def download_workbook(refresh: bool = False) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / "sagis_historic_production.xlsx"
    if target.exists() and not refresh:
        return target

    session = requests.Session()
    session.headers.update({"User-Agent": "global-trade-dashboard/1.0"})
    try:
        url = _latest_workbook_url(session)
    except requests.RequestException:
        url = FALLBACK_URL
    response = session.get(url, timeout=90)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def _harvest_year(season: str) -> int:
    first, second = season.split("/")
    if len(second) == 2:
        century = int(first[:2]) * 100
        year = century + int(second)
        if year < int(first):
            year += 100
        return year
    return int(second)


def parse_workbook(path: os.PathLike) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Area prod and yield", header=None)
    records = []
    pattern = re.compile(r"^\d{4}/(?:\d{2}|\d{4})$")
    for row in raw.itertuples(index=False, name=None):
        season = str(row[0]).strip()
        if not pattern.match(season):
            continue
        area, production, yield_t_ha = row[4], row[5], row[6]
        if pd.isna(area) or pd.isna(production):
            continue
        year = _harvest_year(season)
        calculated = float(production) / float(area)
        reported = float(yield_t_ha) if pd.notna(yield_t_ha) else calculated
        records.append(
            {
                "year": year,
                "season_label": season,
                "area_ha": float(area),
                "production_t": float(production),
                "yield_kg_ha": reported * 1000.0,
                "yield_calculated_kg_ha": calculated * 1000.0,
            }
        )
    frame = pd.DataFrame(records).sort_values("year").reset_index(drop=True)
    if frame.empty:
        raise ValueError("No commercial-maize rows found in SAGIS workbook")
    return frame


def load_labels(refresh: bool = False) -> pd.DataFrame:
    return parse_workbook(download_workbook(refresh=refresh))


if __name__ == "__main__":
    print(load_labels().tail(10).to_string(index=False))
