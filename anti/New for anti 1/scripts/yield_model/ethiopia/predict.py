"""Publish Ethiopia forecast only if weather adds holdout skill."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .climate import latest_source_dates
from .regions import BELT_KEY, CLIMATE_FEATURES, POINTS
from .train import _prepare, _trend

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "public" / "data" / "ethiopia_yield_forecast.json"
USDA_URL = "https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Coffee+Annual_Addis+Ababa_Ethiopia_ET2026-0005.pdf"


def _component_predictions(model, frame, row, year):
    features = model["selected_features"]; results = []
    # Build a two-row temporary frame so the same lag transformation used in
    # validation is applied with the component's own trend.
    for component in model["components"]:
        trend = np.poly1d(component["trend"]["log_poly_coef"]); years = frame.year.to_numpy(float)
        matrix = _prepare(frame, features, years, trend); x = matrix[frame.index[frame.year == year][0]]
        z = (x - np.asarray(component["scaler"]["mean"])) / np.asarray(component["scaler"]["scale"])
        weather = component["ridge"]["intercept"] + z @ np.asarray(component["ridge"]["coef"])
        results.append({"name": component["name"], "trend": float(np.exp(trend(year))), "point": float(np.exp(trend(year) + weather))})
    return results


def predict(year: int = None):
    year = year or date.today().year
    model = json.loads((HERE / "models" / f"{BELT_KEY}.json").read_text(encoding="utf-8"))
    challenger_path = HERE / "models" / "boosted_tree_challenger.json"
    challenger = json.loads(challenger_path.read_text(encoding="utf-8")) if challenger_path.exists() else None
    frame = pd.read_csv(HERE / "training" / f"{BELT_KEY}.csv").reset_index(drop=True)
    row = frame[frame.year == year]
    if row.empty: raise ValueError(f"No climate row for {year}")
    components = _component_predictions(model, frame, row.iloc[0], year)
    trend = float(np.mean([x["trend"] for x in components])); candidate = float(np.mean([x["point"] for x in components]))
    last = frame[(frame.target_status == "final") & frame.yield_kg_ha.notna()].iloc[-1]
    selected_holdout = model["selected_validation"]["holdout_2015_2024"]
    cycle_holdout = model["cycle_only_validation"]["holdout_2015_2024"]
    outlook = {"agency": "USDA FAS", "agency_ko": "USDA FAS (GAIN)", "season": "MY 2026/27", "metric_ko": "생두 생산 전망", "value": 12.1, "unit": "million 60kg bags", "status_ko": "Post 전망 · 모델 학습 제외", "note_ko": "수확면적 80만 ha, 단수 0.91 t/ha. 정상적 강우·남부 생산주기 반등·stumping 및 묘목 효과를 전제.", "url": USDA_URL, "url_label": "USDA Ethiopia Coffee Annual 2026"}
    accepted = model["accepted_weather_forecast"]
    history = frame[(frame.year <= 2024) & frame.yield_kg_ha.notna()]
    current = row.iloc[0]
    climate_anomalies = {}
    for feature in CLIMATE_FEATURES:
        scale = float(history[feature].std(ddof=1))
        climate_anomalies[f"{feature}_z"] = (
            round(
                (float(current[feature]) - float(history[feature].mean())) / scale,
                3,
            )
            if scale
            else 0.0
        )
    try:
        source_dates = latest_source_dates()
    except Exception as exc:  # cached reference generation can remain offline
        source_dates = {"chirps": None, "era5_land": None, "error": str(exc)}
    incomplete = []
    if not source_dates.get("chirps") or source_dates["chirps"] < f"{year}-07-31":
        climate_anomalies["rain_filling_jun_jul_mm_z"] = None
        incomplete.append(
            "CHIRPS Jun-Jul filling-rain window incomplete; do not read the partial sum as drought."
        )
    if not source_dates.get("era5_land") or source_dates["era5_land"] < f"{year}-07-31":
        climate_anomalies["hot30_mar_jul_c_days_z"] = None
        climate_anomalies["root_sm_mar_jul_z"] = None
        climate_anomalies["vpd_mar_jul_kpa_z"] = None
        incomplete.append("ERA5-Land Mar-Jul window incomplete.")
    crop = {"label_ko": "아라비카 생두", "unit": "kg/ha", "last_actual": {"year": int(last.year), "yield": round(float(last.yield_kg_ha), 1)}, "official_outlook": outlook, "structural_context": model["structural_context_not_fitted"], "climate_risk_monitor": {"period": f"{year-1}-08-01 through {year}-07-31", "source_latest_dates": source_dates, "anomalies_vs_1993_2024": climate_anomalies, "coverage_warnings": incomplete, "note_ko": "생산가중 국가 기후 위험값이며 단수 예측이 아닙니다. 미완성 창은 null 처리합니다."}, "model_diagnostics": {"selected": model["selected_full_model"], "holdout_skill_vs_trend": round(selected_holdout["skill_vs_trend"], 3), "holdout_rmse_kg_ha": round(selected_holdout["rmse_kg_ha"], 1), "trend_rmse_kg_ha": round(selected_holdout["baseline_rmse_kg_ha"], 1), "cycle_only_rmse_kg_ha": round(cycle_holdout["rmse_kg_ha"], 1), "weather_incremental_skill_vs_cycle": round(model["weather_incremental_skill_vs_cycle_holdout"], 3), "decision": model["operational_choice"], "candidate_2026_kg_ha": round(candidate, 1), "trend_2026_kg_ha": round(trend, 1), "boosted_tree": ({"development_skill_vs_trend": round(challenger["selected"]["development"]["skill_vs_trend"], 3), "holdout_skill_vs_trend": round(challenger["holdout_2015_2024"]["skill_vs_trend"], 3), "holdout_rmse_kg_ha": round(challenger["holdout_2015_2024"]["rmse_kg_ha"], 1), "decision": challenger["decision"]} if challenger else None)}, "regional_context": {"weights_period": "MY 2023/24-2025/26 three-year average", "shares": {"Oromia": .595, "South-West Ethiopia": .137, "Sidama": .129, "South Ethiopia": .071, "Central Ethiopia": .037, "Gambella": .015, "Amhara": .011}}}
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "season": year if accepted else "FAOSTAT 2024 actual / USDA MY 2026/27 outlook", "country": "Ethiopia", "forecast_available": accepted, "panel_mode": "forecast" if accepted else "reference", "government_outlooks": [outlook], "sources": [{"name": "FAOSTAT QCL via OWID", "url": "https://ourworldindata.org/grapher/coffee-yields", "supports": "국가 단수·생산·면적"}, {"name": "USDA FAS Ethiopia Coffee Annual 2026", "url": USDA_URL, "supports": "지역 비중, stumping, 노령목, MY 2026/27 전망"}, {"name": "GEE CHIRPS + ERA5-Land", "url": "https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY", "supports": "산지 강수·열·토양수분·VPD"}], "regions": {BELT_KEY: {"label": "Ethiopia national Arabica belt", "label_ko": "에티오피아 아라비카 벨트", "zones": list(dict.fromkeys(p["region"] for p in POINTS)), "crops": {"coffee": crop}}}}
    if accepted:
        q68, q95 = model["uncertainty"]["q68_kg_ha"], model["uncertainty"]["q95_kg_ha"]
        crop.update({"point": round(candidate, 1), "range_68": [round(max(0, candidate-q68), 1), round(candidate+q68, 1)], "range_95": [round(max(0, candidate-q95), 1), round(candidate+q95, 1)], "trend": round(trend, 1), "weather_effect": round(candidate-trend, 1), "weather_effect_pct": round((candidate/trend-1)*100, 2), "skill": {"skill_vs_trend_only": round(selected_holdout["skill_vs_trend"], 3), "weather_incremental_skill_vs_cycle": round(model["weather_incremental_skill_vs_cycle_holdout"], 3), "beats_trend": True, "low_confidence": model["low_confidence"], "evaluation_period": "untouched 2015-2024"}, "trained_years": model["trained_years"]})
    else:
        payload.update({"title_ko": "에티오피아 커피 참고자료", "reason_ko": "기후+생산주기 모델이 미사용 홀드아웃에서 추세와 비기상 주기 기준을 동시에 이기지 못해 Forecast를 발행하지 않습니다.", "research_notes": [{"title_ko": "모델 판정", "body_ko": f"선택 모델 {model['selected_full_model']}의 홀드아웃 추세 대비 skill은 {selected_holdout['skill_vs_trend']:+.1%}, 비기상 cycle-only 대비 추가 skill은 {model['weather_incremental_skill_vs_cycle_holdout']:+.1%}입니다. 부스팅 홀드아웃 skill도 {challenger['holdout_2015_2024']['skill_vs_trend']:+.1%}로 기각했습니다."}, {"title_ko": "나무 연령·갱신", "body_ko": "노령목 약 70%, 2025/26 stumping 면적 15%(Oromia 19%, South Ethiopia 14%, Sidama 13%)라는 최신 단면은 중요하지만 장기 연도별 패널이 아니므로 학습계수로 쓰지 않았습니다."}, {"title_ko": "지역 상쇄", "body_ko": "2025/26에는 Sidama·Yirgacheffe·Guji 등 남부가 생산주기와 늦은 강우로 저조한 반면 Jimma·Limmu·Kaffa·Bench Maji·Sheka는 수분 조건과 수확기 건조 날씨가 양호해 전국 합계에서 상쇄됐습니다. 국가 단수 한 줄로는 이 차이를 학습하기 어렵습니다."}, {"title_ko": "기후와 구조의 구분", "body_ko": "강수·열·토양수분·VPD는 위험 모니터로 유지합니다. stumping, 묘목 성숙, 가지치기, 면적 확대와 가격투자는 구조 요인이며 기후 효과로 귀속하지 않습니다."}]})
        crop.update({"forecast_available": False, "reason_ko": payload["reason_ko"]})
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[predict] accepted={accepted} candidate={candidate:,.0f} trend={trend:,.0f}; wrote {OUT}")
    return payload


if __name__ == "__main__": predict()
