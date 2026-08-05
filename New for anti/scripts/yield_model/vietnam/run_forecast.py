"""
Write public/data/vietnam_yield_forecast.json for the dashboard.

Usage: python3 -m vietnam.run_forecast [season]

DATA_LAYOUT: flat regions[key] with crops nest optional; uses common fields
point, range_*, skill.*, last_actual, labels provisional flag in provenance.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_oni
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "vietnam_yield_forecast.json"))


def log(msg):
    print(f"[run] {msg}", flush=True)


def enso_label(oni):
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
    season = override or current_season()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "country": "Vietnam",
        "forecast_available": True,
        "source_note": (
            "Weather: NASA POWER daily (GWETROOT, TEMP, precip, radiation), "
            "ET0 FAO-56. ENSO: NOAA CPC ONI. "
            "Mekong WS labels: GSO Yearbook Mekong-region spring paddy "
            "(2018–2023) + MTN provincial Đông Xuân (2017/2024); pre-2017 "
            "FAOSTAT national rice scaled to WS overlap (season imperfect). "
            "Coffee/RRD still provisional unless labels_official override. "
            "Salinity: coastal distance × dry-season hydrology proxy (not EC). "
            "GEE CHIRPS/SMAP/S1 and MRC discharge not executed in this build."),
        "methodology_note": (
            "T1 models from Regions/베트남 master: Mekong WS rice "
            "(salt/ENSO), Central Highlands robusta (WD_eff + Kath), "
            "Red River rice (flood/typhoon rain proxy). Ridge on log-yield "
            "residual vs trend; read labels_provisional / "
            "labels_season_imperfect on each region."),
        "regions": {},
    }

    # ONI for season note
    from .collect import oni_djf
    enso_name, enso_val = enso_label(oni_djf(oni, season))
    payload["climate_context"] = {
        "oni_djf": enso_val,
        "enso": enso_name,
    }

    any_ok = False
    for cfg in ALL:
        target = override or current_season(cfg)
        r = predict_one(cfg, target, oni)
        if not r or "error" in r:
            if r and "error" in r:
                log(f"{cfg.key}: {r['error']}")
            continue
        any_ok = True
        low_conf = (not r["beats_trend"]) or r.get("labels_provisional", True)
        payload["regions"][cfg.key] = {
            "label": r["label"],
            "label_ko": r["label_ko"],
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1),
                         round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1),
                         round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": {
                "year": r["last_actual"]["year"],
                "yield": round(r["last_actual"]["yield"], 1),
                "provisional": r.get("labels_provisional", True),
            },
            "skill": {
                "beats_trend": r["beats_trend"],
                "recent_skill_vs_trend": r["skill_vs_trend"],
                "low_confidence": low_conf,
                "sigma_kg_ha": r["sigma"],
            },
            "weather_through": r["weather_through"],
            "critical_window_observed": r.get("critical_window_observed"),
            "season_complete": r.get("season_complete"),
            "provenance": {
                "doc": r["doc"],
                "caveat": r["caveat"],
                "non_weather_drivers": r.get("non_weather_drivers", ""),
                "label_source": r.get("label_source", ""),
                "labels_provisional": r.get("labels_provisional", True),
                "labels_season_imperfect": r.get("labels_season_imperfect", False),
                "salinity_is_proxy": True,
                "gee_used": False,
            },
            "crops": {
                cfg.crop: {
                    "label_ko": r["label_ko"],
                    "unit": r["unit"],
                    "point": round(r["point"], 1),
                    "range_68": [round(r["range_68"][0], 1),
                                 round(r["range_68"][1], 1)],
                    "range_95": [round(r["range_95"][0], 1),
                                 round(r["range_95"][1], 1)],
                    "skill": {
                        "beats_trend": r["beats_trend"],
                        "low_confidence": low_conf,
                    },
                }
            },
        }
        log(f"{cfg.key}: {r['point']:.0f} kg/ha "
            f"(skill {r['skill_vs_trend']:+.0%}, provisional="
            f"{r.get('labels_provisional')})")

    if not any_ok:
        payload["forecast_available"] = False
        payload["unavailable_reason"] = (
            "No trained models; run vietnam.collect && vietnam.train first.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
