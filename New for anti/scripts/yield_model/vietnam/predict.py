"""
Apply trained Vietnam models to a live season.

Usage: python3 -m vietnam.predict [--year Y] [region_key ...]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from brazil import climate as BC
from . import climate as C
from .collect import (
    END_YEAR,
    POWER_FILL,
    POWER_PARAMS,
    POWER_URL,
    apply_salt_with_oni,
    blend_features,
    current_season,
    load_oni,
    oni_djf,
    oni_for,
    retry_json,
)
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")
TRAINING = os.path.join(HERE, "training")
CACHE = os.path.join(HERE, "cache")


def log(msg):
    print(f"[predict] {msg}", flush=True)


def recent_weather(point, year):
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    stamp = date.today().isoformat()
    cached = os.path.join(CACHE, f"live_{slug}_{year}_{stamp}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    start = f"{year - 2}0101"
    end = min(date.today(), date(year, 12, 31)).strftime("%Y%m%d")
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
    return df


def predict_one(cfg, year, oni):
    model_path = os.path.join(MODELS, f"{cfg.key}.json")
    if not os.path.exists(model_path):
        return None
    with open(model_path, encoding="utf-8") as f:
        model = json.load(f)

    hist_path = os.path.join(TRAINING, f"{cfg.key}.csv")
    if not os.path.exists(hist_path):
        return None
    history = pd.read_csv(hist_path)

    dailies = {p["name"]: recent_weather(p, year) for p in cfg.points}
    coverage = max(d.date.max() for d in dailies.values())

    feats = blend_features(cfg, dailies, year)
    if not feats:
        return None
    feats["oni_season"] = oni_for(oni, year, cfg.oni_window)
    feats["oni_djf"] = oni_djf(oni, year)
    oni_s = feats["oni_djf"] if feats["oni_djf"] is not None else feats["oni_season"]
    if "salt_water_index" in feats or cfg.crop == "rice":
        feats = apply_salt_with_oni(feats, oni_s or 0.0)

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
    trend_kg = float(np.exp(trend_log))
    point_kg = float(np.exp(trend_log + weather_log))
    sigma = model["uncertainty"]["sigma_kg_ha"]

    last = history.dropna(subset=["yield_kg_ha"]).iloc[-1]

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

    return {
        "key": cfg.key,
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "crop": cfg.crop,
        "year": year,
        "unit": "kg/ha",
        "trend": trend_kg,
        "weather_effect_pct": (np.exp(weather_log) - 1) * 100,
        "point": point_kg,
        "range_68": [point_kg - sigma, point_kg + sigma],
        "range_95": [point_kg - 1.96 * sigma, point_kg + 1.96 * sigma],
        "sigma": sigma,
        "beats_trend": model["beats_trend"],
        "skill_vs_trend": model["recent_skill_vs_trend"],
        "weather_skill": model.get("weather_skill",
                                   model["recent_skill_vs_trend"]),
        "labels_provisional": model.get("labels_provisional", True),
        "labels_season_imperfect": model.get("labels_season_imperfect", False),
        "label_source": model.get("label_source", ""),
        "last_actual": {"year": int(last.year),
                        "yield": float(last.yield_kg_ha)},
        "features": {f: float(feats[f]) for f in model["features"]},
        "weather_through": str(coverage.date()),
        "critical_window_observed": share,
        "season_complete": bool(share is not None and share >= 0.999),
        "doc": model["doc"],
        "caveat": model["caveat"],
        "non_weather_drivers": model.get("non_weather_drivers", ""),
    }


def main():
    args = list(sys.argv[1:])
    year = None
    if "--year" in args:
        i = args.index("--year")
        year = int(args[i + 1])
        del args[i:i + 2]

    configs = [BY_KEY[k] for k in args] if args else list(ALL)
    oni = load_oni()
    results = []
    for cfg in configs:
        target = year or current_season(cfg)
        r = predict_one(cfg, target, oni)
        if r:
            results.append(r)

    for r in results:
        if "error" in r:
            log(f"{r['key']}: {r['error']}")
            continue
        flag = "" if r["beats_trend"] else " [no skill vs trend]"
        prov = " [provisional labels]" if r.get("labels_provisional") else ""
        log(f"{r['label']}{flag}{prov}")
        log(f"  point {r['point']:,.0f} kg/ha  "
            f"(trend {r['trend']:,.0f}, weather {r['weather_effect_pct']:+.1f}%)")
        log(f"  range68 {r['range_68'][0]:,.0f}–{r['range_68'][1]:,.0f}  "
            f"through {r['weather_through']}")
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
