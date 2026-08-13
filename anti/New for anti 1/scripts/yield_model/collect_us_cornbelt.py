"""
Build the US Corn Belt training table for corn and soybean yield modelling.

Feature design follows the published statistical-yield literature rather than
being invented here:

  Thompson (1969, 1986), via the FAO review of crop yield forecasting
    - Regress yield on time; that trend absorbs technology -- genetics,
      management and above all fertiliser use. Correlate *deviations from
      trend* with monthly weather. This is why no fertiliser series is
      collected: the trend already carries it.
    - For Midwest corn he found pre-season precipitation (Sep-Jun), June
      temperature, and July/August temperature and rainfall to be the
      variables tied to yield deviations. Pre-season precipitation is
      included here for exactly that reason.

  Schlenker & Roberts (2009)
    - Heat damage is sharply nonlinear, not a linear function of mean
      temperature: roughly -8.2%/degC for maize and -5.7% for soybean up to
      3 degC, steepening beyond. Counting "days above X" throws that shape
      away, so heat enters as extreme degree days (EDD): the accumulated
      amount by which daily temperature exceeds the damage threshold.

  Urban et al. (2015), Roberts et al. (2012), Lobell et al. (2014)
    - Vapour pressure deficit is a strong predictor of US maize yield,
      capturing combined heat and dryness better than temperature alone.

All weather features are expressed as anomalies against a trailing
climatology, never as raw levels. Raw levels carry their own multi-decade
trends (in a first pass on Brazil, pod-fill soil moisture trended -0.09 over
43 years, r=-0.63 against time), which a model reads as "conditions are
deteriorating" even while yields rise -- producing systematic
underprediction. Anomalies leave only "how unusual was this season".

Sources: USDA NASS Quick Stats (yield), NASA POWER (weather, one continuous
series from 1981), NOAA CPC ONI (ENSO).
"""

import json
import urllib.parse
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

# NASS is quick when a year range is bounded on both sides and very slow when
# it is not -- an open-ended query timed out past 120s, the same query with an
# upper bound returned in 4s. Hence decade chunks.
CHUNK = 10

# Corn Belt states, weighted by their share of national production.
STATES = [
    {"code": "IA", "name": "Iowa",         "lat": 42.0, "lon": -93.5, "weight": 0.17},
    {"code": "IL", "name": "Illinois",     "lat": 40.0, "lon": -89.0, "weight": 0.16},
    {"code": "NE", "name": "Nebraska",     "lat": 41.5, "lon": -99.0, "weight": 0.11},
    {"code": "MN", "name": "Minnesota",    "lat": 44.5, "lon": -94.5, "weight": 0.10},
    {"code": "IN", "name": "Indiana",      "lat": 40.0, "lon": -86.3, "weight": 0.08},
    {"code": "OH", "name": "Ohio",         "lat": 40.3, "lon": -83.0, "weight": 0.06},
    {"code": "MO", "name": "Missouri",     "lat": 38.5, "lon": -92.5, "weight": 0.06},
    {"code": "SD", "name": "South Dakota", "lat": 44.5, "lon": -99.5, "weight": 0.06},
]

START_YEAR = 1982      # NASA POWER starts 1981-01-01; need the prior September
END_YEAR = 2025
POWER_EPOCH = "19810101"

# Trailing window for the climatology that anomalies are measured against.
CLIMATOLOGY_YEARS = 20

CROPS = {
    "corn": {
        "nass_commodity": "CORN",
        "nass_extra": {"class_desc": "ALL CLASSES", "util_practice_desc": "GRAIN"},
        # Schlenker & Roberts put the maize damage threshold near 29C.
        "edd_threshold": 29.0,
        "gdd_base": 10.0,
        "gdd_cap": 30.0,
    },
    "soybeans": {
        "nass_commodity": "SOYBEANS",
        "nass_extra": {},
        # Soybean damage sets in slightly higher than maize.
        "edd_threshold": 30.0,
        "gdd_base": 10.0,
        "gdd_cap": 30.0,
    },
}

# Northern-hemisphere windows, all within the harvest calendar year.
# "preseason" is Thompson's Sep(Y-1)-Jun(Y) moisture recharge term.
STAGES = {
    "preseason":    {"months": [(9, -1), (10, -1), (11, -1), (12, -1), (1, 0), (2, 0),
                                (3, 0), (4, 0), (5, 0), (6, 0)], "vars": ["precip"]},
    "june":         {"months": [(6, 0)], "vars": ["tmean", "edd", "precip", "vpd", "soil"]},
    "july":         {"months": [(7, 0)], "vars": ["tmean", "edd", "precip", "vpd", "soil"]},
    "august":       {"months": [(8, 0)], "vars": ["tmean", "edd", "precip", "vpd", "soil"]},
    "julaug":       {"months": [(7, 0), (8, 0)], "vars": ["edd", "precip", "vpd", "soil", "gdd"]},
}


def log(msg):
    print(f"[us] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=3, timeout=300):
    for attempt in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            log(f"  retry {attempt + 1} after {e}")
            time.sleep(10)


def nass_yields(crop, state):
    """State yield series from NASS, fetched in decade chunks."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"nass_{crop}_{state['code']}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    key = os.environ.get("USDA_NASS_API_KEY")
    if not key:
        raise SystemExit("USDA_NASS_API_KEY is not set in the environment")

    spec = CROPS[crop]
    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        params = {
            "key": key,
            "commodity_desc": spec["nass_commodity"],
            "statisticcat_desc": "YIELD",
            "agg_level_desc": "STATE",
            "state_alpha": state["code"],
            "year__GE": str(lo),
            "year__LE": str(hi),
            "format": "JSON",
        }
        params.update(spec["nass_extra"])
        url = NASS_URL + "?" + urllib.parse.urlencode(params)
        data = retry_json(url)

        for r in data.get("data", []):
            if r.get("reference_period_desc") != "YEAR" or r.get("source_desc") != "SURVEY":
                continue
            try:
                rows.append({"year": int(r["year"]), "yield": float(r["Value"].replace(",", ""))})
            except (ValueError, KeyError):
                continue
        time.sleep(1)  # be polite to a slow public API

    df = (pd.DataFrame(rows)
          .drop_duplicates("year")
          .sort_values("year")
          .reset_index(drop=True))
    df.to_csv(cached, index=False)
    log(f"nass[{crop}/{state['code']}]: {len(df)} years")
    return df


def power_weather(state):
    """Daily NASA POWER series, one continuous record from 1981."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"power_{state['code']}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    params = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,GWETROOT,T2MDEW"
    url = (f"{POWER_URL}?parameters={params}&community=AG"
           f"&longitude={state['lon']}&latitude={state['lat']}"
           f"&start={POWER_EPOCH}&end={END_YEAR}1231&format=JSON")
    log(f"power[{state['code']}]: downloading")
    p = retry_json(url)["properties"]["parameter"]

    dates = sorted(p["T2M_MAX"])
    def col(name):
        return [p[name][d] if p[name][d] > -100 else np.nan for d in dates]

    df = pd.DataFrame({
        "date": pd.to_datetime(dates, format="%Y%m%d"),
        "tmax": col("T2M_MAX"),
        "tmin": col("T2M_MIN"),
        "tmean": col("T2M"),
        "precip": col("PRECTOTCORR"),
        "soil": col("GWETROOT"),
        "tdew": col("T2MDEW"),
    })

    # VPD from daily max temperature and dew point (Tetens saturation curve).
    # Using tmax rather than tmean gives the peak atmospheric demand the crop
    # actually experiences, which is what the VPD-yield literature relates to.
    es = 0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    df["vpd"] = (es - ea).clip(lower=0)

    df.to_csv(cached, index=False)
    log(f"power[{state['code']}]: {len(df):,} days")
    return df


def season_features(df, year, spec):
    """Raw (not yet anomalised) stage features for one state-year."""
    out = {}
    for stage, cfg in STAGES.items():
        mask = np.zeros(len(df), dtype=bool)
        for month, offset in cfg["months"]:
            y = year + offset
            mask |= ((df.date.dt.year == y) & (df.date.dt.month == month)).values
        w = df[mask]
        if w.empty or w.tmax.isna().all():
            return None

        for var in cfg["vars"]:
            if var == "precip":
                out[f"{stage}_precip"] = w.precip.sum()
            elif var == "tmean":
                out[f"{stage}_tmean"] = w.tmean.mean()
            elif var == "vpd":
                out[f"{stage}_vpd"] = w.vpd.mean()
            elif var == "soil":
                out[f"{stage}_soil"] = w.soil.mean()
            elif var == "edd":
                # Extreme degree days: accumulated excess over the damage
                # threshold. Nonlinear by construction, unlike a day count.
                out[f"{stage}_edd"] = (w.tmax - spec["edd_threshold"]).clip(lower=0).sum()
            elif var == "gdd":
                tm = (w.tmax.clip(upper=spec["gdd_cap"]) + w.tmin) / 2
                out[f"{stage}_gdd"] = (tm - spec["gdd_base"]).clip(lower=0).sum()
    return out


def to_anomalies(raw_by_year):
    """
    Convert raw stage features to anomalies against a trailing climatology.

    Each season is compared only with the CLIMATOLOGY_YEARS seasons before it,
    so no future information leaks into a year's own features and a slow
    climate drift is absorbed by the moving baseline instead of being read as
    a yield signal.
    """
    years = sorted(raw_by_year)
    cols = sorted({c for v in raw_by_year.values() for c in v})
    out = {}

    for i, y in enumerate(years):
        base_years = [yy for yy in years[:i] if yy >= y - CLIMATOLOGY_YEARS]
        if len(base_years) < 10:
            continue  # not enough history yet for a stable normal
        row = {"year": y}
        for c in cols:
            hist = [raw_by_year[yy][c] for yy in base_years if c in raw_by_year[yy]]
            cur = raw_by_year[y].get(c)
            if cur is None or not hist:
                continue
            mu = float(np.mean(hist))
            sd = float(np.std(hist))
            row[f"{c}_anom"] = (cur - mu) / sd if sd > 0 else 0.0
        out[y] = row
    return out


def load_oni():
    # Distinct from the Brazil collector's oni.csv, which stores a
    # season-averaged table rather than the raw seasonal rows.
    cached = os.path.join(CACHE, "oni_raw.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)
    text = fetch(ONI_URL, timeout=60).decode("utf-8", "replace")
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            rows.append({"season": parts[0], "year": int(parts[1]), "anom": float(parts[3])})
        except ValueError:
            continue
    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    return df


def growing_season_oni(oni, year):
    """ENSO state over the northern growing season (AMJ..ASO)."""
    seas = {"AMJ", "MJJ", "JJA", "JAS", "ASO"}
    v = oni[(oni.year == year) & (oni.season.isin(seas))].anom
    return float(v.mean()) if len(v) else np.nan


def build(crop):
    spec = CROPS[crop]
    oni = load_oni()

    per_state_anoms, per_state_yield = {}, {}
    for st in STATES:
        wx = power_weather(st)
        raw = {}
        for y in range(START_YEAR, END_YEAR + 1):
            f = season_features(wx, y, spec)
            if f:
                raw[y] = f
        per_state_anoms[st["code"]] = to_anomalies(raw)
        per_state_yield[st["code"]] = nass_yields(crop, st).set_index("year")["yield"].to_dict()

    rows = []
    for y in range(START_YEAR, END_YEAR + 1):
        feats, wsum = {}, 0.0
        ysum, ywsum = 0.0, 0.0
        for st in STATES:
            a = per_state_anoms[st["code"]].get(y)
            yv = per_state_yield[st["code"]].get(y)
            if a is None or yv is None:
                continue
            for k, v in a.items():
                if k == "year":
                    continue
                feats[k] = feats.get(k, 0.0) + v * st["weight"]
            wsum += st["weight"]
            ysum += yv * st["weight"]
            ywsum += st["weight"]
        if wsum == 0 or ywsum == 0:
            continue
        row = {k: v / wsum for k, v in feats.items()}
        row["year"] = y
        row["yield"] = ysum / ywsum
        row["oni_growing"] = growing_season_oni(oni, y)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    out = os.path.join(HERE, f"us_{crop}_training.csv")
    df.to_csv(out, index=False)
    log(f"wrote {out}: {len(df)} years x {len(df.columns)} cols "
        f"({df.year.min()}-{df.year.max()}), yield {df['yield'].min():.1f}-{df['yield'].max():.1f}")
    return df


def main():
    import urllib.parse  # noqa: F401 - used via urllib.parse.urlencode
    for crop in (sys.argv[1:] or ["corn", "soybeans"]):
        log(f"=== {crop} ===")
        build(crop)
    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
