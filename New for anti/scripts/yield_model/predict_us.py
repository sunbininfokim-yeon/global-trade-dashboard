"""
In-season US Corn Belt yield forecast.

Usage: python3 predict_us.py [year] [crop ...]

Builds the current season from three tiers, in order of confidence:

  1. Observed   - NASA POWER daily, the same source the model was trained on.
                  Lags real time by 2-3 days.
  2. Forecast   - Open-Meteo, up to ~16 days ahead, for temperature and rain.
  3. Scenarios  - for every day beyond the forecast, each past year's POWER
                  weather in turn (UNL Yield Forecasting Center approach).

Each past year gives one complete season and one model prediction. The mean
of those predictions is the point estimate; their spread, with the model's
own out-of-sample error laid around each, is the range. Early in the season
the borrowed years dominate and the range is wide; as observed days replace
them it narrows on its own, so there is no hand-tuned widening factor.

Whether the number is a forecast or a reference depends on how far the
season has got. train_us.py backtests the engine at 1 June, 30 June, 31 July
and 31 August; below the 0.20 skill bar at today's date the output is marked
as a reference (trend plus the range of past summers), not a forecast.

Soil moisture is only ever taken from POWER or POWER climatology, never from
Open-Meteo. Open-Meteo's soil moisture sits on a different scale after 2025
(at Goias, identical rainfall in Jan-Feb 2024 and 2025 produced 0.463 vs
0.351), so mixing it into a POWER-trained model would push features several
standard deviations out of distribution.
"""

import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

from collect_us_cornbelt import (
    CLIMATOLOGY_YEARS,
    CROPS,
    POWER_URL,
    STAGES,
    STATES,
    load_oni,
    growing_season_oni,
    power_weather,
    season_features,
)
from us_scenarios import FORECAST_SKILL, mixture_quantiles, skill_at

HERE = os.path.dirname(os.path.abspath(__file__))
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def log(msg):
    print(f"[forecast] {msg}", flush=True)


def fetch_json(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def power_current(state, year):
    """POWER observations for the current season (Sep of Y-1 through Aug of Y)."""
    params = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,GWETROOT,T2MDEW"
    url = (f"{POWER_URL}?parameters={params}&community=AG"
           f"&longitude={state['lon']}&latitude={state['lat']}"
           f"&start={year - 1}0901&end={year}0930&format=JSON")
    p = fetch_json(url)["properties"]["parameter"]

    dates = sorted(p["T2M_MAX"])
    def col(name):
        return [p[name][d] if p[name][d] > -100 else np.nan for d in dates]

    df = pd.DataFrame({
        "date": pd.to_datetime(dates, format="%Y%m%d"),
        "tmax": col("T2M_MAX"), "tmin": col("T2M_MIN"), "tmean": col("T2M"),
        "precip": col("PRECTOTCORR"), "soil": col("GWETROOT"), "tdew": col("T2MDEW"),
    })
    es = 0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    df["vpd"] = (es - ea).clip(lower=0)
    return df.dropna(subset=["tmax"]).reset_index(drop=True)


def forecast_frame(state):
    """Open-Meteo forecast for temperature, rain and dew point (no soil)."""
    url = (f"{FORECAST_URL}?latitude={state['lat']}&longitude={state['lon']}"
           "&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
           "precipitation_sum,dew_point_2m_mean&past_days=7&forecast_days=16&timezone=UTC")
    d = fetch_json(url)["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "tmax": d["temperature_2m_max"],
        "tmin": d["temperature_2m_min"],
        "tmean": d["temperature_2m_mean"],
        "precip": d["precipitation_sum"],
        "tdew": d["dew_point_2m_mean"],
    }).dropna()
    es = 0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    df["vpd"] = (es - ea).clip(lower=0)
    df["soil"] = np.nan  # deliberately not taken from Open-Meteo
    return df


def climatology(hist, year, ref_years=CLIMATOLOGY_YEARS):
    """Day-of-year normals from POWER history, for filling the unobserved tail."""
    h = hist[(hist.date.dt.year >= year - ref_years) & (hist.date.dt.year < year)].copy()
    h["doy"] = h.date.dt.dayofyear
    return h.groupby("doy")[["tmax", "tmin", "tmean", "precip", "soil", "vpd"]].mean()


def known_season(state, year, hist):
    """Observed + forecast days up to 31 August, with provenance per day."""
    end = pd.Timestamp(f"{year}-08-31")
    obs = power_current(state, year)
    obs = obs[obs.date <= end].copy()
    obs["src"] = "observed"
    observed_through = obs.date.max()

    parts, have = [obs], observed_through
    if have < end:
        fc = forecast_frame(state)
        fc = fc[(fc.date > have) & (fc.date <= end)].copy()
        fc["src"] = "forecast"
        if not fc.empty:
            parts.append(fc)
            have = fc.date.max()

    df = pd.concat(parts, ignore_index=True).sort_values("date").reset_index(drop=True)

    # Soil is missing for forecast days; carry the climatological normal there
    # rather than Open-Meteo's incompatible series.
    if df.soil.isna().any():
        clim = climatology(hist, year)
        need = df.soil.isna()
        df.loc[need, "soil"] = [
            clim.loc[d.dayofyear].soil if d.dayofyear in clim.index else np.nan
            for d in df.loc[need, "date"]
        ]
    return df, observed_through, have


def borrowed_tail(hist, past_year, year, have, end):
    """Past year's weather for the days after `have`, relabelled to `year`."""
    days = pd.date_range(have + pd.Timedelta(days=1), end, freq="D")
    src = days - pd.DateOffset(years=year - past_year)
    h = hist.drop_duplicates("date").set_index("date")
    cols = ["tmax", "tmin", "tmean", "precip", "soil", "vpd"]
    tail = h.reindex(src)[cols].reset_index(drop=True)
    if tail.tmax.isna().any():
        return None
    tail["date"] = days
    tail["src"] = "scenario"
    return tail


def anomaly_stats(hist, year, spec):
    """Mean and sd of each stage feature over the trailing climatology."""
    base = [f for y in range(year - CLIMATOLOGY_YEARS, year)
            if (f := season_features(hist, y, spec))]
    if len(base) < 10:
        return None
    keys = set.intersection(*(set(b) for b in base))
    return {k: (float(np.mean([b[k] for b in base])), float(np.std([b[k] for b in base])))
            for k in keys}


def to_anomalies(raw, stats):
    return {f"{k}_anom": (v - stats[k][0]) / stats[k][1] if stats[k][1] > 0 else 0.0
            for k, v in raw.items() if k in stats}


def state_scenarios(state, year, hist, spec):
    """Anomaly features per scenario for one state, keyed by past year.

    Once the season is complete there is nothing to borrow and the only
    scenario is the observed season itself (key None).
    """
    end = pd.Timestamp(f"{year}-08-31")
    known, observed_through, have = known_season(state, year, hist)
    stats = anomaly_stats(hist, year, spec)
    if stats is None:
        return None

    ja = known[(known.date >= f"{year}-07-01") & (known.date <= end)]
    n_ja = (end - pd.Timestamp(f"{year}-07-01")).days + 1
    provenance = {"observed": int((ja.src == "observed").sum()),
                  "forecast": int((ja.src == "forecast").sum())}
    provenance["scenario"] = n_ja - provenance["observed"] - provenance["forecast"]

    out = {}
    if have >= end:
        raw = season_features(known, year, spec)
        if raw:
            out[None] = to_anomalies(raw, stats)
    else:
        first = int(hist.date.dt.year.min()) + 1   # first year with a full Sep-Aug
        for past in range(first, year):
            tail = borrowed_tail(hist, past, year, have, end)
            if tail is None:
                continue
            season = pd.concat([known, tail], ignore_index=True)
            raw = season_features(season, year, spec)
            if raw:
                out[past] = to_anomalies(raw, stats)
    return {"scenarios": out, "provenance": provenance,
            "observed_through": observed_through, "known_through": have}


def predict(crop, year):
    with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
        model = json.load(f)
    spec = CROPS[crop]
    feats = model["features"]

    per_state = []
    for st in STATES:
        hist = power_weather(st)
        r = state_scenarios(st, year, hist, spec)
        if r is None or not r["scenarios"]:
            log(f"  {st['code']}: insufficient history, skipped")
            continue
        per_state.append((st, r))
    if not per_state:
        return None

    # The same past year fills every state, so a scenario is one coherent
    # summer across the Corn Belt rather than a patchwork of different years.
    keys = set.intersection(*(set(r["scenarios"]) for _, r in per_state))
    keys = sorted(keys, key=lambda k: -1 if k is None else k)
    wsum = sum(st["weight"] for st, _ in per_state)

    rows = []
    for k in keys:
        blended = {}
        for st, r in per_state:
            for f, v in r["scenarios"][k].items():
                blended[f] = blended.get(f, 0.0) + v * st["weight"] / wsum
        if "oni_growing" in feats:   # older artifacts still carry it
            blended["oni_growing"] = growing_season_oni(load_oni(), year)
        rows.append(blended)

    missing = [f for f in feats if any(f not in b or pd.isna(b[f]) for b in rows)]
    if missing or not rows:
        log(f"  missing features: {missing}")
        return None

    X = np.array([[b[f] for f in feats] for b in rows])
    z = (X - np.array(model["scaler"]["mean"])) / np.array(model["scaler"]["scale"])
    resid = model["ridge"]["intercept"] + z @ np.array(model["ridge"]["coef"])

    trend = model["trend"]["slope_per_year"] * year + model["trend"]["intercept"]
    preds = trend + resid
    point = float(preds.mean())

    base_sigma = model["uncertainty"]["sigma"]
    q025, q10, q16, q50, q84, q90, q975 = mixture_quantiles(
        preds, base_sigma, (0.025, 0.10, 0.16, 0.50, 0.84, 0.90, 0.975))

    provenance = {s: sum(r["provenance"][s] for _, r in per_state) for s in
                  ("observed", "forecast", "scenario")}
    total_ja = sum(provenance.values()) or 1
    observed_share = provenance["observed"] / total_ja
    observed_through = min(r["observed_through"] for _, r in per_state)
    known_through = min(r["known_through"] for _, r in per_state)

    # How far the season has got decides whether this is a forecast. Day of
    # year counts only observed days; the 16-day forecast is not credited.
    if observed_through.year < year:
        doy = 0
    else:
        doy = min(observed_through.dayofyear - (observed_through.is_leap_year
                                                and observed_through.month > 2), 365)
    if model.get("inseason"):
        skill_now = skill_at(model["inseason"], doy)
    else:
        sel = model.get("selected", "core")
        skill_now = model["validation"].get(f"{sel}_forward", {}).get("skill_vs_trend")
    mode = "forecast" if skill_now is not None and skill_now >= FORECAST_SKILL else "reference"

    past = [k for k in keys if k is not None]
    return {
        "crop": crop, "year": year, "unit": model["unit"],
        "trend": trend, "weather_effect": point - trend, "point": point,
        "range_68": [q16, q84], "range_95": [q025, q975],
        "percentiles": {"p10": q10, "p50": q50, "p90": q90},
        "sigma": (q84 - q16) / 2, "base_sigma": base_sigma,
        "julaug_days": provenance, "observed_share": observed_share,
        "inseason": {
            "mode": mode,
            "skill_now": skill_now,
            "observed_through": observed_through.date().isoformat(),
            "known_through": known_through.date().isoformat(),
            "n_scenarios": len(keys),
            "scenario_years": [min(past), max(past)] if past else None,
            "scenario_spread_sd": float(preds.std()),
        },
        "features": {f: float(X[:, i].mean()) for i, f in enumerate(feats)},
    }


def main():
    args = sys.argv[1:]
    year = int(args[0]) if args and args[0].isdigit() else 2026
    crops = [a for a in args if not a.isdigit()] or ["corn", "soybeans"]

    for crop in crops:
        log(f"=== {crop} {year} ===")
        r = predict(crop, year)
        if r is None:
            log("  no forecast")
            continue
        p = r["julaug_days"]
        ins = r["inseason"]
        log(f"  Jul-Aug window: {p['observed']}d observed, {p['forecast']}d forecast, "
            f"{p['scenario']}d from past years ({r['observed_share']:.0%} observed)")
        log(f"  observed through {ins['observed_through']}, {ins['n_scenarios']} scenarios, "
            f"skill now {ins['skill_now']:+.0%} -> {ins['mode']}")
        log(f"  trend           {r['trend']:8.1f} {r['unit']}")
        log(f"  weather effect  {r['weather_effect']:+8.1f}")
        log(f"  point estimate  {r['point']:8.1f}")
        log(f"  68% range       {r['range_68'][0]:.1f} - {r['range_68'][1]:.1f}")
        log(f"  95% range       {r['range_95'][0]:.1f} - {r['range_95'][1]:.1f}")
        q = r["percentiles"]
        log(f"  P10/P50/P90     {q['p10']:.1f} / {q['p50']:.1f} / {q['p90']:.1f}")
        log("  key anomalies (sd): " + ", ".join(
            f"{k.replace('_anom','')}={v:+.2f}" for k, v in list(r["features"].items())[:5]))
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
