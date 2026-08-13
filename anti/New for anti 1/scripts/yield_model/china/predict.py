"""
Apply the trained China models to a live season.

Usage: python3 -m china.predict [--year Y] [region_key ...]

Pulls the season's actual weather from NASA POWER, rebuilds exactly the
features the model was trained on, and reports a central estimate with the band
the model's own out-of-sample error justifies.

None of the six models beat a trend-only baseline (see README), so in practice
every band published here is the trend's own error and every point estimate is
a trend extrapolation nudged by a weather term that has not been shown to help.
That is stated in the payload rather than left implicit: `beats_trend` is false
for all six and the uncertainty basis names the trend as its source.
"""

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import climate as C
from .collect import (
    ONI_SUMMER,
    ONI_WINDOW,
    POWER_FILL,
    POWER_PARAMS,
    POWER_URL,
    blend_features,
    current_season,
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
    grows every day and a stale cache would silently forecast last week's
    weather. POWER runs about three days behind real time.

    Wind and radiation are kept, unlike the Brazil equivalent which drops them
    after computing ET0. Henan's 干热风 index needs wind as part of a
    three-way conjunction and Shandong's greenhouse index needs radiation
    directly, so dropping them here would make those two models fail every
    live run with "features unavailable".
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    stamp = date.today().isoformat()
    cached = os.path.join(CACHE, f"live_{slug}_{year}_{stamp}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    # Two years of lead-in: winter wheat reaches back to the previous October
    # and Shandong's winter window to the previous December.
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
    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean",
             "wind", "rs", "vpd_max", "et0"]]
    df.to_csv(cached, index=False)
    return df


def panel_features(cfg, feats, year, history):
    """
    Add cross-year features, scoring this season against the training
    climatology rather than refitting the distribution to include it.
    """
    notes = []
    for name, source in cfg.panel.items():
        if source in history.columns and source in feats:
            params = C.fit_spi(history[source])
            if params is None:
                notes.append(f"{name}: SPI fit failed on the training history")
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
        # Distinct from a missing model file: the model exists, but the season
        # has not produced any observable weather yet. Says which, because
        # "no trained model" sent the reader looking for a training bug when
        # the real answer was that the crop is not in the ground.
        return {"key": cfg.key, "year": year,
                "error": (f"season {year} has no observed weather yet "
                          f"(record ends {coverage.date()})"),
                "weather_through": str(coverage.date())}
    feats["oni_season"] = oni_for(oni, year, ONI_WINDOW.get(cfg.key, ONI_SUMMER))

    notes = panel_features(cfg, feats, year, history)

    missing = [f for f in model["features"]
               if f not in feats or feats[f] is None or pd.isna(feats[f])]
    if missing:
        return {"key": cfg.key, "year": year,
                "error": f"features unavailable: {', '.join(missing)}",
                "weather_through": str(coverage.date())}

    trend_log = float(np.polyval(model["trend"]["log_poly_coef"], year))

    x = np.array([feats[f] for f in model["features"]], dtype=float)
    for i, f in enumerate(model["features"]):
        if f in ("lag1", "lag2"):
            lag = 1 if f == "lag1" else 2
            x[i] = np.log(max(x[i], 1.0)) - np.polyval(
                model["trend"]["log_poly_coef"], year - lag)

    z = (x - np.array(model["scaler"]["mean"])) / np.array(model["scaler"]["scale"])
    weather_log = float(model["ridge"]["intercept"]
                        + np.dot(z, model["ridge"]["coef"]))

    trend_val = float(np.exp(trend_log))
    point_val = float(np.exp(trend_log + weather_log))
    sigma = model["uncertainty"]["sigma"]

    last = history.dropna(subset=["target"]).iloc[-1]

    # How much of the deciding window has actually happened. A figure published
    # while the critical months are still ahead is a projection off
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
        "unit": model["target_unit"],
        "target_label": model["target_label"],
        "label_source": model["label_source"],
        "region_share": model["region_share"],
        "trend": trend_val,
        "weather_effect_pct": (np.exp(weather_log) - 1) * 100,
        "point": point_val,
        "range_68": [point_val - sigma, point_val + sigma],
        "range_95": [point_val - 1.96 * sigma, point_val + 1.96 * sigma],
        "sigma": sigma,
        "uncertainty_basis": model["uncertainty"]["basis"],
        "beats_trend": model["beats_trend"],
        "skill_vs_trend": model["recent_skill_vs_trend"],
        "weather_skill": model.get("weather_skill", model["recent_skill_vs_trend"]),
        "non_weather_features": model.get("non_weather_features", []),
        "last_actual": {"year": int(last.year), "value": float(last.target)},
        "features": {f: float(feats[f]) for f in model["features"]},
        "weather_through": str(coverage.date()),
        "critical_window_observed": share,
        "season_complete": bool(share is not None and share >= 0.999),
        "doc": model["doc"],
        "caveat": model["caveat"],
        "non_weather_drivers": model.get("non_weather_drivers", ""),
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
            log(f"{r['key']:24} no forecast -- {r['error']}")
            continue
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{r['label']}{flag}")
        log(f"  trend            {r['trend']:11,.0f} {r['unit']}")
        log(f"  weather effect   {r['weather_effect_pct']:+11.1f} %")
        log(f"  point estimate   {r['point']:11,.0f} {r['unit']}")
        log(f"  68% range        {r['range_68'][0]:,.0f} - {r['range_68'][1]:,.0f}")
        log(f"  last actual      {r['last_actual']['value']:,.0f} "
            f"({r['last_actual']['year']})")
        log(f"  weather through  {r['weather_through']}")
        if r.get("critical_window_observed") is not None:
            log(f"  critical window  {r['critical_window_observed']:.0%} observed"
                + ("" if r["season_complete"] else "  <-- season still running"))
        for n in r["notes"]:
            log(f"  note: {n}")
        log("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
