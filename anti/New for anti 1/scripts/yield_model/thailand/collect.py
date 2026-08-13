"""
Build one Thailand training table per region-crop.

Usage (from scripts/yield_model):

    PYTHONPATH=. python3 -m thailand.collect
    PYTHONPATH=. python3 -m thailand.collect central_ne_sugarcane
    PYTHONPATH=. python3 -m thailand.collect --stubs

Sources:
  · NASA POWER daily (temp, precip, radiation, GWETROOT) — real
  · FAO-56 ET0 (brazil.climate) — computed
  · NOAA CPC ONI — real
  · Yield — FAOSTAT Thailand national, or labels_official/ override
  · RID dam storage / SMAP / OAE wet-vs-dry rice — **not wired**
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

from brazil import climate as BC
from . import climate as C
from . import labels as L
from .regions import ALL, ALL_WITH_STUBS, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
TRAINING = os.path.join(HERE, "training")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

POWER_PARAMS = ("T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,T2MDEW,"
                "ALLSKY_SFC_SW_DWN,WS2M,GWETROOT,GWETTOP")
CACHE_SCHEMA = "v1"
POWER_START = "19810101"
POWER_FILL = -900
END_YEAR = date.today().year

# Off-season rice rolls with Nov storage decision
OFF_ROLLOVER_MONTH = 11

UA = {"User-Agent": "yield-model-thailand/1.0"}


def current_season(cfg=None, today=None):
    today = today or date.today()
    if cfg is not None and not getattr(cfg, "calendar_year_crop", True):
        return today.year + (1 if today.month >= OFF_ROLLOVER_MONTH else 0)
    return today.year


def log(msg):
    print(f"[collect] {msg}", flush=True)


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry_json(url, attempts=6, timeout=300):
    delay = 20
    for i in range(attempts):
        try:
            return json.loads(fetch(url, timeout=timeout))
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} in {delay}s after {e}")
            time.sleep(delay)
            delay = min(delay * 2, 240)


def point_weather(point):
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
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean", "tdew", "rs",
                 "wind", "gwetroot", "gwettop"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)
    elev = point.get("elevation", 50)
    df["et0"] = BC.fao56_et0(df, point["lat"], elev)
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean", "vpd_max",
             "et0", "gwetroot", "gwettop"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days")
    time.sleep(1.5)
    return df


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


def oni_djf(oni, year):
    vals = list(oni[(oni.year == year) & (oni.season == "DJF")].anom)
    if vals:
        return float(vals[0])
    return oni_for(oni, year, (set(), {"DJF"}))


def blend_features(cfg, dailies, year):
    acc, wsum = {}, {}
    for p in cfg.points:
        try:
            feats = cfg.build(dailies[p["name"]], year, p)
        except Exception as e:  # noqa: BLE001
            log(f"  {year} {p['name']}: {e}")
            continue
        for k, v in (feats or {}).items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            # Upstream wet precip: only average across upstream points
            if k == "upstream_wet_precip" and p.get("role") != "upstream":
                continue
            if k == "role_upstream":
                continue
            acc[k] = acc.get(k, 0.0) + float(v) * p["weight"]
            wsum[k] = wsum.get(k, 0.0) + p["weight"]
    return {k: acc[k] / wsum[k] for k in acc if wsum[k] > 0}


def apply_dam_proxy(feats, oni_val):
    wet = feats.get("upstream_wet_precip", feats.get("precip_wet_prior", 0.0))
    feats["dam_recharge_proxy"] = C.dam_recharge_proxy(wet, oni_val or 0.0)
    return feats


def build_region(cfg, oni):
    log(f"{cfg.key}: {cfg.label}" + (" [stub]" if cfg.stub else ""))
    dailies = {p["name"]: point_weather(p) for p in cfg.points}

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(oni, year, cfg.oni_window)
        feats["oni_djf"] = oni_djf(oni, year)
        if cfg.key == "chao_phraya_rice_off":
            feats = apply_dam_proxy(
                feats, feats["oni_djf"] if feats["oni_djf"] is not None
                else feats["oni_season"])
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no seasons produced")
        return df

    df = L.attach_labels(cfg, df)
    src = (df.label_source.dropna().iloc[0]
           if "label_source" in df.columns and df.label_source.notna().any()
           else "unknown")
    log(f"  label_source={src}")

    for name, source in cfg.panel.items():
        if source in df.columns:
            s = df[source].astype(float)
            df[name] = (s - s.mean()) / (s.std() or 1.0)

    # Onset delay anomaly vs prior-20 mean DOY
    if "onset_doy" in df.columns:
        od = df["onset_doy"].astype(float)
        delay = []
        for i, y in enumerate(df.year):
            hist = od.iloc[max(0, i - 20):i]
            hist = hist[hist.notna()]
            if len(hist) < 5 or pd.isna(od.iloc[i]):
                delay.append(np.nan)
            else:
                delay.append(float(od.iloc[i] - hist.mean()))
        df["onset_delay"] = delay

    df = df.sort_values("year").reset_index(drop=True)
    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)
    labelled = df.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with yield) -> "
        f"{os.path.basename(out)}")
    if len(labelled):
        log(f"  yield {labelled.yield_kg_ha.min():.0f}-"
            f"{labelled.yield_kg_ha.max():.0f} kg/ha "
            f"({int(labelled.year.min())}-{int(labelled.year.max())})")
    return df


def write_schema_stub(cfg):
    os.makedirs(TRAINING, exist_ok=True)
    cols = (["year"] + list(cfg.core) + ["yield_kg_ha", "label_source"])
    path = os.path.join(TRAINING, f"{cfg.key}.schema.csv")
    pd.DataFrame(columns=cols).to_csv(path, index=False)
    log(f"{cfg.key}: schema stub only -> {os.path.basename(path)}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    use_stubs = "--stubs" in argv
    if use_stubs:
        argv.remove("--stubs")

    if argv:
        configs = [BY_KEY[k] for k in argv]
    else:
        configs = list(ALL_WITH_STUBS if use_stubs else ALL)

    for cfg in ALL_WITH_STUBS:
        if cfg.stub and cfg not in configs:
            write_schema_stub(cfg)

    oni = load_oni()
    for cfg in configs:
        if cfg.stub and not use_stubs and cfg.key not in (argv or []):
            write_schema_stub(cfg)
            continue
        build_region(cfg, oni)
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
