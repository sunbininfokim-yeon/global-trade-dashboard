"""
Build one training table per region-crop.

Usage: python3 -m brazil.collect [region_key ...]

For each config in regions.py: pull daily NASA POWER weather for its points,
run that region's own derived-variable formulas at each point, production-weight
the results, add the panel-level features that need a cross-year view (SPI,
coffee's biennial lags), and join IBGE state yields and NOAA ONI.

Output: training/<region_key>.csv, one row per harvest year.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date

import pandas as pd

from . import climate as C
from . import sidra
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

# NASA POWER rather than Open-Meteo's ERA5 archive. Open-Meteo would reach
# back to 1940 instead of 1981, but its free tier meters by data volume and
# eighteen 50-year six-variable pulls exhaust the daily quota outright. POWER
# has no comparable cap, serves a 45-year daily record in one call, and gives
# the radiation, wind and dewpoint needed to compute FAO-56 ET0 here instead
# of accepting a precomputed one -- which is what the safrinha guide asks for.
POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M")

POWER_START = "19810101"
POWER_FILL = -900          # POWER writes -999 for missing

# Last season the training tables try to build. Derived, not pinned: a literal
# year here silently freezes the pipeline -- the site would go on publishing a
# 2026 forecast in 2027 with no error anywhere.
END_YEAR = date.today().year


# The Brazilian summer crops run across the calendar boundary: a "2026" soybean
# season is sown from September 2025 and harvested by May 2026. So the season
# now under way rolls over in September, not in January. Wheat is a winter crop
# sown and harvested inside one calendar year and rolls with it.
SEASON_ROLLOVER_MONTH = 9


def current_season(cfg=None, today=None):
    """The harvest year a forecast should be aimed at right now."""
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", False):
        return today.year
    return today.year + (1 if today.month >= SEASON_ROLLOVER_MONTH else 0)

# ONI seasons spanning each crop's growing window. Summer crops take the
# austral wet season; wheat is a winter crop and takes the austral winter.
ONI_SUMMER = ({"OND", "NDJ"}, {"DJF", "JFM"})
ONI_WINTER = (set(), {"JJA", "JAS", "ASO"})
ONI_WINDOW = {"parana_trigo": ONI_WINTER}


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
    """
    Fetch with exponential backoff.

    POWER is generous, but the retry is kept because the earlier Open-Meteo
    attempt showed how a keyless bulk feed fails: a volume-metered 429 that
    seconds of backoff will not clear.
    """
    delay = 30
    for i in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001 - retry any transport failure
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} in {delay}s after {e}")
            time.sleep(delay)
            delay = min(delay * 2, 480)


def point_weather(point):
    """
    Daily weather for one location, cached by coordinate so points shared
    between region-crops (Mato Grosso soy and safrinha corn, for instance) are
    downloaded once.

    Returns date, tmax, tmin, tmean, precip, rh_mean, vpd_max, et0 -- the last
    two computed here rather than fetched.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    cached = os.path.join(CACHE, f"power_{slug}.csv")
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
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean",
                 "tdew", "rs", "wind"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)

    df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
    # Daytime vapour pressure deficit: saturation at Tmax against the day's
    # actual vapour pressure, matching what the guides mean by VPD.
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)

    df = df[["date", "tmax", "tmin", "tmean", "precip",
             "rh_mean", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day")
    time.sleep(2)
    return df


def blend_features(cfg, dailies, year):
    """
    Run the region's formulas at each point, then production-weight the
    resulting features.

    Averaging the daily weather first and deriving features from the mean
    would be simpler but wrong for this set of guides: nearly every one of
    them counts threshold exceedances (Tmax > 35, Tmin <= 1, rain > 300 mm in
    a month), and a mean across four locations hundreds of kilometres apart
    rarely crosses a threshold that any single location crosses often. Doing
    it in this order, a heatwave over 40% of the region registers as 40% of a
    heatwave instead of vanishing.

    Weights are renormalised over the points that returned a value, so a
    feature undefined at one location is not silently counted as zero.
    """
    acc, wsum = {}, {}
    for p in cfg.points:
        try:
            feats = cfg.build(dailies[p["name"]], year)
        except Exception as e:  # noqa: BLE001 - one bad point must not stop the season
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


def oni_for(oni, year, window):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def build_region(cfg, oni):
    log(f"{cfg.key}: {cfg.label}")
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    first = cfg.start_year
    rows = []
    for year in range(first, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(
            oni, year, ONI_WINDOW.get(cfg.key, ONI_SUMMER))
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no season produced any feature -- check the build function")
        return df

    yields = sidra.region_yield(cfg.crop, cfg.states)
    df = df.merge(yields, on="year", how="left")

    # Panel features: SPI needs the whole cross-year distribution to fit its
    # Gamma, and the coffee lags need the yield series itself.
    for name, source in cfg.panel.items():
        if source == "__yield__":
            df[name] = df.yield_kg_ha.shift(1)
        elif source == "__yield2__":
            df[name] = df.yield_kg_ha.shift(2)
        elif source in df.columns:
            df[name] = C.spi(df[source]).reindex(df.index)
        else:
            log(f"  panel feature {name}: source {source} missing, skipped")

    df = df.sort_values("year").reset_index(drop=True)

    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)

    labelled = df.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with yield), "
        f"{len(df.columns)} columns -> {os.path.basename(out)}")
    if len(labelled):
        log(f"  yield {labelled.yield_kg_ha.min():.0f}-"
            f"{labelled.yield_kg_ha.max():.0f} kg/ha")
    return df


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL

    oni = load_oni()
    for cfg in configs:
        build_region(cfg, oni)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
