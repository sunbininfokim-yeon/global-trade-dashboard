"""
Target series for Russia winter-wheat models.

Primary (Phase-1 bootstrap): USDA FAS PSD national Wheat yield for Russia.
  - Open, keyless bulk CSV
  - No oblast resolution
  - Unit: MT/HA → kg/ha

Rosstat / EMISS oblast yields are the intended primary label once a stable
indicator extract is wired (see labels.md). fedstat.ru scraping is unreliable
from automated clients and is not in this package yet.

Crimea and post-2022 "new regions" are not in PSD as separate geographies;
the national series may still embed production accounting disputes — documented
in labels.md rather than silently corrected here.
"""

from __future__ import annotations

import io
import os
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

PSD_GRAINS = "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip"
PSD_COLUMNS = ["Commodity_Description", "Country_Name", "Market_Year",
               "Attribute_Description", "Unit_Description", "Value"]


def log(msg):
    print(f"[labels] {msg}", flush=True)


def _fetch(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _psd_russia():
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "psd_grains_russia.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("downloading PSD grains_pulses zip for Russia slice")
    blob = _fetch(PSD_GRAINS)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith("psd_grains_pulses.csv"))
        with z.open(name) as fh:
            df = pd.read_csv(fh, usecols=PSD_COLUMNS, encoding="latin-1",
                             low_memory=False)

    # Country_Name is "Russia" in PSD (not "Russian Federation")
    out = df[df.Country_Name == "Russia"].drop(columns=["Country_Name"])
    if out.empty:
        # Fall back if naming changes
        out = df[df.Country_Name.str.contains("Russia", case=False, na=False)]
        out = out.drop(columns=["Country_Name"], errors="ignore")
    out.to_csv(cached, index=False)
    log(f"  cached {len(out):,} rows -> psd_grains_russia.csv")
    return out


def psd_series(commodity, attribute):
    df = _psd_russia()
    s = df[(df.Commodity_Description == commodity)
           & (df.Attribute_Description == attribute)]
    if s.empty:
        raise KeyError(f"PSD has no Russia {commodity} / {attribute}")
    return (s[["Market_Year", "Value", "Unit_Description"]]
            .rename(columns={"Market_Year": "year", "Value": "value"})
            .sort_values("year").reset_index(drop=True))


def psd_yield_kg_ha(commodity="Wheat"):
    """
    PSD yield in kg/ha.

    Market_Year for Russian wheat is the marketing year that ends with the
    summer harvest of that year (harvest-year alignment for winter wheat).
    """
    s = psd_series(commodity, "Yield")
    unit = str(s.Unit_Description.iloc[0])
    if "MT/HA" not in unit.upper() and "MT" not in unit.upper():
        log(f"  warning: unexpected PSD yield unit: {unit}")
    return pd.DataFrame({"year": s.year.astype(int),
                         "target": s.value.astype(float) * 1000.0})


def psd_production_1000t(commodity="Wheat"):
    s = psd_series(commodity, "Production")
    return pd.DataFrame({"year": s.year.astype(int),
                         "production_1000t": s.value.astype(float)})


def load_curated_oblast_csv(path=None):
    """
    Optional oblast yields if a researcher drops a CSV at training/oblast_yields.csv.

    Expected columns: year, oblast, yield_kg_ha  (or yield_c_ha × 100).
    Returns None if missing — Phase-1 does not require it.
    """
    path = path or os.path.join(HERE, "training", "oblast_yields.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "yield_c_ha" in df.columns and "yield_kg_ha" not in df.columns:
        df["yield_kg_ha"] = df["yield_c_ha"] * 100.0  # 1 c/ha = 0.1 t/ha = 100 kg/ha
    return df
