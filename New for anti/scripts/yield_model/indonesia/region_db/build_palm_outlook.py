"""Build a candidate CPO outlook with explicit forecast/reference states."""

import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .palm_backtest import (
    CORE_FEATURES,
    DATA,
    EXPLORATORY_MIN_TRAIN,
    STABLE_PROVINCE,
    _log_model,
    _predict_log,
    forward_predictions,
    horizon2_predictions,
    load_frames,
    regional_backtest,
)


OUT = os.path.join(DATA, "palm_outlook_candidate.json")
BPS_URL = (
    "https://www.bps.go.id/id/publication/2025/08/29/"
    "8d2a6ab3510f9828daf73191/statistik-tanaman-perkebunan-tahunan-"
    "indonesia-2024-kelapa-sawit-kopi-kakao-karet-teh-dan-komoditas-"
    "perkebunan-unggulan-.html"
)


def empirical_ranges(point, actual, predicted):
    actual = np.asarray(actual, float)
    predicted = np.asarray(predicted, float)
    errors = np.abs(predicted - actual) / actual
    error68, error95 = np.quantile(errors, [0.68, 0.95])
    low68, high68 = point * (1 - error68), point * (1 + error68)
    low95, high95 = point * (1 - error95), point * (1 + error95)
    return {
        "point": round(float(point), 1),
        "range_68": [round(float(low68), 1), round(float(high68), 1)],
        "range_95": [round(float(low95), 1), round(float(high95), 1)],
        "interval_method": "symmetric_empirical_forward_ape",
    }


def _national_outlook(national):
    future_2025 = national.iloc[-1].copy()
    future_2025["year"] = 2025
    last = float(national["total_cpo_tonnes"].iloc[-1])
    structural_2025 = float(national["mature_ha"].iloc[-1]) * _predict_log(
        _log_model(national, "mature_yield_t_ha", ridge=0), future_2025)
    point_2025 = 0.5 * (last + structural_2025)
    h1 = forward_predictions(national)
    h1 = h1[h1["model"] == "fixed_equal_baseline"]
    h1_baseline = forward_predictions(national)
    h1_baseline = h1_baseline[h1_baseline["model"] == "last_year"]

    future_2026 = future_2025.copy()
    future_2026["year"] = 2026
    point_2026 = float(national["mature_ha"].iloc[-1]) * _predict_log(
        _log_model(national, "mature_yield_t_ha", ridge=0), future_2026)
    h2 = horizon2_predictions(national)
    h2 = h2[h2["model"] == "h2_structure_no_climate"]
    h2_baseline = horizon2_predictions(national)
    h2_baseline = h2_baseline[h2_baseline["model"] == "h2_last_year"]

    def backtest_summary(folds, baseline, horizon):
        mape = float(folds["absolute_percentage_error"].mean())
        baseline_mape = float(baseline["absolute_percentage_error"].mean())
        return {
            "horizon_years": horizon,
            "forward_folds": len(folds),
            "mape": mape,
            "baseline_last_year_mape": baseline_mape,
            "skill_vs_last_year": 1 - mape / baseline_mape,
            "latest_ape": float(folds.sort_values("year")[
                "absolute_percentage_error"].iloc[-1]),
            "max_ape": float(folds["absolute_percentage_error"].max()),
        }

    return {
        "2025": {
            "status": "baseline_estimate_pending_actual",
            "confidence": "medium_low",
            "method": "fixed_50_50_last_year_and_mature_area_yield_trend",
            **empirical_ranges(
                point_2025, h1["actual_tonnes"], h1["prediction_tonnes"]),
            "backtest": backtest_summary(h1, h1_baseline, 1),
        },
        "2026": {
            "status": "baseline_forecast_low_confidence",
            "confidence": "low",
            "method": "two_year_mature_area_yield_trend",
            **empirical_ranges(
                point_2026, h2["actual_tonnes"], h2["prediction_tonnes"]),
            "backtest": backtest_summary(h2, h2_baseline, 2),
            "caveat_ko": (
                "2025년 BPS 생산량·성숙면적이 아직 없어 2024년 구조를 "
                "두 해 앞까지 연장한 저신뢰 기준 전망"
            ),
        },
    }


def _region_fold_predictions(frame, model):
    rows = []
    for position in range(EXPLORATORY_MIN_TRAIN, len(frame)):
        train = frame.iloc[:position]
        test = frame.iloc[position]
        if model == "last_year":
            prediction = float(train["production_tonnes"].iloc[-1])
        elif model == "structure_no_climate":
            prediction = float(train["mature_ha"].iloc[-1]) * _predict_log(
                _log_model(train, "mature_yield_t_ha", ridge=0), test)
        else:
            raise KeyError(model)
        rows.append({
            "actual": float(test["production_tonnes"]),
            "prediction": prediction,
        })
    return pd.DataFrame(rows)


def _region_horizon2_predictions(frame):
    rows = []
    for position in range(EXPLORATORY_MIN_TRAIN + 1, len(frame)):
        train = frame.iloc[:position - 1]
        test = frame.iloc[position]
        if len(train) < EXPLORATORY_MIN_TRAIN:
            continue
        last = float(train["production_tonnes"].iloc[-1])
        structural = float(train["mature_ha"].iloc[-1]) * _predict_log(
            _log_model(train, "mature_yield_t_ha", ridge=0), test)
        predictions = {
            "h2_last_year": last,
            "h2_structure_no_climate": structural,
            "h2_fixed_equal_baseline": 0.5 * (last + structural),
        }
        for model, prediction in predictions.items():
            actual = float(test["production_tonnes"])
            rows.append({
                "year": int(test["year"]), "model": model,
                "actual": actual, "prediction": prediction,
                "ape": abs(prediction - actual) / actual,
            })
    return pd.DataFrame(rows)


def _select_region_horizon2(folds):
    scores = (folds.groupby("model")
              .agg(mape=("ape", "mean"), latest=("ape", "last"),
                   max_ape=("ape", "max")))
    baseline = float(scores.loc["h2_last_year", "mape"])
    eligible = []
    for model, row in scores.iterrows():
        if row["mape"] > 0.15 or row["latest"] > 0.15 or row["max_ape"] > 0.25:
            continue
        if model == "h2_last_year" or 1 - row["mape"] / baseline >= 0.10:
            eligible.append(model)
    if not eligible:
        return None, scores
    return min(eligible, key=lambda model: scores.loc[model, "mape"]), scores


def _region_outlook(region):
    gates = regional_backtest(region)
    results = []
    for gate in gates.itertuples(index=False):
        frame = region[region["province"] == gate.province].sort_values("year")
        latest = frame.iloc[-1]
        item = {
            "province": gate.province,
            "status": gate.status,
            "target": "CPO",
            "unit": "tonnes",
            "last_actual": {
                "year": int(latest["year"]),
                "production_tonnes": round(float(latest["production_tonnes"]), 1),
                "mature_area_ha": round(float(latest["mature_ha"]), 1),
            },
            "climate_adjustment_applied": False,
            "crop_calendar_ref": "indonesia_oil_palm_perennial",
        }
        if gate.status == "reference":
            item["status"] = "reference_only"
            item["forecast_available"] = False
            item["forecast_2025"] = None
            item["reason"] = "regional_forward_gate_failed"
            item["reason_ko"] = (
                "지역별 전진검증 기준을 통과하지 못해 수치 전망은 제공하지 않고, "
                "최근 BPS 실적과 기후 관측만 참고자료로 제공"
            )
        else:
            item["forecast_available"] = True
            future = latest.copy()
            future["year"] = 2025
            if gate.selected_model == "last_year":
                point = float(latest["production_tonnes"])
            else:
                point = float(latest["mature_ha"]) * _predict_log(
                    _log_model(frame, "mature_yield_t_ha", ridge=0), future)
            folds = _region_fold_predictions(frame, gate.selected_model)
            item["forecast_2025"] = {
                "method": gate.selected_model,
                **empirical_ranges(point, folds["actual"], folds["prediction"]),
                "backtest_mape": float(
                    np.mean(np.abs(folds["prediction"] - folds["actual"])
                            / folds["actual"])),
                "forward_folds": len(folds),
            }
        h2_folds = _region_horizon2_predictions(frame)
        h2_model, h2_scores = _select_region_horizon2(h2_folds)
        if h2_model is None:
            item["forecast_2026"] = None
            item["forecast_2026_reason"] = "two_year_regional_gate_failed"
        else:
            future_2026 = latest.copy()
            future_2026["year"] = 2026
            last = float(latest["production_tonnes"])
            structural = float(latest["mature_ha"]) * _predict_log(
                _log_model(frame, "mature_yield_t_ha", ridge=0), future_2026)
            points = {
                "h2_last_year": last,
                "h2_structure_no_climate": structural,
                "h2_fixed_equal_baseline": 0.5 * (last + structural),
            }
            selected_folds = h2_folds[h2_folds["model"] == h2_model]
            score = h2_scores.loc[h2_model]
            item["forecast_2026"] = {
                "method": h2_model,
                "confidence": "low",
                **empirical_ranges(
                    points[h2_model], selected_folds["actual"],
                    selected_folds["prediction"]),
                "backtest_mape": float(score["mape"]),
                "latest_ape": float(score["latest"]),
                "max_ape": float(score["max_ape"]),
                "forward_folds": len(selected_folds),
            }
        results.append(item)
    return results


def _future_climate_reference(national):
    structure = pd.read_csv(os.path.join(DATA, "palm_structure.csv"))
    latest_year = int(structure["year"].max())
    weights = structure[
        (structure["year"] == latest_year)
        & (structure["province"] != "INDONESIA")].copy()
    weights["province"] = weights["province"].replace(STABLE_PROVINCE)
    weights = (weights.groupby("province", as_index=False)
               .agg(mature_ha=("mature_ha", "sum")))

    climate = pd.read_csv(os.path.join(DATA, "province_climate.csv"))
    climate = climate[climate["crop"] == "oil_palm"].copy()
    climate["province"] = climate["province"].replace(STABLE_PROVINCE)
    climate = (climate.groupby(
        ["year", "province", "window", "metric"], as_index=False)
        .agg(value=("value", "mean")))
    result = {}
    for year in [2025, 2026]:
        joined = climate[climate["year"] == year].merge(
            weights, on="province")
        joined["weighted"] = joined["value"] * joined["mature_ha"]
        grouped = (joined.groupby(["window", "metric"])
                   .agg(weighted=("weighted", "sum"),
                        weight=("mature_ha", "sum")))
        grouped["value"] = grouped["weighted"] / grouped["weight"]
        metrics = {}
        for name, feature in CORE_FEATURES.items():
            window, metric = feature.split("__", 1)
            value = float(grouped.loc[(window, metric), "value"])
            history = national[feature].to_numpy(float)
            metrics[name] = {
                "value": value,
                "z_score_vs_2006_2024": float(
                    (value - history.mean()) / history.std()),
                "historical_percentile": float(np.mean(history <= value)),
            }
        result[str(year)] = {
            "status": "reference_only_not_applied_to_point",
            "mature_area_weight_vintage": latest_year,
            "metrics": metrics,
        }
    return result


def build_payload():
    national, region = load_frames()
    climate = pd.read_csv(os.path.join(DATA, "province_climate.csv"))
    palm_climate = climate[climate["crop"] == "oil_palm"]
    folds = forward_predictions(national)
    model_mape = folds.groupby("model")["absolute_percentage_error"].mean()
    incremental_skill = 1 - (
        model_mape["climate_soil_lag2"]
        / model_mape["structure_no_climate"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_status": "input_to_public_forecast_pipeline",
        "country": "Indonesia",
        "crop": "palm_oil",
        "target": "CPO",
        "unit": "tonnes",
        "label_data_through": 2024,
        "climate_inputs_through": int(palm_climate["year"].max()),
        "climate_adjustment": {
            "applied": False,
            "status": "stopped_no_incremental_skill",
            "available_labeled_seasons": len(national),
            "best_incremental_skill_vs_structure": float(incremental_skill),
            "core_features": list(CORE_FEATURES.values()),
        },
        "crop_calendar": {
            "id": "indonesia_oil_palm_perennial",
            "type": "perennial_tree_crop",
            "annual_sowing_season": False,
            "establishment": {
                "nursery_months": [10, 12],
                "field_transplant_timing": "beginning_of_local_rainy_season",
                "note_ko": (
                    "묘목을 약 10–12개월 육묘한 뒤 지역 우기 시작에 본밭에 "
                    "정식한다. 전국 공통 고정월로 표시하지 않는다."
                ),
            },
            "growth_stages": [{
                "stage": "nursery", "age_months": "0–12",
                "label_ko": "육묘·활착 준비",
            }, {
                "stage": "TBM", "age_months_after_field_planting": "0–36/48",
                "label_ko": "미성숙기·영양생장",
                "management_ko": "제초·시비·수분관리·초기 꽃/과실 제거",
            }, {
                "stage": "TM", "age_months_after_field_planting": ">36",
                "label_ko": "성숙 생산기",
            }, {
                "stage": "replanting_candidate", "age_years": ">25",
                "label_ko": "노후목 재식재 검토",
            }],
            "harvest": {
                "months": list(range(1, 13)),
                "pattern": "year_round",
                "ideal_round_days": 7,
                "note_ko": (
                    "단일 수확기가 아니라 성숙 TBS를 연중 반복 수확한다. "
                    "이상적 수확 회전은 약 7일이며 생산 피크는 기후와 지역에 따라 변한다."
                ),
            },
            "model_windows": [{
                "name": "dry_lag2", "timing": "harvest_year_minus_2_Jun-Oct",
                "role_ko": "개화·착과의 2년 지연 수분 스트레스 참고",
            }, {
                "name": "dry_lag1", "timing": "harvest_year_minus_1_Jun-Oct",
                "role_ko": "과실 발달 전년 건기 스트레스 참고",
            }],
            "sources": [{
                "name": "Indonesia Ministry of Agriculture Regulation 18/2016",
                "url": "https://jdih.pertanian.go.id/jdih-ops/storage/sources/files/Permentan_18-2016_Peremajaan_Kelapa_Sawit_Sawit.pdf",
                "supports": "10–12 month planting material; TBM 36–48 months; TM definition",
            }, {
                "name": "Indonesia Ministry of Agriculture oil-palm good cultivation guide",
                "url": "https://repository.pertanian.go.id/server/api/core/bitstreams/ded4029b-5a17-4de9-8461-2b7e447a7d24/content",
                "supports": "year-round repeated harvest and ideal seven-day harvest rotation",
            }, {
                "name": "FAO oil-palm establishment guide",
                "url": "https://www.fao.org/4/t0309e/T0309E03.htm",
                "supports": "field transplant at the beginning of the rainy season",
            }],
        },
        "climate_reference": _future_climate_reference(national),
        "national": _national_outlook(national),
        "regions": _region_outlook(region),
        "sources": [{"name": "BPS-Statistics Indonesia", "url": BPS_URL}, {
            "name": "Google Earth Engine: ERA5-Land and CHIRPS",
            "project": "climate-project-504313",
        }],
    }


def main():
    payload = build_payload()
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    forecast_regions = [item["province"] for item in payload["regions"]
                        if item["status"].startswith("forecast_")]
    print("[palm:outlook] wrote " + OUT)
    print("[palm:outlook] forecast regions: " + ", ".join(forecast_regions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
