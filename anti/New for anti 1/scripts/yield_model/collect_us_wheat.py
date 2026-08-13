"""
Build the US wheat training tables — winter wheat and spring wheat separately.

Wheat is not corn with different numbers. Both classes have physics the
Corn Belt model does not model at all, which is why they get their own
feature sets rather than a re-run of the corn one.

WINTER WHEAT (Kansas, Oklahoma, Texas, Colorado, Nebraska)
  Sown in autumn, overwinters, harvested early summer. Two mechanisms that
  simply do not exist for a summer crop:
    - Vernalization. The plant needs a spell of cold (roughly 0-10C) over
      winter to head properly in spring. A winter that is too warm is itself
      a yield problem, so cold is not monotonically bad here.
    - Freezing injury. Severe cold without snow cover, or a late frost once
      the crop is heading, destroys tissue outright. Entered as an
      accumulated penalty, following the regional guide:
          Frost_Penalty = sum over heading..flowering of max(0, T_crit - Tmin)

SPRING WHEAT (North Dakota, Montana, Minnesota, South Dakota)
  Sown April-May, harvested late summer. No vernalization, so the risk is a
  short season colliding with midsummer heat: planting late pushes flowering
  into the hottest, driest weeks. Wheat is markedly more heat-sensitive than
  maize, so the damage threshold is set lower.

Deliberately NOT following the guides' recommended architecture. Both call
for WOFOST/LSTM with satellite data assimilation; those need far more
training data than the ~35 seasons available here. On this record, adding
four features to the corn model already made it worse. What carries over is
the feature engineering -- which is where the agronomy lives -- inside the
same trend + weather-anomaly + ridge structure that has been validated for
corn and soybeans.
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
    "winter_wheat": {
        "nass_class": "WINTER",
        # Yield is reported for all/irrigated/non-irrigated separately; take
        # the headline all-practice series so irrigation is not double-counted.
        "short_desc": "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE",
        "states": [
            {"code": "KS", "lat": 38.5, "lon": -98.4, "weight": 0.34},
            {"code": "OK", "lat": 36.1, "lon": -98.0, "weight": 0.15},
            {"code": "TX", "lat": 34.4, "lon": -101.5, "weight": 0.13},
            {"code": "CO", "lat": 39.3, "lon": -103.0, "weight": 0.13},
            {"code": "NE", "lat": 40.6, "lon": -100.5, "weight": 0.13},
            {"code": "MT", "lat": 47.5, "lon": -110.0, "weight": 0.12},
        ],
        "edd_threshold": 30.0,   # grain fill heat damage
        "frost_tcrit": 0.0,      # tissue damage once heading
    },
    "spring_wheat": {
        "nass_class": "SPRING, (EXCL DURUM)",
        "short_desc": "WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE",
        "states": [
            {"code": "ND", "lat": 47.4, "lon": -100.5, "weight": 0.50},
            {"code": "MT", "lat": 47.5, "lon": -110.0, "weight": 0.22},
            {"code": "MN", "lat": 47.5, "lon": -96.0, "weight": 0.15},
            {"code": "SD", "lat": 45.0, "lon": -99.5, "weight": 0.13},
        ],
        "edd_threshold": 28.0,   # wheat suffers earlier than maize
        "frost_tcrit": None,
    },
}

# Growth-stage windows. (month, year offset); offset -1 = previous calendar
# year, which winter wheat needs because its season straddles New Year.
STAGES = {
    "winter_wheat": {
        # Autumn establishment before dormancy.
        "fall":       {"months": [(9, -1), (10, -1), (11, -1)],
                       "vars": ["precip", "tmean", "soil"]},
        # Dormancy: this is where vernalization chill accumulates and where a
        # hard freeze does damage.
        "winter":     {"months": [(12, -1), (1, 0), (2, 0)],
                       "vars": ["chill", "freeze", "tmean", "precip", "soil"]},
        # Green-up and stem extension.
        "spring":     {"months": [(3, 0), (4, 0)],
                       "vars": ["precip", "tmean", "soil", "frost"]},
        # Heading through flowering: late frost here is catastrophic.
        "heading":    {"months": [(4, 0), (5, 0)],
                       "vars": ["frost", "edd", "vpd", "precip", "soil"]},
        # Grain fill into harvest: heat and dryness cut kernel weight.
        "grainfill":  {"months": [(5, 0), (6, 0)],
                       "vars": ["edd", "vpd", "precip", "soil", "gdd"]},
    },
    "spring_wheat": {
        # Pre-season moisture recharge, Thompson's term for this geography.
        "preseason":  {"months": [(9, -1), (10, -1), (11, -1), (12, -1),
                                  (1, 0), (2, 0), (3, 0)], "vars": ["precip", "soil"]},
        "planting":   {"months": [(4, 0), (5, 0)], "vars": ["precip", "tmean", "soil"]},
        "vegetative": {"months": [(6, 0)], "vars": ["edd", "vpd", "precip", "soil", "srad"]},
        # Flowering: the window a delayed planting pushes into midsummer heat.
        "flowering":  {"months": [(7, 0)], "vars": ["edd", "vpd", "precip", "soil", "srad"]},
        "grainfill":  {"months": [(7, 0), (8, 0)],
                       "vars": ["edd", "vpd", "precip", "soil", "gdd", "srad"]},
    },
}

GDD_BASE = 4.0    # wheat grows at lower temperatures than maize
GDD_CAP = 25.0


def log(msg):
    print(f"[wheat] {msg}", flush=True)


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


def nass_yields(crop, state):
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"nass_{crop}_{state['code']}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    key = os.environ.get("USDA_NASS_API_KEY")
    if not key:
        raise SystemExit("USDA_NASS_API_KEY is not set")

    spec = CROPS[crop]
    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        q = urllib.parse.urlencode({
            "key": key, "commodity_desc": "WHEAT", "statisticcat_desc": "YIELD",
            "agg_level_desc": "STATE", "state_alpha": state["code"],
            "class_desc": spec["nass_class"],
            "year__GE": str(lo), "year__LE": str(hi), "format": "JSON",
        })
        for r in retry_json(NASS_URL + "?" + q).get("data", []):
            # short_desc pins the all-practice series; without it the
            # irrigated and non-irrigated rows would be mixed in.
            if (r.get("reference_period_desc") != "YEAR"
                    or r.get("source_desc") != "SURVEY"
                    or r.get("short_desc") != spec["short_desc"]):
                continue
            try:
                rows.append({"year": int(r["year"]),
                             "yield": float(r["Value"].replace(",", ""))})
            except (ValueError, KeyError):
                continue
        time.sleep(1)

    df = (pd.DataFrame(rows).drop_duplicates("year")
          .sort_values("year").reset_index(drop=True))
    df.to_csv(cached, index=False)
    log(f"nass[{crop}/{state['code']}]: {len(df)} years")
    return df


def power_weather(state):
    """Shared with the Corn Belt collector where the state overlaps."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"power_wheat_{state['code']}.csv")
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

    df.to_csv(cached, index=False)
    log(f"power[{state['code']}]: {len(df):,} days")
    return df


def season_features(df, year, crop):
    spec = CROPS[crop]
    out = {}
    for stage, cfg in STAGES[crop].items():
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
            elif var == "srad":
                out[f"{stage}_srad"] = w.srad.sum()
            elif var == "edd":
                out[f"{stage}_edd"] = (w.tmax - spec["edd_threshold"]).clip(lower=0).sum()
            elif var == "gdd":
                tm = (w.tmax.clip(upper=GDD_CAP) + w.tmin) / 2
                out[f"{stage}_gdd"] = (tm - GDD_BASE).clip(lower=0).sum()
            elif var == "chill":
                # Vernalization: hours-equivalent of days spent in the
                # effective chilling band. Too few and the crop heads poorly.
                out[f"{stage}_chill"] = int(((w.tmean >= 0) & (w.tmean <= 10)).sum())
            elif var == "freeze":
                # Severity of hard winter cold, the damage side of the same
                # coin as chill.
                out[f"{stage}_freeze"] = (-10.0 - w.tmin).clip(lower=0).sum()
            elif var == "frost":
                # Late frost once the crop is exposed: accumulated depth below
                # the critical temperature, per the regional guide's formula.
                tcrit = spec["frost_tcrit"]
                if tcrit is None:
                    continue
                out[f"{stage}_frost"] = (tcrit - w.tmin).clip(lower=0).sum()
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


def season_oni(oni, year, crop):
    # Winter wheat's season is dominated by the preceding winter's ENSO state;
    # spring wheat's by the same summer it is grown in.
    seas = ({"NDJ", "DJF", "JFM"} if crop == "winter_wheat"
            else {"AMJ", "MJJ", "JJA", "JAS"})
    v = oni[(oni.year == year) & (oni.season.isin(seas))].anom
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
        yields_[st["code"]] = nass_yields(crop, st).set_index("year")["yield"].to_dict()

    rows = []
    for y in range(START_YEAR, END_YEAR + 1):
        feats, w_f = {}, 0.0
        ysum, w_y = 0.0, 0.0
        for st in spec["states"]:
            a = anoms[st["code"]].get(y)
            yv = yields_[st["code"]].get(y)
            if a is None or yv is None:
                continue
            for k, v in a.items():
                if k == "year":
                    continue
                feats[k] = feats.get(k, 0.0) + v * st["weight"]
            w_f += st["weight"]
            ysum += yv * st["weight"]
            w_y += st["weight"]
        if w_f == 0 or w_y == 0:
            continue
        row = {k: v / w_f for k, v in feats.items()}
        row["year"] = y
        row["yield"] = ysum / w_y
        row["oni_season"] = season_oni(oni, y, crop)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    out = os.path.join(HERE, f"us_{crop}_training.csv")
    df.to_csv(out, index=False)
    log(f"wrote {out}: {len(df)} years x {len(df.columns)} cols "
        f"({df.year.min()}-{df.year.max()}), yield {df['yield'].min():.1f}-{df['yield'].max():.1f}")
    return df


def main():
    for crop in (sys.argv[1:] or ["winter_wheat", "spring_wheat"]):
        log(f"=== {crop} ===")
        build(crop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
