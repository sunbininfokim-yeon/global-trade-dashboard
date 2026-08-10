"""Build the observation-only China crop-monitor panel.

The weather models in this package were tested and all eight failed to beat
their honest baselines.  This publisher therefore emits no forecast point or
interval.  It combines two things that remain useful and auditable:

* region-weighted, completed-season weather observations from the committed
  training tables; and
* the latest national USDA PSD / FAOSTAT value used as context, explicitly
  labelled as a national reference rather than a regional observation.

Outputs
-------
``data/region_observations_v1.json``
    Model-side observation artifact.  Kept separate from raw caches.

``public/data/china_yield_forecast.json``
    Dashboard contract.  The historical filename is retained, but the payload
    declares ``panel_mode: reference`` and contains no forecast values.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd


HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")
DATA = os.path.join(HERE, "data")
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data"))

PSD_URL = "https://apps.fas.usda.gov/psdonline/app/index.html#/app/home"
FAOSTAT_URL = "https://www.fao.org/faostat/en/#data/QCL"
POWER_URL = "https://power.larc.nasa.gov/"

METRIC_KO = {
    "frost_days_sep": "9월 결빙일",
    "frost_penalty": "미성숙 서리위험지수",
    "gdd_season": "생육 적산온도",
    "heat_days_podfill": "협실비대기 35°C 초과일",
    "precip_podfill": "협실비대기 강수",
    "heat_days_silking": "출사기 35°C 초과일",
    "precip_silking": "출사기 강수",
    "silking_stress": "출사기 평균 수분수지",
    "dhw_days": "5월 건조열풍일",
    "dhw_severity": "건조열풍 강도지수",
    "preharvest_rain": "수확 전 강수",
    "preharvest_rain_excess": "30mm 초과 수확기 강우",
    "winterkill_days": "월동 한파일",
    "heat_excess_fill": "등숙기 고온초과",
    "heat_penalty": "출수기 지속고온지수",
    "max_heat_run": "최장 폭염 지속",
    "heat_days_heading": "출수기 35°C 초과일",
    "max_7day_rain": "최대 7일 강수",
    "monsoon_rain": "장마기 강수",
    "waterlogging": "과습 초과강수",
    "spring_chill_days": "조기벼 봄 저온일",
    "spring_rain": "봄 강수",
    "cold_dew_days": "만기벼 한로풍 저온일",
    "turnaround_rain": "7월 작기전환 강수",
    "typhoon_days": "태풍성 기상 프록시일",
    "heat_days_summer": "여름 35°C 초과일",
    "low_light_days": "겨울 저일사일",
    "winter_radiation": "겨울 누적일사",
    "snow_load": "적설하중 프록시",
    "winter_cold_days": "겨울 강한 한파일",
    "summer_rain": "여름 강수",
}

UNIT_KO = {
    "days": "일",
    "index": "지수",
    "degree-days": "°C·일",
    "duration-weighted index": "지수",
    "mm water balance": "mm",
    "mm above threshold": "mm",
    "proxy days": "일(프록시)",
    "MJ/m2": "MJ/m²",
    "proxy index": "지수",
}


def _frame(key):
    return pd.read_csv(os.path.join(TRAINING, f"{key}.csv"))


def _latest_target(key):
    data = _frame(key).dropna(subset=["target"]).sort_values("year")
    row = data.iloc[-1]
    return {"year": int(row.year), "value": float(row.target)}


def _latest_weather(key, fields):
    data = _frame(key).sort_values("year")
    row = data.iloc[-1]
    values = {field: (None if pd.isna(row[field]) else float(row[field]))
              for field in fields}
    return {"year": int(row.year), "values": values}


def _diagnostic(key):
    with open(os.path.join(MODELS, f"{key}.json"), encoding="utf-8") as handle:
        model = json.load(handle)
    return {
        "beats_trend": bool(model.get("beats_trend", False)),
        "skill_vs_trend": model.get("recent_skill_vs_trend"),
        "trained_years": model.get("trained_years"),
        "verdict_ko": "추세 기준선을 이기지 못해 forecast를 발행하지 않음",
    }


def _national_reference(key, label_ko, unit, source, note_ko):
    value = _latest_target(key)
    return {
        "label_ko": label_ko,
        "year": value["year"],
        "value": value["value"],
        "unit": unit,
        "scope": "China national",
        "source": source,
        "note_ko": note_ko,
    }


def build_observations():
    soy_ref = _national_reference(
        "northeast_soy", "전국 대두 단수 참고치", "kg/ha", "USDA PSD",
        "동북3성 실적이 아니라 모델 라벨로 사용한 중국 전국 추정치")
    corn_ref = _national_reference(
        "northeast_corn", "전국 옥수수 단수 참고치", "kg/ha", "USDA PSD",
        "동북3성 실적이 아니라 모델 라벨로 사용한 중국 전국 추정치")
    wheat_ref = _national_reference(
        "henan_wheat", "전국 밀 단수 참고치", "kg/ha", "USDA PSD",
        "허난·황화이하이 실적이 아니라 모델 라벨로 사용한 중국 전국 추정치")
    rice_ref = _national_reference(
        "yangtze_rice", "전국 도정 쌀 단수 참고치", "kg/ha", "USDA PSD",
        "장강 유역 실적이 아니라 중국 전국 도정 기준 추정치")
    rice_area_ref = _national_reference(
        "south_china_rice_area", "전국 쌀 수확면적 참고치", "1000 ha", "USDA PSD",
        "화남 이모작 면적이 아니라 작기별 면적을 합산한 중국 전국 추정치")
    veg_ref = _national_reference(
        "shandong_vegetables", "전국 1차 채소 단수 참고치", "kg/ha", "FAOSTAT",
        "산둥 실적이 아니라 FAOSTAT 중국 본토 전국치")

    regions = {
        "northeast_grains": {
            "label_ko": "동북3성 곡창지대",
            "coordinates": [125.84, 45.60],
            "geography_ko": "헤이룽장·지린·랴오닝",
            "production_context_ko": (
                "중국 대두의 약 40%, 옥수수의 약 30%를 담당하는 핵심 산지. "
                "공개 성급 장기 라벨을 확보하지 못해 비중을 생산량으로 환산하지 않음."),
            "forecast_available": False,
            "reason_ko": (
                "동북 기상을 전국 USDA 단수에 회귀하면 지역 신호가 희석되어 "
                "대두·옥수수 모두 추세 기준선을 이기지 못했습니다."),
            "crops": {
                "soybeans": {
                    "label_ko": "대두",
                    "national_reference": soy_ref,
                    "crop_calendar": {
                        "planting": "May", "pod_fill": "July-August",
                        "harvest": "September-October"},
                    "weather_observation": {
                        **_latest_weather("northeast_soy", [
                            "frost_days_sep", "frost_penalty", "gdd_season",
                            "heat_days_podfill", "precip_podfill"]),
                        "scope": "six production-weighted NASA POWER points",
                        "units": {
                            "frost_days_sep": "days", "frost_penalty": "index",
                            "gdd_season": "degree-days", "heat_days_podfill": "days",
                            "precip_podfill": "mm"}},
                    "model_diagnostic": _diagnostic("northeast_soy"),
                },
                "corn": {
                    "label_ko": "옥수수",
                    "national_reference": corn_ref,
                    "crop_calendar": {
                        "planting": "May", "silking": "July",
                        "harvest": "September-October"},
                    "weather_observation": {
                        **_latest_weather("northeast_corn", [
                            "frost_days_sep", "frost_penalty", "gdd_season",
                            "heat_days_silking", "precip_silking", "silking_stress"]),
                        "scope": "seven production-weighted NASA POWER points",
                        "units": {
                            "frost_days_sep": "days", "frost_penalty": "index",
                            "gdd_season": "degree-days", "heat_days_silking": "days",
                            "precip_silking": "mm", "silking_stress": "mm water balance"}},
                    "model_diagnostic": _diagnostic("northeast_corn"),
                },
            },
        },
        "henan_wheat": {
            "label_ko": "허난·황화이하이 겨울밀",
            "coordinates": [115.456, 34.791],
            "geography_ko": "허난 중심 황화이하이 평원",
            "production_context_ko": (
                "황화이하이 평원은 중국 밀의 약 4분의 3을 담당. 수량보다 "
                "수확기 품질 피해가 수입 수요에 먼저 나타날 수 있음."),
            "forecast_available": False,
            "reason_ko": (
                "2023년 수발아처럼 품질 피해가 커도 전국 톤수 단수에는 거의 "
                "반영되지 않아 기상 모델을 검증할 수 없었습니다."),
            "crops": {
                "wheat": {
                    "label_ko": "겨울밀",
                    "national_reference": wheat_ref,
                    "crop_calendar": {
                        "planting": "October (previous year)",
                        "grain_fill": "May", "harvest": "late May-early June"},
                    "weather_observation": {
                        **_latest_weather("henan_wheat", [
                            "dhw_days", "dhw_severity", "preharvest_rain",
                            "preharvest_rain_excess", "winterkill_days",
                            "heat_excess_fill"]),
                        "scope": "eight production-weighted NASA POWER points",
                        "units": {
                            "dhw_days": "days", "dhw_severity": "index",
                            "preharvest_rain": "mm", "preharvest_rain_excess": "mm",
                            "winterkill_days": "days", "heat_excess_fill": "degree-days"}},
                    "model_diagnostic": _diagnostic("henan_wheat"),
                }
            },
        },
        "yangtze_rice": {
            "label_ko": "장강 유역 벼",
            "coordinates": [114.189, 30.139],
            "geography_ko": "후난·장시·후베이·안후이·장쑤·쓰촨 대표점",
            "production_context_ko": (
                "중국 쌀의 다수를 생산하지만 단작·이모작과 동북 자포니카가 "
                "전국 한 개 단수에 혼합됨."),
            "forecast_available": False,
            "reason_ko": (
                "장강 폭염·홍수 지표는 실제 극한연도를 포착하지만 전국 도정 쌀 "
                "단수의 연간 변동성이 1.6%에 불과해 검증 신호가 남지 않았습니다."),
            "crops": {
                "rice": {
                    "label_ko": "벼",
                    "national_reference": rice_ref,
                    "crop_calendar": {
                        "systems": "single and double cropping",
                        "heading_risk_window": "July-August",
                        "harvest": "September-November, system-dependent"},
                    "weather_observation": {
                        **_latest_weather("yangtze_rice", [
                            "heat_penalty", "max_heat_run", "heat_days_heading",
                            "max_7day_rain", "monsoon_rain", "waterlogging"]),
                        "scope": "six production-weighted NASA POWER points",
                        "units": {
                            "heat_penalty": "duration-weighted index",
                            "max_heat_run": "days", "heat_days_heading": "days",
                            "max_7day_rain": "mm", "monsoon_rain": "mm",
                            "waterlogging": "mm above threshold"}},
                    "model_diagnostic": _diagnostic("yangtze_rice"),
                }
            },
        },
        "south_china_rice": {
            "label_ko": "화남 이모작 벼",
            "coordinates": [111.213, 23.432],
            "geography_ko": "광둥·광시 대표점",
            "production_context_ko": (
                "단수보다 두 번째 작기를 실제로 심었는지가 핵심. 전국 수확면적은 "
                "화남의 이모작 준수율을 직접 측정하지 못함."),
            "forecast_available": False,
            "reason_ko": (
                "이모작 여부는 정책·농촌임금·도시화 영향을 크게 받으며, 공개된 "
                "전국 면적만으로 화남 지역 변화를 검증할 수 없었습니다."),
            "crops": {
                "rice": {
                    "label_ko": "이모작 벼",
                    "national_reference": rice_area_ref,
                    "crop_calendar": {
                        "early_rice": "March-July",
                        "late_rice": "July-November",
                        "turnaround_risk": "July"},
                    "weather_observation": {
                        **_latest_weather("south_china_rice_area", [
                            "spring_chill_days", "spring_rain", "cold_dew_days",
                            "turnaround_rain", "typhoon_days", "heat_days_summer"]),
                        "scope": "five production-weighted NASA POWER points",
                        "units": {
                            "spring_chill_days": "days", "spring_rain": "mm",
                            "cold_dew_days": "days", "turnaround_rain": "mm",
                            "typhoon_days": "proxy days", "heat_days_summer": "days"}},
                    "model_diagnostic": _diagnostic("south_china_rice_area"),
                }
            },
        },
        "shandong_vegetables": {
            "label_ko": "산둥 시설·노지 채소",
            "coordinates": [118.688, 36.412],
            "geography_ko": "서우광·웨이팡 중심 산둥 대표점",
            "production_context_ko": (
                "시설면적과 투자주기가 생산능력을 결정. 외부 강수·기온만으로 "
                "온실 작황을 설명하기 어려움."),
            "forecast_available": False,
            "reason_ko": (
                "공개 라벨이 산둥이 아닌 FAOSTAT 전국치이고, 핵심 설명변수인 "
                "온실 면적 시계열이 없어 기상 forecast를 발행하지 않습니다."),
            "crops": {
                "vegetables": {
                    "label_ko": "채소",
                    "national_reference": veg_ref,
                    "crop_calendar": {
                        "system": "year-round protected cultivation plus open field",
                        "winter_risks": "low light, snow load and severe cold"},
                    "weather_observation": {
                        **_latest_weather("shandong_vegetables", [
                            "low_light_days", "winter_radiation", "snow_load",
                            "winter_cold_days", "heat_days_summer", "summer_rain"]),
                        "scope": "five production-weighted NASA POWER points",
                        "units": {
                            "low_light_days": "days", "winter_radiation": "MJ/m2",
                            "snow_load": "proxy index", "winter_cold_days": "days",
                            "heat_days_summer": "days", "summer_rain": "mm"}},
                    "model_diagnostic": _diagnostic("shandong_vegetables"),
                }
            },
        },
    }

    return {
        "schema": "china_region_observations_v1",
        "observation_through": 2025,
        "scope_note_ko": (
            "기상값은 산지 대표점의 생산가중 NASA POWER 관측입니다. 단수·면적은 "
            "USDA PSD/FAOSTAT 전국 참고치이며 지역 실적으로 해석하지 않습니다."),
        "regions": regions,
    }


def _outlook(reference, agency, url):
    return {
        "agency": agency,
        "agency_ko": agency,
        "season": str(reference["year"]),
        "metric_ko": reference["label_ko"],
        "value": reference["value"],
        "unit": reference["unit"],
        "status_ko": "전국 관측·추정 참고치 · 지역 forecast 아님",
        "note_ko": reference["note_ko"],
        "url": url,
        "url_label": agency,
    }


def _render_weather(crop):
    observation = crop["weather_observation"]
    units = observation["units"]
    parts = []
    for name, value in observation["values"].items():
        if value is None:
            continue
        unit = UNIT_KO.get(units.get(name, ""), units.get(name, ""))
        parts.append(f"{METRIC_KO.get(name, name)} {value:.1f}{(' ' + unit) if unit else ''}")
    return f"{crop['label_ko']} {observation['year']}: " + ", ".join(parts)


def build_public(observations):
    regions = observations["regions"]
    references = []
    for region in regions.values():
        for crop in region["crops"].values():
            ref = crop["national_reference"]
            key = (ref["label_ko"], ref["year"], ref["value"])
            if key not in {(r["label_ko"], r["year"], r["value"]) for r in references}:
                references.append(ref)

    notes = []
    for region in regions.values():
        summaries = []
        for crop in region["crops"].values():
            summaries.append(_render_weather(crop))
        notes.append({
            "title_ko": region["label_ko"],
            "body_ko": (f"{region['production_context_ko']} "
                        f"관측 — {' / '.join(summaries)}. "
                        f"예측 보류 — {region['reason_ko']}"),
            "links": [
                {"label": "NASA POWER", "url": POWER_URL},
                {"label": "USDA PSD", "url": PSD_URL},
            ],
        })

    public_regions = {}
    for key, region in regions.items():
        public_regions[key] = {
            "label": region["label_ko"],
            "label_ko": region["label_ko"],
            "note": "지역 기상 관측 + 전국 농업 참고치 · forecast 아님",
            "forecast_available": False,
            "reason_ko": region["reason_ko"],
            "geography_ko": region["geography_ko"],
            "production_context_ko": region["production_context_ko"],
            "crops": region["crops"],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": "2025 관측",
        "country": "China",
        "forecast_available": False,
        "panel_mode": "reference",
        "title_ko": "중국 주요 산지 관측자료",
        "reason_ko": (
            "공개 성급 생산 라벨을 확보하지 못했고 전국 단수·면적을 사용한 8개 "
            "모델이 모두 추세 기준선을 이기지 못해 forecast를 철회합니다. 지역별 "
            "기상 관측과 전국 농업 참고치만 제공합니다."),
        "government_outlooks": [
            _outlook(ref, ref["source"],
                     FAOSTAT_URL if ref["source"] == "FAOSTAT" else PSD_URL)
            for ref in references
        ],
        "research_notes": notes,
        "sources": [
            {"name": "USDA Production, Supply and Distribution",
             "url": PSD_URL,
             "supports": "전국 곡물·유지작물 단수와 수확면적 참고치"},
            {"name": "FAOSTAT Crops and livestock products",
             "url": FAOSTAT_URL,
             "supports": "전국 채소 단수 참고치"},
            {"name": "NASA POWER Agroclimatology",
             "url": POWER_URL,
             "supports": "산지 대표점 일별 기상과 파생 위험지표"},
        ],
        "regions": public_regions,
    }


def main():
    observations = build_observations()
    public = build_public(observations)
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(PUBLIC, exist_ok=True)
    data_path = os.path.join(DATA, "region_observations_v1.json")
    public_path = os.path.join(PUBLIC, "china_yield_forecast.json")
    with open(data_path, "w", encoding="utf-8") as handle:
        json.dump(observations, handle, ensure_ascii=False, indent=2)
    with open(public_path, "w", encoding="utf-8") as handle:
        json.dump(public, handle, ensure_ascii=False, indent=2)
    print(f"[china-reference] wrote {data_path}")
    print(f"[china-reference] wrote {public_path}")
    print(f"[china-reference] {len(observations['regions'])} regions, no forecasts")


if __name__ == "__main__":
    main()
