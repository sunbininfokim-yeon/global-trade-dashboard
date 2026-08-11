"""
Build Canadian province-crop training tables.

Usage (from scripts/yield_model):

    python3 -m canada.collect sk_canola
    python3 -m canada.collect

Labels: Statistics Canada 32-10-0359 average yield (kg/ha).
Climate: NASA POWER daily (phase-1 global benchmark).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

import pandas as pd

from . import statcan
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = (
    "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,GWETROOT,T2MDEW,"
    "ALLSKY_SFC_SW_DWN"
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
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"failed after {attempts} attempts: {url}: {last}")


def _fresh(path: str, days: int = CACHE_DAYS) -> bool:
    return (os.path.exists(path)
            and time.time() - os.path.getmtime(path) < days * 86400)


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
    mapping = {
        "tmax": "T2M_MAX", "tmin": "T2M_MIN", "tmean": "T2M",
        "precip": "PRECTOTCORR", "gwetroot": "GWETROOT",
        "tdew": "T2MDEW", "solar": "ALLSKY_SFC_SW_DWN",
    }
    frame = pd.DataFrame({"date": pd.to_datetime(dates, format="%Y%m%d")})
    for local, remote in mapping.items():
        frame[local] = [params[remote].get(day, -999.0) for day in dates]
    valid = (frame[list(mapping)] > POWER_FILL).all(axis=1)
    frame = frame.loc[valid].reset_index(drop=True)
    frame.to_csv(cached, index=False)
    return frame


def load_oni() -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "oni.txt")
    if not _fresh(path, 30):
        log("  oni.txt: downloading")
        with open(path, "wb") as handle:
            handle.write(fetch(ONI_URL, timeout=120))
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle.read().splitlines()[1:]:
            parts = line.split()
            if len(parts) != 4:
                continue
            try:
                rows.append({"season": parts[0], "year": int(parts[1]),
                             "value": float(parts[3])})
            except ValueError:
                continue
    return pd.DataFrame(rows)


def _oni_mean(oni: pd.DataFrame, year: int, seasons: list[str]) -> float:
    values = oni[(oni.year == year) & (oni.season.isin(seasons))].value
    return float(values.mean()) if not values.empty else float("nan")


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
        prior = frame[name].shift(1).rolling(window, min_periods=min_history)
        mean = prior.mean()
        scale = prior.std(ddof=1)
        # Near-zero variance priors (e.g. rare frost) → leave NaN so the
        # season drops from training rather than inject infinite z-scores.
        scale = scale.mask(scale < 1e-8, float("nan"))
        frame[name + "_z20"] = (frame[name] - mean) / scale
    return frame


def build_region(cfg, oni: pd.DataFrame) -> pd.DataFrame:
    log(f"{cfg.key}: {cfg.label} [{cfg.label_scale}]")
    dailies = {point["name"]: point_weather(point) for point in cfg.points}
    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        features = blend_features(cfg, dailies, year)
        if not features:
            continue
        features["year"] = year
        features["oni_summer"] = _oni_mean(
            oni, year, ["MJJ", "JJA", "JAS", "ASO"])
        rows.append(features)

    frame = pd.DataFrame(rows).sort_values("year")
    raw_features = sorted({
        name[:-4]
        for names in cfg.feature_sets.values()
        for name in names if name.endswith("_z20")
    })
    missing = [name for name in raw_features if name not in frame]
    if missing:
        raise ValueError(f"{cfg.key}: raw features not built: {', '.join(missing)}")
    frame = add_causal_anomalies(frame, raw_features)

    if cfg.label_scale == "sad":
        crop = cfg.sad_crop()
        if cfg.stitch_sk_cd is not None:
            targets = statcan.sad_yield_series(
                "", crop, stitch_sk_cd=cfg.stitch_sk_cd)
        else:
            targets = statcan.sad_yield_series(cfg.geo, crop)
        source = "Statistics Canada 32-10-0002 SAD average yield kg/ha"
    else:
        targets = statcan.province_yield_series(cfg.geo, cfg.crop_label)
        source = "Statistics Canada 32-10-0359 province average yield kg/ha"

    frame = frame.merge(
        targets[["year", "yield_kg_ha", "target_status", "label_scale"]],
        on="year", how="left")
    frame["target_source"] = source

    os.makedirs(TRAINING, exist_ok=True)
    path = os.path.join(TRAINING, f"{cfg.key}.csv")
    frame.to_csv(path, index=False)
    labelled = frame.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(frame)} seasons, {len(labelled)} labelled; "
        f"yield {labelled.yield_kg_ha.min():.0f}-"
        f"{labelled.yield_kg_ha.max():.0f} kg/ha")
    return frame


def main() -> int:
    keys = sys.argv[1:]
    unknown = [key for key in keys if key not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown config(s): {', '.join(unknown)}")
    configs = [BY_KEY[key] for key in keys] if keys else ALL

    # Warm both tables once
    log(f"province table: {statcan.province_csv_path()}")
    log(f"SAD table: {statcan.sad_csv_path()}")
    oni = load_oni()
    for cfg in configs:
        build_region(cfg, oni)
    return 0


if __name__ == "__main__":
    sys.exit(main())
