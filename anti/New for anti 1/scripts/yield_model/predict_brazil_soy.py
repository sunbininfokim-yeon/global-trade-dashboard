"""
Apply the trained Brazil soybean model to a season.

Usage: python3 predict_brazil_soy.py [harvest_year ...]

Pulls that season's actual weather (and, for a season still in progress, the
forecast tail) from Open-Meteo, builds the same stage features the model was
trained on, and reports a central estimate with an uncertainty band taken
from the model's measured out-of-sample error.

FAOSTAT currently ends at 2024, so 2025 onward are genuinely unseen seasons
rather than a re-run of training data.
"""

import json
import os
import sys
import urllib.request

import pandas as pd

from collect_brazil_soy import (
    ARCHIVE_URL,
    GDD_BASE,
    ONI_URL,
    POWER_URL,
    REGIONS,
    STAGES,
    fetch,
    stage_features,
)

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "brazil_soy_model.json")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DAILY_VARS = ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
              "et0_fao_evapotranspiration")


def log(msg):
    print(f"[predict] {msg}", flush=True)


def fetch_json(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def to_frame(daily):
    return pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "tmax": daily["temperature_2m_max"],
        "tmin": daily["temperature_2m_min"],
        "precip": daily["precipitation_sum"],
        "et0": daily["et0_fao_evapotranspiration"],
    })


def power_soil(region, start, end):
    """
    Root-zone soil wetness from NASA POWER, matching how the model was
    trained. Open-Meteo's soil moisture is deliberately not used here: it
    shifts level in 2025, which would feed the model features several
    standard deviations outside its training range.
    """
    url = (f"{POWER_URL}?parameters=GWETROOT&community=AG"
           f"&longitude={region['lon']}&latitude={region['lat']}"
           f"&start={start}&end={end}&format=JSON")
    series = fetch_json(url)["properties"]["parameter"]["GWETROOT"]
    rows = [
        {"date": pd.to_datetime(k, format="%Y%m%d"), "soil": v}
        for k, v in series.items()
        if v is not None and v > -100  # -999 is POWER's fill value
    ]
    return pd.DataFrame(rows)


def season_weather(region, harvest_year):
    """Sep(Y-1) .. Apr(Y), archive plus forecast where the archive stops short."""
    start = f"{harvest_year - 1}-09-01"
    end = f"{harvest_year}-04-30"

    url = (f"{ARCHIVE_URL}?latitude={region['lat']}&longitude={region['lon']}"
           f"&start_date={start}&end_date={end}&daily={DAILY_VARS}&timezone=UTC")
    df = to_frame(fetch_json(url)["daily"])

    needed_end = pd.Timestamp(f"{harvest_year}-04-30")
    covered = df.date.max() if not df.empty else None

    # ERA5 lags real time by ~5 days; for an in-progress season top up the
    # remainder from the forecast model so the stage windows aren't truncated.
    if covered is not None and covered < needed_end:
        fc = fetch_json(
            f"{FORECAST_URL}?latitude={region['lat']}&longitude={region['lon']}"
            f"&daily={DAILY_VARS}&past_days=92&forecast_days=16&timezone=UTC"
        )
        extra = to_frame(fc["daily"]).dropna()
        extra = extra[(extra.date > covered) & (extra.date <= needed_end)]
        if not extra.empty:
            df = pd.concat([df, extra], ignore_index=True)

    soil = power_soil(region,
                      f"{harvest_year - 1}0901",
                      f"{harvest_year}0430")
    df = df.merge(soil, on="date", how="left")

    return df.sort_values("date").reset_index(drop=True), covered


def season_oni(harvest_year):
    """
    Mean ONI across the Brazilian growing season, matching how the training
    table was built: OND/NDJ from the planting year, DJF/JFM/FMA from the
    harvest year. Returns None if NOAA has not published enough of the
    season yet.
    """
    text = fetch(ONI_URL, timeout=60).decode("utf-8", "replace")
    prev, cur = {"OND", "NDJ"}, {"DJF", "JFM", "FMA"}

    vals = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        seas, yr, _total, anom = parts
        try:
            yr, anom = int(yr), float(anom)
        except ValueError:
            continue
        if (yr == harvest_year - 1 and seas in prev) or (yr == harvest_year and seas in cur):
            vals.append(anom)

    if not vals:
        return None
    return sum(vals) / len(vals), len(vals)


def predict(model, harvest_year):
    blended, total_w, coverage = {}, 0.0, []

    for r in REGIONS:
        df, covered = season_weather(r, harvest_year)
        feats = stage_features(df, harvest_year)
        if feats is None:
            log(f"  {r['name']}: insufficient weather coverage, skipped")
            continue
        for k, v in feats.items():
            blended[k] = blended.get(k, 0.0) + v * r["weight"]
        total_w += r["weight"]
        coverage.append(covered)

    if not blended:
        return None
    blended = {k: v / total_w for k, v in blended.items()}

    oni = season_oni(harvest_year)
    if oni is None:
        log("  ONI unavailable for this season, skipped")
        return None
    blended["oni_season"], oni_months = oni

    trend = (model["trend"]["slope_kg_ha_per_year"] * harvest_year
             + model["trend"]["intercept"])

    x = [blended[f] for f in model["features"]]
    mean = model["scaler"]["mean"]
    scale = model["scaler"]["scale"]
    z = [(xi - m) / s for xi, m, s in zip(x, mean, scale)]

    resid = model["ridge"]["intercept"]
    for zi, c in zip(z, model["ridge"]["coef"]):
        resid += zi * c

    sigma = model["uncertainty"]["sigma_kg_ha"]
    return {
        "harvest_year": harvest_year,
        "trend_kg_ha": trend,
        "weather_effect_kg_ha": resid,
        "point_kg_ha": trend + resid,
        "range_68": [trend + resid - sigma, trend + resid + sigma],
        "range_95": [trend + resid - 1.96 * sigma, trend + resid + 1.96 * sigma],
        "features": {f: blended[f] for f in model["features"]},
        "weather_through": str(max(c for c in coverage if c is not None)) if coverage else None,
        # 5 = the full OND..FMA window; fewer means the season is still running.
        "oni_seasons_available": oni_months,
    }


def main():
    with open(MODEL, encoding="utf-8") as f:
        model = json.load(f)

    years = [int(a) for a in sys.argv[1:]] or [2025, 2026]

    log(f"model trained on {model['trained_years'][0]}-{model['trained_years'][1]} "
        f"({model['n_seasons']} seasons)")
    log(f"features: {', '.join(model['features'])}")
    log(f"out-of-sample sigma: +/-{model['uncertainty']['sigma_kg_ha']:.0f} kg/ha")
    log("")

    for year in years:
        log(f"=== harvest year {year} ===")
        res = predict(model, year)
        if res is None:
            log("  no prediction (weather unavailable)")
            continue
        log(f"  trend            {res['trend_kg_ha']:8.0f} kg/ha")
        log(f"  weather effect   {res['weather_effect_kg_ha']:+8.0f} kg/ha")
        log(f"  point estimate   {res['point_kg_ha']:8.0f} kg/ha")
        log(f"  68% range        {res['range_68'][0]:.0f} - {res['range_68'][1]:.0f}")
        log(f"  95% range        {res['range_95'][0]:.0f} - {res['range_95'][1]:.0f}")
        log(f"  weather through  {res['weather_through']}")
        log("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
