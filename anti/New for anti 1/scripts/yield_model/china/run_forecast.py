"""
Produce the China forecast the dashboard reads.

Usage: python3 -m china.run_forecast [season]

Writes public/data/china_yield_forecast.json in the same shape as the Brazil
payload, so the frontend work is mechanical.

Every one of the six models is published even though none of them beats a
trend-only baseline. Hiding them would misrepresent the result, which is
itself the most useful thing this pipeline found: the national USDA/FAOSTAT
series these models are scored against move so little year to year -- Chinese
rice yield by 1.6% a year against 24.5% for a Brazilian state -- that there is
almost no weather residual left to explain. That is a statement about the
available labels, not about whether weather moves Chinese crops.

So each region carries `beats_trend: false`, a band taken from the trend's own
error, and `presentation: "trend extrapolation"` to say in one field what the
number should be read as.
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
    HERE, "..", "..", "..", "public", "data", "china_yield_forecast.json"))


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
        "country": "China",
        "source_note": (
            "Targets: USDA PSD (grains, oilseeds) and FAOSTAT (vegetables), "
            "both national. China's own statistical bureau blocks automated "
            "access, so province-level official yields are unavailable and "
            "every guide's regional question is answered against a national "
            "series. Weather: NASA POWER daily, production-weighted across "
            "each region's growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI."),
        "methodology_note": (
            "One model per guide in Regions/중국. Yield is a log technology "
            "trend plus a weather deviation; only the deviation is modelled. "
            "Skill is measured by forward chaining with the trend refit inside "
            "every fold."),
        "headline_finding": (
            "None of the six models beats a trend-only baseline out of "
            "sample. The national targets carry very little year-to-year "
            "movement to explain -- 1.6% for rice, 3.7% for wheat, against "
            "24.5% for a Brazilian state soybean series -- because "
            "aggregating a continent cancels regional weather and because the "
            "PSD series is an estimate rather than a survey measurement. "
            "Every number below should be read as a trend extrapolation."),
        "regions": {},
    }

    skipped = []

    for cfg in ALL:
        season = override or current_season(cfg)
        r = predict_one(cfg, season, oni)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        label, value = enso_label(r["features"].get("oni_season"))

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "target_label": r["target_label"],
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": r["last_actual"],
            # One field the frontend can branch on without reasoning about
            # skill numbers.
            "presentation": ("weather-driven forecast" if r["beats_trend"]
                             else "trend extrapolation"),
            "enso": {"state": label, "oni_growing_season": value},
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on the most recent folds"),
                "skill_vs_trend_only": round(r["skill_vs_trend"], 3),
                "weather_skill": round(r["weather_skill"], 3),
                "weather_driven": bool(r["weather_skill"] > 0),
                "non_weather_features": r["non_weather_features"],
                "beats_trend": r["beats_trend"],
                "sigma": round(r["sigma"], 1),
                "sigma_unit": r["unit"],
                "uncertainty_basis": r["uncertainty_basis"],
            },
            "provenance": {
                "guide": r["doc"],
                "label_source": r["label_source"],
                # The ceiling on this model regardless of methodology.
                "region_share": r["region_share"],
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
        flag = "" if r["beats_trend"] else "  [trend extrapolation]"
        log(f"{cfg.key:24} {r['point']:11,.0f} {r['unit']:>8} "
            f"({r['weather_effect_pct']:+.1f}% weather){flag}")

    for key, why in skipped:
        log(f"{key:24} skipped -- {why}")
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
