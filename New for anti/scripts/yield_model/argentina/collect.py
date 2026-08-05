"""
Build one training table per region-crop.

Usage: python3 -m argentina.collect [region_key ...]

For each config in regions.py: pull daily NASA POWER weather for its points,
run that region's own derived-variable formulas at each point,
production-weight the results, add the panel features that need a cross-year
view (SPI, the ENSO x IOD switch, cane's lag), and join MAGyP yields, NOAA ONI
and NOAA PSL DMI.

Output: training/<region_key>.csv, one row per harvest year.

The one new feed relative to Brazil is the **IOD**. 팜파스/옥수수 §2A does not
treat ENSO alone as sufficient: its `Climate_Shock_Index` fires only when a La
Niña (ONI < -0.5) coincides with a positive Indian Ocean Dipole (DMI > 0.4),
and the guide's claim is that this conjunction, not either index by itself, is
what empties the Pampas spring. HadISST's DMI reconstruction runs from 1870,
so it costs nothing in record length to test that claim.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date

import pandas as pd

from brazil import climate as C
from . import climate_ar as A
from . import magyp
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"

# GWETROOT and GWETTOP are the 0803 작업지시서's soil-moisture channel. The
# sheet asks for SMAP, which starts in 2015; POWER's MERRA-2 root-zone wetness
# starts in 1981, costs no extra request, and keeps the record at 42 seasons.
POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M,GWETROOT,GWETTOP,GWETPROF")

# Bumped whenever POWER_PARAMS or the derived columns change, so a cache
# written before a variable existed is not silently reused without it.
#   v1  no soil moisture
#   v2  + GWETROOT, GWETTOP
#   v3  + GWETPROF (water-table proxy for wheat) and `rs` retained for the
#       photothermal quotient -- shortwave radiation was being fetched, used
#       once for ET0, and then dropped before caching.
CACHE_SCHEMA = "v3"
POWER_START = "19810101"
POWER_FILL = -900
END_YEAR = 2025

# Default ONI window for a summer crop, used when a config names none.
ONI_SUMMER = ({"OND", "NDJ"}, {"DJF", "JFM"})

# Spring (SON) DMI is what 팜파스/옥수수 §2A means by "인도양 쌍극자(IOD)":
# the dipole peaks in the austral spring and that is the season whose rainfall
# it is claimed to steal.
IOD_SEASON = [9, 10, 11]

UA = {"User-Agent": "yield-model/1.0"}

# The Argentine summer crops cross the calendar boundary: a "2026" soybean
# season is sown from October 2025 and harvested by April 2026. The season now
# under way therefore rolls over in September. Wheat is sown in June and cut in
# December of one calendar year and rolls with it -- which is the same
# distinction magyp.HARVEST_OFFSET encodes for the historical record.
SEASON_ROLLOVER_MONTH = 9


def current_season(cfg=None, today=None):
    """The harvest year a forecast should be aimed at right now."""
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", False):
        return today.year
    return today.year + (1 if today.month >= SEASON_ROLLOVER_MONTH else 0)


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
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
    Daily weather for one location, cached by coordinate so points shared
    between region-crops (Pergamino and Marcos Juárez serve soy, corn and
    wheat) are downloaded once.

    Returns date, tmax, tmin, tmean, precip, rh_mean, vpd_max, et0 -- the last
    two computed here rather than fetched.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    cached = os.path.join(CACHE, f"power_{CACHE_SCHEMA}_{slug}.csv")
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
        "gwetroot": list(p["GWETROOT"].values()),
        "gwettop": list(p["GWETTOP"].values()),
        "gwetprof": list(p["GWETPROF"].values()),
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean", "tdew", "rs",
                 "wind", "gwetroot", "gwettop",
                 "gwetprof"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)

    df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
    # Percentiles against this point's own day-of-year climatology. Done here,
    # once per point over the whole record, because the ranking is a property
    # of the location and not of any one season. Root zone drives the drought
    # features; the full profile is the wheat water-table proxy.
    df["sm_pct"] = A.soil_wetness_percentile(df, "gwetroot")
    df["prof_pct"] = A.soil_wetness_percentile(df, "gwetprof")

    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean", "vpd_max",
             "et0", "rs", "gwetroot", "gwettop", "gwetprof",
             "sm_pct", "prof_pct"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day, "
        f"GWETROOT p05-p95 {df.gwetroot.quantile(.05):.2f}-"
        f"{df.gwetroot.quantile(.95):.2f}")
    time.sleep(2)
    return df


def blend_features(cfg, dailies, year):
    """
    Run the region's formulas at each point, then production-weight the
    resulting features -- never the reverse.

    Nearly every Argentine guide counts threshold exceedances (Tmax > 35 C,
    Tmin < 0 C, ADD crossings), and a mean across stations 500 km apart rarely
    crosses a threshold that any single station crosses often. Done in this
    order, a frost over a quarter of the wheat belt registers as a quarter of a
    frost instead of vanishing.

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
    NOAA PSL's HadISST Dipole Mode Index, monthly, 1870-.

    The file is a fixed-width block: a `first_year last_year` header, then one
    row per year of twelve monthly values, then a trailing prose block. The
    missing-value sentinel is given in the footer but is reliably a large
    negative; anything below -90 is dropped.
    """
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "dmi.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("dmi (IOD): downloading")
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
            if v < -90:
                continue
            rows.append({"year": year, "month": month, "dmi": v})

    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    log(f"  dmi: {df.year.min()}-{df.year.max()}, {len(df)} months")
    return df


def oni_for(oni, year, window):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def iod_for(dmi, year, offset=-1, months=IOD_SEASON):
    """
    Mean DMI over the austral spring of the planting year.

    `offset` is -1 for summer crops (spring of the year before harvest) and 0
    for wheat, whose own spring is the harvest year's.
    """
    w = dmi[(dmi.year == year + offset) & (dmi.month.isin(months))]
    return float(w.dmi.mean()) if not w.empty else None


def build_region(cfg, oni, dmi):
    log(f"{cfg.key}: {cfg.label}")
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    # Wheat's growing season sits inside its harvest year, so its "planting
    # spring" is that same year; summer crops planted in the spring before
    # harvest take the previous year's.
    iod_offset = 0 if cfg.crop == "trigo" else -1

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_lag"] = oni_for(oni, year, cfg.oni_window or ONI_SUMMER)
        feats["iod_spring"] = iod_for(dmi, year, iod_offset)
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no season produced any feature -- check the build function")
        return df

    yields = magyp.region_yield(cfg.crop, cfg.provinces, cfg.departments)
    df = df.merge(yields, on="year", how="left")

    # Panel features: SPI needs the whole cross-year distribution to fit its
    # Gamma, the shock index needs both indices in hand, lags need the yield
    # series itself.
    for name, source in cfg.panel.items():
        if source == "__yield__":
            df[name] = df.yield_kg_ha.shift(1)
        elif source == "__shock__":
            df[name] = [A.climate_shock_index(o, i)
                        for o, i in zip(df.oni_lag, df.iod_spring)]
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
            f"mean abandonment {labelled.abandonment.mean() * 100:.1f}%")
    return df


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL

    magyp.download()
    oni, dmi = load_oni(), load_dmi()
    for cfg in configs:
        build_region(cfg, oni, dmi)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
