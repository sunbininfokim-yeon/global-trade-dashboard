"""Generate the South African maize dashboard forecast payload."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .regions import BELT_KEY, POINTS

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
MODELS = HERE / "models"
OUT = HERE.parents[2] / "public" / "data" / "south_africa_yield_forecast.json"


def predict(year: int = None) -> dict:
    year = year or date.today().year
    with (MODELS / f"{BELT_KEY}.json").open(encoding="utf-8") as handle:
        model = json.load(handle)
    frame = pd.read_csv(TRAINING / f"{BELT_KEY}.csv")
    row = frame[frame.year == year]
    if row.empty:
        raise ValueError(f"No climate features for harvest year {year}")
    row = row.iloc[0]

    features = model["selected_features"]
    x = np.asarray([row[name] for name in features], dtype=float)
    if np.isnan(x).any():
        raise ValueError("Forecast climate anomalies are incomplete")
    component_results = []
    for component in model["components"]:
        trend_log = float(np.polyval(component["trend"]["log_poly_coef"], year))
        trend_component = float(np.exp(trend_log))
        z = (x - np.asarray(component["scaler"]["mean"])) / np.asarray(
            component["scaler"]["scale"]
        )
        weather_log = float(
            component["ridge"]["intercept"]
            + z @ np.asarray(component["ridge"]["coef"])
        )
        component_results.append(
            {
                "name": component["name"],
                "trend": trend_component,
                "point": float(np.exp(trend_log + weather_log)),
            }
        )
    trend = float(np.mean([item["trend"] for item in component_results]))
    point = float(np.mean([item["point"] for item in component_results]))
    if model["operational_choice"] == "trend_ensemble_only":
        point = trend
    q68 = model["uncertainty"]["q68_kg_ha"]
    q95 = model["uncertainty"]["q95_kg_ha"]
    last = frame[(frame.target_status == "final") & frame.yield_kg_ha.notna()].iloc[-1]
    cec = frame[(frame.year == year) & (frame.target_status == "cec_estimate")]
    cec_outlook = None
    if not cec.empty:
        cec_row = cec.iloc[0]
        cec_outlook = {
            "season": cec_row.season_label,
            "yield_kg_ha": round(float(cec_row.yield_kg_ha), 1),
            "production_t": round(float(cec_row.production_t), 0),
            "area_ha": round(float(cec_row.area_ha), 0),
            "status": "CEC estimate; excluded from model training",
        }

    area_ha = float(cec.iloc[0].area_ha) if not cec.empty else float(last.area_ha)
    production = {
        "unit": "metric_tons",
        "area_ha": round(area_ha, 0),
        "area_source": "CEC planted area; production estimate excluded from model",
        "point": round(point * area_ha / 1000.0, 0),
        "range_68": [
            round(max(0, point - q68) * area_ha / 1000.0, 0),
            round((point + q68) * area_ha / 1000.0, 0),
        ],
        "range_95": [
            round(max(0, point - q95) * area_ha / 1000.0, 0),
            round((point + q95) * area_ha / 1000.0, 0),
        ],
    }

    crop = {
        "label_ko": "옥수수",
        "unit": "kg/ha",
        "point": round(point, 1),
        "range_68": [round(max(0, point - q68), 1), round(point + q68, 1)],
        "range_95": [round(max(0, point - q95), 1), round(point + q95, 1)],
        "trend": round(trend, 1),
        "weather_effect": round(point - trend, 1),
        "weather_effect_pct": round((point / trend - 1) * 100, 2),
        "last_actual": {"year": int(last.year), "yield": round(last.yield_kg_ha, 1)},
        "season_progress": {
            "critical_days": {"observed": 59, "forecast": 0, "climatology": 0},
            "observed_share": 1.0,
            "weather_window": f"{year - 1}-10-01 through {year}-02-28",
        },
        "skill": {
            "method": "forward chaining; log trend refit inside every fold",
            "skill_vs_trend_only": round(model["skill"]["skill_vs_trend"], 3),
            "detrended_r2": round(model["skill"]["detrended_r2"], 3),
            "evaluation_period": model["skill"]["evaluation_period"],
            "holdout_folds": model["skill"]["n_folds"],
            "beats_trend": model["beats_trend"],
            "low_confidence": model["low_confidence"],
            "operational_choice": model["operational_choice"],
            "selected_feature_set": model["selected_feature_set"],
            "sigma_used": round(q68, 1),
            "model_warnings": model.get("model_warnings", []),
            "challengers": model.get("challengers", {}),
        },
        "trained_years": model["trained_years"],
        "government_outlook": cec_outlook,
        "production": production,
        "trend_components": [
            {
                "name": item["name"],
                "trend": round(item["trend"], 1),
                "point": round(item["point"], 1),
            }
            for item in component_results
        ],
        "diagnostics": {
            name: round(float(row[name]), 3)
            for name in model["selected_features"]
        },
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": year,
        "country": "South Africa",
        "forecast_available": True,
        "source_note": (
            "Commercial maize yield labels: Crop Estimates Committee via SAGIS. "
            "Climate: Google Earth Engine CHIRPS daily precipitation and "
            "ERA5-Land daily temperature, VPD and 0-100 cm soil moisture."
        ),
        "methodology_note": (
            "A national commercial-maize yield target is paired with a fixed, "
            "mean-2023-2025-production-weighted six-location climate proxy over "
            "Free State, North West and Mpumalanga. Feature selection stops in "
            "2015; 2016-2025 is an untouched holdout. Full-history and rolling-20 "
            "trend forecasts are equally weighted. The current CEC estimate is "
            "shown only as an external comparison and is excluded from training."
        ),
        "regions": {
            BELT_KEY: {
                "label": "South Africa commercial maize belt",
                "label_ko": "남아공 상업용 옥수수 벨트",
                "note": "Free State · North West · Mpumalanga climate proxy",
                "provinces": list(dict.fromkeys(point["province"] for point in POINTS)),
                "crops": {"corn": crop},
            }
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(
        f"[predict] {year}: {point:,.0f} kg/ha "
        f"({crop['weather_effect_pct']:+.1f}% vs trend); wrote {OUT}"
    )
    return payload


if __name__ == "__main__":
    predict()
