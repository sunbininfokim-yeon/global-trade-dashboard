"""
Produce the France regional yield forecast the dashboard reads.

Usage: python3 -m france.run_forecast [season]

Same payload as india.run_forecast (public/data/france_yield_forecast.json):
per region-crop the season's estimate and interval, trend and weather split,
last published actual, provenance and measured skill. Region-crops that do
not beat a trend-only baseline are still published, flagged, with the
trend's own error as their band.
"""

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_nao, load_oni
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))

# Seasons between the last published label and the forecast season beyond
# which the figure is shown as low confidence regardless of backtest skill.
MAX_LABEL_GAP = 3
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "france_yield_forecast.json"))


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


def nao_label(nao):
    """Winter NAO phase, +/-0.5 as the usual cut for a clear phase."""
    if nao is None:
        return "unknown", None
    if nao >= 0.5:
        return "positive NAO", nao
    if nao <= -0.5:
        return "negative NAO", nao
    return "neutral", nao


def main():
    override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    oni, nao = load_oni(), load_nao()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "France",
        "source_note": (
            "Yields: Eurostat apro_cpshr (NUTS 2, EU standard humidity), "
            "area-weighted across each region's NUTS 2 units. "
            "Weather: NASA POWER daily, area-weighted across each region's "
            "growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI. NAO: NOAA CPC monthly index."),
        "methodology_note": (
            "Same method as the India and Brazil models: yield is a log "
            "technology trend plus a weather deviation; only the deviation is "
            "modelled, with ridge regression on features fixed before "
            "training. Skill is measured by forward chaining with the trend "
            "refit inside every fold, scored over the most recent folds."),
        "regions": {},
    }

    skipped = []

    for cfg in ALL:
        # Maize rolls with the calendar; winter wheat rolls over in
        # September, ahead of its own sowing.
        season = override or current_season(cfg)
        r = predict_one(cfg, season, oni, nao)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        enso_state, enso_val = enso_label(r["features"].get("oni_season"))
        nao_state, nao_val = nao_label(r["features"].get("nao_season"))

        # A forecast extrapolated many seasons past the last published
        # label is a trend guess however good the backtest was.
        label_year = (r["last_actual"] or {}).get("year")
        label_gap = season - label_year if label_year else None
        stale_label = label_gap is not None and label_gap > MAX_LABEL_GAP

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
            "model_weather_effect_pct": round(r["model_weather_effect_pct"], 2),
            "point_basis": r["point_basis"],
            "features_filled": r["features_filled"],
            "last_actual": r["last_actual"],
            "enso": {"state": enso_state, "oni_growing_season": enso_val},
            "nao": {"state": nao_state, "nao_season": nao_val},
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on the most recent folds"),
                "skill_vs_trend_only": round(r["skill_vs_trend"], 3),
                "weather_skill": round(r["weather_skill"], 3),
                "weather_driven": bool(r["weather_skill"] > 0),
                "non_weather_features": r["non_weather_features"],
                "beats_trend": r["beats_trend"],
                "low_confidence": bool((not r["beats_trend"])
                                       or r["skill_vs_trend"] < 0.20
                                       or stale_label),
                "label_through": label_year,
                "stale_label": stale_label,
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
