"""
Build one MENA training table per region-crop.

Usage (from scripts/yield_model):

    python3 -m mena.collect              # T1 only
    python3 -m mena.collect --stubs      # include T2 Tunisia stub
    python3 -m mena.collect egypt_nile_wheat

Sources:
  · NASA POWER daily (temp, precip, radiation, wind, GWETROOT) — real
  · FAO-56 ET0 computed locally (brazil.climate) — real
  · NOAA CPC ONI — real
  · NOAA PSL HadISST DMI — real
  · FAOSTAT Wheat yield for Egypt / Morocco / Algeria → labels_official/
  · Blue Nile JJAS precip → nile_inflow_proxy for Egypt (G-REALM placeholder)
  · CHIRPS / ERA5 / GRACE / GEE — **not run**
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import zipfile
from datetime import date

import pandas as pd

from brazil import climate as BC
from . import climate as C
from . import labels as L
from .regions import (ALL, ALL_WITH_STUBS, BLUE_NILE_POINTS, BY_KEY,
                      NILE_WET)

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")
LABELS_OFFICIAL = os.path.join(TRAINING, "labels_official")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
FAOSTAT_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip")
FAOSTAT_MEMBER = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"

POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M,GWETROOT,GWETTOP")
CACHE_SCHEMA = "v1"
POWER_START = "19810101"
POWER_FILL = -900
END_YEAR = date.today().year

# Winter wheat season rolls once sowing starts (~October).
WHEAT_ROLLOVER_MONTH = 10

UA = {"User-Agent": "yield-model-mena/1.0"}


def current_season(cfg=None, today=None):
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", False):
        return today.year
    return today.year + (1 if today.month >= WHEAT_ROLLOVER_MONTH else 0)


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
    delay = 20
    for i in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} in {delay}s after {e}")
            time.sleep(delay)
            delay = min(delay * 2, 240)


def point_weather(point):
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    cached = os.path.join(CACHE, f"power_{CACHE_SCHEMA}_{slug}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    url = (f"{POWER_URL}?parameters={POWER_PARAMS}&community=AG"
           f"&longitude={point['lon']}&latitude={point['lat']}"
           f"&start={POWER_START}&end={END_YEAR}1231&format=JSON")
    log(f"  power {point['name']}: downloading")
    p = retry_json(url)["properties"]["parameter"]

    df = pd.DataFrame({
        "date": pd.to_datetime(list(p["T2M_MAX"].keys()), format="%Y%m%d"),
        "tmax": list(p["T2M_MAX"].values()),
        "tmin": list(p["T2M_MIN"].values()),
        "tmean": list(p["T2M"].values()),
        "precip": list(p["PRECTOTCORR"].values()),
        "rh_mean": list(p["RH2M"].values()),
        "tdew": list(p["T2MDEW"].values()),
        "rs": list(p["ALLSKY_SFC_SW_DWN"].values()),
        "wind": list(p["WS2M"].values()),
        "gwetroot": list(p["GWETROOT"].values()),
        "gwettop": list(p["GWETTOP"].values()),
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean", "tdew", "rs",
                 "wind", "gwetroot", "gwettop"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)

    df["et0"] = BC.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)

    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean", "vpd_max",
             "et0", "gwetroot", "gwettop"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day")
    time.sleep(1.5)
    return df


def load_oni():
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "oni.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("oni: downloading")
    text = fetch(ONI_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        seas, yr, _total, anom = parts
        try:
            rows.append({"season": seas, "year": int(yr), "anom": float(anom)})
        except ValueError:
            continue
    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    return df


def load_dmi():
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "dmi.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("dmi (IOD): downloading")
    text = fetch(DMI_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 13:
            continue
        try:
            year = int(parts[0])
            vals = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        if not 1800 <= year <= 2100:
            continue
        for month, v in enumerate(vals, start=1):
            if v < -90:
                continue
            rows.append({"year": year, "month": month, "dmi": v})

    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    log(f"  dmi: {df.year.min()}-{df.year.max()}, {len(df)} months")
    return df


def oni_for(oni, year, window):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def oni_ndj(oni, year):
    vals = list(oni[(oni.year == year) & (oni.season == "DJF")].anom)
    if vals:
        return float(vals[0])
    return oni_for(oni, year, (set(), {"DJF"}))


def iod_ond(dmi, year):
    """Mean DMI over OND of the planting year (harvest y → OND of y−1)."""
    w = dmi[(dmi.year == year - 1) & (dmi.month.isin([10, 11, 12]))]
    return float(w.dmi.mean()) if not w.empty else None


def blend_features(cfg, dailies, year):
    """Point-level build then production-weight — never mean weather first."""
    acc, wsum = {}, {}
    for p in cfg.points:
        try:
            feats = cfg.build(dailies[p["name"]], year, p)
        except Exception as e:  # noqa: BLE001
            log(f"  {year} {p['name']}: {e}")
            continue
        for k, v in (feats or {}).items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            acc[k] = acc.get(k, 0.0) + float(v) * p["weight"]
            wsum[k] = wsum.get(k, 0.0) + p["weight"]
    return {k: acc[k] / wsum[k] for k in acc if wsum[k] > 0}


def nile_inflow_proxy(blue_dailies, year):
    """Blue Nile JJAS precip sum — upstream inflow memory for Egypt."""
    jjas = [(6, -1), (7, -1), (8, -1)]
    acc, wsum = 0.0, 0.0
    for p in BLUE_NILE_POINTS:
        daily = blue_dailies[p["name"]]
        psum = C.window_sum(daily, "precip", jjas, year)
        if not pd.isna(psum):
            acc += psum * p["weight"]
            wsum += p["weight"]
    return acc / wsum if wsum > 0 else None


def apply_salt_with_oni(feats, oni_val, wet_recharge=None):
    if oni_val is None:
        return feats
    coast = feats.get("coast_km", 80.0)
    dry = feats.get("wd_gs", feats.get("wd_eff", 50.0))
    wet = wet_recharge if wet_recharge is not None else feats.get(
        "nile_inflow_proxy", 400.0)
    salt = C.delta_salt_proxy(coast, dry, oni_val, wet)
    feats["salt_proxy"] = salt["salt_proxy"]
    feats["delta_salt"] = salt["delta_salt"]
    return feats


def faostat_zip():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "faostat_production.zip")
    if not os.path.exists(path):
        log("FAOSTAT bulk production downloading (~34 MB)")
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(fetch(FAOSTAT_URL, timeout=600))
        os.replace(tmp, path)
    return path


def fetch_faostat_labels(area: str, key: str):
    """Write labels_official/{key}.csv from FAOSTAT national wheat yield."""
    os.makedirs(LABELS_OFFICIAL, exist_ok=True)
    out = os.path.join(LABELS_OFFICIAL, f"{key}.csv")
    usecols = ["Area", "Item", "Element", "Year", "Unit", "Value"]
    chunks = []
    with zipfile.ZipFile(faostat_zip()) as zf, zf.open(FAOSTAT_MEMBER) as src:
        for chunk in pd.read_csv(src, encoding="latin-1", usecols=usecols,
                                 chunksize=250000):
            keep = (chunk.Area.eq(area) & chunk.Item.eq("Wheat")
                    & chunk.Element.eq("Yield"))
            if keep.any():
                chunks.append(chunk[keep])
    if not chunks:
        log(f"  FAOSTAT: no wheat yield for {area}")
        return None
    df = pd.concat(chunks, ignore_index=True)
    labels = (df[["Year", "Value"]]
              .rename(columns={"Year": "year", "Value": "yield_kg_ha"})
              .dropna()
              .drop_duplicates("year")
              .sort_values("year"))
    labels["label_source"] = L.LABEL_SOURCE_FAOSTAT
    labels["label_note"] = (
        f"FAOSTAT national wheat yield for {area}; not subnational season.")
    labels.to_csv(out, index=False)
    log(f"  FAOSTAT {area}: {len(labels)} years -> {os.path.basename(out)}")
    return labels


def ensure_official_labels(configs):
    for cfg in configs:
        if cfg.faostat_area and not cfg.stub:
            fetch_faostat_labels(cfg.faostat_area, cfg.key)


def build_region(cfg, oni, dmi, blue_dailies=None):
    log(f"{cfg.key}: {cfg.label}"
        + (" [stub]" if cfg.stub else ""))
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(oni, year, cfg.oni_window)
        feats["oni_ndj"] = oni_ndj(oni, year)
        feats["iod_ond"] = iod_ond(dmi, year)

        if cfg.key.startswith("egypt") and blue_dailies:
            proxy = nile_inflow_proxy(blue_dailies, year)
            if proxy is not None:
                feats["nile_inflow_proxy"] = proxy
            oni_s = feats["oni_ndj"] if feats["oni_ndj"] is not None \
                else feats["oni_season"]
            wet = feats.get("nile_inflow_proxy")
            feats = apply_salt_with_oni(feats, oni_s or 0.0, wet_recharge=wet)

        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no seasons produced")
        return df

    df = L.attach_labels(cfg, df)
    src = (df.label_source.dropna().iloc[0]
           if "label_source" in df.columns and df.label_source.notna().any()
           else "unknown")
    log(f"  label_source={src}")

    for name, source in cfg.panel.items():
        if source in df.columns:
            s = df[source].astype(float)
            df[name] = (s - s.mean()) / (s.std() or 1.0)
        else:
            log(f"  panel {name}: missing source {source}")

    df = df.sort_values("year").reset_index(drop=True)
    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)

    labelled = df.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with yield), "
        f"{len(df.columns)} cols -> {os.path.basename(out)}")
    if len(labelled):
        log(f"  yield {labelled.yield_kg_ha.min():.0f}-"
            f"{labelled.yield_kg_ha.max():.0f} kg/ha "
            f"({int(labelled.year.min())}-{int(labelled.year.max())})")
    return df


def write_schema_stub(cfg):
    os.makedirs(TRAINING, exist_ok=True)
    cols = (["year"] + list(cfg.core) + ["yield_kg_ha", "label_source"])
    path = os.path.join(TRAINING, f"{cfg.key}.schema.csv")
    pd.DataFrame(columns=cols).to_csv(path, index=False)
    log(f"{cfg.key}: schema stub only -> {os.path.basename(path)}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    use_stubs = False
    if "--stubs" in argv:
        use_stubs = True
        argv.remove("--stubs")
    if "--schema-only-stubs" in argv:
        argv.remove("--schema-only-stubs")
        for cfg in ALL_WITH_STUBS:
            if cfg.stub:
                write_schema_stub(cfg)
        return 0

    if argv:
        configs = [BY_KEY[k] for k in argv]
    else:
        configs = list(ALL_WITH_STUBS if use_stubs else ALL)

    for cfg in ALL_WITH_STUBS:
        if cfg.stub and cfg not in configs:
            write_schema_stub(cfg)

    ensure_official_labels(configs)

    oni = load_oni()
    dmi = load_dmi()
    blue_dailies = {p["name"]: point_weather(p) for p in BLUE_NILE_POINTS}

    for cfg in configs:
        if cfg.stub and not use_stubs and cfg.key not in (argv or []):
            write_schema_stub(cfg)
            continue
        build_region(cfg, oni, dmi, blue_dailies=blue_dailies)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
