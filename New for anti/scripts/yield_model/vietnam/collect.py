"""
Build one Vietnam training table per region-crop.

Usage (from scripts/yield_model):

    python3 -m vietnam.collect              # T1 only
    python3 -m vietnam.collect --stubs      # include T2 stubs
    python3 -m vietnam.collect mekong_rice_ws

Sources:
  · NASA POWER daily (temp, precip, radiation, wind, GWETROOT) — real
  · FAO-56 ET0 computed locally (brazil.climate) — real
  · NOAA CPC ONI — real
  · Yield labels — training/labels_official/ when present (Mekong WS: GSO
    Yearbook spring + MTN Đông Xuân + FAOSTAT prior); else provisional synthetic
  · GEE CHIRPS / SMAP / Sentinel-1 / MRC discharge — **not run** (no GEE auth
    in this path); POWER precip and GWETROOT stand in; salinity is a documented
    proxy, never claimed as field EC.
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
from .regions import ALL, ALL_WITH_STUBS, BY_KEY, MEKONG_UPSTREAM_POINTS, WS_DRY, WS_PEAK, WS_WET_PRIOR

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

# WS (Mekong) rolls over once sowing starts (~Nov). Calendar crops roll Jan 1.
WS_ROLLOVER_MONTH = 11

UA = {"User-Agent": "yield-model-vietnam/1.0"}


def current_season(cfg=None, today=None):
    today = today or date.today()
    if cfg is not None and getattr(cfg, "calendar_year_crop", False):
        return today.year
    return today.year + (1 if today.month >= WS_ROLLOVER_MONTH else 0)


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

    df["et0"] = BC.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)

    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean", "vpd_max",
             "et0", "gwetroot", "gwettop"]]
    df.to_csv(cached, index=False)
    log(f"  power {point['name']}: {len(df):,} days, "
        f"mean ET0 {df.et0.mean():.2f} mm/day")
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
    """DJF ONI ending in calendar year `year` (classic El Niño DJF of that year)."""
    # CPC rows: DJF is labelled by the year of the January–February months.
    vals = list(oni[(oni.year == year) & (oni.season == "DJF")].anom)
    if vals:
        return float(vals[0])
    return oni_for(oni, year, (set(), {"DJF"}))


def oni_lag2(oni, year):
    """
    ENSO lagged ~2 months ahead of mid dry-season (Feb–Mar) moisture.

    Atmospheres 2026 / AF-1022: ONI→SPI peak correlation at lag ≈ 2 months.
    Uses OND (year−1) + NDJ (year) — seasons ending before peak WS drought.
    """
    vals = list(oni[(oni.year == year - 1) & (oni.season == "OND")].anom)
    vals += list(oni[(oni.year == year) & (oni.season == "NDJ")].anom)
    return sum(vals) / len(vals) if vals else None


def upstream_q_features(dailies_up, year):
    """
    Dry-season Mekong inflow proxy without MRC gauged discharge.

    Yen et al. (2024) QTCmin (Tan Chau min discharge) + Eslami et al. (2021)
    dry-season SWI mechanism. MRC portal requires request / returns 403 here,
    so we combine:
      · Pakse wet-season precip (y−1 May–Oct) — upstream storage/flood memory
      · Tan Chau dry SM + dry precip — local delta-gate dryness
    Scaled to O(1); higher ⇒ more freshwater push ⇒ less intrusion.
    """
    pakse = dailies_up.get("Pakse")
    tc = dailies_up.get("TanChau")
    if pakse is None or tc is None:
        return {}
    wet = C.window_sum(pakse, "precip", WS_WET_PRIOR, year)
    dry_p = C.window_sum(tc, "precip", WS_DRY, year)
    sm = C.window_mean(tc, "gwetroot", WS_PEAK, year)
    if any(np.isnan(v) for v in (wet, dry_p, sm)):
        return {
            "q_wet_pakse": wet,
            "precip_dry_tanchau": dry_p,
            "q_sm_tanchau": sm,
        }
    # Weighted composite in roughly unit scale (typical wet ~1200–2000 mm).
    q = 0.55 * (wet / 1500.0) + 0.30 * (sm / 0.45) + 0.15 * (dry_p / 80.0)
    return {
        "q_upstream_proxy": float(q),
        "q_wet_pakse": float(wet),
        "precip_dry_tanchau": float(dry_p),
        "q_sm_tanchau": float(sm),
    }


def blend_features(cfg, dailies, year):
    """Point-level build then production-weight — never mean weather first."""
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
            acc[k] = acc.get(k, 0.0) + float(v) * p["weight"]
            wsum[k] = wsum.get(k, 0.0) + p["weight"]
    return {k: acc[k] / wsum[k] for k in acc if wsum[k] > 0}


def apply_salt_with_oni(feats, oni_val, q_upstream=None):
    """Rebuild salinity features once region-mean ONI (and optional Q) known."""
    if oni_val is None:
        return feats
    dry = feats.get("precip_dry_ws", feats.get("precip_dry_coast",
                    feats.get("precip_dry", 100.0)))
    wet = feats.get("precip_wet_prior", feats.get("precip_typhoon_window",
                   1000.0))
    coast = feats.get("coast_km", 40.0)
    q = q_upstream
    if q is None:
        q = feats.get("q_upstream_proxy")
    salt = C.salinity_proxy(coast, dry, oni_val, wet, q_upstream=q)
    feats["salt_proxy"] = salt["salt_proxy"]
    feats["ec_proxy"] = salt["ec_proxy"]
    feats["y_rel_salt"] = salt["y_rel_salt"]
    feats["coastal_exposure"] = salt["coastal_exposure"]
    # Refresh coastal interaction with ONI-aware salt
    feats["salt_x_coast"] = float(
        salt["salt_proxy"] * salt["coastal_exposure"])
    return feats


def attach_sample_weights(df):
    """
    Up-weight official WS years (2017+) vs FAOSTAT-scaled prior.

    Gap note: full 2017–2024-only train is n≈8 — too thin for min_train=18 CV;
    weighting keeps history while emphasising GSO/MTN Đông Xuân labels.
    """
    w = pd.Series(1.0, index=df.index)
    if "label_source" in df.columns:
        src = df.label_source.fillna("").astype(str)
        official = (df.year >= 2017) & (~src.str.contains("faostat", case=False))
        w.loc[official] = 3.0
    elif "year" in df.columns:
        w.loc[df.year >= 2017] = 3.0
    df = df.copy()
    df["sample_weight"] = w.values
    return df


def build_region(cfg, oni):
    log(f"{cfg.key}: {cfg.label}"
        + (" [stub]" if cfg.stub else ""))
    dailies = {p["name"]: point_weather(p) for p in cfg.points}
    dailies_up = {}
    if cfg.key == "mekong_rice_ws":
        dailies_up = {p["name"]: point_weather(p) for p in MEKONG_UPSTREAM_POINTS}

    rows = []
    for year in range(cfg.start_year, END_YEAR + 1):
        feats = blend_features(cfg, dailies, year)
        if not feats:
            continue
        feats["year"] = year
        window = cfg.oni_window
        feats["oni_season"] = oni_for(oni, year, window)
        feats["oni_djf"] = oni_djf(oni, year)
        feats["oni_lag2"] = oni_lag2(oni, year)
        if dailies_up:
            feats.update(upstream_q_features(dailies_up, year))
        # Prefer lag-2 ONI for salt channel when available (teleconnection papers)
        oni_for_salt = feats.get("oni_lag2")
        if oni_for_salt is None:
            oni_for_salt = feats["oni_djf"] if feats["oni_djf"] is not None \
                else feats["oni_season"]
        if cfg.crop in ("rice",) or "salt_water_index" in feats:
            feats = apply_salt_with_oni(
                feats, oni_for_salt or 0.0,
                q_upstream=feats.get("q_upstream_proxy"))
        rows.append(feats)

    df = pd.DataFrame(rows)
    if df.empty:
        log("  no seasons produced")
        return df

    df = L.attach_labels(cfg, df)
    if cfg.key == "mekong_rice_ws":
        df = attach_sample_weights(df)
    src = (df.label_source.dropna().iloc[0]
           if "label_source" in df.columns and df.label_source.notna().any()
           else "unknown")
    log(f"  label_source={src}")

    for name, source in cfg.panel.items():
        if source in df.columns:
            # lightweight z-score panel rather than full SPI Gamma
            s = df[source].astype(float)
            df[name] = (s - s.mean()) / (s.std() or 1.0)
        else:
            log(f"  panel {name}: missing source {source}")

    df = df.sort_values("year").reset_index(drop=True)
    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{cfg.key}.csv")
    df.to_csv(out, index=False)

    labelled = df.dropna(subset=["yield_kg_ha"])
    log(f"  wrote {len(df)} seasons ({len(labelled)} with yield), "
        f"{len(df.columns)} cols -> {os.path.basename(out)}")
    if len(labelled):
        log(f"  yield {labelled.yield_kg_ha.min():.0f}-"
            f"{labelled.yield_kg_ha.max():.0f} kg/ha "
            f"({int(labelled.year.min())}-{int(labelled.year.max())})")
    return df


def write_schema_stub(cfg):
    """Empty labelled schema for T2 stub documentation."""
    os.makedirs(TRAINING, exist_ok=True)
    cols = (["year"] + list(cfg.core) + ["yield_kg_ha", "label_source"])
    path = os.path.join(TRAINING, f"{cfg.key}.schema.csv")
    pd.DataFrame(columns=cols).to_csv(path, index=False)
    log(f"{cfg.key}: schema stub only -> {os.path.basename(path)}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    use_stubs = False
    if "--stubs" in argv:
        use_stubs = True
        argv.remove("--stubs")
    if "--schema-only-stubs" in argv:
        argv.remove("--schema-only-stubs")
        for cfg in ALL_WITH_STUBS:
            if cfg.stub:
                write_schema_stub(cfg)
        return 0

    if argv:
        configs = [BY_KEY[k] for k in argv]
    else:
        configs = list(ALL_WITH_STUBS if use_stubs else ALL)

    # Always drop schema files for stubs we do not fully collect
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
