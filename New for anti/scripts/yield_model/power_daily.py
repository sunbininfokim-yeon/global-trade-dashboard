"""NASA POWER daily point weather and seasonal window features.

Stands in for Earth Engine CHIRPS + ERA5-Land where a model needs to run in
CI without a Google credential. POWER's 0.5-degree cells play the role of the
25-40 km zone buffers the Earth Engine version averaged over.
  precip   PRECTOTCORR (mm/day)
  tmax     T2M_MAX (C)        -> degree-days above a threshold
  tdew     T2MDEW (C)         -> VPD = es(tmax) - ea(tdew), as in the GEE code
  root_sm  GWETROOT (0-1 root-zone wetness; not volumetric, so only its
           anomalies are comparable with the ERA5-Land version)
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "PRECTOTCORR,T2M_MAX,T2MDEW,GWETROOT"
FIRST_DAY = date(1981, 1, 1)
FILL = -900
SOURCE = "nasa_power"


def _get_json(url: str, attempts: int = 6) -> dict:
    delay = 20
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            print(f"[power] retry {attempt + 1} in {delay}s after {exc}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 240)


def _svp(t):
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def point_daily(point: dict, start: date, cache_dir: Path) -> pd.DataFrame:
    """Daily weather from `start` to today, cached for the day."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    slug = f"{point['lat']:.3f}_{point['lon']:.3f}".replace("-", "m").replace(".", "p")
    cached = cache_dir / f"power_{slug}_{start:%Y%m%d}_{date.today().isoformat()}.csv"
    if cached.exists():
        return pd.read_csv(cached, parse_dates=["date"])
    url = (
        f"{POWER_URL}?parameters={PARAMS}&community=AG"
        f"&longitude={point['lon']}&latitude={point['lat']}"
        f"&start={start:%Y%m%d}&end={date.today():%Y%m%d}&format=JSON"
    )
    print(f"[power] {point['name']}: {start} onward", flush=True)
    p = _get_json(url)["properties"]["parameter"]
    frame = pd.DataFrame({
        "date": pd.to_datetime(list(p["T2M_MAX"].keys()), format="%Y%m%d"),
        "precip": list(p["PRECTOTCORR"].values()),
        "tmax": list(p["T2M_MAX"].values()),
        "tdew": list(p["T2MDEW"].values()),
        "root_sm": list(p["GWETROOT"].values()),
    })
    frame = frame[(frame[["precip", "tmax", "tdew", "root_sm"]] > FILL).all(axis=1)]
    frame["vpd"] = (_svp(frame.tmax) - _svp(frame.tdew)).clip(lower=0)
    frame = frame.sort_values("date").reset_index(drop=True)
    frame.to_csv(cached, index=False)
    return frame


class PointWeather:
    """Loads each point once per run, from the earliest window asked for."""

    def __init__(self, points: list[dict], cache_dir: Path):
        self.points = points
        self.cache_dir = cache_dir
        self.start = None
        self.frames = {}

    def daily(self, earliest: date) -> dict:
        if self.start is None or earliest < self.start:
            # One widening step straight to the record start avoids a
            # download per year when a full rebuild walks backwards.
            self.start = max(FIRST_DAY, earliest if self.start is None else FIRST_DAY)
            self.frames = {
                p["name"]: point_daily(p, self.start, self.cache_dir) for p in self.points
            }
        return self.frames

    def latest_date(self) -> str | None:
        if not self.frames:
            return None
        return min(frame.date.max() for frame in self.frames.values()).date().isoformat()


def _window_value(frame: pd.DataFrame, var: str, how: str, start: date, end: date) -> float:
    """Aggregate [start, end), matching Earth Engine's exclusive filterDate end."""
    rows = frame[(frame.date >= pd.Timestamp(start)) & (frame.date < pd.Timestamp(end))]
    if rows.empty:
        return np.nan
    if how == "sum":
        return float(rows[var].sum())
    if how == "mean":
        return float(rows[var].mean())
    if how.startswith("edd"):
        return float((rows.tmax - float(how[3:])).clip(lower=0).sum())
    raise ValueError(how)


def season_features(weather: PointWeather, specs: dict, year: int) -> dict:
    """specs: name -> (var, how, (year_offset, month), (year_offset, month))."""
    earliest = min(date(year + s[2][0], s[2][1], 1) for s in specs.values())
    frames = weather.daily(earliest - timedelta(days=1))
    weights = np.array([p["weight"] for p in weather.points], dtype=float)
    out = {"year": year}
    for name, (var, how, (y0, m0), (y1, m1)) in specs.items():
        values = np.array([
            _window_value(frames[p["name"]], var, how, date(year + y0, m0, 1), date(year + y1, m1, 1))
            for p in weather.points
        ])
        ok = ~np.isnan(values)
        out[name] = float(np.dot(values[ok], weights[ok]) / weights[ok].sum()) if ok.any() else np.nan
    return out
