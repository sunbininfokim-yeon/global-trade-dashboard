"""
Build one training table per region-crop.

Usage: python3 -m india.collect [region_key ...]

For each config in regions.py: pull daily NASA POWER weather for its points,
run that region's own derived-variable formulas at each point, area-weight the
results, add the panel-level features that need a cross-year view, and join
ICRISAT district yields, NOAA ONI and the Indian Ocean Dipole index.

Output: training/<region_key>.csv, one row per harvest year.

Two things differ structurally from the Brazilian collector:

  - The Indian Ocean Dipole is carried alongside ENSO. 중부_마디아프라데시/대두 §3A
    asks for both as first-layer inputs, and it is right to: a positive IOD
    can hold the monsoon up through an El Nino year, so ONI alone mis-scores
    exactly the seasons the model most needs to get right.
  - Kharif and Rabi run on opposite calendars. A Kharif crop is sown and
    harvested inside one calendar year, so its features never reach across the
    year boundary; Rabi wheat is sown in November of the previous year. The
    (month, offset) convention from the Brazilian package handles both, but
    the season rollover and the ENSO window have to be set per crop.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date

import pandas as pd

from . import climate as C
from . import icrisat
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
# HadISST-based DMI, the standard IOD index: SST anomaly over the western
# equatorial Indian Ocean (50-70E, 10S-10N) minus the eastern pole
# (90-110E, 10S-0). Monthly from 1870, which outruns every other series here.
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"

POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M")

POWER_START = "19810101"
POWER_FILL = -900          # POWER writes -999 for missing

# Derived rather than pinned, for the reason the Brazilian collector gives: a
# literal year freezes the pipeline silently a year later.
END_YEAR = date.today().year

# A Kharif crop sown in June and harvested by November belongs to the calendar
# year it is harvested in, so its season rolls over in January like the
# calendar. Rabi wheat is sown from November and harvested the following
# March, so from November onward the season under way is next year's.
RABI_ROLLOVER_MONTH = 11


def current_season(cfg=None, today=None):
    """The harvest year a forecast should be aimed at right now."""
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", True):
        return today.year
    return today.year + (1 if today.month >= RABI_ROLLOVER_MONTH else 0)


# ENSO windows. Kharif takes the boreal summer seasons of the harvest year --
# the monsoon it is grown on. Rabi wheat is sown into the following winter, so
# it takes the seasons spanning its own sowing and grain fill.
#
# The teleconnection sign is the opposite of Brazil's: El Nino suppresses the
# Indian monsoon where it wets southern Brazil. Nothing here encodes that --
# the coefficient is fitted from the data -- but it is why a Brazilian model
# cannot be carried over, only the code.
ONI_KHARIF = (set(), {"JJA", "JAS", "ASO"})
ONI_RABI = ({"OND", "NDJ"}, {"DJF", "JFM"})
ONI_WINDOW = {"punjab_wheat": ONI_RABI}

# IOD peaks in the second half of the monsoon and decays by December, so the
# Kharif window is where it carries information.
DMI_KHARIF = (set(), {7, 8, 9, 10})
DMI_RABI = ({10, 11, 12}, {1})
DMI_WINDOW = {"punjab_wheat": DMI_RABI}


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
    """Fetch with exponential backoff."""
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

    Returns date, tmax, tmin, tmean, precip, rh_mean, vpd_max, et0 -- the last
    two computed here rather than fetched, so that ET0 is FAO-56
    Penman-Monteith from radiation, wind and dewpoint rather than a
    temperature-only estimate.
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

    df = df[["date", "tmax", "tmin", "tmean", "precip",
             "rh_mean", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day")
    time.sleep(2)
    return df


def blend_features(cfg, dailies, year):
    """
    Run the region's formulas at each point, then area-weight the results.

    Same order of operations as the Brazilian collector and for the same
    reason, which if anything binds harder here: every headline variable in
    these three guides is a threshold crossing -- Tmax above 30, seven
    consecutive rainless days, RH above 80% -- and none of them survives
    averaging the weather first. A dry spell that breaks in Indore on day 6 and
    in Ujjain on day 12 is not a nine-day dry spell anywhere, but that is what
    the mean rainfall series would show.

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


def load_dmi():
    """
    Monthly Dipole Mode Index, the IOD measure 대두 §3A asks for.

    The file is a fixed-width block: a header line giving the first and last
    year, then one row per year of twelve monthly values, then a trailer of
    provenance text. Missing months are written as a large negative sentinel.
    """
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "dmi.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("dmi: downloading")
    text = fetch(DMI_URL, timeout=60).decode("utf-8", "replace")

    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 13:
            continue
        try:
            year = int(parts[0])
            vals = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        if not 1800 <= year <= 2100:
            continue
        for month, v in enumerate(vals, start=1):
            if v < -90:            # sentinel for a month with no SST coverage
                continue
            rows.append({"year": year, "month": month, "dmi": v})

    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    log(f"dmi: {len(df):,} months, {df.year.min()}-{df.year.max()}")
    return df


def oni_for(oni, year, window):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def dmi_for(dmi, year, window):
    prev, cur = window
    vals = list(dmi[(dmi.year == year - 1) & (dmi.month.isin(prev))].dmi)
    vals += list(dmi[(dmi.year == year) & (dmi.month.isin(cur))].dmi)
    return sum(vals) / len(vals) if vals else None


def build_region(cfg, oni, dmi):
    log(f"{cfg.key}: {cfg.label}")
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(
            oni, year, ONI_WINDOW.get(cfg.key, ONI_KHARIF))
        feats["dmi_season"] = dmi_for(
            dmi, year, DMI_WINDOW.get(cfg.key, DMI_KHARIF))
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no season produced any feature -- check the build function")
        return df

    yields = icrisat.region_yield(cfg.crop, cfg.selector)
    df = df.merge(yields[["year", "yield_kg_ha"]], on="year", how="left")

    for name, source in cfg.panel.items():
        if source == "__yield__":
            df[name] = df.yield_kg_ha.shift(1)
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
            f"{labelled.yield_kg_ha.max():.0f} kg/ha, "
            f"labelled {int(labelled.year.min())}-{int(labelled.year.max())}")
    return df


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL

    oni, dmi = load_oni(), load_dmi()
    for cfg in configs:
        build_region(cfg, oni, dmi)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
