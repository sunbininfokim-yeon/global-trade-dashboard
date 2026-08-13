"""
Produce the India regional yield forecast the dashboard reads.

Usage: python3 -m india.run_forecast [season]

Run weekly from CI. Writes public/data/india_yield_forecast.json with, per
region-crop: the season's central estimate and interval, the trend and weather
components split apart, last published actual for comparison, and enough
provenance (which guide the methodology came from, what was substituted for
missing data, how much of the season is observed, measured skill) that a
number on screen can be judged rather than just believed.

Region-crops whose weather features do not beat a trend-only baseline are
still published, flagged `beats_trend: false` and given the trend's own error
as their band. Hiding a weak result would misrepresent which of these three
methodologies actually carries at this resolution -- and unlike the Brazilian
set, none of these three has yet been confirmed against real out-of-sample
data at the time this module was written; see india/README.md for the current
numbers before treating any of them as settled.

Where a crop is moved substantially by things that are not weather -- Bt
adoption and pink bollworm resistance for cotton, MSP-driven area shifts for
soybean, groundwater and procurement policy for wheat -- that is stated in
`provenance.non_weather_drivers` rather than left for the reader to infer from
a low skill score.
"""

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_dmi, load_oni
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "india_yield_forecast.json"))


def log(msg):
    print(f"[run] {msg}", flush=True)


def enso_label(oni):
    """NOAA's convention: +/-0.5 for El Nino / La Nina, +/-1.5 for strong."""
    if oni is None:
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


def iod_label(dmi):
    """
    Loosely following the range commonly used for Indian Ocean Dipole events
    (Saji & Yamagata 2003): a positive IOD tends to support the monsoon, a
    negative one to weaken it -- the opposite-signed partner to ENSO's effect
    on India, which is why the soybean guide asks for both together.
    """
    if dmi is None:
        return "unknown", None
    if dmi >= 0.4:
        return "positive IOD", dmi
    if dmi <= -0.4:
        return "negative IOD", dmi
    return "neutral", dmi


def main():
    override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    oni, dmi = load_oni(), load_dmi()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "India",
        "source_note": (
            "Yields: ICRISAT District Level Database, district level, "
            "aggregated to region by actual production / actual area. "
            "Weather: NASA POWER daily, area-weighted across each region's "
            "growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI. IOD: NOAA PSL HadISST Dipole Mode Index."),
        "methodology_note": (
            "One model per region-crop, each implementing the derived "
            "variables of its own guide in Regions/인도. Yield is a log "
            "technology trend plus a weather deviation; only the deviation is "
            "modelled. Skill is measured by forward chaining with the trend "
            "refit inside every fold, scored over the most recent folds. "
            "Each guide names an ML method (Random Forest, an ENSO-coupled "
            "LSTM, XGBoost) that the labelled record here -- roughly thirty "
            "seasons per region -- cannot support without fitting noise; the "
            "guide's own derived variables are computed in full and fed to "
            "the same ridge regression used throughout this repo instead. "
            "See each config's caveat below."),
        "regions": {},
    }

    skipped = []

    for cfg in ALL:
        # Kharif crops roll with the calendar; Rabi wheat rolls over in
        # November, ahead of its own sowing.
        season = override or current_season(cfg)
        r = predict_one(cfg, season, oni, dmi)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        enso_state, enso_val = enso_label(r["features"].get("oni_season"))
        iod_state, iod_val = iod_label(r["features"].get("dmi_season"))

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "crop": cfg.crop,
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": r["last_actual"],
            "enso": {"state": enso_state, "oni_growing_season": enso_val},
            "iod": {"state": iod_state, "dmi_growing_season": iod_val},
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on the most recent folds"),
                "skill_vs_trend_only": round(r["skill_vs_trend"], 3),
                "weather_skill": round(r["weather_skill"], 3),
                "weather_driven": bool(r["weather_skill"] > 0),
                "non_weather_features": r["non_weather_features"],
                "beats_trend": r["beats_trend"],
                "sigma_kg_ha": round(r["sigma"], 1),
            },
            "provenance": {
                "guide": r["doc"],
                "caveat": r["caveat"],
                "non_weather_drivers": r["non_weather_drivers"],
                "weather_through": r["weather_through"],
                "critical_window_observed": (
                    round(r["critical_window_observed"], 3)
                    if r["critical_window_observed"] is not None else None),
                "season_complete": r["season_complete"],
            },
        }
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{cfg.key:22} {r['point']:9,.0f} {r['unit']} "
            f"({r['weather_effect_pct']:+.1f}% weather){flag}")

    for key, why in skipped:
        log(f"{key:22} skipped -- {why}")
    payload["skipped"] = {k: w for k, w in skipped}

    if not payload["regions"]:
        log("nothing to write")
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
