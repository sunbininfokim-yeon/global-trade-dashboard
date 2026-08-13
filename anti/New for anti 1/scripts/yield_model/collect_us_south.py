"""
Texas cotton and Mississippi Delta rice — the two remaining US regions.

Same structure as the other US models (trend + weather anomaly + ridge). Two
things are specific to these crops and are not stylistic choices:

COTTON — the target is yield per PLANTED acre, not per harvested acre.
  Texas abandonment runs from 4% to 75% of planted area between seasons, and
  it is drought that drives it: growers walk away from failed dryland fields,
  so what gets measured is the surviving, largely irrigated remainder.
  Measured on the 2010-2025 record, yield per harvested acre has a coefficient
  of variation of 10.0% and does not identify drought years at all -- 2022 had
  74.5% abandonment yet reported 734 lb/acre, above the 703 of the benign 2010.
  Re-based on planted area the CV is 37.1% and the three worst seasons come out
  as 2022, 2011 and 2023, which are the documented Texas droughts. In this
  region drought destroys area, not yield, and a model fitted to
  yield-per-harvested-acre would be fitting the wrong quantity.

RICE — expectations here should be low, and that is a property of the crop.
  Delta rice is essentially fully pump-irrigated, which decouples it from
  rainfall by design. After removing the technology trend the residual
  coefficient of variation is only 3.5% (AR) and 3.2% (MS), against 7.4% for
  corn and 11.9% for winter wheat. There is roughly a third as much year-to-year
  variation available to explain, and some of that will be survey noise. It is
  collected because the region belongs in the picture, not because a strong
  weather signal is expected.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

CHUNK = 10
START_YEAR = 1982
END_YEAR = 2025
POWER_EPOCH = "19810101"
CLIMATOLOGY_YEARS = 20

CROPS = {
    "cotton": {
        "commodity": "COTTON",
        "class_desc": "UPLAND",
        "yield_desc": "COTTON, UPLAND - YIELD, MEASURED IN LB / ACRE",
        "planted_desc": "COTTON, UPLAND - ACRES PLANTED",
        "harvested_desc": "COTTON, UPLAND - ACRES HARVESTED",
        # Rebase onto planted area; see the module docstring.
        "planted_basis": True,
        "states": [
            {"code": "TX", "lat": 33.6, "lon": -101.9, "weight": 0.62},  # High Plains
            {"code": "GA", "lat": 31.8, "lon": -83.7, "weight": 0.14},
            {"code": "MS", "lat": 33.4, "lon": -90.5, "weight": 0.08},
            {"code": "AR", "lat": 34.7, "lon": -91.2, "weight": 0.08},
            {"code": "AL", "lat": 32.5, "lon": -86.8, "weight": 0.08},
        ],
        "edd_threshold": 32.0,   # cotton tolerates more heat than maize
        "gdd_base": 15.5,        # cotton's base is much higher
        "gdd_cap": 32.0,
    },
    "rice": {
        "commodity": "RICE",
        "class_desc": None,
        "yield_desc": "RICE - YIELD, MEASURED IN LB / ACRE",
        "planted_desc": None,
        "harvested_desc": None,
        "planted_basis": False,   # rice is irrigated; abandonment is minimal
        "states": [
            {"code": "AR", "lat": 34.7, "lon": -91.2, "weight": 0.49},
            {"code": "CA", "lat": 39.2, "lon": -121.8, "weight": 0.22},
            {"code": "LA", "lat": 30.4, "lon": -92.4, "weight": 0.13},
            {"code": "MS", "lat": 33.4, "lon": -90.5, "weight": 0.09},
            {"code": "MO", "lat": 36.6, "lon": -89.8, "weight": 0.07},
        ],
        "edd_threshold": 33.0,   # night heat matters more than day for rice
        "gdd_base": 10.0,
        "gdd_cap": 30.0,
    },
}

STAGES = {
    "cotton": {
        # Texas dryland depends on winter/spring recharge before planting.
        "preseason":  {"months": [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0), (4, 0)],
                       "vars": ["precip", "soil"]},
        "planting":   {"months": [(5, 0), (6, 0)], "vars": ["precip", "tmean", "soil"]},
        # Flowering and boll set: the window that decides boll number.
        "flowering":  {"months": [(7, 0), (8, 0)],
                       "vars": ["edd", "vpd", "precip", "soil", "gdd"]},
        "bollfill":   {"months": [(8, 0), (9, 0)], "vars": ["edd", "vpd", "precip", "soil"]},
        # Rain on open bolls stains the lint and costs grade.
        "harvest":    {"months": [(10, 0), (11, 0)], "vars": ["precip", "soil"]},
    },
    "rice": {
        "preseason":  {"months": [(1, 0), (2, 0), (3, 0)], "vars": ["precip", "soil"]},
        "planting":   {"months": [(4, 0), (5, 0)], "vars": ["precip", "tmean", "soil"]},
        "vegetative": {"months": [(6, 0)], "vars": ["tmean", "edd", "srad", "soil"]},
        # Panicle initiation through heading: rice is most sensitive to night
        # temperature here, which is why tmin enters separately.
        "reproductive": {"months": [(7, 0), (8, 0)],
                         "vars": ["edd", "tmin", "srad", "vpd", "soil", "gdd"]},
        "ripening":   {"months": [(8, 0), (9, 0)], "vars": ["srad", "tmean", "precip"]},
    },
}


def log(m):
    print(f"[south] {m}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=3, timeout=300):
    for i in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} after {e}")
            time.sleep(10)


def nass_series(crop, state, stat, short_desc):
    """One NASS statistic for one state, in decade chunks."""
    if short_desc is None:
        return {}
    slug = short_desc.replace(" ", "_").replace(",", "").replace("/", "")[:40]
    cached = os.path.join(CACHE, f"nass_{crop}_{state['code']}_{slug}.csv")
    if os.path.exists(cached):
        df = pd.read_csv(cached)
        return dict(zip(df.year, df.value))

    key = os.environ.get("USDA_NASS_API_KEY")
    if not key:
        raise SystemExit("USDA_NASS_API_KEY is not set")

    spec = CROPS[crop]
    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        params = {"key": key, "commodity_desc": spec["commodity"],
                  "statisticcat_desc": stat, "agg_level_desc": "STATE",
                  "state_alpha": state["code"], "year__GE": str(lo),
                  "year__LE": str(hi), "format": "JSON"}
        if spec["class_desc"]:
            params["class_desc"] = spec["class_desc"]
        for r in retry_json(NASS_URL + "?" + urllib.parse.urlencode(params)).get("data", []):
            if (r.get("reference_period_desc") != "YEAR"
                    or r.get("source_desc") != "SURVEY"
                    or r.get("short_desc") != short_desc):
                continue
            try:
                rows.append({"year": int(r["year"]),
                             "value": float(r["Value"].replace(",", ""))})
            except (ValueError, KeyError):
                continue
        time.sleep(1)

    df = pd.DataFrame(rows).drop_duplicates("year").sort_values("year")
    os.makedirs(CACHE, exist_ok=True)
    df.to_csv(cached, index=False)
    return dict(zip(df.year, df.value))


def crop_yield(crop, state):
    """
    Yield for one state. For cotton this is rebased onto planted area, so the
    series reflects what a grower actually got per acre committed rather than
    per acre that survived to harvest.
    """
    spec = CROPS[crop]
    y = nass_series(crop, state, "YIELD", spec["yield_desc"])
    if not spec["planted_basis"]:
        log(f"nass[{crop}/{state['code']}]: {len(y)} years")
        return y

    planted = nass_series(crop, state, "AREA PLANTED", spec["planted_desc"])
    harvested = nass_series(crop, state, "AREA HARVESTED", spec["harvested_desc"])
    out = {}
    for yr, v in y.items():
        p, h = planted.get(yr), harvested.get(yr)
        if p and h and p > 0:
            out[yr] = v * h / p
    log(f"nass[{crop}/{state['code']}]: {len(out)} years (planted-acre basis)")
    return out


def power_weather(state):
    cached = os.path.join(CACHE, f"power_south_{state['code']}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    params = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,GWETROOT,T2MDEW,ALLSKY_SFC_SW_DWN"
    url = (f"{POWER_URL}?parameters={params}&community=AG"
           f"&longitude={state['lon']}&latitude={state['lat']}"
           f"&start={POWER_EPOCH}&end={END_YEAR}1231&format=JSON")
    log(f"power[{state['code']}]: downloading")
    p = retry_json(url)["properties"]["parameter"]

    dates = sorted(p["T2M_MAX"])
    def col(n):
        return [p[n][d] if p[n][d] > -100 else np.nan for d in dates]

    df = pd.DataFrame({
        "date": pd.to_datetime(dates, format="%Y%m%d"),
        "tmax": col("T2M_MAX"), "tmin": col("T2M_MIN"), "tmean": col("T2M"),
        "precip": col("PRECTOTCORR"), "soil": col("GWETROOT"),
        "tdew": col("T2MDEW"), "srad": col("ALLSKY_SFC_SW_DWN"),
    })
    es = 0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    df["vpd"] = (es - ea).clip(lower=0)

    os.makedirs(CACHE, exist_ok=True)
    df.to_csv(cached, index=False)
    log(f"power[{state['code']}]: {len(df):,} days")
    return df


def season_features(df, year, crop):
    spec = CROPS[crop]
    out = {}
    for stage, cfg in STAGES[crop].items():
        mask = np.zeros(len(df), dtype=bool)
        for month, off in cfg["months"]:
            mask |= ((df.date.dt.year == year + off) & (df.date.dt.month == month)).values
        w = df[mask]
        if w.empty or w.tmax.isna().all():
            return None
        for var in cfg["vars"]:
            if var == "precip":
                out[f"{stage}_precip"] = w.precip.sum()
            elif var == "tmean":
                out[f"{stage}_tmean"] = w.tmean.mean()
            elif var == "tmin":
                out[f"{stage}_tmin"] = w.tmin.mean()
            elif var == "vpd":
                out[f"{stage}_vpd"] = w.vpd.mean()
            elif var == "soil":
                out[f"{stage}_soil"] = w.soil.mean()
            elif var == "srad":
                out[f"{stage}_srad"] = w.srad.sum()
            elif var == "edd":
                out[f"{stage}_edd"] = (w.tmax - spec["edd_threshold"]).clip(lower=0).sum()
            elif var == "gdd":
                tm = (w.tmax.clip(upper=spec["gdd_cap"]) + w.tmin) / 2
                out[f"{stage}_gdd"] = (tm - spec["gdd_base"]).clip(lower=0).sum()
    return out


def to_anomalies(raw):
    years = sorted(raw)
    cols = sorted({c for v in raw.values() for c in v})
    out = {}
    for i, y in enumerate(years):
        base = [b for b in years[:i] if b >= y - CLIMATOLOGY_YEARS]
        if len(base) < 10:
            continue
        row = {"year": y}
        for c in cols:
            hist = [raw[b][c] for b in base if c in raw[b]]
            cur = raw[y].get(c)
            if cur is None or not hist:
                continue
            mu, sd = float(np.mean(hist)), float(np.std(hist))
            row[f"{c}_anom"] = (cur - mu) / sd if sd > 0 else 0.0
        out[y] = row
    return out


def load_oni():
    cached = os.path.join(CACHE, "oni_raw.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)
    text = fetch(ONI_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) != 4:
            continue
        try:
            rows.append({"season": p[0], "year": int(p[1]), "anom": float(p[3])})
        except ValueError:
            continue
    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    return df


def season_oni(oni, year):
    v = oni[(oni.year == year) & (oni.season.isin({"AMJ", "MJJ", "JJA", "JAS"}))].anom
    return float(v.mean()) if len(v) else np.nan


def build(crop):
    spec = CROPS[crop]
    oni = load_oni()

    anoms, yields_ = {}, {}
    for st in spec["states"]:
        wx = power_weather(st)
        raw = {}
        for y in range(START_YEAR, END_YEAR + 1):
            f = season_features(wx, y, crop)
            if f:
                raw[y] = f
        anoms[st["code"]] = to_anomalies(raw)
        yields_[st["code"]] = crop_yield(crop, st)

    rows = []
    for y in range(START_YEAR, END_YEAR + 1):
        feats, wf, ysum, wy = {}, 0.0, 0.0, 0.0
        for st in spec["states"]:
            a = anoms[st["code"]].get(y)
            yv = yields_[st["code"]].get(y)
            if a is None or yv is None:
                continue
            for k, v in a.items():
                if k == "year":
                    continue
                feats[k] = feats.get(k, 0.0) + v * st["weight"]
            wf += st["weight"]
            ysum += yv * st["weight"]
            wy += st["weight"]
        if wf == 0 or wy == 0:
            continue
        row = {k: v / wf for k, v in feats.items()}
        row.update({"year": y, "yield": ysum / wy, "oni_season": season_oni(oni, y)})
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    out = os.path.join(HERE, f"us_{crop}_training.csv")
    df.to_csv(out, index=False)
    log(f"wrote {out}: {len(df)} years x {len(df.columns)} cols "
        f"({df.year.min()}-{df.year.max()}), yield {df['yield'].min():.0f}-{df['yield'].max():.0f}")
    return df


def main():
    for crop in (sys.argv[1:] or ["cotton", "rice"]):
        log(f"=== {crop} ===")
        build(crop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
