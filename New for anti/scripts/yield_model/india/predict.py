"""
Apply the trained India region-crop models to a live season.

Usage: python3 -m india.predict [--year Y] [region_key ...]

Pulls the season's actual weather from NASA POWER, rebuilds exactly the
features the model was trained on, and reports a central estimate with the
band the model's own out-of-sample error justifies.

ICRISAT's published record ends well before the present, so every season from
then on is a genuinely unseen forecast rather than a replay of training data --
see india/README.md for the exact last labelled year per crop.
"""

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import climate as C
from . import icrisat
from .collect import (
    END_YEAR,
    current_season,
    DMI_WINDOW,
    DMI_KHARIF,
    ONI_WINDOW,
    ONI_KHARIF,
    POWER_FILL,
    POWER_PARAMS,
    POWER_URL,
    blend_features,
    dmi_for,
    load_dmi,
    load_oni,
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
    """
    Daily weather covering the requested season, fetched fresh.

    Cached under today's date rather than permanently: a live season's tail
    grows every day, and a stale cache would silently forecast last week's
    weather. POWER runs a few days behind real time.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    stamp = date.today().isoformat()
    cached = os.path.join(CACHE, f"live_{slug}_{year}_{stamp}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    # Two years of lead-in: the monsoon-onset and water-balance formulas reach
    # back into the year before the harvest year, and wheat's window opens the
    # previous November.
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
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean",
                 "tdew", "rs", "wind"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)

    df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
    df = df[["date", "tmax", "tmin", "tmean", "precip",
             "rh_mean", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    return df


def panel_features(cfg, feats, year, history):
    """
    Add the cross-year features -- currently just SPI -- scoring this season
    against the training climatology rather than refitting it to include this
    season.
    """
    for name, source in cfg.panel.items():
        if source in history.columns and source in feats:
            params = C.fit_spi(history[source])
            feats[name] = float(C.apply_spi(params, [feats[source]])[0])


def predict_one(cfg, year, oni, dmi):
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
        return None
    feats["oni_season"] = oni_for(oni, year, ONI_WINDOW.get(cfg.key, ONI_KHARIF))
    feats["dmi_season"] = dmi_for(dmi, year, DMI_WINDOW.get(cfg.key, DMI_KHARIF))

    panel_features(cfg, feats, year, history)

    missing = [f for f in model["features"]
               if f not in feats or feats[f] is None or pd.isna(feats[f])]
    if missing:
        return {"key": cfg.key, "year": year, "error":
                f"features unavailable: {', '.join(missing)}",
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

    # How much of the yield-deciding window has actually happened. A figure
    # published while the critical months are still ahead is a projection off
    # climatology, not a read on this season, and the site should say which.
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
        "weather_skill": model.get("weather_skill", model["recent_skill_vs_trend"]),
        "non_weather_features": model.get("non_weather_features", []),
        "last_actual": {"year": int(last.year), "yield": float(last.yield_kg_ha)},
        "features": {f: float(feats[f]) for f in model["features"]},
        "weather_through": str(coverage.date()),
        "critical_window_observed": share,
        "season_complete": bool(share is not None and share >= 0.999),
        "doc": model["doc"],
        "caveat": model["caveat"],
        "non_weather_drivers": model.get("non_weather_drivers", ""),
    }


def main():
    args = [a for a in sys.argv[1:]]
    year = None
    if "--year" in args:
        i = args.index("--year")
        year = int(args[i + 1])
        del args[i:i + 2]

    configs = [BY_KEY[k] for k in args] if args else ALL
    oni, dmi = load_oni(), load_dmi()

    log(f"season {year or 'per-crop (' + str(current_season()) + ')'}"
        "  -- beyond the last ICRISAT actual, so genuinely unseen")
    log("")

    results = []
    for cfg in configs:
        target = year or current_season(cfg)
        r = predict_one(cfg, target, oni, dmi)
        if r:
            results.append(r)

    for r in sorted(results, key=lambda x: -x.get("skill_vs_trend", -9)):
        if "error" in r:
            log(f"{r['key']:20} no forecast -- {r['error']}")
            continue
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{r['label']}{flag}")
        log(f"  trend            {r['trend']:9,.0f} kg/ha")
        log(f"  weather effect   {r['weather_effect_pct']:+9.1f} %")
        log(f"  point estimate   {r['point']:9,.0f} kg/ha")
        log(f"  68% range        {r['range_68'][0]:,.0f} - {r['range_68'][1]:,.0f}")
        log(f"  last actual      {r['last_actual']['yield']:,.0f} "
            f"({r['last_actual']['year']})")
        log(f"  weather through  {r['weather_through']}")
        if r.get("critical_window_observed") is not None:
            log(f"  critical window  {r['critical_window_observed']:.0%} observed"
                + ("" if r["season_complete"] else "  <-- season still running"))
        log("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
