"""
Fetch NASA POWER and write annual weather-risk tables (no yield labels).

Usage:
  python3 -m latam_banana.collect_risk
  python3 -m latam_banana.collect_risk ecuador_coast_banana
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

from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = (
    "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,WS2M,GWETROOT"
)
POWER_START = "20000101"
POWER_FILL = -900.0
END_YEAR = date.today().year
START_YEAR = 2000
UA = {"User-Agent": "yield-model/1.0 (latam-banana risk panel)"}
CACHE_DAYS = 7


def log(message: str) -> None:
    print(f"[risk] {message}", flush=True)


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
    raise RuntimeError(f"failed: {url}: {last}")


def _fresh(path: str) -> bool:
    return (os.path.exists(path)
            and time.time() - os.path.getmtime(path) < CACHE_DAYS * 86400)


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
        "wind": [params["WS2M"][d] for d in dates],
        "gwetroot": [params["GWETROOT"][d] for d in dates],
    })
    keep = ["tmax", "tmin", "tmean", "precip", "rh_mean", "wind", "gwetroot"]
    frame = frame[(frame[keep] > POWER_FILL).all(axis=1)]
    frame = frame.sort_values("date").reset_index(drop=True)
    frame.to_csv(cached, index=False)
    log(f"  POWER {point['name']}: {len(frame):,} days")
    time.sleep(1.0)
    return frame


def blend(belt, dailies: dict, year: int) -> dict:
    sums: dict[str, float] = {}
    weights: dict[str, float] = {}
    for point in belt.points:
        feats = belt.build(dailies[point["name"]], year)
        for key, value in feats.items():
            if pd.isna(value):
                continue
            sums[key] = sums.get(key, 0.0) + float(value) * point["weight"]
            weights[key] = weights.get(key, 0.0) + point["weight"]
    return {k: sums[k] / weights[k] for k in sums if weights[k] > 0}


def build_belt(belt) -> pd.DataFrame:
    log(f"{belt.key}: risk features (not yield)")
    dailies = {p["name"]: point_weather(p) for p in belt.points}
    rows = []
    for year in range(START_YEAR, END_YEAR + 1):
        feats = blend(belt, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        rows.append(feats)
    frame = pd.DataFrame(rows).sort_values("year")
    os.makedirs(TRAINING, exist_ok=True)
    path = os.path.join(TRAINING, f"{belt.key}_risk.csv")
    frame.to_csv(path, index=False)
    log(f"  wrote {path} ({len(frame)} years)")
    return frame


def main() -> int:
    keys = sys.argv[1:]
    unknown = [k for k in keys if k not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown: {', '.join(unknown)}")
    belts = [BY_KEY[k] for k in keys] if keys else ALL
    for belt in belts:
        build_belt(belt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
