"""
Write the dashboard forecast payload for Ukraine winter wheat.

Usage: python3 -m ukraine.run_forecast [season]

Output: public/data/ukraine_yield_forecast.json  (DATA_LAYOUT contract)

Skipped until models exist; publishes forecast_available=false skeletons when
predict returns errors.
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
    HERE, "..", "..", "..", "public", "data", "ukraine_yield_forecast.json"))


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

    wheat = [c for c in ALL if "wheat" in c.key]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "Ukraine",
        "source_note": (
            "Target: SSSU/Ukrstat oblast wheat yield, sown-area-weighted by "
            "zone (Central / Southern / Western). Train ≤2021; Crimea/"
            "Donetsk/Luhansk excluded. War area/abandonment is a separate "
            "layer. Weather: NASA POWER + GWETROOT; Open-Meteo T/P only."
        ),
        "methodology_note": (
            "Log technology trend + ridge weather residual. Skill from "
            "forward chaining with trend refit inside each fold. Features: "
            "autumn recharge, winterkill proxies, April GWETROOT, spring "
            "precip, grain-fill EDD. Shipping black_sea routes not mixed in."
        ),
        "regions": {},
    }

    skipped = []
    for cfg in wheat:
        season = override or current_season(cfg)
        r = predict_one(cfg, season, oni)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            payload["regions"][cfg.key] = {
                "label": cfg.label,
                "label_ko": cfg.label_ko,
                "forecast_available": False,
                "reason_ko": "모델 없음 — 2015–2021 라벨만 있어 min_train 미달 (pre-2015 아카이브 필요)",
                "season": season,
                "unit": cfg.target_unit,
            }
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            payload["regions"][cfg.key] = {
                "label": cfg.label,
                "label_ko": cfg.label_ko,
                "forecast_available": False,
                "reason_ko": r["error"],
                "season": season,
                "unit": cfg.target_unit,
            }
            continue

        skill_vs = r["skill_vs_trend"]
        low_conf = (not r["beats_trend"]) or (skill_vs is not None and skill_vs < 0.20)
        label_enso, oni_val = enso_label(r["features"].get("oni_season"))
        share = r.get("critical_window_observed")

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "label_ko": r["label_ko"],
            "target_label": r["target_label"],
            "forecast_available": True,
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect": round(r["weather_effect"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": {
                "year": r["last_actual"]["year"],
                "yield": r["last_actual"]["yield"],
            },
            "season_progress": r.get("season_progress"),
            "presentation": ("weather-driven forecast" if r["beats_trend"]
                             else "trend extrapolation"),
            "enso": {"state": label_enso, "oni_growing_season": oni_val},
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on recent folds"),
                "skill_vs_trend_only": round(skill_vs, 3) if skill_vs is not None else None,
                "weather_skill": round(r["weather_skill"], 3),
                "detrended_r2": None,
                "beats_trend": bool(r["beats_trend"]),
                "low_confidence": bool(low_conf),
                "sigma_used": round(r["sigma_used"], 1),
                "model_sigma": round(r["sigma"], 1),
                "sigma": round(r["sigma_used"], 1),
                "sigma_unit": r["unit"],
                "train_window_years": None,
                "uncertainty_basis": r["uncertainty_basis"],
            },
            "trained_years": r.get("trained_years"),
            "provenance": {
                "guide": r["doc"],
                "label_source": r["label_source"],
                "region_share": r["region_share"],
                "caveat": r["caveat"],
                "non_weather_drivers": r["non_weather_drivers"],
                "weather_through": r["weather_through"],
                "critical_window_observed": (
                    round(share, 3) if share is not None else None),
                "season_complete": r["season_complete"],
                "notes": r["notes"],
            },
        }
        flag = "" if r["beats_trend"] else "  [trend extrapolation]"
        log(f"{cfg.key:28} {r['point']:11,.0f} kg/ha "
            f"({r['weather_effect_pct']:+.1f}% weather){flag}")

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
