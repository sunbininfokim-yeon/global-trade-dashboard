"""
Apply trained Russia models to a live season.

Usage: python3 -m russia.predict [--year Y] [region_key ...]

POWER for observed weather. Optional Open-Meteo forecast extends T/precip only
past the last POWER day (no OM soil — climatological GWETROOT on forecast days).
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

from . import climate as C
from .collect import (
    ONI_WINTER,
    POWER_FILL,
    POWER_PARAMS,
    POWER_URL,
    blend_features,
    current_season,
    load_oni,
    oni_for,
    point_slug,
    retry_json,
)
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")
TRAINING = os.path.join(HERE, "training")
CACHE = os.path.join(HERE, "cache")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def log(msg):
    print(f"[predict] {msg}", flush=True)


def om_forecast_tp(point):
    """Tmax/Tmin/Tmean + precip only — project forbids Open-Meteo soil."""
    url = (f"{FORECAST_URL}?latitude={point['lat']}&longitude={point['lon']}"
           f"&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
           f"precipitation_sum,dew_point_2m_mean,shortwave_radiation_sum,"
           f"windspeed_10m_max,relative_humidity_2m_mean"
           f"&past_days=7&forecast_days=16&timezone=UTC")
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    d = data["daily"]
    # shortwave_radiation_sum is often MJ? OM is J/m2 sometimes — convert if large
    rs = np.array(d["shortwave_radiation_sum"], dtype=float)
    if np.nanmax(rs) > 50:  # likely J → MJ
        rs = rs / 1e6
    return pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "tmax": d["temperature_2m_max"],
        "tmin": d["temperature_2m_min"],
        "tmean": d["temperature_2m_mean"],
        "precip": d["precipitation_sum"],
        "tdew": d["dew_point_2m_mean"],
        "rh_mean": d["relative_humidity_2m_mean"],
        "rs": rs,
        "wind": d["windspeed_10m_max"],
    })


def recent_weather(point, year):
    os.makedirs(CACHE, exist_ok=True)
    slug = point_slug(point)
    stamp = date.today().isoformat()
    cached = os.path.join(CACHE, f"live_{slug}_{year}_{stamp}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    start = f"{year - 2}0101"
    end = date.today().strftime("%Y%m%d")
    url = (f"{POWER_URL}?parameters={POWER_PARAMS}&community=AG"
           f"&longitude={point['lon']}&latitude={point['lat']}"
           f"&start={start}&end={end}&format=JSON")
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
    })
    keep = ["tmax", "tmin", "tmean", "precip", "rh_mean",
            "tdew", "rs", "wind", "gwetroot"]
    df = df[(df[keep] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)
    df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)

    # Extend with Open-Meteo T/P forecast; soil from POWER DOY climatology.
    try:
        fc = om_forecast_tp(point)
        last = df.date.max()
        fc = fc[fc.date > last].copy()
        if not fc.empty:
            doy = df.date.dt.dayofyear
            clim = df.groupby(doy)["gwetroot"].mean()
            fc_doy = fc.date.dt.dayofyear
            fc["gwetroot"] = fc_doy.map(clim).fillna(df.gwetroot.mean())
            fc["rh_mean"] = fc["rh_mean"].fillna(df.rh_mean.mean())
            fc["wind"] = fc["wind"].fillna(df.wind.mean())
            fc["et0"] = C.fao56_et0(fc, point["lat"], point["elevation"])
            fc["vpd_max"] = (C._svp(fc.tmax) - C._svp(fc.tdew)).clip(lower=0)
            cols = ["date", "tmax", "tmin", "tmean", "precip", "rh_mean",
                    "wind", "rs", "gwetroot", "vpd_max", "et0"]
            df = pd.concat([df[cols], fc[cols]], ignore_index=True)
            df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
        time.sleep(0.4)
    except Exception as e:  # noqa: BLE001
        log(f"  forecast tail skipped for {point['name']}: {e}")

    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean",
             "wind", "rs", "gwetroot", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    return df


def panel_features(cfg, feats, year, history):
    notes = []
    for name, source in cfg.panel.items():
        if source in history.columns and source in feats:
            params = C.fit_spi(history[source])
            if params is None:
                notes.append(f"{name}: SPI fit failed")
                continue
            feats[name] = float(C.apply_spi(params, [feats[source]])[0])
    return notes


def predict_one(cfg, year, oni):
    model_path = os.path.join(MODELS, f"{cfg.key}.json")
    if not os.path.exists(model_path):
        return None
    with open(model_path, encoding="utf-8") as f:
        model = json.load(f)

    history = pd.read_csv(os.path.join(TRAINING, f"{cfg.key}.csv"))
    dailies = {p["name"]: recent_weather(p, year) for p in cfg.points}
    coverage = max(d.date.max() for d in dailies.values())

    feats = blend_features(cfg, dailies, year)
    if not feats:
        return {"key": cfg.key, "year": year,
                "error": f"season {year} has no observed weather yet "
                         f"(record ends {coverage.date()})",
                "weather_through": str(coverage.date())}

    feats["oni_season"] = oni_for(oni, year, ONI_WINTER)
    notes = panel_features(cfg, feats, year, history)

    missing = [f for f in model["features"]
               if f not in feats or feats[f] is None or pd.isna(feats[f])]
    if missing:
        return {"key": cfg.key, "year": year,
                "error": f"features unavailable: {', '.join(missing)}",
                "weather_through": str(coverage.date())}

    trend_log = float(np.polyval(model["trend"]["log_poly_coef"], year))
    x = np.array([feats[f] for f in model["features"]], dtype=float)
    z = (x - np.array(model["scaler"]["mean"])) / np.array(model["scaler"]["scale"])
    weather_log = float(model["ridge"]["intercept"]
                        + np.dot(z, model["ridge"]["coef"]))

    trend_val = float(np.exp(trend_log))
    point_val = float(np.exp(trend_log + weather_log))
    sigma = model["uncertainty"]["sigma"]
    last = history.dropna(subset=["target"]).iloc[-1]

    observed = total = 0
    for month, offset in cfg.critical_window:
        m_start = pd.Timestamp(year=year + offset, month=month, day=1)
        m_end = m_start + pd.offsets.MonthEnd(0)
        days = (m_end - m_start).days + 1
        total += days
        if coverage >= m_end:
            observed += days
        elif coverage >= m_start:
            observed += (coverage - m_start).days + 1
    share = (observed / total) if total else None
    sigma_used = sigma * (1 + 0.5 * (1 - (share if share is not None else 0)))

    return {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "year": year,
        "unit": model["target_unit"],
        "target_label": model["target_label"],
        "label_source": model["label_source"],
        "region_share": model["region_share"],
        "trend": trend_val,
        "weather_effect": point_val - trend_val,
        "weather_effect_pct": (np.exp(weather_log) - 1) * 100,
        "point": point_val,
        "range_68": [point_val - sigma_used, point_val + sigma_used],
        "range_95": [point_val - 1.96 * sigma_used, point_val + 1.96 * sigma_used],
        "sigma": sigma,
        "sigma_used": sigma_used,
        "uncertainty_basis": model["uncertainty"]["basis"],
        "beats_trend": model["beats_trend"],
        "skill_vs_trend": model["recent_skill_vs_trend"],
        "weather_skill": model.get("weather_skill", model["recent_skill_vs_trend"]),
        "last_actual": {"year": int(last.year), "yield": float(last.target),
                        "value": float(last.target)},
        "features": {f: float(feats[f]) for f in model["features"]},
        "weather_through": str(coverage.date()),
        "critical_window_observed": share,
        "season_progress": {
            "critical_days": {
                "observed": observed,
                "forecast": 0,
                "climatology": max(0, total - observed),
            },
            "observed_share": share,
        },
        "season_complete": bool(share is not None and share >= 0.999),
        "doc": model["doc"],
        "caveat": model["caveat"],
        "non_weather_drivers": model.get("non_weather_drivers", ""),
        "trained_years": model.get("trained_years"),
        "notes": notes,
    }


def main():
    args = list(sys.argv[1:])
    year = None
    if "--year" in args:
        i = args.index("--year")
        year = int(args[i + 1])
        del args[i:i + 2]

    configs = [BY_KEY[k] for k in args] if args else ALL
    oni = load_oni()
    results = []
    for cfg in configs:
        target_year = year or current_season(cfg)
        r = predict_one(cfg, target_year, oni)
        if r:
            results.append(r)

    log("")
    for r in sorted(results, key=lambda x: -x.get("skill_vs_trend", -9)):
        if "error" in r:
            log(f"{r['key']:28} no forecast -- {r['error']}")
            continue
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{r['label']}{flag}")
        log(f"  point {r['point']:,.0f} {r['unit']}  "
            f"weather {r['weather_effect_pct']:+.1f}%  "
            f"through {r['weather_through']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
