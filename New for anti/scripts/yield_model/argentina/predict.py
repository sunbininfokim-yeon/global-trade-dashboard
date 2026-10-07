"""
Apply the trained region-crop models to a live season.

Usage: python3 -m argentina.predict [--year Y] [region_key ...]

Pulls the season's actual weather from NASA POWER, rebuilds exactly the
features the model was trained on, and reports a central estimate with the band
the model's own out-of-sample error justifies.

MAGyP's estimaciones file currently ends at campaign 2024/25, so 2026 onward
are genuinely unseen seasons rather than a replay of training data.

One Argentine wrinkle at forecast time: the wheat season and the summer-crop
seasons are never the same harvest year. In August, Pampas wheat is a standing
crop two months from anthesis (season 2026) while soybeans are four months from
sowing (season 2027). `current_season` resolves that per config rather than
stamping one year across the whole country.
"""

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from brazil import climate as C
from . import climate_ar as A
from .collect import (
    IOD_SEASON,
    ONI_SUMMER,
    POWER_FILL,
    POWER_PARAMS,
    POWER_URL,
    blend_features,
    current_season,
    iod_for,
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
    grows every day and a stale cache would silently forecast last week's
    weather. POWER runs about three days behind real time.
    """
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    stamp = date.today().isoformat()
    # Keyed on point and date only. The requested range starts at 1981 and ends
    # today regardless of `year`, so keying on the season as well would fetch
    # the same 45-year record once per season asked for -- and run_forecast
    # asks for two.
    cached = os.path.join(CACHE, f"live_{slug}_{stamp}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])

    # The whole record, not a two-year lead-in. The soil-moisture features are
    # day-of-year percentiles against a point's own climatology, and scoring a
    # live season against two years of history would rank it against a sample
    # of ~30 days per date instead of ~675 -- a different variable from the one
    # the model was fitted on.
    start = "19810101"
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
        "gwettop": list(p["GWETTOP"].values()),
    })
    df = df[(df[["tmax", "tmin", "tmean", "precip", "rh_mean", "tdew", "rs",
                 "wind", "gwetroot", "gwettop"]] > POWER_FILL).all(axis=1)]
    df = df.sort_values("date").reset_index(drop=True)

    df["et0"] = C.fao56_et0(df, point["lat"], point["elevation"])
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
    df["sm_pct"] = A.soil_wetness_percentile(df, "gwetroot")
    df = df[["date", "tmax", "tmin", "tmean", "precip", "rh_mean", "vpd_max",
             "et0", "gwetroot", "gwettop", "sm_pct"]]
    df.to_csv(cached, index=False)
    return df


def _prior_yield(year, history, predicted):
    row = history[history.year == year]
    if not row.empty and pd.notna(row.yield_kg_ha.iloc[0]):
        return float(row.yield_kg_ha.iloc[0]), []
    if year in predicted:
        return predicted[year], [f"lag for {year} uses this model's own forecast"]
    return np.nan, [f"no yield or forecast available for {year}"]


def panel_features(cfg, feats, year, history, predicted):
    """
    Add the cross-year features, scoring this season against the *training*
    climatology rather than refitting it to include this season.

    Refitting the SPI Gamma on a record that includes the season being scored
    would let a drought partly define the distribution it is measured against,
    and shrink its own anomaly.
    """
    notes = []
    for name, source in cfg.panel.items():
        if source == "__yield__":
            feats[name], note = _prior_yield(year - 1, history, predicted)
            notes += note
        elif source == "__shock__":
            feats[name] = A.climate_shock_index(
                feats.get("oni_lag"), feats.get("iod_spring"))
        elif source in history.columns and source in feats:
            params = C.fit_spi(history[source])
            feats[name] = float(C.apply_spi(params, [feats[source]])[0])
    return notes


def predict_one(cfg, year, oni, dmi, predicted):
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
        # The model exists; the season's weather window has not started.
        # Returning None here made run_forecast report "no trained model".
        return {"key": cfg.key, "year": year, "error":
                f"season {year} has no observed weather in the model window yet",
                "weather_through": str(coverage.date())}

    feats["oni_lag"] = oni_for(oni, year, cfg.oni_window or ONI_SUMMER)
    feats["iod_spring"] = iod_for(
        dmi, year, 0 if cfg.crop == "trigo" else -1, IOD_SEASON)

    notes = panel_features(cfg, feats, year, history, predicted)

    missing = [f for f in model["features"]
               if f not in feats or feats[f] is None or pd.isna(feats[f])]
    if missing:
        return {"key": cfg.key, "year": year,
                "error": f"features unavailable: {', '.join(missing)}",
                "weather_through": str(coverage.date())}

    trend_log = float(np.polyval(model["trend"]["log_poly_coef"], year))

    x = np.array([feats[f] for f in model["features"]], dtype=float)
    # Lag features enter as log deviations from trend, matching training.
    for i, f in enumerate(model["features"]):
        if f in ("lag1", "lag2"):
            lag = 1 if f == "lag1" else 2
            x[i] = np.log(max(x[i], 1.0)) - np.polyval(
                model["trend"]["log_poly_coef"], year - lag)

    z = (x - np.array(model["scaler"]["mean"])) / np.array(model["scaler"]["scale"])
    weather_log = float(model["ridge"]["intercept"]
                        + np.dot(z, model["ridge"]["coef"]))

    trend_kg = float(np.exp(trend_log))
    point_kg = float(np.exp(trend_log + weather_log))
    sigma = model["uncertainty"]["sigma_kg_ha"]

    last = history.dropna(subset=["yield_kg_ha"]).iloc[-1]

    # How much of the yield-deciding window has actually happened.
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
        "oni": feats.get("oni_lag"),
        "iod": feats.get("iod_spring"),
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
    oni, dmi = load_oni(), load_dmi()

    predicted, results = {}, []
    for offset in (-1, 0):
        for cfg in configs:
            target = (year or current_season(cfg)) + offset
            r = predict_one(cfg, target, oni, dmi, predicted)
            if r and "error" not in r:
                predicted[target] = r["point"]
                if offset == 0:
                    results.append(r)
            elif r and offset == 0:
                results.append(r)

    log("")
    for r in sorted(results, key=lambda x: -x.get("skill_vs_trend", -9)):
        if "error" in r:
            log(f"{r['key']:20} no forecast -- {r['error']}")
            continue
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{r['label']}  (season {r['year']}){flag}")
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
        for n in r["notes"]:
            log(f"  note: {n}")
        log("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
