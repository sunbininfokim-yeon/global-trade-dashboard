"""
Produce the yield forecast the dashboard reads.

Run weekly from CI. Writes public/data/yield_forecast.json with, per crop:
the current season's central estimate and interval, the trend and weather
components, last season's actual for comparison, and enough provenance
(how much of the season is observed vs forecast, which ENSO state, when the
model was trained and how well it scored) that the number on screen can be
judged rather than just believed.
"""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "public", "data", "yield_forecast.json"))

from collect_us_cornbelt import load_oni, growing_season_oni  # noqa: E402
from predict_us import predict  # noqa: E402


def log(msg):
    print(f"[run] {msg}", flush=True)


def enso_label(oni):
    """NOAA's convention: +/-0.5 for El Nino / La Nina, +/-1.5 for strong."""
    if oni is None or pd.isna(oni):
        return "unknown", None
    if oni >= 1.5:
        return "strong El Nino", oni
    if oni >= 0.5:
        return "El Nino", oni
    if oni <= -1.5:
        return "strong La Nina", oni
    if oni <= -0.5:
        return "La Nina", oni
    return "neutral", oni


def last_actual(crop):
    """Most recent observed season, for a like-for-like comparison on screen."""
    path = os.path.join(HERE, f"us_{crop}_training.csv")
    df = pd.read_csv(path).sort_values("year")
    row = df.iloc[-1]
    return {"year": int(row.year), "yield": float(row["yield"])}


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc).year

    oni = growing_season_oni(load_oni(), year)
    label, value = enso_label(oni)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": year,
        "region": "US Corn Belt",
        "region_note": "8 states, production-weighted: IA IL NE MN IN OH MO SD",
        "enso": {"state": label, "oni_growing_season": value},
        "crops": {},
    }

    for crop in ("corn", "soybeans"):
        r = predict(crop, year)
        if r is None:
            log(f"{crop}: no forecast produced")
            continue

        with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
            model = json.load(f)
        fwd = model["validation"].get("core_forward") or model["validation"].get("all_forward", {})

        payload["crops"][crop] = {
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect": round(r["weather_effect"], 1),
            "last_actual": last_actual(crop),
            "season_progress": {
                "julaug_days": r["julaug_days"],
                "observed_share": round(r["observed_share"], 3),
            },
            "skill": {
                "method": "forward-chaining, trend refit inside each fold",
                "skill_vs_trend_only": round(fwd.get("skill_vs_trend", float("nan")), 3),
                "detrended_r2": round(fwd.get("detrended_r2", float("nan")), 3),
                "sigma_used": round(r["sigma"], 2),
                "model_sigma": round(r["base_sigma"], 2),
            },
            "trained_years": model["trained_years"],
        }
        log(f"{crop}: {r['point']:.1f} {r['unit']} "
            f"({r['range_68'][0]:.1f}-{r['range_68'][1]:.1f} at 68%)")

    if not payload["crops"]:
        log("nothing to write")
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
