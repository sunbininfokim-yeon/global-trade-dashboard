"""
Target series for Ukraine winter-wheat / sunflower models.

Primary: SSSU/Ukrstat oblast yields + sown area (CSV drop — see labels.md).
Cross-check helper: USDA FAS PSD national Ukraine series (NOT for training).

Crimea, Donetsk, Luhansk excluded. Default label years ≤ 2021.
"""

from __future__ import annotations

import io
import os
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

PSD_GRAINS = "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip"
PSD_OILSEEDS = "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip"
PSD_COLUMNS = ["Commodity_Description", "Country_Name", "Market_Year",
               "Attribute_Description", "Unit_Description", "Value"]

# Hard cap for biophysical train (full-scale invasion starts 2022).
LABEL_MAX_YEAR = 2021

CENTRAL_OBLASTS = ["Poltava", "Vinnytsia", "Cherkasy"]
SOUTH_OBLASTS = ["Odesa", "Mykolaiv", "Kherson"]
WEST_OBLASTS = ["Ternopil", "Khmelnytskyi", "Rivne"]
BELT_OBLASTS = CENTRAL_OBLASTS + SOUTH_OBLASTS + WEST_OBLASTS

EXCLUDED_OBLASTS = {"Crimea", "Donetsk", "Luhansk", "Sevastopol"}


def log(msg):
    print(f"[labels] {msg}", flush=True)


def _fetch(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _psd_ukraine(kind="grains"):
    os.makedirs(CACHE, exist_ok=True)
    url = PSD_GRAINS if kind == "grains" else PSD_OILSEEDS
    cached = os.path.join(CACHE, f"psd_{kind}_ukraine.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log(f"downloading PSD {kind} zip for Ukraine slice")
    blob = _fetch(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as fh:
            df = pd.read_csv(fh, usecols=PSD_COLUMNS, encoding="latin-1",
                             low_memory=False)

    out = df[df.Country_Name == "Ukraine"].drop(columns=["Country_Name"])
    if out.empty:
        out = df[df.Country_Name.str.contains("Ukraine", case=False, na=False)]
        out = out.drop(columns=["Country_Name"], errors="ignore")
    out.to_csv(cached, index=False)
    log(f"  cached {len(out):,} rows -> {os.path.basename(cached)}")
    return out


def psd_series(commodity, attribute, kind="grains"):
    df = _psd_ukraine(kind=kind)
    s = df[(df.Commodity_Description == commodity)
           & (df.Attribute_Description == attribute)]
    if s.empty:
        raise KeyError(f"PSD has no Ukraine {commodity} / {attribute}")
    return (s[["Market_Year", "Value", "Unit_Description"]]
            .rename(columns={"Market_Year": "year", "Value": "value"})
            .sort_values("year").reset_index(drop=True))


def psd_yield_kg_ha(commodity="Wheat", kind="grains", max_year=None):
    """National PSD yield in kg/ha — cross-check only, never zone train target."""
    s = psd_series(commodity, "Yield", kind=kind)
    unit = str(s.Unit_Description.iloc[0])
    if "MT/HA" not in unit.upper() and "MT" not in unit.upper():
        log(f"  warning: unexpected PSD yield unit: {unit}")
    out = pd.DataFrame({"year": s.year.astype(int),
                        "psd_yield_kg_ha": s.value.astype(float) * 1000.0})
    if max_year is not None:
        out = out[out.year <= int(max_year)].reset_index(drop=True)
    return out


def wheat_oblast_available():
    return os.path.exists(os.path.join(TRAINING, "oblast_wheat_yields.csv"))


def sunflower_oblast_available():
    return os.path.exists(os.path.join(TRAINING, "oblast_sunflower_yields.csv"))


def load_curated_oblast_csv(path, max_year=LABEL_MAX_YEAR):
    """
    Oblast yields CSV: year, oblast, yield_kg_ha (or yield_c_ha × 100).

    Drops excluded oblasts and years after max_year (default 2021).
    """
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "yield_c_ha" in df.columns and "yield_kg_ha" not in df.columns:
        df["yield_kg_ha"] = df["yield_c_ha"] * 100.0
    if "yield_c_ha" in df.columns:
        df = df[(df.yield_c_ha > 0) & (df.yield_c_ha < 100)]
    if "yield_kg_ha" in df.columns:
        df = df[(df.yield_kg_ha > 0) & (df.yield_kg_ha < 10000)]
    df = df[~df.oblast.isin(EXCLUDED_OBLASTS)]
    if max_year is not None:
        df = df[df.year <= int(max_year)]
    return df.reset_index(drop=True)


def load_oblast_sown_area(path, max_year=LABEL_MAX_YEAR):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df = df[~df.oblast.isin(EXCLUDED_OBLASTS)]
    if max_year is not None:
        df = df[df.year <= int(max_year)]
    return df.reset_index(drop=True)


def zone_yield_kg_ha(oblasts, fallback_weights=None,
                     yield_path=None, area_path=None, label="wheat",
                     max_year=LABEL_MAX_YEAR):
    """Sown-area-weighted mean of oblast yields (kg/ha) for a zone."""
    y = load_curated_oblast_csv(yield_path, max_year=max_year)
    if y is None or y.empty:
        raise FileNotFoundError(
            f"oblast yield CSV missing for {label} "
            f"({yield_path or 'see labels.md'}). "
            f"Drop real SSSU/Ukrstat data — do not invent rows; "
            f"PSD national is cross-check only.")
    y = y[y.oblast.isin(oblasts)].copy()
    if y.empty:
        raise KeyError(f"no {label} yields for {oblasts}")

    area = load_oblast_sown_area(area_path, max_year=max_year)
    rows = []
    for year, g in y.groupby("year"):
        g = g.dropna(subset=["yield_kg_ha"])
        if g.empty:
            continue
        if area is not None:
            a = area[(area.year == year) & (area.oblast.isin(g.oblast))]
            if not a.empty:
                merged = g.merge(a[["oblast", "sown_1000ha"]], on="oblast",
                                 how="left")
                w = merged.sown_1000ha.fillna(0).astype(float).values
                vals = merged.yield_kg_ha.astype(float).values
                if w.sum() > 0:
                    rows.append({
                        "year": int(year),
                        "target": float((vals * w).sum() / w.sum()),
                    })
                    continue
        if fallback_weights:
            w = g.oblast.map(fallback_weights).astype(float).fillna(1.0).values
            vals = g.yield_kg_ha.astype(float).values
            target = (float((vals * w).sum() / w.sum())
                      if w.sum() > 0 else float(vals.mean()))
        else:
            target = float(g.yield_kg_ha.astype(float).mean())
        rows.append({"year": int(year), "target": target})

    out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    log(f"  {label} zone [{', '.join(oblasts)}]: {len(out)} yrs "
        f"{int(out.year.min())}-{int(out.year.max())}")
    return out


def _wheat_paths():
    return (
        os.path.join(TRAINING, "oblast_wheat_yields.csv"),
        os.path.join(TRAINING, "oblast_wheat_sown_area.csv"),
    )


def _sunflower_paths():
    return (
        os.path.join(TRAINING, "oblast_sunflower_yields.csv"),
        os.path.join(TRAINING, "oblast_sunflower_sown_area.csv"),
    )


def central_wheat_yield_kg_ha():
    yp, ap = _wheat_paths()
    return zone_yield_kg_ha(
        CENTRAL_OBLASTS,
        fallback_weights={"Poltava": 0.40, "Vinnytsia": 0.35, "Cherkasy": 0.25},
        yield_path=yp, area_path=ap, label="central wheat")


def southern_wheat_yield_kg_ha():
    yp, ap = _wheat_paths()
    return zone_yield_kg_ha(
        SOUTH_OBLASTS,
        fallback_weights={"Odesa": 0.40, "Mykolaiv": 0.35, "Kherson": 0.25},
        yield_path=yp, area_path=ap, label="southern wheat")


def western_wheat_yield_kg_ha():
    yp, ap = _wheat_paths()
    return zone_yield_kg_ha(
        WEST_OBLASTS,
        fallback_weights={"Ternopil": 0.35, "Khmelnytskyi": 0.35, "Rivne": 0.30},
        yield_path=yp, area_path=ap, label="western wheat")


def belt_wheat_yield_kg_ha():
    yp, ap = _wheat_paths()
    return zone_yield_kg_ha(
        BELT_OBLASTS, yield_path=yp, area_path=ap, label="belt wheat")


def central_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        CENTRAL_OBLASTS,
        fallback_weights={"Poltava": 0.40, "Vinnytsia": 0.30, "Cherkasy": 0.30},
        yield_path=yp, area_path=ap, label="central sunflower")


def southern_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        SOUTH_OBLASTS,
        fallback_weights={"Odesa": 0.35, "Mykolaiv": 0.35, "Kherson": 0.30},
        yield_path=yp, area_path=ap, label="southern sunflower")


def western_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        WEST_OBLASTS,
        fallback_weights={"Ternopil": 0.30, "Khmelnytskyi": 0.40, "Rivne": 0.30},
        yield_path=yp, area_path=ap, label="western sunflower")


def belt_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        BELT_OBLASTS, yield_path=yp, area_path=ap, label="belt sunflower")
