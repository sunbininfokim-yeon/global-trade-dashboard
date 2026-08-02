"""
Collect the training table for the Brazil soybean yield model.

Sources (all keyless):
  - FAOSTAT bulk  : national soybean yield, 1961-2024
  - Open-Meteo ERA5: daily weather per producing state, 1980-
  - NOAA ONI       : El Nino / La Nina, 1950-

Brazil's soybean season runs across the calendar year boundary: planting
Sep-Dec, harvest Feb-May. FAOSTAT labels a season by its *harvest* year, so
the weather window for harvest year Y starts in Sep of Y-1.

Output: brazil_soy_training.csv, one row per harvest year.
"""

import io
import json
import os
import sys
import time
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "brazil_soy_training.csv")

FAOSTAT_ZIP = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Soil moisture comes from NASA POWER, not Open-Meteo, on purpose.
#
# Open-Meteo's soil_moisture_0_to_7cm_mean has a level shift starting in 2025:
# at Goias, Jan-Feb 2024 and Jan-Feb 2025 both recorded 348 mm of rain, yet
# its soil moisture fell 0.463 -> 0.351 (-24%), which cannot follow from
# identical rainfall. NASA POWER's root-zone wetness over the same two
# seasons goes 0.716 -> 0.754, i.e. slightly wetter -- consistent with 2025
# being a record Brazilian crop.
#
# Soil moisture was the model's two strongest features, so training on
# Open-Meteo values and then predicting on post-2025 values pushed the
# features 5+ standard deviations out of distribution and produced an
# 800 kg/ha underforecast. POWER is one continuous series from 1981.

# Soybean-producing states with approximate production centroids and their
# share of the national crop. Weather is averaged across these, weighted by
# share, so a drought in Mato Grosso moves the national figure more than one
# in Bahia.
REGIONS = [
    {"name": "Mato Grosso",        "lat": -12.6, "lon": -55.4, "weight": 0.28},
    {"name": "Parana",             "lat": -24.5, "lon": -51.5, "weight": 0.14},
    {"name": "Rio Grande do Sul",  "lat": -29.5, "lon": -53.5, "weight": 0.13},
    {"name": "Goias",              "lat": -16.0, "lon": -49.5, "weight": 0.10},
    {"name": "Mato Grosso do Sul", "lat": -20.5, "lon": -54.5, "weight": 0.09},
    {"name": "Bahia",              "lat": -12.0, "lon": -45.5, "weight": 0.07},
]

# NASA POWER's record starts 1981-01-01, and each season needs the previous
# September, so 1982 is the first harvest year with complete coverage.
START_YEAR = 1982
END_YEAR = 2024
POWER_EPOCH = "19810101"

# Growth stages, as (month, year-offset) windows. Offset -1 = previous
# calendar year. Pod fill is the water-stress-critical window for soybeans.
STAGES = {
    "planting":   [(9, -1), (10, -1), (11, -1)],
    "vegetative": [(12, -1), (1, 0)],
    "podfill":    [(1, 0), (2, 0)],
    "harvest":    [(3, 0), (4, 0)],
}

# Soybean base temperature for growing degree days (deg C).
GDD_BASE = 10.0


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_faostat_yield():
    """Brazil soybean yield (kg/ha) by year."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "faostat_brazil_soy.csv")
    if os.path.exists(cached):
        log("FAOSTAT: using cache")
        return pd.read_csv(cached)

    log("FAOSTAT: downloading bulk archive (~34 MB)")
    raw = fetch(FAOSTAT_ZIP)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(n for n in z.namelist() if n.endswith("(Normalized).csv"))
        with z.open(name) as f:
            df = pd.read_csv(
                f, encoding="latin-1", low_memory=False,
                usecols=["Area", "Item", "Element", "Year", "Unit", "Value"],
            )

    df = df[
        (df.Area == "Brazil")
        & (df.Item == "Soya beans")
        & (df.Element == "Yield")
    ][["Year", "Value", "Unit"]].rename(columns={"Year": "year", "Value": "yield_kg_ha"})

    df = df.dropna().sort_values("year").reset_index(drop=True)
    df.to_csv(cached, index=False)
    log(f"FAOSTAT: {len(df)} years ({df.year.min()}-{df.year.max()})")
    return df


def load_oni():
    """Seasonal ONI -> mean over the Brazilian growing season (SON..FMA)."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "oni.csv")
    if os.path.exists(cached):
        log("ONI: using cache")
        return pd.read_csv(cached)

    log("ONI: downloading")
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

    # Seasons spanning the Brazilian season; OND/NDJ/DJF/JFM/FMA. The ones
    # starting in the previous calendar year are attributed to harvest year Y.
    prev = {"OND", "NDJ"}
    cur = {"DJF", "JFM", "FMA"}
    out = []
    for y in range(START_YEAR, END_YEAR + 1):
        vals = list(df[(df.year == y - 1) & (df.season.isin(prev))].anom)
        vals += list(df[(df.year == y) & (df.season.isin(cur))].anom)
        if vals:
            out.append({"year": y, "oni_season": sum(vals) / len(vals)})

    res = pd.DataFrame(out)
    res.to_csv(cached, index=False)
    log(f"ONI: {len(res)} years")
    return res


def load_region_weather(region):
    """Daily ERA5 for one region, cached to disk."""
    os.makedirs(CACHE, exist_ok=True)
    slug = region["name"].lower().replace(" ", "_")
    cached = os.path.join(CACHE, f"weather_{slug}.csv")
    if os.path.exists(cached):
        log(f"weather[{region['name']}]: using cache")
        return pd.read_csv(cached, parse_dates=["date"])

    url = (
        f"{ARCHIVE_URL}?latitude={region['lat']}&longitude={region['lon']}"
        f"&start_date={START_YEAR - 1}-09-01&end_date={END_YEAR}-12-31"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "et0_fao_evapotranspiration&timezone=UTC"
    )
    log(f"weather[{region['name']}]: downloading {START_YEAR - 1}-{END_YEAR}")
    data = retry_json(url)

    d = data["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "tmax": d["temperature_2m_max"],
        "tmin": d["temperature_2m_min"],
        "precip": d["precipitation_sum"],
        "et0": d["et0_fao_evapotranspiration"],
    })

    df = df.merge(load_region_soil(region), on="date", how="left")
    df.to_csv(cached, index=False)
    log(f"weather[{region['name']}]: {len(df):,} days, "
        f"soil missing {int(df.soil.isna().sum())}")
    return df


def retry_json(url, attempts=3, timeout=300):
    for attempt in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001 - retry any transport failure
            if attempt == attempts - 1:
                raise
            log(f"  retry {attempt + 1} after {e}")
            time.sleep(10)


def load_region_soil(region):
    """NASA POWER root-zone soil wetness (GWETROOT), one continuous series."""
    slug = region["name"].lower().replace(" ", "_")
    cached = os.path.join(CACHE, f"soil_{slug}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    url = (
        f"{POWER_URL}?parameters=GWETROOT&community=AG"
        f"&longitude={region['lon']}&latitude={region['lat']}"
        f"&start={POWER_EPOCH}&end={END_YEAR}1231&format=JSON"
    )
    log(f"soil[{region['name']}]: downloading NASA POWER")
    data = retry_json(url)

    series = data["properties"]["parameter"]["GWETROOT"]
    rows = [
        {"date": pd.to_datetime(k, format="%Y%m%d"), "soil": v}
        for k, v in series.items()
        if v is not None and v > -100  # POWER uses -999 as its fill value
    ]
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df.to_csv(cached, index=False)
    return df


def stage_features(df, harvest_year):
    """Aggregate one region's daily weather into per-stage features."""
    feats = {}
    for stage, months in STAGES.items():
        mask = False
        for month, offset in months:
            y = harvest_year + offset
            mask = mask | ((df.date.dt.year == y) & (df.date.dt.month == month))
        w = df[mask]
        if w.empty:
            return None

        tmean = (w.tmax + w.tmin) / 2
        # GDD caps the daily contribution at 30C: past that soybeans gain no
        # further development, so uncapped sums would reward damaging heat.
        gdd = (tmean.clip(upper=30.0) - GDD_BASE).clip(lower=0).sum()

        feats[f"{stage}_gdd"] = gdd
        feats[f"{stage}_precip"] = w.precip.sum()
        feats[f"{stage}_soil"] = w.soil.mean()
        # Water balance: rainfall minus atmospheric demand. Negative means the
        # crop drew down soil moisture faster than rain replaced it.
        feats[f"{stage}_wbal"] = w.precip.sum() - w.et0.sum()
        feats[f"{stage}_hotdays"] = int((w.tmax > 34.0).sum())
    return feats


def main():
    yields = load_faostat_yield()
    oni = load_oni()

    weather = {r["name"]: load_region_weather(r) for r in REGIONS}

    rows = []
    for year in range(START_YEAR, END_YEAR + 1):
        blended = {}
        total_w = 0.0
        for r in REGIONS:
            f = stage_features(weather[r["name"]], year)
            if f is None:
                continue
            for k, v in f.items():
                blended[k] = blended.get(k, 0.0) + v * r["weight"]
            total_w += r["weight"]
        if not blended or total_w == 0:
            continue
        # Normalise in case a region was skipped for this year.
        blended = {k: v / total_w for k, v in blended.items()}
        blended["year"] = year
        rows.append(blended)

    feat = pd.DataFrame(rows)
    df = feat.merge(yields, on="year", how="inner").merge(oni, on="year", how="left")
    df = df.sort_values("year").reset_index(drop=True)
    df.to_csv(OUT, index=False)

    log(f"wrote {OUT}: {len(df)} years x {len(df.columns)} columns")
    log(f"years {df.year.min()}-{df.year.max()}, yield {df.yield_kg_ha.min():.0f}-{df.yield_kg_ha.max():.0f} kg/ha")
    return 0


if __name__ == "__main__":
    sys.exit(main())
