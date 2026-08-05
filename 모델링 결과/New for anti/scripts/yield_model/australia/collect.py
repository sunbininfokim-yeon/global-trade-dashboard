"""
Build Australian state-crop training tables.

Usage (from scripts/yield_model):

    python3 -m australia.collect wa_wheat
    python3 -m australia.collect

Phase 1 intentionally uses NASA POWER as a reproducible global benchmark.  It
does not claim POWER is the best Australian feed: the README pre-registers
SILO/AGCD and AWRA-L as the next source ablation.  Every annual climate feature
is also expressed as a causal 20-season anomaly using only earlier seasons.
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

from . import abares
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
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
SAM_URL = (
    "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/"
    "daily_ao_index/aao/monthly.aao.index.b79.current.ascii"
)
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
        except Exception as exc:  # network feeds fail in several ordinary ways
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


def _cached_text(name: str, url: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not _fresh(path, 30):
        log(f"  {name}: downloading")
        with open(path, "wb") as handle:
            handle.write(fetch(url, timeout=120))
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def load_oni() -> pd.DataFrame:
    rows = []
    for line in _cached_text("oni.txt", ONI_URL).splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            rows.append({"season": parts[0], "year": int(parts[1]),
                         "value": float(parts[3])})
        except ValueError:
            continue
    return pd.DataFrame(rows)


def load_dmi() -> pd.DataFrame:
    rows = []
    for line in _cached_text("dmi.txt", DMI_URL).splitlines():
        parts = line.split()
        if len(parts) != 13:
            continue
        try:
            year = int(parts[0])
            values = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        if not 1800 <= year <= 2100:
            continue
        rows.extend({"year": year, "month": month, "value": value}
                    for month, value in enumerate(values, 1) if value > -90)
    return pd.DataFrame(rows)


def load_sam() -> pd.DataFrame:
    """NOAA CPC monthly Antarctic Oscillation (the SAM circulation index)."""
    rows = []
    for line in _cached_text("sam.txt", SAM_URL).splitlines():
        parts = line.split()
        try:
            if len(parts) == 3:
                year, month, value = int(parts[0]), int(parts[1]), float(parts[2])
                rows.append({"year": year, "month": month, "value": value})
            elif len(parts) == 13:
                year = int(parts[0])
                rows.extend({"year": year, "month": month, "value": float(value)}
                            for month, value in enumerate(parts[1:], 1))
        except ValueError:
            continue
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("NOAA CPC SAM feed parsed to zero rows")
    return frame[(frame.year >= 1979) & (frame.value > -90)].reset_index(drop=True)


def _mean_index(frame: pd.DataFrame, year: int, months: list[int]) -> float:
    window = frame[(frame.year == year) & (frame.month.isin(months))]
    return float(window.value.mean()) if not window.empty else float("nan")


def _oni_mean(oni: pd.DataFrame, selections: list[tuple[int, list[str]]]) -> float:
    values = []
    for year, seasons in selections:
        values.extend(oni[(oni.year == year)
                          & (oni.season.isin(seasons))].value.tolist())
    return float(sum(values) / len(values)) if values else float("nan")


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
    """Add z-scores against the preceding seasons only; current/future excluded."""
    frame = frame.sort_values("year").copy()
    for name in feature_names:
        prior = frame[name].shift(1).rolling(window, min_periods=min_history)
        mean = prior.mean()
        scale = prior.std(ddof=1).replace(0, float("nan"))
        frame[name + "_z20"] = (frame[name] - mean) / scale
    return frame


def build_region(cfg, oni: pd.DataFrame, dmi: pd.DataFrame,
                 sam: pd.DataFrame, target_path: str) -> pd.DataFrame:
    log(f"{cfg.key}: {cfg.label}")
    dailies = {point["name"]: point_weather(point) for point in cfg.points}
    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        features = blend_features(cfg, dailies, year)
        if not features:
            continue
        features["year"] = year
        if cfg.crop == "wheat":
            features.update({
                "iod_winter_spring": _mean_index(dmi, year, [6, 7, 8, 9, 10, 11]),
                "sam_winter_spring": _mean_index(sam, year, [6, 7, 8, 9, 10, 11]),
                "oni_winter_spring": _oni_mean(
                    oni, [(year, ["MJJ", "JJA", "JAS", "ASO", "SON"])]),
            })
        else:
            features["oni_flowering"] = _oni_mean(
                oni, [(year - 1, ["OND", "NDJ"]), (year, ["DJF", "JFM"])])
        rows.append(features)

    frame = pd.DataFrame(rows).sort_values("year")
    raw_features = sorted(set().union(*cfg.feature_sets.values()))
    raw_features = sorted({name[:-4] for name in raw_features if name.endswith("_z20")})
    missing = [name for name in raw_features if name not in frame]
    if missing:
        raise ValueError(f"{cfg.key}: raw features not built: {', '.join(missing)}")
    frame = add_causal_anomalies(frame, raw_features)

    targets = abares.state_crop_series(
        cfg.state_sheet, cfg.crop_label, cfg.harvest_rule, path=target_path)
    frame = frame.merge(targets, on="year", how="left")
    frame["target_source"] = "ABARES Australian Crop Report state data"

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

    target_path = abares.workbook_path()
    log(f"ABARES workbook: {target_path}")
    oni, dmi, sam = load_oni(), load_dmi(), load_sam()
    for cfg in configs:
        build_region(cfg, oni, dmi, sam, target_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

