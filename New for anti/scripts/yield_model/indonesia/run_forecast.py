"""Write the Indonesia forecast JSON consumed by the dashboard/data layer."""

import json
import os
import sys
from datetime import date, datetime, timezone

from .predict import predict_crop
from .regions import ALL


HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "indonesia_yield_forecast.json"))


def rounded_prediction(result):
    def one(target):
        return {
            "point": round(target["point"], 1),
            "range_68": [round(value, 1) for value in target["range_68"]],
            "range_95": [round(value, 1) for value in target["range_95"]],
            "trend": round(target["trend"], 1),
            "weather_effect": round(target["weather_effect"], 1),
            "candidate_weather_effect": round(target["candidate_weather_effect"], 1),
            "sigma_used": round(target["sigma"], 1),
            "model_sigma": round(target["base_sigma"], 1),
        }

    return {name: one(target) for name, target in result["targets"].items()}


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": year, "country": "Indonesia",
        "methodology": (
            "FAOSTAT national yield/area/production trend plus NASA POWER climate "
            "deviations from a leak-free prior-20-year normal. Ridge strength is "
            "selected inside each training fold; skill is forward-chained against "
            "a trend-only baseline. Weak weather models publish the trend, not an "
            "unvalidated climate adjustment."),
        "regions": {}, "skipped": {},
    }
    for cfg in ALL:
        result = predict_crop(cfg, year)
        if "error" in result:
            payload["skipped"][cfg.key] = result["error"]
            continue
        targets = rounded_prediction(result)
        skills = {}
        model_path = os.path.join(HERE, "models", cfg.key + ".json")
        with open(model_path, encoding="utf-8") as handle:
            model = json.load(handle)
        for name, target in model["targets"].items():
            validation = target["validation"][target["feature_set"]]
            skills[name] = {
                "skill_vs_trend_only": round(validation["skill_vs_trend"], 3),
                "detrended_r2": round(validation["detrended_r2"], 3),
                "forward_folds": validation["n_folds"],
                "weather_applied": target["beats_trend"],
                "feature_set": target["feature_set"],
                "features": target["features"],
                "trained_years": target["trained_years"],
                "low_confidence": validation["skill_vs_trend"] < 0.20,
            }
        payload["regions"][cfg.key] = {
            "label": cfg.label, "label_ko": cfg.label_ko,
            "headline": {"production_tonnes": targets.get("production")},
            "yield_kg_ha": targets.get("yield"),
            "area_ha": targets.get("area"),
            "production_crosscheck_tonnes": (
                round(result["production_crosscheck_tonnes"], 1)
                if result["production_crosscheck_tonnes"] is not None else None),
            "last_actual": result["last_actual"],
            "season_progress": result["season_progress"],
            "weather_through": result["weather_through"],
            "skill": skills,
            "provenance": {"guide": cfg.doc, "caveat": cfg.caveat,
                           "non_weather_drivers": cfg.non_weather_drivers},
        }

    if not payload["regions"]:
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print("[indonesia:run] wrote " + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

