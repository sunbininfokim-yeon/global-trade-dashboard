"""
Yield labels for Thailand training tables.

Priority:
  1. training/labels_official/<key>.csv  (OAE / OCSB / custom)
  2. FAOSTAT national Yield for cfg.faostat_item (Area == Thailand)
  3. provisional synthetic (scaffold only — never claim production skill)
"""

from __future__ import annotations

import os
import shutil
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL_DIR = os.path.join(HERE, "training", "labels_official")
CACHE = os.path.join(HERE, "cache")

# Prefer shared Indonesia FAOSTAT zip if present (same bulk file).
_SHARED_FAOSTAT = os.path.abspath(os.path.join(
    HERE, "..", "indonesia", "cache", "faostat_production.zip"))

FAOSTAT_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
FAOSTAT_MEMBER = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"

LABEL_SOURCE_SYNTHETIC = "provisional_synthetic_climate_response"
LABEL_SOURCE_OFFICIAL = "official_csv_override"
LABEL_SOURCE_FAOSTAT = "faostat_thailand_national_yield"


def log(msg):
    print(f"[labels] {msg}", flush=True)


def load_official(key: str) -> pd.DataFrame | None:
    path = os.path.join(OFFICIAL_DIR, f"{key}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "year" not in df.columns or "yield_kg_ha" not in df.columns:
        raise ValueError(f"{path} needs year,yield_kg_ha")
    cols = ["year", "yield_kg_ha"]
    for optional in ("label_source", "label_note"):
        if optional in df.columns:
            cols.append(optional)
    out = df[cols].copy()
    if "label_source" not in out.columns:
        out["label_source"] = LABEL_SOURCE_OFFICIAL
    else:
        out["label_source"] = out["label_source"].fillna(LABEL_SOURCE_OFFICIAL)
    return out


def _faostat_zip_path() -> str:
    os.makedirs(CACHE, exist_ok=True)
    local = os.path.join(CACHE, "faostat_production.zip")
    if os.path.exists(local):
        return local
    if os.path.exists(_SHARED_FAOSTAT):
        log(f"linking FAOSTAT zip from indonesia cache")
        try:
            os.symlink(_SHARED_FAOSTAT, local)
        except OSError:
            shutil.copy2(_SHARED_FAOSTAT, local)
        return local
    import urllib.request
    log("FAOSTAT bulk downloading (~34 MB)")
    tmp = local + ".part"
    req = urllib.request.Request(
        FAOSTAT_URL, headers={"User-Agent": "yield-model-thailand/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        f.write(r.read())
    os.replace(tmp, local)
    return local


_FAOSTAT_CACHE: dict[str, pd.DataFrame] = {}


def faostat_thailand(item: str) -> pd.DataFrame:
    """Annual Yield (kg/ha) for Thailand × FAOSTAT Item."""
    if item in _FAOSTAT_CACHE:
        return _FAOSTAT_CACHE[item]

    usecols = ["Area", "Item", "Element", "Year", "Value"]
    chunks = []
    with zipfile.ZipFile(_faostat_zip_path()) as archive, \
            archive.open(FAOSTAT_MEMBER) as source:
        for chunk in pd.read_csv(
                source, encoding="latin-1", usecols=usecols, chunksize=250000):
            keep = (chunk.Area.eq("Thailand")
                    & chunk.Item.eq(item)
                    & chunk.Element.eq("Yield"))
            if keep.any():
                chunks.append(chunk.loc[keep, ["Year", "Value"]])
    if not chunks:
        # Try alternate cassava name
        if item == "Cassava, fresh":
            return faostat_thailand("Cassava")
        raise RuntimeError(f"No FAOSTAT Thailand Yield rows for Item={item!r}")

    long = pd.concat(chunks, ignore_index=True)
    out = (long.groupby("Year", as_index=False)["Value"].first()
           .rename(columns={"Year": "year", "Value": "yield_kg_ha"}))
    out["label_source"] = LABEL_SOURCE_FAOSTAT
    _FAOSTAT_CACHE[item] = out
    return out


def synthetic_yields(cfg, feature_df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed + abs(hash(cfg.key)) % 10_000)
    years = feature_df.year.values.astype(int)
    n = len(years)
    t0 = years.min()
    base = cfg.yield_base_kg_ha or 3000.0
    trend = base * np.exp(cfg.yield_growth * (years - t0))

    def z(col, default=0.0):
        if col not in feature_df.columns:
            return np.full(n, default)
        s = feature_df[col].astype(float)
        sd = s.std()
        if sd is None or sd == 0 or np.isnan(sd):
            return np.zeros(n)
        return ((s - s.mean()) / sd).fillna(0.0).values

    if cfg.crop == "sugarcane":
        stress = (0.12 * z("wd_early") + 0.10 * z("heat_x_drought_early")
                  - 0.08 * z("sm_early") - 0.06 * z("sm_grand")
                  + 0.08 * z("oni_djf"))
    elif cfg.key.endswith("_off"):
        stress = (0.14 * (-z("dam_recharge_proxy")) + 0.10 * z("oni_djf")
                  + 0.06 * z("heat_days_35_off"))
    elif cfg.crop == "rubber":
        stress = (0.12 * z("rainy_days_5mm") + 0.08 * z("rainy_days_1mm")
                  - 0.04 * z("oni_season"))
    else:
        stress = (0.10 * z("dry_spell_mid") + 0.08 * z("onset_doy")
                  + 0.06 * z("oni_season") - 0.05 * z("sm_mid"))

    crisis = np.zeros(n)
    for y, hit in ((2016, 0.10), (2020, 0.12), (2010, 0.05), (2015, 0.08)):
        crisis[years == y] += hit

    noise = rng.normal(0.0, 0.04, size=n)
    mult = np.clip(1.0 - 0.10 * stress - crisis + noise, 0.55, 1.25)
    return pd.DataFrame({
        "year": years,
        "yield_kg_ha": trend * mult,
        "label_source": LABEL_SOURCE_SYNTHETIC,
    })


def attach_labels(cfg, feature_df: pd.DataFrame) -> pd.DataFrame:
    official = load_official(cfg.key)
    if official is not None:
        return feature_df.merge(official, on="year", how="left")

    try:
        fao = faostat_thailand(cfg.faostat_item)
        out = feature_df.merge(fao, on="year", how="left")
        if out.yield_kg_ha.notna().sum() >= 15:
            return out
        log(f"{cfg.key}: FAOSTAT sparse ({out.yield_kg_ha.notna().sum()} yrs); "
            f"falling back to synthetic")
    except Exception as e:  # noqa: BLE001
        log(f"{cfg.key}: FAOSTAT unavailable ({e}); synthetic labels")

    labels = synthetic_yields(cfg, feature_df)
    return feature_df.merge(labels, on="year", how="left")
