"""
Target series for Russia winter-wheat models.

Primary: Rosstat oblast grain yields (Regions of Russia yearbook extract),
area-weighted into Southern / CBE / South+CBE zones. See labels.md.

Cross-check helper: USDA FAS PSD national Wheat yield remains available.

Crimea and wartime "new regions" are excluded from the oblast set.
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
PSD_COLUMNS = ["Commodity_Description", "Country_Name", "Market_Year",
               "Attribute_Description", "Unit_Description", "Value"]

SOUTH_OBLASTS = ["Krasnodar", "Rostov", "Stavropol"]
CBE_OBLASTS = ["Belgorod", "Voronezh", "Kursk", "Tambov"]
BELT_OBLASTS = SOUTH_OBLASTS + CBE_OBLASTS
VOLGA_OBLASTS = ["Saratov", "Samara", "Volgograd"]
SUNFLOWER_SOUTH = SOUTH_OBLASTS
SUNFLOWER_CBE = CBE_OBLASTS
SUNFLOWER_VOLGA = VOLGA_OBLASTS
SUNFLOWER_BELT = SUNFLOWER_SOUTH + SUNFLOWER_CBE + SUNFLOWER_VOLGA


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
    Oblast yields CSV: year, oblast, yield_kg_ha (or yield_c_ha × 100).
    """
    path = path or os.path.join(TRAINING, "oblast_yields.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "yield_c_ha" in df.columns and "yield_kg_ha" not in df.columns:
        df["yield_kg_ha"] = df["yield_c_ha"] * 100.0  # 1 c/ha = 0.1 t/ha = 100 kg/ha
    return df


def load_oblast_sown_area(path=None):
    path = path or os.path.join(TRAINING, "oblast_sown_area.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def zone_yield_kg_ha(oblasts, fallback_weights=None,
                     yield_path=None, area_path=None, label="grain"):
    """
    Sown-area-weighted mean of oblast yields (kg/ha) for a zone.
    """
    y = load_curated_oblast_csv(yield_path)
    if y is None or y.empty:
        raise FileNotFoundError(
            f"oblast yield CSV missing ({yield_path or 'oblast_yields.csv'})")
    y = y[y.oblast.isin(oblasts)].copy()
    if y.empty:
        raise KeyError(f"no {label} yields for {oblasts}")

    area = load_oblast_sown_area(area_path)
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
            target = float((vals * w).sum() / w.sum()) if w.sum() > 0 else float(vals.mean())
        else:
            target = float(g.yield_kg_ha.astype(float).mean())
        rows.append({"year": int(year), "target": target})

    out = (pd.DataFrame(rows).sort_values("year").reset_index(drop=True))
    log(f"  {label} zone [{', '.join(oblasts)}]: {len(out)} yrs "
        f"{int(out.year.min())}-{int(out.year.max())}")
    return out


def southern_yield_kg_ha():
    return zone_yield_kg_ha(
        SOUTH_OBLASTS,
        fallback_weights={"Krasnodar": 0.40, "Rostov": 0.35, "Stavropol": 0.25})


def cbe_yield_kg_ha():
    return zone_yield_kg_ha(
        CBE_OBLASTS,
        fallback_weights={"Belgorod": 0.25, "Voronezh": 0.30,
                          "Kursk": 0.25, "Tambov": 0.20})


def belt_yield_kg_ha():
    return zone_yield_kg_ha(BELT_OBLASTS)


def volga_yield_kg_ha():
    return zone_yield_kg_ha(
        VOLGA_OBLASTS,
        fallback_weights={"Saratov": 0.40, "Samara": 0.30, "Volgograd": 0.30},
        label="volga grain")


def _sunflower_paths():
    return (
        os.path.join(TRAINING, "oblast_sunflower_yields.csv"),
        os.path.join(TRAINING, "oblast_sunflower_sown_area.csv"),
    )


def southern_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        SUNFLOWER_SOUTH,
        fallback_weights={"Krasnodar": 0.35, "Rostov": 0.40, "Stavropol": 0.25},
        yield_path=yp, area_path=ap, label="sunflower")


def cbe_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        SUNFLOWER_CBE,
        fallback_weights={"Belgorod": 0.25, "Voronezh": 0.30,
                          "Kursk": 0.20, "Tambov": 0.25},
        yield_path=yp, area_path=ap, label="sunflower")


def volga_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        SUNFLOWER_VOLGA,
        fallback_weights={"Saratov": 0.45, "Samara": 0.30, "Volgograd": 0.25},
        yield_path=yp, area_path=ap, label="sunflower")


def belt_sunflower_yield_kg_ha():
    yp, ap = _sunflower_paths()
    return zone_yield_kg_ha(
        SUNFLOWER_BELT, yield_path=yp, area_path=ap, label="sunflower")
