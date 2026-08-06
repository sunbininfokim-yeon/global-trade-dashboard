"""
Build training tables for Russia winter-wheat configs.

Usage (from scripts/yield_model):
  python3 -m russia.collect [region_key ...]

NASA POWER daily (with GWETROOT). Optional ERA5-Land snow_depth via Open-Meteo
archive is joined when `--snow` is passed or env RUSSIA_FETCH_SNOW=1.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from . import climate as C
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
OM_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

# Soil = POWER only (no Open-Meteo soil). Snow is a separate optional join.
POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M,GWETROOT")
CACHE_SCHEMA = "v1"
POWER_START = "19810101"
POWER_FILL = -900
END_YEAR = 2025

ONI_WINTER = ({"DJF", "JFM"}, {"MAM", "AMJ"})

# Winter wheat harvested ~Jun–Jul; next season sown ~Sep–Oct → rollover Oct.
SEASON_ROLLOVER = 10


def log(msg):
    print(f"[collect] {msg}", flush=True)


def current_season(cfg=None):
    now = datetime.now(timezone.utc)
    return now.year if now.month < SEASON_ROLLOVER else now.year + 1


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
    delay = 30
    for i in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} in {delay}s after {e}")
            time.sleep(delay)
            delay = min(delay * 2, 480)


def point_slug(point):
    return f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")


def point_weather(point, fetch_snow=False):
    """
    Daily POWER frame. Optional snow_depth (m) from Open-Meteo ERA5-Land.

    ERA5-Land snow can overestimate pack depth; treat threshold 0.05 m as a
    reanalysis scale, not field centimetres (deep-dive + Aase notes).
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = point_slug(point)
    cached = os.path.join(CACHE, f"power_{CACHE_SCHEMA}_{slug}.csv")
    if os.path.exists(cached):
        df = pd.read_csv(cached, parse_dates=["date"])
    else:
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
        })
        keep = ["tmax", "tmin", "tmean", "precip", "rh_mean",
                "tdew", "rs", "wind", "gwetroot"]
        df = df[(df[keep] > POWER_FILL).all(axis=1)]
        df = df.sort_values("date").reset_index(drop=True)
        df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
        df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
        df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean",
                 "wind", "rs", "gwetroot", "vpd_max", "et0"]]
        df.to_csv(cached, index=False)
        log(f"  power {point['name']}: {len(df):,} days, "
            f"mean GWETROOT {df.gwetroot.mean():.2f}")
        time.sleep(1.5)

    if fetch_snow and "snow_depth" not in df.columns:
        snow = fetch_era5_snow(point)
        if snow is not None and not snow.empty:
            df = df.merge(snow, on="date", how="left")
            # Refresh cache with snow joined for faster reruns
            df.to_csv(cached, index=False)
    return df


def fetch_era5_snow(point):
    """
    Daily mean snow depth (m) from Open-Meteo archive, models=era5_land.

    Year-chunked to keep response size manageable. Failures return None so
    training continues on bare-frost winterkill only.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = point_slug(point)
    cached = os.path.join(CACHE, f"era5_snow_{slug}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    frames = []
    # Archive free tier: request per multi-year block
    for start_y in range(1981, END_YEAR + 1, 5):
        end_y = min(start_y + 4, END_YEAR)
        url = (f"{OM_ARCHIVE}?latitude={point['lat']}&longitude={point['lon']}"
               f"&start_date={start_y}-01-01&end_date={end_y}-12-31"
               f"&daily=snow_depth&models=era5_land&timezone=UTC")
        try:
            log(f"  era5 snow {point['name']} {start_y}-{end_y}")
            data = retry_json(url, attempts=3, timeout=120)
            daily = data.get("daily") or {}
            if not daily.get("time"):
                continue
            frame = pd.DataFrame({
                "date": pd.to_datetime(daily["time"]),
                "snow_depth": daily.get("snow_depth"),
            })
            frames.append(frame)
            time.sleep(0.8)
        except Exception as e:  # noqa: BLE001
            log(f"  era5 snow failed {point['name']} {start_y}: {e}")
            continue

    if not frames:
        return None
    out = (pd.concat(frames, ignore_index=True)
           .drop_duplicates("date")
           .sort_values("date")
           .reset_index(drop=True))
    out.to_csv(cached, index=False)
    log(f"  era5 snow {point['name']}: {len(out):,} days")
    return out


def blend_features(cfg, dailies, year):
    acc, wsum = {}, {}
    for p in cfg.points:
        try:
            feats = cfg.build(dailies[p["name"]], year)
        except Exception as e:  # noqa: BLE001
            log(f"  {year} {p['name']}: {e}")
            continue
        for k, v in (feats or {}).items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            acc[k] = acc.get(k, 0.0) + float(v) * p["weight"]
            wsum[k] = wsum.get(k, 0.0) + p["weight"]
    return {k: acc[k] / wsum[k] for k in acc if wsum[k] > 0}


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


def oni_for(oni, year, window=ONI_WINTER):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def build_region(cfg, oni, fetch_snow=False):
    log(f"{cfg.key}: {cfg.label}")
    dailies = {p["name"]: point_weather(p, fetch_snow=fetch_snow)
               for p in cfg.points}
    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(oni, year)
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no features produced")
        return df

    target = cfg.target()
    df = df.merge(target, on="year", how="left")

    for name, source in cfg.panel.items():
        if source in df.columns:
            df[name] = C.spi(df[source]).reindex(df.index)
        else:
            log(f"  panel {name}: source {source} missing")

    df = df.sort_values("year").reset_index(drop=True)
    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)
    labelled = df.dropna(subset=["target"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with target) -> "
        f"{os.path.basename(out)}")
    if len(labelled):
        log(f"  {cfg.target_label} {labelled.target.min():,.0f}-"
            f"{labelled.target.max():,.0f} {cfg.target_unit}")
    return df


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    fetch_snow = "--snow" in argv or os.environ.get("RUSSIA_FETCH_SNOW") == "1"
    argv = [a for a in argv if a != "--snow"]
    configs = [BY_KEY[k] for k in argv] if argv else ALL

    if fetch_snow:
        log("ERA5-Land snow_depth join enabled")
    else:
        log("POWER-only winterkill (use --snow for ERA5-Land snow_depth)")

    oni = load_oni()
    for cfg in configs:
        build_region(cfg, oni, fetch_snow=fetch_snow)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
