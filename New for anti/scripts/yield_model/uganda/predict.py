"""Generate the Uganda coffee dashboard forecast payload."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .regions import BELT_KEY, POINTS

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "public" / "data" / "uganda_yield_forecast.json"


def predict(year: int = None) -> dict:
    year = year or date.today().year
    model = json.loads((HERE / "models" / f"{BELT_KEY}.json").read_text(encoding="utf-8"))
    challenger_path = HERE / "models" / "boosted_tree_challenger.json"
    challenger = (
        json.loads(challenger_path.read_text(encoding="utf-8"))
        if challenger_path.exists()
        else None
    )
    frame = pd.read_csv(HERE / "training" / f"{BELT_KEY}.csv")
    row = frame[frame.year == year]
    if row.empty:
        raise ValueError(f"No climate row for {year}")
    row = row.iloc[0]; features = model["selected_features"]
    x = np.asarray([row[name] for name in features], dtype=float)
    components = []
    for component in model["components"]:
        trend_log = float(np.polyval(component["trend"]["log_poly_coef"], year))
        z = (x - np.asarray(component["scaler"]["mean"])) / np.asarray(component["scaler"]["scale"])
        weather_log = float(component["ridge"]["intercept"] + z @ np.asarray(component["ridge"]["coef"]))
        components.append({"name": component["name"], "trend": float(np.exp(trend_log)), "point": float(np.exp(trend_log + weather_log))})
    trend = float(np.mean([item["trend"] for item in components]))
    weather_point = float(np.mean([item["point"] for item in components]))
    last = frame[(frame.target_status == "final") & frame.yield_kg_ha.notna()].iloc[-1]
    ridge_diagnostic = {
        "candidate": "Ridge weather residual",
        "selected_features": model["selected_features"],
        "development_skill_vs_trend": round(
            model["ensemble_validation"]["development_2004_2014"][
                "skill_vs_trend"
            ],
            3,
        ),
        "holdout_period": "2015-2024",
        "holdout_skill_vs_trend": round(model["skill"]["skill_vs_trend"], 3),
        "holdout_rmse_kg_ha": round(model["skill"]["rmse_kg_ha"], 1),
        "trend_rmse_kg_ha": round(model["skill"]["baseline_rmse_kg_ha"], 1),
        "decision": "rejected; do not publish a weather forecast",
    }
    tree_diagnostic = (
        {
            "candidate": challenger["model_family"],
            "development_skill_vs_trend": round(
                challenger["selected"]["development"]["skill_vs_trend"], 3
            ),
            "holdout_period": "2015-2024",
            "holdout_skill_vs_trend": round(
                challenger["holdout_2015_2024"]["skill_vs_trend"], 3
            ),
            "holdout_rmse_kg_ha": round(
                challenger["holdout_2015_2024"]["rmse_kg_ha"], 1
            ),
            "decision": challenger["decision"],
        }
        if challenger
        else None
    )
    crop = {
        "label_ko": "생두 커피",
        "unit": "kg/ha",
        "forecast_available": False,
        "reason_ko": "추세를 뺀 기상 신호가 미사용 2015~2024 자료에서 기준선보다 나빠 기상 단수 예측을 발행하지 않습니다.",
        "last_actual": {"year": int(last.year), "yield": round(float(last.yield_kg_ha), 1)},
        "official_outlook": {
            "season": "MY 2025/26",
            "production_million_60kg_bags": 6.875,
            "area_harvested_ha": 575000,
            "robusta_share": 0.85,
            "arabica_share": 0.15,
            "status": "USDA/FAS Post forecast; not a model label",
        },
        "rejected_model_evidence": [
            ridge_diagnostic,
            *([tree_diagnostic] if tree_diagnostic else []),
        ],
        "climate_risk_monitor": {
            "weather_window": f"{year-1}-10-01 through {year}-07-31",
            "long_rains_anomaly_z": round(float(row["rain_long_rains_mm_z"]), 3),
            "tmax_excess_28c_anomaly_z": round(float(row["hot28_edd_c_days_z"]), 3),
            "note_ko": "위험 관측값이며 단수 예측값이 아닙니다.",
        },
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": "FAOSTAT 2024 actual / USDA MY 2025/26 outlook",
        "country": "Uganda",
        "forecast_available": False,
        "panel_mode": "reference",
        "title_ko": "우간다 커피 참고자료",
        "reason_ko": "단순 추세는 날씨 예측이 아닙니다. Ridge와 부스팅 모두 미사용 2015~2024 구간에서 추세 기준을 이기지 못해 point와 신뢰구간을 발행하지 않습니다.",
        "government_outlooks": [
            {
                "agency": "USDA FAS",
                "agency_ko": "USDA FAS (GAIN)",
                "season": "MY 2025/26",
                "metric_ko": "생두 생산 전망",
                "value": 6.875,
                "unit": "million 60kg bags",
                "status_ko": "Post 전망 · 모델 학습에서 제외",
                "note_ko": "수확면적 57.5만 ha, Robusta 약 85%, Arabica 약 15%. 관리 개선·유리한 날씨·새 고수확 묘목 성숙을 증가 요인으로 설명합니다.",
                "url": "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Nairobi_Uganda_UG2025-0001",
                "url_label": "USDA Uganda Coffee Annual 2025",
            }
        ],
        "research_notes": [
            {
                "title_ko": "왜 추세를 Forecast로 취급하지 않는가",
                "body_ko": "2026년 추세 기준 538 kg/ha는 과거 시계열의 연장일 뿐 날씨 반응이 아닙니다. Ridge 기상 모델의 2015~2024 홀드아웃 skill은 -3.9%(RMSE 21.5 kg/ha, 추세 20.7), 부스팅은 -86.7%(38.6 kg/ha)로 더 나빴습니다. 따라서 예측 point를 제거하고 검증 결과만 남깁니다.",
                "links": [
                    {"label": "FAOSTAT/OWID coffee yield", "url": "https://ourworldindata.org/grapher/coffee-yields"}
                ],
            },
            {
                "title_ko": "국가 단수에서 더 크게 섞이는 비기상 요인",
                "body_ko": "나무 연령과 갱신, 고수확 묘목의 성숙, 가지치기·멀칭·비료·방제, 병해, 가격과 신용에 따른 투자가 국가 단수와 생산량을 함께 바꿉니다. USDA도 최근 증산을 관리 개선과 새 묘목 성숙에 연결합니다. 이 변수들이 연도별·지역별로 공개되지 않아 기후만으로 분리할 수 없습니다.",
                "links": [
                    {"label": "USDA Uganda Coffee Annual 2025", "url": "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Nairobi_Uganda_UG2025-0001"}
                ],
            },
            {
                "title_ko": "날씨는 무관한가",
                "body_ko": "아닙니다. 농가 패널 연구에서는 Robusta에 강수의 양(+) 효과와 고온의 비선형 손실이 관측됐습니다. 다만 그 관계가 FAOSTAT 국가 연간 단수에서는 관리·수종·두 수확 주기와 섞여 시간순 예측력으로 재현되지 않았습니다. 기상 지표는 예측값이 아니라 위험 모니터로만 유지합니다.",
                "links": [
                    {"label": "Lwiza & Barkley (2025)", "url": "https://doi.org/10.1007/s10113-025-02370-4"}
                ],
            },
            {
                "title_ko": "지역 분해의 한계",
                "body_ko": "Central·Western Robusta와 Mt Elgon·Rwenzori·Zombo Arabica의 기후는 다르지만, 공개된 연속 지역 단수 라벨이 없습니다. 7개 위치와 85:15 수종 가중치는 국가 기후 위험을 보는 프록시일 뿐 지역별 생산 예측이 아닙니다.",
                "links": [
                    {"label": "USDA Uganda Coffee Annual 2025", "url": "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Nairobi_Uganda_UG2025-0001"}
                ],
            },
            {
                "title_ko": "나무 연령 모델의 한계",
                "body_ko": "나무 연령을 직접 넣으려면 최소한 지역별 정식·고사·재식재·stumping 면적을 연도별 코호트로 알아야 합니다. 현재 공개자료에는 이 장기 패널이 없습니다. 위성 수관 변화나 NDVI 회복, 묘목 배포량으로 신규·갱신 면적을 추정할 수는 있지만 그늘나무, 가지치기, 병해와 구분되지 않아 검증 전에는 설명용 프록시일 뿐입니다.",
                "links": [
                    {"label": "USDA Uganda Coffee Annual 2025", "url": "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Nairobi_Uganda_UG2025-0001"}
                ],
            },
        ],
        "model_diagnostics": {
            "trained_years": model["trained_years"],
            "ridge": ridge_diagnostic,
            "boosted_tree": tree_diagnostic,
            "trend_reference_2026_kg_ha_not_forecast": round(trend, 1),
            "weather_candidate_2026_kg_ha_rejected": round(weather_point, 1),
        },
        "sources": [
            {"name": "FAOSTAT QCL via Our World in Data", "url": "https://ourworldindata.org/grapher/coffee-yields", "supports": "1961~2024 국가 생두 단수"},
            {"name": "USDA FAS Uganda Coffee Annual 2025", "url": "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Nairobi_Uganda_UG2025-0001", "supports": "생산·면적 전망, 수종 비중, 관리·묘목 요인"},
            {"name": "Lwiza & Barkley (2025)", "url": "https://doi.org/10.1007/s10113-025-02370-4", "supports": "Robusta 강수·고온 반응"},
            {"name": "NASA POWER daily", "url": "https://power.larc.nasa.gov/", "supports": "산지 기후 위험 지표"},
        ],
        "regions": {BELT_KEY: {"label": "Uganda national coffee belt", "label_ko": "우간다 커피 벨트", "note": "Robusta 85% · Arabica 15% fixed species proxy", "zones": list(dict.fromkeys(point["zone"] for point in POINTS)), "crops": {"coffee": crop}}},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[reference] {year}: weather forecast rejected; wrote {OUT}")
    return payload


if __name__ == "__main__":
    predict()
