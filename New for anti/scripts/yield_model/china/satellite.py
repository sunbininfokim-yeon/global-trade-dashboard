"""
Satellite features for the China models, via Google Earth Engine.

Usage: python3 -m china.satellite [region_key ...]

Why this exists: the weather models found nothing because the national USDA and
FAOSTAT targets carry almost no year-to-year variance to explain (see README).
Satellite indices attack that from the other side -- rather than adding more
weather to predict a smoothed number, they measure the crop directly, which is
what every one of the six guides actually asked for.

What is pulled, all from collections with a long enough record to be useful:

    MOD13Q1  NDVI / EVI, 16-day, 250 m, 2000-      vegetation vigour
    MOD11A2  LST day / night, 8-day, 1 km, 2000-   canopy thermal stress
    MCD12Q1  IGBP land cover, annual, 500 m        cropland mask

Everything is masked to cropland before reduction. Without that mask a
Heilongjiang buffer is mostly forest and a Guangdong one mostly built-up, and
the resulting NDVI tracks the surrounding landscape rather than the crop.

The record starts in 2000, which is the real cost here: 26 seasons against 42
for the weather features. Models using these are therefore trained on the
satellite era only, with a lower minimum training size, and that restriction is
recorded in the artifact rather than hidden.

Credentials: `earthengine authenticate` once, then the project id below. No
key material is read or stored by this module.
"""

import os
import sys
import time

import pandas as pd

from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# Registered Earth Engine Cloud project. Not a secret -- it is an identifier
# that appears in every request, and access is controlled by the user's own
# authenticated credentials, not by this string.
EE_PROJECT = os.environ.get("EE_PROJECT", "climate-project-504313")

# Radius around each config point, in metres. 40 km is wide enough to average
# over field-scale noise and narrow enough that a point still represents its
# own prefecture rather than half a province.
BUFFER_M = 40_000

# MODIS scale factors: NDVI/EVI are stored as int16 x 10000, LST in Kelvin
# x 0.02.
NDVI_SCALE = 1e-4
LST_SCALE = 0.02

# IGBP classes counted as cropland: 12 = croplands, 14 = cropland/natural
# vegetation mosaic.
CROP_CLASSES = [12, 14]

# MOD13Q1's first composite is 2000-02-18 and MOD11A2's 2000-02-24, so the
# 2000 season is missing its whole first quarter -- including the sowing window
# for every spring crop here. Starting at 2001 costs one season and buys a
# record with no partial year at the front.
SAT_START = 2001
SAT_END = 2025


def log(msg):
    print(f"[satellite] {msg}", flush=True)


def _ee():
    """Import and initialise Earth Engine, with an actionable error."""
    try:
        import ee
    except ImportError as e:
        raise SystemExit(
            "earthengine-api is not installed. Run:\n"
            "  pip3 install earthengine-api") from e
    try:
        ee.Initialize(project=EE_PROJECT)
    except Exception as e:  # noqa: BLE001 - surface the real cause verbatim
        raise SystemExit(
            f"Earth Engine failed to initialise for project {EE_PROJECT}.\n"
            f"  {e}\n"
            "Run `earthengine authenticate` once, or set EE_PROJECT to a "
            "different registered project.") from e
    return ee


def cropland_mask(ee, year):
    """
    Cropland mask for a given year from MCD12Q1 IGBP.

    Uses the nearest available year: the collection runs 2001-2023, so 2000
    borrows 2001 and anything past the end borrows the last published year.
    Cropland extent moves slowly enough that a one- or two-year offset is
    immaterial next to the 250 m pixel.
    """
    y = min(max(year, 2001), 2023)
    lc = (ee.ImageCollection("MODIS/061/MCD12Q1")
          .filter(ee.Filter.calendarRange(y, y, "year"))
          .first()
          .select("LC_Type1"))
    mask = lc.eq(CROP_CLASSES[0])
    for c in CROP_CLASSES[1:]:
        mask = mask.Or(lc.eq(c))
    return mask


def _monthly_series(ee, geom, year):
    """
    Monthly cropland-masked NDVI, EVI and day/night LST for one geometry and
    one calendar year.

    One reduceRegions call per month rather than per 16-day composite: the
    features every guide uses are monthly or seasonal aggregates, and monthly
    batching keeps the request count -- and so the EECU budget -- an order of
    magnitude lower than per-scene extraction would.
    """
    mask = cropland_mask(ee, year)
    rows = []

    for month in range(1, 13):
        start = ee.Date.fromYMD(year, month, 1)
        end = start.advance(1, "month")

        # The cropland mask is applied to each image *inside* its collection
        # rather than to the merged composite. Masking the composite breaks
        # whenever a collection is empty for the month -- mean() then returns a
        # zero-band image and updateMask refuses to pair 0 bands with 1. MODIS
        # Terra only opens in February 2000, so that is not hypothetical.
        # Applied this way an empty month simply yields no bands, reduceRegion
        # omits those keys, and the row lands as a missing value.
        veg = (ee.ImageCollection("MODIS/061/MOD13Q1")
               .filterDate(start, end).select(["NDVI", "EVI"])
               .map(lambda i: i.updateMask(mask)).mean())
        lst = (ee.ImageCollection("MODIS/061/MOD11A2")
               .filterDate(start, end).select(["LST_Day_1km", "LST_Night_1km"])
               .map(lambda i: i.updateMask(mask)).mean())

        img = veg.addBands(lst)
        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=250,
            maxPixels=1e9,
            bestEffort=True,
        )
        rows.append(ee.Feature(None, stats).set("month", month))

    return ee.FeatureCollection(rows)


def point_satellite(point, start=SAT_START, end=SAT_END):
    """
    Monthly satellite indices for one location, cached by coordinate.

    Returns year, month, ndvi, evi, lst_day, lst_night. LST is converted to
    degrees Celsius; NDVI and EVI to their natural -1..1 range.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    cached = os.path.join(CACHE, f"modis_{slug}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    ee = _ee()
    geom = ee.Geometry.Point([point["lon"], point["lat"]]).buffer(BUFFER_M)

    log(f"  modis {point['name']}: {start}-{end}")
    rows = []
    for year in range(start, end + 1):
        fc = _monthly_series(ee, geom, year)
        try:
            got = fc.getInfo()["features"]
        except Exception as e:  # noqa: BLE001 - one bad year must not stop the point
            log(f"    {year}: {e}")
            continue
        for f in got:
            p = f["properties"]
            rows.append({
                "year": year,
                "month": p.get("month"),
                "ndvi": (p["NDVI"] * NDVI_SCALE) if p.get("NDVI") is not None else None,
                "evi": (p["EVI"] * NDVI_SCALE) if p.get("EVI") is not None else None,
                "lst_day": (p["LST_Day_1km"] * LST_SCALE - 273.15)
                           if p.get("LST_Day_1km") is not None else None,
                "lst_night": (p["LST_Night_1km"] * LST_SCALE - 273.15)
                             if p.get("LST_Night_1km") is not None else None,
            })
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    if df.empty:
        log(f"  modis {point['name']}: no data returned")
        return df
    df.to_csv(cached, index=False)
    log(f"  modis {point['name']}: {len(df)} month-rows, "
        f"mean NDVI {df.ndvi.mean():.3f}")
    return df


# ---------------------------------------------------------------------------
# Derived features
# ---------------------------------------------------------------------------

def season_features(monthly, harvest_year, window, prefix="veg"):
    """
    Vegetation and thermal features over one config's critical window.

    `window` is the same (month, year_offset) list the weather features use, so
    a satellite feature and its weather counterpart describe the same period.

    Peak NDVI is the single variable 마투그로수/대두 §3B and 상파울루 §3B both
    name, and the one omitted from the Brazil package for lack of a satellite
    feed. Integrated NDVI is carried alongside it because a crop that holds a
    moderate canopy for ten weeks outyields one that spikes and collapses.
    """
    if monthly.empty:
        return {}

    mask = False
    for month, offset in window:
        y = harvest_year + offset
        mask = mask | ((monthly.year == y) & (monthly.month == month))
    w = monthly[mask]
    if w.empty:
        return {}

    out = {}
    if w.ndvi.notna().any():
        out[f"{prefix}_ndvi_peak"] = float(w.ndvi.max())
        out[f"{prefix}_ndvi_mean"] = float(w.ndvi.mean())
        # Integrated greenness: monthly means summed over the window, the
        # discrete form of the seasonal NDVI integral.
        out[f"{prefix}_ndvi_integral"] = float(w.ndvi.sum())
    if w.evi.notna().any():
        out[f"{prefix}_evi_peak"] = float(w.evi.max())
    if w.lst_day.notna().any():
        # Canopy temperature is what CWSI needs and what the Brazil package had
        # to replace with a VPD proxy. Here it is measured.
        out[f"{prefix}_lst_day_max"] = float(w.lst_day.max())
        out[f"{prefix}_lst_day_mean"] = float(w.lst_day.mean())
    if w.lst_night.notna().any():
        out[f"{prefix}_lst_night_mean"] = float(w.lst_night.mean())
    return out


def build_region(cfg):
    """
    Production-weighted satellite features per season for one config.

    Same order of operations as the weather pipeline: compute at each point,
    then weight. Averaging the imagery first would blur a drought-stricken
    prefecture into a healthy neighbour before the peak is taken.
    """
    log(f"{cfg.key}: {cfg.label}")
    per_point = {}
    for p in cfg.points:
        df = point_satellite(p)
        if not df.empty:
            per_point[p["name"]] = df

    if not per_point:
        log("  no satellite data for any point")
        return pd.DataFrame()

    window = cfg.critical_window or [(m, 0) for m in range(5, 10)]

    rows = []
    for year in range(SAT_START, SAT_END + 1):
        acc, wsum = {}, {}
        for p in cfg.points:
            monthly = per_point.get(p["name"])
            if monthly is None:
                continue
            feats = season_features(monthly, year, window)
            for k, v in feats.items():
                if v is None or pd.isna(v):
                    continue
                acc[k] = acc.get(k, 0.0) + float(v) * p["weight"]
                wsum[k] = wsum.get(k, 0.0) + p["weight"]
        if not acc:
            continue
        row = {k: acc[k] / wsum[k] for k in acc if wsum[k] > 0}
        row["year"] = year
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    out = os.path.join(CACHE, f"satellite_{cfg.key}.csv")
    df.to_csv(out, index=False)
    log(f"  wrote {len(df)} seasons, {len(df.columns) - 1} features")
    return df


def load_region(key):
    """Cached satellite table for one config, empty frame if not built yet."""
    path = os.path.join(CACHE, f"satellite_{key}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def main():
    keys = sys.argv[1:]
    configs = [BY_KEY[k] for k in keys] if keys else ALL
    for cfg in configs:
        build_region(cfg)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
