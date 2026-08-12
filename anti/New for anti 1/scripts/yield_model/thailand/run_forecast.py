"""
Write public/data/thailand_yield_forecast.json for the dashboard.

Usage: PYTHONPATH=. python3 -m thailand.run_forecast [season]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_oni, oni_djf
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "thailand_yield_forecast.json"))


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
        "country": "Thailand",
        "forecast_available": True,
        "source_note": (
            "Weather: NASA POWER daily (GWETROOT, TEMP, precip), ET0 FAO-56. "
            "ENSO: NOAA CPC ONI. Labels: FAOSTAT Thailand national Yield "
            "(Sugar cane / Rice / Natural rubber) unless labels_official "
            "override. RID Bhumibol–Sirikit Nov-1 storage NOT wired — "
            "off-season rice uses dam_recharge_proxy only. "
            "OAE wet/dry rice split and OCSB province cane not wired. "
            "Isan cassava is T2 stub (CMD disease-primary)."),
        "methodology_note": (
            "T1 from Regions/태국 + peer-reviewed Thai sources (see SOURCES.md): "
            "Central–NE sugarcane (SM/SPI/ENSO), Chao Phraya wet rice "
            "(onset/ENSO), Chao Phraya off-season rice (dam PROXY + heat), "
            "rubber (rainy/tapping days). Ridge on log-yield residual vs "
            "tech trend; read labels_season_imperfect / dam_storage_is_proxy."),
        "regions": {},
    }

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
        low_conf = (
            (not r["beats_trend"])
            or r.get("labels_provisional", True)
            or r.get("labels_season_imperfect", False)
            or r.get("dam_storage_is_proxy", False)
            or r.get("weather_withheld_incomplete_season", False)
        )
        # Off-season dam proxy: still emit point but always low_confidence
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
                "dam_storage_is_proxy": r.get("dam_storage_is_proxy", False),
                "weather_withheld_incomplete_season": r.get(
                    "weather_withheld_incomplete_season", False),
                "rid_dam_wired": False,
                "gee_used": False,
                "sources": r.get("sources", []),
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
            f"(skill {r['skill_vs_trend']:+.0%}, low_conf={low_conf})")

    # Cassava reference stub entry (no fake point)
    payload["regions"]["isan_cassava"] = {
        "label": "Isan cassava (reference)",
        "label_ko": "이산 카사바",
        "unit": "kg/ha",
        "point": None,
        "forecast_available": False,
        "panel_mode": "reference",
        "unavailable_reason": (
            "Cassava Mosaic Disease (CMD) / whitefly dominates recent Isan "
            "supply risk; weather-only yield model withheld."),
        "provenance": {
            "doc": "Regions/태국/북동부_이산/카사바",
            "sources": [
                "Regions cassava guide — CMD mechanism",
                "OAE cassava statistics (not wired as climate yield)",
            ],
        },
        "crops": {
            "cassava": {
                "label_ko": "카사바",
                "point": None,
                "skill": {"low_confidence": True, "beats_trend": False},
            }
        },
    }

    if not any_ok:
        payload["forecast_available"] = False
        payload["unavailable_reason"] = (
            "No trained models; run thailand.collect && thailand.train first.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
