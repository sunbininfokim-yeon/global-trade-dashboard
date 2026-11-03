"""
Build one training table per region-crop for France.

Usage: python3 -m france.collect [region_key ...]

Same pipeline as india.collect (the code was carried over): daily NASA POWER
weather per point, the region's own formulas at each point, area-weighted,
then ENSO and the North Atlantic Oscillation joined, and Eurostat NUTS 2
yields as the label (france/eurostat.py).

Output: training/<region_key>.csv, one row per harvest year.

Winter wheat is sown in October and harvested in July, so a season reaches
back into the previous autumn; features use the (month, offset) convention
with offset -1 for the sowing months.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date

import pandas as pd

from . import climate as C
from . import eurostat
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
# NOAA CPC monthly North Atlantic Oscillation index (1950-). A positive
# winter NAO brings mild, wet westerlies to northern France; it is the
# Atlantic counterpart of the ENSO term and is fitted, not assumed.
NAO_URL = ("https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/"
           "norm.nao.monthly.b5001.current.ascii")

POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M")

POWER_START = "19810101"
POWER_FILL = -900          # POWER writes -999 for missing

# Derived rather than pinned, for the reason the Brazilian collector gives: a
# literal year freezes the pipeline silently a year later.
END_YEAR = date.today().year

# Winter wheat is harvested in July; from September the season under way is
# the next harvest year's (sowing starts late September).
ROLLOVER_MONTH = 9


def current_season(cfg=None, today=None):
    """The harvest year a forecast should be aimed at right now."""
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", False):
        return today.year
    return today.year + (1 if today.month >= ROLLOVER_MONTH else 0)


# ENSO over the season (previous autumn through spring); its reach into
# Europe is weak, so it is kept only as a candidate the ridge can zero out.
ONI_WHEAT = ({"SON", "OND", "NDJ"}, {"DJF", "JFM", "FMA", "MAM"})
ONI_WINDOW = {"west_maize": (set(), {"MJJ", "JJA", "JAS"})}

# Winter NAO (Dec-Mar): the mode that sets how wet and mild the crop's
# winter and early spring are.
NAO_WHEAT = ({12}, {1, 2, 3})
NAO_WINDOW = {"west_maize": (set(), {6, 7, 8})}


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


def load_nao():
    """Monthly NAO: one "year month value" line per month."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "nao.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log("nao: downloading")
    text = fetch(NAO_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            year, month, v = int(parts[0]), int(parts[1]), float(parts[2])
        except ValueError:
            continue
        if 1900 <= year <= 2100 and 1 <= month <= 12 and v > -90:
            rows.append({"year": year, "month": month, "nao": v})

    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    log(f"nao: {len(df):,} months, {df.year.min()}-{df.year.max()}")
    return df


def oni_for(oni, year, window):
    prev, cur = window
    vals = list(oni[(oni.year == year - 1) & (oni.season.isin(prev))].anom)
    vals += list(oni[(oni.year == year) & (oni.season.isin(cur))].anom)
    return sum(vals) / len(vals) if vals else None


def nao_for(nao, year, window):
    prev, cur = window
    vals = list(nao[(nao.year == year - 1) & (nao.month.isin(prev))].nao)
    vals += list(nao[(nao.year == year) & (nao.month.isin(cur))].nao)
    return sum(vals) / len(vals) if vals else None


def build_region(cfg, oni, nao):
    log(f"{cfg.key}: {cfg.label}")
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(
            oni, year, ONI_WINDOW.get(cfg.key, ONI_WHEAT))
        feats["nao_season"] = nao_for(
            nao, year, NAO_WINDOW.get(cfg.key, NAO_WHEAT))
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no season produced any feature -- check the build function")
        return df

    yields = eurostat.region_yield(cfg.crop, cfg.selector)
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

    oni, nao = load_oni(), load_nao()
    for cfg in configs:
        build_region(cfg, oni, nao)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
