"""USDA FAS PSD free CSV downloads — Russia / World export series."""

from __future__ import annotations

import io
import os
import zipfile
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

PSD_URLS = {
    "grains": "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
    "oilseeds": "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
}

COLUMNS = [
    "Commodity_Description",
    "Country_Name",
    "Market_Year",
    "Attribute_Description",
    "Unit_Description",
    "Value",
]


def log(msg: str) -> None:
    print(f"[psd_exports] {msg}", flush=True)


def _fetch(url: str, timeout: int = 600) -> bytes:
    req = Request(url, headers={"User-Agent": "russia-export-pulse/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_psd_table(bundle: str, force: bool = False) -> pd.DataFrame:
    """Load full PSD CSV for a commodity family (cached)."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"psd_{bundle}.csv")
    if os.path.exists(cached) and not force:
        return pd.read_csv(cached)
    url = PSD_URLS[bundle]
    log(f"downloading {bundle} from PSD zip")
    blob = _fetch(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv") and "psd_" in n.lower())
        with zf.open(name) as fh:
            df = pd.read_csv(fh, usecols=COLUMNS, encoding="latin-1", low_memory=False)
    df.to_csv(cached, index=False)
    log(f"  cached {len(df):,} rows -> {os.path.basename(cached)}")
    return df


AGGREGATE_COUNTRIES = {
    "European Union",
    "Union of Soviet Socialist Repu",
}


def _country_mask(series: pd.Series, name: str) -> pd.Series:
    if name.lower() == "world":
        # PSD grains CSV has no literal "World" row for Exports — callers should
        # use world_export_series() instead.
        return series.str.fullmatch(r"World", case=False, na=False)
    return series.str.fullmatch(name, case=False, na=False) | series.str.contains(
        name, case=False, na=False
    )


def export_series(
    df: pd.DataFrame,
    *,
    commodity: str,
    country: str,
    attribute: str = "Exports",
) -> pd.DataFrame:
    """Return Market_Year / value / unit for one PSD export series."""
    if country.lower() == "world":
        return world_export_series(df, commodity=commodity, attribute=attribute)

    hit = df[
        (df.Commodity_Description == commodity)
        & (df.Attribute_Description == attribute)
        & _country_mask(df.Country_Name, country)
    ]
    if hit.empty:
        raise KeyError(f"PSD missing {country} / {commodity} / {attribute}")
    # Prefer exact Russia over 'Russian Federation' duplicates if both appear
    if country.lower() == "russia" and (hit.Country_Name == "Russia").any():
        hit = hit[hit.Country_Name == "Russia"]
    out = (
        hit[["Market_Year", "Value", "Unit_Description"]]
        .rename(columns={"Market_Year": "year", "Value": "value", "Unit_Description": "unit"})
        .drop_duplicates(subset=["year"], keep="last")
        .sort_values("year")
        .reset_index(drop=True)
    )
    out["year"] = out["year"].astype(int)
    out["value"] = out["value"].astype(float)
    return out


def world_export_series(
    df: pd.DataFrame,
    *,
    commodity: str,
    attribute: str = "Exports",
) -> pd.DataFrame:
    """
    Construct world exports by summing country rows.

    The free PSD grains/oilseeds CSV dumps do not include a 'World' country for
    Exports. We sum all countries except known aggregates (EU bloc, USSR) to
    avoid double-counting member states.
    """
    hit = df[
        (df.Commodity_Description == commodity)
        & (df.Attribute_Description == attribute)
        & ~df.Country_Name.isin(AGGREGATE_COUNTRIES)
    ]
    if hit.empty:
        raise KeyError(f"PSD missing country rows for {commodity} / {attribute}")
    unit = str(hit["Unit_Description"].iloc[0])
    grouped = (
        hit.groupby("Market_Year", as_index=False)["Value"]
        .sum()
        .rename(columns={"Market_Year": "year", "Value": "value"})
        .sort_values("year")
        .reset_index(drop=True)
    )
    grouped["year"] = grouped["year"].astype(int)
    grouped["value"] = grouped["value"].astype(float)
    grouped["unit"] = unit
    return grouped


def series_payload(
    df: pd.DataFrame,
    *,
    source_name: str,
    source_url: str,
    construction: str | None = None,
) -> dict[str, Any]:
    unit = str(df["unit"].iloc[0]) if len(df) else "1000 MT"
    out: dict[str, Any] = {
        "unit": unit,
        "frequency": "marketing_year",
        "source": {"name": source_name, "url": source_url},
        "series": [
            {"period": str(int(row.year)), "value": round(float(row.value), 3)}
            for row in df.itertuples(index=False)
        ],
    }
    if construction:
        out["construction"] = construction
    return out


def contribution_table(russia: pd.DataFrame, world: pd.DataFrame) -> list[dict[str, Any]]:
    """YoY Russia export change as share of prior world exports."""
    r = russia.set_index("year")["value"]
    w = world.set_index("year")["value"]
    years = sorted(set(r.index) & set(w.index))
    rows: list[dict[str, Any]] = []
    for i, year in enumerate(years):
        share = float(r[year] / w[year]) if w[year] else None
        prev = years[i - 1] if i else None
        if prev is None or not w[prev]:
            rows.append({
                "period": str(year),
                "russia_exports": round(float(r[year]), 3),
                "world_exports": round(float(w[year]), 3),
                "russia_share_of_world_pct": round(100.0 * share, 3) if share is not None else None,
                "russia_yoy_change_pct": None,
                "implied_world_trade_contribution_pct": None,
            })
            continue
        yoy = 100.0 * (r[year] - r[prev]) / r[prev] if r[prev] else None
        contrib = 100.0 * (r[year] - r[prev]) / w[prev]
        rows.append({
            "period": str(year),
            "russia_exports": round(float(r[year]), 3),
            "world_exports": round(float(w[year]), 3),
            "russia_share_of_world_pct": round(100.0 * share, 3) if share is not None else None,
            "russia_yoy_change_pct": round(yoy, 3) if yoy is not None else None,
            "implied_world_trade_contribution_pct": round(contrib, 3),
        })
    return rows
