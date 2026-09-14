"""
In-season forecast for US winter and spring wheat.

Usage: python3 predict_wheat.py [year]

Same three-tier season assembly as the Corn Belt forecaster: NASA POWER
observations first, Open-Meteo forecast for the near term, then day-of-year
climatology for whatever is still beyond the forecast horizon. Soil moisture
is only ever POWER or POWER climatology -- never Open-Meteo, whose soil series
sits on a different scale after 2025 and would push features well outside the
training distribution.

The two classes sit at different points in the calendar, and the reported
uncertainty reflects that:

  Winter wheat  sown autumn, harvested June. By August its season is over, the
                weather is fully observed, and the interval is the model's own
                sigma with nothing added.
  Spring wheat  sown April-May, harvested late summer. In early August part of
                grain fill is still unobserved, so the interval is widened in
                proportion.

Spring wheat is additionally fitted on a rolling 20-season window, so the
trend used here is the one fitted on that window rather than on all 34
seasons -- otherwise the deployed forecast would not match what was validated.
"""

import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from collect_us_wheat import (  # noqa: E402
    CLIMATOLOGY_YEARS, CROPS, POWER_URL, STAGES,
    load_oni, power_weather, season_features, season_oni,
)
import collect_us_south as south  # noqa: E402

# Cotton lives in its own collector (different states, different stages, and a
# planted-acre target). Route to it rather than duplicating the definitions.
SOUTH_CROPS = {"cotton"}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = ("temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
              "precipitation_sum,dew_point_2m_mean,shortwave_radiation_sum")

# Last month of each crop's season, i.e. how far the weather record must reach.
SEASON_END_MONTH = {"winter_wheat": 6, "spring_wheat": 8, "cotton": 11}


def log(m):
    print(f"[wheat-fc] {m}", flush=True)


def fetch_json(url, timeout=180, attempts=3):
    # Same SSL-handshake-timeout flake collect_us_cornbelt.py/collect_us_wheat.py
    # already retry around for the Open-Meteo/NASA POWER APIs -- this call site
    # (the Open-Meteo forecast fetch below) was never reaching a real network
    # call before, since a run always crashed earlier on the yield_model cache
    # directory. Now that it does, it needs the same retry.
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            log(f"  retry {attempt + 1} after {e}")
            time.sleep(10)


def power_current(state, year, end_month):
    params = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,GWETROOT,T2MDEW,ALLSKY_SFC_SW_DWN"
    end_day = pd.Timestamp(year=year, month=end_month, day=1) + pd.offsets.MonthEnd(0)
    url = (f"{POWER_URL}?parameters={params}&community=AG"
           f"&longitude={state['lon']}&latitude={state['lat']}"
           f"&start={year - 1}0901&end={end_day.strftime('%Y%m%d')}&format=JSON")
    p = fetch_json(url)["properties"]["parameter"]

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
    return df.dropna(subset=["tmax"]).reset_index(drop=True)


def forecast_frame(state):
    url = (f"{FORECAST_URL}?latitude={state['lat']}&longitude={state['lon']}"
           f"&daily={DAILY_VARS}&past_days=7&forecast_days=16&timezone=UTC")
    d = fetch_json(url)["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "tmax": d["temperature_2m_max"], "tmin": d["temperature_2m_min"],
        "tmean": d["temperature_2m_mean"], "precip": d["precipitation_sum"],
        "tdew": d["dew_point_2m_mean"], "srad": d["shortwave_radiation_sum"],
    }).dropna()
    es = 0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    df["vpd"] = (es - ea).clip(lower=0)
    df["soil"] = np.nan     # deliberately not taken from Open-Meteo
    return df


def climatology(hist, year):
    h = hist[(hist.date.dt.year >= year - CLIMATOLOGY_YEARS) & (hist.date.dt.year < year)].copy()
    h["doy"] = h.date.dt.dayofyear
    return h.groupby("doy")[["tmax", "tmin", "tmean", "precip", "soil", "vpd", "srad"]].mean()


def assemble(state, year, hist, end_month):
    obs = power_current(state, year, end_month)
    obs["src"] = "observed"
    end = pd.Timestamp(year=year, month=end_month, day=1) + pd.offsets.MonthEnd(0)

    parts = [obs[obs.date <= end]]
    have = obs.date.max() if not obs.empty else None

    if have is not None and have < end:
        fc = forecast_frame(state)
        fc = fc[(fc.date > have) & (fc.date <= end)].copy()
        fc["src"] = "forecast"
        if not fc.empty:
            parts.append(fc)
            have = fc.date.max()

    if have is not None and have < end:
        clim = climatology(hist, year)
        rows = []
        for d in pd.date_range(have + pd.Timedelta(days=1), end, freq="D"):
            if d.dayofyear not in clim.index:
                continue
            c = clim.loc[d.dayofyear]
            rows.append({"date": d, "tmax": c.tmax, "tmin": c.tmin, "tmean": c.tmean,
                         "precip": c.precip, "soil": c.soil, "vpd": c.vpd,
                         "srad": c.srad, "src": "climatology"})
        if rows:
            parts.append(pd.DataFrame(rows))

    df = pd.concat(parts, ignore_index=True).sort_values("date").reset_index(drop=True)

    if df.soil.isna().any():
        clim = climatology(hist, year)
        need = df.soil.isna()
        df.loc[need, "soil"] = [
            clim.loc[d.dayofyear].soil if d.dayofyear in clim.index else np.nan
            for d in df.loc[need, "date"]
        ]
    return df


def anomalies(state, year, season_df, hist, crop, feat_fn=season_features):
    cur = feat_fn(season_df, year, crop)
    if cur is None:
        return None
    base = {}
    for y in range(year - CLIMATOLOGY_YEARS, year):
        f = feat_fn(hist, y, crop)
        if f:
            base[y] = f
    if len(base) < 10:
        return None

    out = {}
    for k, v in cur.items():
        h = [base[y][k] for y in base if k in base[y]]
        if not h:
            continue
        mu, sd = float(np.mean(h)), float(np.std(h))
        out[f"{k}_anom"] = (v - mu) / sd if sd > 0 else 0.0
    return out


def predict(crop, year):
    with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
        model = json.load(f)

    is_south = crop in SOUTH_CROPS
    spec = south.CROPS[crop] if is_south else CROPS[crop]
    feat_fn = south.season_features if is_south else season_features
    stages = south.STAGES[crop] if is_south else STAGES[crop]
    wx_fn = south.power_weather if is_south else power_weather
    oni_fn = ((lambda o, y, c: south.season_oni(o, y)) if is_south else season_oni)
    end_month = SEASON_END_MONTH[crop]
    blended, wsum = {}, 0.0
    prov = {"observed": 0, "forecast": 0, "climatology": 0}

    for st in spec["states"]:
        hist = wx_fn(st)
        season = assemble(st, year, hist, end_month)

        # Count provenance over the yield-critical window only.
        crit = stages["bollfill" if is_south else "grainfill"]["months"]
        mask = np.zeros(len(season), dtype=bool)
        for m, off in crit:
            mask |= ((season.date.dt.year == year + off) & (season.date.dt.month == m)).values
        for s in prov:
            prov[s] += int((season[mask].src == s).sum())

        a = anomalies(st, year, season, hist, crop, feat_fn)
        if a is None:
            log(f"  {st['code']}: insufficient history, skipped")
            continue
        for k, v in a.items():
            blended[k] = blended.get(k, 0.0) + v * st["weight"]
        wsum += st["weight"]

    if wsum == 0:
        return None
    blended = {k: v / wsum for k, v in blended.items()}
    blended["oni_season"] = oni_fn(load_oni(), year, crop)

    missing = [f for f in model["features"] if f not in blended or pd.isna(blended[f])]
    if missing:
        log(f"  missing features: {missing}")
        return None

    trend = model["trend"]["slope_per_year"] * year + model["trend"]["intercept"]
    z = [(blended[f] - m) / s for f, m, s
         in zip(model["features"], model["scaler"]["mean"], model["scaler"]["scale"])]
    resid = model["ridge"]["intercept"] + float(np.dot(z, model["ridge"]["coef"]))

    total = sum(prov.values()) or 1
    observed_share = prov["observed"] / total
    sigma = model["uncertainty"]["sigma"] * (1 + 0.5 * (1 - observed_share))

    return {
        "crop": crop, "year": year, "unit": model["unit"],
        "trend": trend, "weather_effect": resid, "point": trend + resid,
        "range_68": [trend + resid - sigma, trend + resid + sigma],
        "range_95": [trend + resid - 1.96 * sigma, trend + resid + 1.96 * sigma],
        "sigma": sigma, "base_sigma": model["uncertainty"]["sigma"],
        "critical_days": prov, "observed_share": observed_share,
        "train_window_years": model.get("train_window_years"),
        "skill": model["validation"].get("core_forward")
                 or model["validation"].get("all_forward", {}),
        "trained_years": model["trained_years"],
    }


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    for crop in ("winter_wheat", "spring_wheat", "cotton"):
        log(f"=== {crop} {year} ===")
        r = predict(crop, year)
        if r is None:
            log("  no forecast")
            continue
        p = r["critical_days"]
        log(f"  등숙기 관측 {p['observed']}d / 예보 {p['forecast']}d / 평년 {p['climatology']}d "
            f"({r['observed_share']:.0%} 관측)")
        log(f"  추세 {r['trend']:.1f} | 기상효과 {r['weather_effect']:+.1f} | "
            f"예상 {r['point']:.1f} {r['unit']}")
        log(f"  68% {r['range_68'][0]:.1f}-{r['range_68'][1]:.1f}  "
            f"(sigma {r['sigma']:.2f}, 모델 {r['base_sigma']:.2f})")
        log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
