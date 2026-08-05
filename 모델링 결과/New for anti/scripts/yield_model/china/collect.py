"""
Build one training table per China region-crop.

Usage: python3 -m china.collect [region_key ...]

Same shape as brazil.collect: pull daily NASA POWER weather for each config's
points, run that config's own derived-variable formulas at each point,
production-weight the results, add panel features needing a cross-year view,
and join the target series and NOAA ONI.

Two differences from the Brazil collector, both forced by the guides:

  Wind and radiation are kept. Brazil's cache drops WS2M and ALLSKY after
  computing ET0. Henan's 干热风 index needs wind and humidity as a
  conjunction with temperature, and Shandong's greenhouse index needs
  radiation directly, so both columns survive into the cache here.

  The target column is called `target`, not `yield_kg_ha`. Five configs are
  yields; south_china_rice_area is a harvested-area series, because the
  question its guide asks -- did farmers plant the second crop? -- is
  invisible in yield per harvested hectare and visible in area.

Output: training/<region_key>.csv, one row per season.
"""

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
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M")

POWER_START = "19810101"
POWER_FILL = -900
END_YEAR = 2025

# ONI windows over each crop's growing season. ENSO reaches Chinese
# agriculture mainly through the East Asian summer monsoon -- the Meiyu front
# that floods the Yangtze and the northern droughts that follow -- so summer
# crops take the boreal summer seasons, and winter wheat the winter it
# overwinters through.
ONI_SUMMER = (set(), {"JJA", "JAS", "ASO"})
ONI_WINTER = ({"DJF", "JFM"}, {"MAM", "AMJ"})
ONI_WINDOW = {"henan_wheat": ONI_WINTER}

# Month from which the *next* calendar year becomes the season to forecast.
#
# The rule is when the next crop goes in the ground, not when the last one came
# out. Winter wheat is the case that forces the distinction: it is harvested in
# June, but the following season's crop is not sown until October, so rolling
# over in August would spend two months forecasting a crop that does not exist
# yet and has no weather to observe.
SEASON_ROLLOVER = {
    "northeast_soy": 11,
    "northeast_corn": 11,
    "henan_wheat": 10,          # sown October, harvested the following June
    "yangtze_rice": 12,
    "south_china_rice_area": 12,
    "shandong_vegetables": 12,
}


def log(msg):
    print(f"[collect] {msg}", flush=True)


def current_season(cfg=None):
    """
    The season a forecast run should be aiming at.

    Before the rollover month the current calendar year's crop is still in the
    ground and is what a forecast is for; after it, that crop is harvested and
    attention moves to the next one.
    """
    now = datetime.now(timezone.utc)
    if cfg is None:
        return now.year
    rollover = SEASON_ROLLOVER.get(cfg.key, 11)
    return now.year if now.month < rollover else now.year + 1


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
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
    Daily weather for one location, cached by coordinate.

    Returns date, tmax, tmin, tmean, precip, rh_mean, wind, rs, vpd_max, et0.
    Wind and radiation are kept rather than consumed into ET0 and discarded:
    two of the six guides use them as first-class variables.
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
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)

    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean",
             "wind", "rs", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day, "
        f"mean Rs {df.rs.mean():.1f} MJ/m2")
    time.sleep(2)
    return df


def blend_features(cfg, dailies, year):
    """
    Run the config's formulas at each point, then production-weight them.

    Order matters for the same reason it does in Brazil, and more so here:
    every headline China variable is a threshold conjunction. A regional mean
    of temperature, humidity and wind almost never satisfies Tmax >= 30 AND
    RH <= 30 AND wind >= 3 simultaneously, even in a year when half the North
    China Plain sat under a dry-hot wind for a week.
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

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
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

    target = cfg.target()
    df = df.merge(target, on="year", how="left")

    for name, source in cfg.panel.items():
        if source == "__target__":
            df[name] = df.target.shift(1)
        elif source in df.columns:
            df[name] = C.spi(df[source]).reindex(df.index)
        else:
            log(f"  panel feature {name}: source {source} missing, skipped")

    df = df.sort_values("year").reset_index(drop=True)

    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)

    labelled = df.dropna(subset=["target"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with target), "
        f"{len(df.columns)} columns -> {os.path.basename(out)}")
    if len(labelled):
        log(f"  {cfg.target_label} {labelled.target.min():,.0f}-"
            f"{labelled.target.max():,.0f} {cfg.target_unit}")
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
