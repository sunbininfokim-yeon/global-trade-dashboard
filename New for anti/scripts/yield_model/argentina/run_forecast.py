"""
Produce the Argentina regional yield forecast the dashboard reads.

Usage: python3 -m argentina.run_forecast [season]

Writes public/data/argentina_yield_forecast.json with, per region-crop: the
season's central estimate and interval, the trend and weather components split
apart, the last published actual for comparison, and enough provenance (which
guide the methodology came from, what was substituted for missing data, how
much of the season is observed, measured skill) that a number on screen can be
judged rather than just believed.

Region-crops whose weather features do not beat a trend-only baseline are still
published, flagged `beats_trend: false` and given the trend's own error as
their band. Hiding them would misrepresent which of the six methodologies
actually carries at this resolution.

Two fields exist here that the Brazil payload has no use for:

  - `enso.iod_spring` and the shock flag, because 팜파스/옥수수 §2A's claim is
    specifically about the conjunction of a La Niña with a positive dipole, and
    a reader should be able to see whether that conjunction is live.
  - `abandonment`, the mean share of sown area written off before harvest.
    Argentine yield is computed over harvested area, so a drought severe enough
    to destroy fields partly removes itself from the target. Publishing the
    abandonment rate alongside the yield is what stops a reader from mistaking
    "yield held up" for "the crop was fine".
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
    HERE, "..", "..", "..", "public", "data", "argentina_yield_forecast.json"))


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


def main():
    override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    oni, dmi = load_oni(), load_dmi()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "Argentina",
        "source_note": (
            "Yields: MAGyP Estimaciones Agrícolas, department level, "
            "aggregated as sum(production)/sum(harvested area). "
            "Weather: NASA POWER daily, production-weighted across each "
            "region's growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI. IOD: NOAA PSL HadISST DMI."),
        "methodology_note": (
            "One model per region-crop, each implementing the derived "
            "variables of its own guide in Regions/아르헨티나. Yield is a log "
            "technology trend plus a weather deviation; only the deviation is "
            "modelled. Skill is measured by forward chaining with the trend "
            "refit inside every fold, scored over the most recent folds. "
            "Yield is measured over harvested area, so seasons with heavy "
            "abandonment understate the damage -- see `abandonment`."),
        "regions": {},
    }

    predicted = {}
    skipped = []

    for cfg in ALL:
        # Resolved per crop: in August, wheat is a standing crop and the summer
        # crops are not yet sown, so they are not on the same harvest year.
        season = override or current_season(cfg)
        prior = predict_one(cfg, season - 1, oni, dmi, predicted)
        if prior and "error" not in prior:
            predicted[season - 1] = prior["point"]

        r = predict_one(cfg, season, oni, dmi, predicted)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        label, value = enso_label(r.get("oni"))
        iod = r.get("iod")

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "crop": cfg.crop,
            "provinces": cfg.provinces,
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": r["last_actual"],
            "enso": {
                "state": label,
                "oni_growing_season": value,
                "iod_spring": round(iod, 3) if iod is not None else None,
                # The guide's own conjunction, surfaced so a reader can see
                # whether the shock condition is actually live this season.
                "la_nina_positive_iod": bool(
                    value is not None and iod is not None
                    and value < -0.5 and iod > 0.4),
            },
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
                "notes": r["notes"],
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
