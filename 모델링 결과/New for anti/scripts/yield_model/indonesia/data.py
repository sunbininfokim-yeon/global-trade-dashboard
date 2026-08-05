"""Official/open data clients for the Indonesia yield models."""

import json
import os
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta

import pandas as pd

from . import climate as C


HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = (
    "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
    "ALLSKY_SFC_SW_DWN,GWETROOT"
)
POWER_START = "19840101"
POWER_FILL = -900

FAOSTAT_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
FAOSTAT_MEMBER = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def log(message):
    print("[indonesia:data] " + message, flush=True)


def fetch(url, timeout=300):
    request = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def retry_fetch(url, attempts=5, timeout=300):
    delay = 5
    for attempt in range(attempts):
        try:
            return fetch(url, timeout=timeout)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)


def _slug(point):
    raw = "{:.2f}_{:.2f}".format(point["lat"], point["lon"])
    return raw.replace("-", "m").replace(".", "p")


def point_weather(point, refresh=False):
    """NASA POWER daily history for one production point."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "power_{}.csv".format(_slug(point)))
    if os.path.exists(cached) and not refresh:
        frame = pd.read_csv(cached, parse_dates=["date"])
        if not frame.empty and frame.date.max().date() >= date.today() - timedelta(days=7):
            return C.add_vpd(frame)

    end = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    query = urllib.parse.urlencode({
        "parameters": POWER_PARAMS,
        "community": "AG",
        "longitude": point["lon"],
        "latitude": point["lat"],
        "start": POWER_START,
        "end": end,
        "format": "JSON",
    })
    log("POWER {} downloading".format(point["name"]))
    payload = json.loads(retry_fetch(POWER_URL + "?" + query))
    parameters = payload["properties"]["parameter"]
    frame = pd.DataFrame(parameters)
    frame.index = pd.to_datetime(frame.index, format="%Y%m%d")
    frame.index.name = "date"
    frame = frame.reset_index().rename(columns={
        "T2M_MAX": "tmax", "T2M_MIN": "tmin", "T2M": "tmean",
        "PRECTOTCORR": "precip", "RH2M": "rh_mean", "T2MDEW": "tdew",
        "ALLSKY_SFC_SW_DWN": "solar", "GWETROOT": "soil",
    })
    frame = frame[["date"] + C.WEATHER_COLUMNS]
    frame = frame[(frame[C.WEATHER_COLUMNS] > POWER_FILL).all(axis=1)]
    frame = frame.sort_values("date").reset_index(drop=True)
    frame.to_csv(cached, index=False)
    time.sleep(1)
    return C.add_vpd(frame)


def point_forecast(point, refresh=False):
    """Open-Meteo 16-day temperature/precipitation/radiation forecast."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(
        CACHE, "forecast_{}_{}.csv".format(_slug(point), date.today().isoformat()))
    if os.path.exists(cached) and not refresh:
        return pd.read_csv(cached, parse_dates=["date"])

    query = urllib.parse.urlencode({
        "latitude": point["lat"], "longitude": point["lon"],
        "daily": ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
                  "shortwave_radiation_sum"),
        "forecast_days": 16, "timezone": "auto",
    })
    payload = json.loads(retry_fetch(FORECAST_URL + "?" + query, timeout=60))
    daily = payload["daily"]
    frame = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "tmax": daily["temperature_2m_max"],
        "tmin": daily["temperature_2m_min"],
        "precip": daily["precipitation_sum"],
        "solar": daily["shortwave_radiation_sum"],
    })
    frame["tmean"] = (frame.tmax + frame.tmin) / 2.0
    frame.to_csv(cached, index=False)
    return frame


def faostat_zip():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "faostat_production.zip")
    if not os.path.exists(path):
        log("FAOSTAT bulk production downloading (~34 MB)")
        temporary = path + ".part"
        with open(temporary, "wb") as handle:
            handle.write(retry_fetch(FAOSTAT_URL, timeout=600))
        os.replace(temporary, path)
    return path


def faostat_indonesia(items):
    """Return official FAOSTAT annual yield, area and production for items."""
    wanted = set(items)
    usecols = ["Area", "Item", "Element", "Year", "Unit", "Value", "Flag"]
    chunks = []
    with zipfile.ZipFile(faostat_zip()) as archive, archive.open(FAOSTAT_MEMBER) as source:
        for chunk in pd.read_csv(
                source, encoding="latin-1", usecols=usecols, chunksize=250000):
            keep = chunk.Area.eq("Indonesia") & chunk.Item.isin(wanted)
            if keep.any():
                chunks.append(chunk[keep])
    if not chunks:
        raise RuntimeError("No Indonesia rows found in FAOSTAT bulk file")
    long = pd.concat(chunks, ignore_index=True)

    values = long.pivot_table(
        index=["Item", "Year"], columns="Element", values="Value", aggfunc="first")
    flags = long.pivot_table(
        index=["Item", "Year"], columns="Element", values="Flag", aggfunc="first")
    values = values.rename(columns={
        "Yield": "yield_kg_ha", "Area harvested": "area_ha",
        "Production": "production_tonnes",
    })
    flags = flags.rename(columns={
        "Yield": "yield_flag", "Area harvested": "area_flag",
        "Production": "production_flag",
    })
    return values.join(flags).reset_index().rename(columns={"Item": "item", "Year": "year"})


def load_oni(refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "oni.csv")
    if os.path.exists(cached) and not refresh:
        return pd.read_csv(cached)
    text = retry_fetch(ONI_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            rows.append({"season": parts[0], "year": int(parts[1]),
                         "anom": float(parts[3])})
        except ValueError:
            continue
    frame = pd.DataFrame(rows)
    frame.to_csv(cached, index=False)
    return frame


def oni_for(oni, year):
    """Indonesia dry-season ENSO state preceding the labelled harvest year."""
    seasons = {"JJA", "JAS", "ASO", "SON", "OND"}
    values = oni[(oni.year == year - 1) & oni.season.isin(seasons)].anom
    return float(values.mean()) if len(values) else None

