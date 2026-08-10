"""Write the Indonesia forecast JSON consumed by the dashboard/data layer."""

import json
import os
import sys
from datetime import date, datetime, timezone

from .predict import predict_crop
from .region_db.build_palm_outlook import build_payload as build_palm_payload
from .region_db.palm_backtest import load_frames as load_palm_frames
from .regions import ALL


HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "indonesia_yield_forecast.json"))


def rounded_prediction(result):
    def one(target):
        publishable = target["forecast_gate"]["publishable"]
        return {
            "point": round(target["point"], 1) if publishable else None,
            "range_68": ([round(value, 1) for value in target["range_68"]]
                         if publishable else None),
            "range_95": ([round(value, 1) for value in target["range_95"]]
                         if publishable else None),
            "diagnostic_trend": round(target["trend"], 1),
            "weather_effect": (round(target["weather_effect"], 1)
                               if publishable else None),
            "sigma_used": round(target["sigma"], 1),
            "model_sigma": round(target["base_sigma"], 1),
            "forecast_gate": target["forecast_gate"],
            "climate_gate": target["climate_gate"],
        }

    return {name: one(target) for name, target in result["targets"].items()}


def palm_public_region(year):
    """Return the BPS CPO outlook in the dashboard's flat crop schema."""
    outlook = build_palm_payload()
    target = outlook["national"].get(str(year))
    if target is None:
        raise ValueError(f"CPO outlook is not available for {year}")

    national, _ = load_palm_frames()
    latest = national.sort_values("year").iloc[-1]
    mature_area = float(latest["mature_ha"])

    def per_hectare(values):
        if values is None:
            return None
        return [round(value / mature_area * 1000, 1) for value in values]

    production = {
        "point": target["point"],
        "range_68": target["range_68"],
        "range_95": target["range_95"],
        "diagnostic_trend": target["point"],
        "weather_effect": 0.0,
        "forecast_gate": {
            "publishable": True,
            "status": target["status"],
            "confidence": target["confidence"],
        },
        "climate_gate": outlook["climate_adjustment"],
    }
    yield_forecast = {
        "point": round(target["point"] / mature_area * 1000, 1),
        "range_68": per_hectare(target["range_68"]),
        "range_95": per_hectare(target["range_95"]),
        "diagnostic_trend": round(target["point"] / mature_area * 1000, 1),
        "weather_effect": 0.0,
        "forecast_gate": production["forecast_gate"],
        "climate_gate": production["climate_gate"],
    }
    area = {
        "point": round(mature_area, 1),
        "range_68": [round(mature_area, 1), round(mature_area, 1)],
        "range_95": [round(mature_area, 1), round(mature_area, 1)],
        "diagnostic_trend": round(mature_area, 1),
        "weather_effect": 0.0,
        "basis": "2024_BPS_mature_area_held_constant",
        "forecast_gate": production["forecast_gate"],
        "climate_gate": production["climate_gate"],
    }
    skill = target["backtest"]
    return {
        "label": "Indonesia crude palm oil (CPO)",
        "label_ko": "인도네시아 팜유(CPO)",
        "unit": "kg CPO/성숙면적 ha",
        "forecast_available": True,
        "headline": {"production_tonnes": production},
        "yield_kg_ha": yield_forecast,
        "area_ha": area,
        "production_crosscheck_tonnes": target["point"],
        "last_actual": {
            "year": int(latest["year"]),
            "yield": round(float(latest["mature_yield_t_ha"]) * 1000, 1),
            "area": round(mature_area, 1),
            "production": round(float(latest["total_cpo_tonnes"]), 1),
            "area_basis": "mature_area",
            "source_status": "BPS_final_2024",
        },
        "season_progress": {
            "type": "perennial_year_round_harvest",
            "climate_windows_complete": True,
            "observed_share": 1.0,
        },
        "weather_through": "2025-10-31",
        "skill": {
            "skill_vs_trend_only": round(skill["skill_vs_last_year"], 3),
            "baseline": "last_year",
            "mape": round(skill["mape"], 4),
            "baseline_mape": round(skill["baseline_last_year_mape"], 4),
            "forward_folds": skill["forward_folds"],
            "weather_applied": False,
            "low_confidence": target["confidence"] != "medium",
            "climate_gate": outlook["climate_adjustment"],
        },
        "crop_calendar": outlook["crop_calendar"],
        "regional_outlook": outlook["regions"],
        "climate_reference": outlook["climate_reference"].get(str(year)),
        "provenance": {
            "target": "CPO, not fresh fruit bunches (FFB)",
            "sources": outlook["sources"],
            "caveat_ko": target.get("caveat_ko", (
                "기후 변수는 추가 검증력을 보이지 않아 점 전망에 적용하지 않았다. "
                "지역 수치는 검증 관문을 통과한 곳만 예측하고 나머지는 관측 참고지역이다."
            )),
        },
    }


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
        if cfg.key == "indonesia_oil_palm":
            try:
                payload["regions"][cfg.key] = palm_public_region(year)
            except ValueError as exc:
                payload["skipped"][cfg.key] = str(exc)
            continue
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
            validation = target["validation"][target["configuration"]]
            skills[name] = {
                "skill_vs_trend_only": round(validation["skill_vs_trend"], 3),
                "detrended_r2": round(validation["detrended_r2"], 3),
                "forward_folds": validation["n_folds"],
                "weather_applied": target["beats_trend"],
                "feature_set": target["feature_set"],
                "features": target["features"],
                "trained_years": target["trained_years"],
                "low_confidence": validation["skill_vs_trend"] < 0.20,
                "climate_gate": target["climate_gate"],
                "forecast_gate": target["forecast_gate"],
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
