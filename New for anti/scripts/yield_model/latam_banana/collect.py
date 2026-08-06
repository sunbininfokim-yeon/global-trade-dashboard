"""
Build LatAm banana training tables.

Usage (from scripts/yield_model):

    python3 -m latam_banana.collect
    python3 -m latam_banana.collect ecuador_coast_banana

Labels merge only if province CSVs exist; otherwise feature tables are
still written with empty target for inspection.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

from .labels import province_available, refresh_label_resolution
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = (
    "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
    "ALLSKY_SFC_SW_DWN,WS2M,GWETROOT"
)
POWER_START = "19810101"
POWER_FILL = -900.0
END_YEAR = date.today().year
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
UA = {"User-Agent": "yield-model/1.0 (public climate-data client)"}
CACHE_DAYS = 7


def log(message: str) -> None:
    print(f"[collect] {message}", flush=True)


def fetch(url: str, timeout: int = 300, attempts: int = 5) -> bytes:
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"failed after {attempts} attempts: {url}: {last}")


def _fresh(path: str, days: int = CACHE_DAYS) -> bool:
    return (os.path.exists(path)
            and time.time() - os.path.getmtime(path) < days * 86400)


def _svp(temp_c: pd.Series) -> pd.Series:
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def point_weather(point: dict) -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    slug = point["name"].lower().replace(" ", "_")
    cached = os.path.join(CACHE, f"power_v1_{slug}.csv")
    if _fresh(cached):
        frame = pd.read_csv(cached, parse_dates=["date"])
        if frame.date.dt.year.max() >= END_YEAR - 1:
            return frame

    query = urllib.parse.urlencode({
        "parameters": POWER_PARAMS,
        "community": "AG",
        "longitude": point["lon"],
        "latitude": point["lat"],
        "start": POWER_START,
        "end": f"{END_YEAR}1231",
        "format": "JSON",
    })
    log(f"  POWER {point['name']}: downloading")
    payload = json.loads(fetch(f"{POWER_URL}?{query}").decode("utf-8"))
    params = payload["properties"]["parameter"]
    dates = sorted(params["T2M_MAX"])
    frame = pd.DataFrame({
        "date": pd.to_datetime(dates, format="%Y%m%d"),
        "tmax": [params["T2M_MAX"][d] for d in dates],
        "tmin": [params["T2M_MIN"][d] for d in dates],
        "tmean": [params["T2M"][d] for d in dates],
        "precip": [params["PRECTOTCORR"][d] for d in dates],
        "rh_mean": [params["RH2M"][d] for d in dates],
        "tdew": [params["T2MDEW"][d] for d in dates],
        "rs": [params["ALLSKY_SFC_SW_DWN"][d] for d in dates],
        "wind": [params["WS2M"][d] for d in dates],
        "gwetroot": [params["GWETROOT"][d] for d in dates],
    })
    keep = ["tmax", "tmin", "tmean", "precip", "rh_mean",
            "tdew", "rs", "wind", "gwetroot"]
    frame = frame[(frame[keep] > POWER_FILL).all(axis=1)]
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["vpd_max"] = (_svp(frame.tmax) - _svp(frame.tdew)).clip(lower=0)
    frame.to_csv(cached, index=False)
    log(f"  POWER {point['name']}: {len(frame):,} days")
    time.sleep(1.2)
    return frame


def load_oni() -> pd.DataFrame:
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
            rows.append({"season": seas, "year": int(yr), "value": float(anom)})
        except ValueError:
            continue
    frame = pd.DataFrame(rows)
    frame.to_csv(cached, index=False)
    return frame


def oni_amj(oni: pd.DataFrame, year: int) -> float:
    """Apr–Jun ONI mean — Ecuador dry-season ENSO context."""
    vals = oni[(oni.year == year) & (oni.season.isin(["AMJ", "MJJ", "JJA"]))].value
    return float(vals.mean()) if len(vals) else float("nan")


def blend_features(cfg, dailies: dict[str, pd.DataFrame], year: int) -> dict:
    sums: dict[str, float] = {}
    weights: dict[str, float] = {}
    for point in cfg.points:
        features = cfg.build(dailies[point["name"]], year)
        for key, value in features.items():
            if pd.isna(value):
                continue
            sums[key] = sums.get(key, 0.0) + float(value) * point["weight"]
            weights[key] = weights.get(key, 0.0) + point["weight"]
    return {key: sums[key] / weights[key] for key in sums if weights[key] > 0}


def add_causal_anomalies(frame: pd.DataFrame, feature_names: list[str],
                         window: int = 20, min_history: int = 10) -> pd.DataFrame:
    frame = frame.sort_values("year").copy()
    for name in feature_names:
        if name not in frame.columns:
            continue
        prior = frame[name].shift(1).rolling(window, min_periods=min_history)
        mean = prior.mean()
        scale = prior.std(ddof=1).replace(0, float("nan"))
        frame[name + "_z20"] = (frame[name] - mean) / scale
    return frame


def build_region(cfg, oni: pd.DataFrame) -> pd.DataFrame:
    log(f"{cfg.key}: {cfg.label}")
    if cfg.label_resolution == "blocked":
        log("  NOTE: province labels blocked — features with empty target")

    dailies = {point["name"]: point_weather(point) for point in cfg.points}
    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        features = blend_features(cfg, dailies, year)
        if not features:
            continue
        features["year"] = year
        if cfg.country == "ecuador":
            features["oni_amj"] = oni_amj(oni, year)
        rows.append(features)

    frame = pd.DataFrame(rows).sort_values("year")
    raw = sorted(set().union(*cfg.feature_sets.values()))
    raw = sorted({name[:-4] for name in raw if name.endswith("_z20")})
    missing = [name for name in raw if name not in frame.columns]
    if missing:
        raise ValueError(f"{cfg.key}: raw features not built: {', '.join(missing)}")
    frame = add_causal_anomalies(frame, raw)

    try:
        target = cfg.target()
        frame = frame.merge(target, on="year", how="left")
        if "yield_kg_ha" not in frame.columns and "target" in frame.columns:
            frame["yield_kg_ha"] = frame["target"]
    except FileNotFoundError as exc:
        log(f"  labels unavailable: {exc}")
        frame["target"] = pd.NA
        frame["yield_kg_ha"] = pd.NA

    os.makedirs(TRAINING, exist_ok=True)
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    frame.to_csv(path, index=False)
    labelled = frame.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(frame)} seasons ({len(labelled)} labelled) -> "
        f"{os.path.basename(path)}")
    return frame


def main() -> int:
    keys = sys.argv[1:]
    unknown = [key for key in keys if key not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown config(s): {', '.join(unknown)}")
    configs = [BY_KEY[key] for key in keys] if keys else ALL
    refresh_label_resolution(configs)
    log(f"province CSVs: {'OK' if province_available() else 'MISSING'}")
    oni = load_oni()
    for cfg in configs:
        build_region(cfg, oni)
    return 0


if __name__ == "__main__":
    sys.exit(main())
