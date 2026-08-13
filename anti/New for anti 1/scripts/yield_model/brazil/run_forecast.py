"""
Produce the Brazil regional yield forecast the dashboard reads.

Usage: python3 -m brazil.run_forecast [season]

Run weekly from CI. Writes public/data/brazil_yield_forecast.json with, per
region-crop: the season's central estimate and interval, the trend and weather
components split apart, last published actual for comparison, and enough
provenance (which guide the methodology came from, what was substituted for
missing data, how much of the season is observed, measured skill) that a
number on screen can be judged rather than just believed.

Region-crops whose weather features do not beat a trend-only baseline are
still published, flagged `beats_trend: false` and given the trend's own error
as their band. Hiding them would misrepresent which of the nine methodologies
actually carries at this resolution.

Where a crop is moved substantially by things that are not weather -- the
ratoon age profile of a cane plantation, coffee's biennial bearing, an
acreage split between first-season and safrinha corn -- that is stated in
`provenance.non_weather_drivers` rather than left for the reader to infer from
a low skill score. A weather model failing on a crop that weather does not
drive is a correct result, and it should read as one.
"""

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_oni
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "brazil_yield_forecast.json"))


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
    oni = load_oni()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "Brazil",
        "source_note": (
            "Yields: IBGE SIDRA (PAM tables 1612/1613), state level. "
            "Weather: NASA POWER daily, production-weighted across each "
            "region's growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI."),
        "methodology_note": (
            "One model per region-crop, each implementing the derived "
            "variables of its own guide in Regions/브라질. Yield is a log "
            "technology trend plus a weather deviation; only the deviation is "
            "modelled. Skill is measured by forward chaining with the trend "
            "refit inside every fold, scored over the most recent folds."),
        "regions": {},
    }

    predicted = {}
    skipped = []

    for cfg in ALL:
        # Season is resolved per crop: the summer crops roll over in September,
        # wheat with the calendar, so in October they are not all on the same
        # harvest year.
        season = override or current_season(cfg)
        # The prior season first, so coffee's biennial lag has something to
        # stand on where SIDRA has not published yet.
        prior = predict_one(cfg, season - 1, oni, predicted)
        if prior and "error" not in prior:
            predicted[season - 1] = prior["point"]

        r = predict_one(cfg, season, oni, predicted)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        label, value = enso_label(r["features"].get("oni_season"))

        # IBGE finalises PAM municipal data slowly -- typically well over a
        # year after harvest -- so the "last actual" season is routinely one
        # or more years behind the season being forecast. That gap is normal
        # publication lag, not a missing pipeline step, but it should say so
        # explicitly rather than let a 2024 figure sit next to a 2026 forecast
        # with no explanation of why 2025 is absent.
        expected_year = season - 1
        published_year = r["last_actual"]["year"]
        gap = expected_year - published_year
        r["last_actual"]["sidra_current"] = gap <= 0
        r["last_actual"]["note"] = (
            None if gap <= 0 else
            (f"IBGE has not yet published {published_year + 1}"
             + (f"-{expected_year}" if gap > 1 else "")
             + f"; {published_year} is the latest season SIDRA has released "
               f"as of this run."))

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "crop": cfg.crop,
            "states": [uf for uf, _ in cfg.states],
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": r["last_actual"],
            "enso": {"state": label, "oni_growing_season": value},
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on the most recent folds"),
                "skill_vs_trend_only": round(r["skill_vs_trend"], 3),
                # Skill left once the non-weather features (lags) are held out.
                # This, not the headline number, is what a climate panel may
                # claim: São Paulo cane scores +8.2% overall but -3.1% on
                # weather alone, because lag1 is carrying stand persistence.
                "weather_skill": round(r["weather_skill"], 3),
                "weather_driven": bool(r["weather_skill"] > 0),
                "non_weather_features": r["non_weather_features"],
                # Ranked standardised effects (feature, % yield per 1 SD),
                # every feature the model uses, weather and non-weather
                # alike. The point: when weather_skill is low, the reader
                # should see exactly what IS carrying the model instead of
                # being told only what isn't.
                "top_effects": r["top_effects"],
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

    published_years = [r["last_actual"]["year"]
                       for r in payload["regions"].values()]
    if published_years:
        payload["sidra_latest_published_year"] = max(published_years)

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
