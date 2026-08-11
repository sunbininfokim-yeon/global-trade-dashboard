"""
In-season US Corn Belt yield forecast.

Usage: python3 predict_us.py [year] [crop ...]

Assembles the current season from three tiers, in order of confidence:

  1. Observed   - NASA POWER daily, the same source the model was trained on.
                  Lags real time by 2-3 days.
  2. Forecast   - Open-Meteo, up to ~16 days ahead, for temperature and rain.
  3. Climatology- Day-of-year normals from POWER history, for whatever remains
                  of the season beyond the forecast horizon.

Soil moisture is only ever taken from POWER or POWER climatology, never from
Open-Meteo. Open-Meteo's soil moisture sits on a different scale after 2025
(at Goias, identical rainfall in Jan-Feb 2024 and 2025 produced 0.463 vs
0.351), so mixing it into a POWER-trained model would push features several
standard deviations out of distribution.

The reported interval widens with the share of the critical July-August
window that is still unobserved, because the model's historical sigma was
measured on complete seasons and understates a mid-season forecast.
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


def assemble_season(state, year, hist):
    """Observed + forecast + climatology, with provenance per day."""
    obs = power_current(state, year)
    obs["src"] = "observed"

    end = pd.Timestamp(f"{year}-08-31")
    have = obs.date.max()

    parts = [obs[obs.date <= end]]

    if have < end:
        fc = forecast_frame(state)
        fc = fc[(fc.date > have) & (fc.date <= end)].copy()
        fc["src"] = "forecast"
        if not fc.empty:
            parts.append(fc)
            have = fc.date.max()

    if have < end:
        clim = climatology(hist, year)
        days = pd.date_range(have + pd.Timedelta(days=1), end, freq="D")
        rows = []
        for d in days:
            c = clim.loc[d.dayofyear] if d.dayofyear in clim.index else None
            if c is None:
                continue
            rows.append({"date": d, "tmax": c.tmax, "tmin": c.tmin, "tmean": c.tmean,
                         "precip": c.precip, "soil": c.soil, "vpd": c.vpd,
                         "src": "climatology"})
        if rows:
            parts.append(pd.DataFrame(rows))

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
    return df


def anomalies_for(state, year, season_df, hist, spec):
    """Stage features for the season, expressed vs the trailing climatology."""
    cur = season_features(season_df, year, spec)
    if cur is None:
        return None

    base = {}
    for y in range(year - CLIMATOLOGY_YEARS, year):
        f = season_features(hist, y, spec)
        if f:
            base[y] = f
    if len(base) < 10:
        return None

    out = {}
    for k, v in cur.items():
        hist_vals = [base[y][k] for y in base if k in base[y]]
        if not hist_vals:
            continue
        mu, sd = float(np.mean(hist_vals)), float(np.std(hist_vals))
        out[f"{k}_anom"] = (v - mu) / sd if sd > 0 else 0.0
    return out


def predict(crop, year):
    with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
        model = json.load(f)
    spec = CROPS[crop]

    blended, wsum = {}, 0.0
    provenance = {"observed": 0, "forecast": 0, "climatology": 0}

    for st in STATES:
        hist = power_weather(st)
        season = assemble_season(st, year, hist)

        # Track how much of the decisive July-August window is real.
        ja = season[(season.date >= f"{year}-07-01") & (season.date <= f"{year}-08-31")]
        for s in provenance:
            provenance[s] += int((ja.src == s).sum())

        a = anomalies_for(st, year, season, hist, spec)
        if a is None:
            log(f"  {st['code']}: insufficient history, skipped")
            continue
        for k, v in a.items():
            blended[k] = blended.get(k, 0.0) + v * st["weight"]
        wsum += st["weight"]

    if wsum == 0:
        return None
    blended = {k: v / wsum for k, v in blended.items()}
    blended["oni_growing"] = growing_season_oni(load_oni(), year)

    missing = [f for f in model["features"] if f not in blended or pd.isna(blended[f])]
    if missing:
        log(f"  missing features: {missing}")
        return None

    trend = model["trend"]["slope_per_year"] * year + model["trend"]["intercept"]
    z = [(blended[f] - m) / s
         for f, m, s in zip(model["features"], model["scaler"]["mean"], model["scaler"]["scale"])]
    resid = model["ridge"]["intercept"] + float(np.dot(z, model["ridge"]["coef"]))

    total_ja = sum(provenance.values()) or 1
    observed_share = provenance["observed"] / total_ja

    # The model's sigma was measured on finished seasons. Inflate it by the
    # share of the July-August window that is still forecast or climatology,
    # so a mid-season number is not quoted as confidently as a final one.
    sigma = model["uncertainty"]["sigma"] * (1 + 0.5 * (1 - observed_share))

    return {
        "crop": crop, "year": year, "unit": model["unit"],
        "trend": trend, "weather_effect": resid, "point": trend + resid,
        "range_68": [trend + resid - sigma, trend + resid + sigma],
        "range_95": [trend + resid - 1.96 * sigma, trend + resid + 1.96 * sigma],
        "sigma": sigma, "base_sigma": model["uncertainty"]["sigma"],
        "julaug_days": provenance, "observed_share": observed_share,
        "features": {f: blended[f] for f in model["features"]},
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
        log(f"  Jul-Aug window: {p['observed']}d observed, {p['forecast']}d forecast, "
            f"{p['climatology']}d climatology ({r['observed_share']:.0%} observed)")
        log(f"  trend           {r['trend']:8.1f} {r['unit']}")
        log(f"  weather effect  {r['weather_effect']:+8.1f}")
        log(f"  point estimate  {r['point']:8.1f}")
        log(f"  68% range       {r['range_68'][0]:.1f} - {r['range_68'][1]:.1f}")
        log(f"  95% range       {r['range_95'][0]:.1f} - {r['range_95'][1]:.1f}")
        log(f"  sigma {r['sigma']:.2f} (model {r['base_sigma']:.2f}, widened for unobserved days)")
        log("  key anomalies (sd): " + ", ".join(
            f"{k.replace('_anom','')}={v:+.2f}" for k, v in list(r["features"].items())[:5]))
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
