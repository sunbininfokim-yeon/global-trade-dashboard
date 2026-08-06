"""
Build LatAm banana reference JSON (DATA_LAYOUT §4b).

Usage:
  python3 -m latam_banana.build_reference
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "reference", "banana_country_profiles.json")
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data"))

REASON = (
    "캐번디시 수출은 블랙 시가토카·폭풍·TR4가 지배적입니다. "
    "주간 YLWS/YLS 시계열은 협동조합·CORBANA 등 비공개이고 "
    "(Olivares et al. 2022 Data Availability: Not applicable) "
    "공개 기상만으로 검증된 수량성 예측을 내지 않습니다. "
    "기관 통계와 리스크 메모만 표시합니다."
)

FILE_FOR = {
    "ecuador": "ecuador_yield_forecast.json",
    "guatemala": "guatemala_yield_forecast.json",
    "costa_rica": "costa_rica_yield_forecast.json",
    "honduras": "honduras_yield_forecast.json",
}


def log(message: str) -> None:
    print(f"[banana-ref] {message}", flush=True)


def build_one(key: str, country: dict, shared: dict) -> dict:
    research = [
        {
            "title_ko": item["label_ko"],
            "body_ko": f"{item['summary_ko']} {item['operational_note_ko']}",
            "links": [],
        }
        for item in shared.get("risk_framework", [])
    ]
    if country.get("hurricane_prone"):
        research.append({
            "title_ko": "이 벨트: 허리케인 노출",
            "body_ko": "중미 카리브/북부 벨트는 blowdown 연도에 수출이 급락할 수 있음. "
                       "최대풍 기록 없이 소프트 기상 잔차로 대체하지 않음.",
            "links": [],
        })
    research.append({
        "title_ko": "YLWS 시계열 상태",
        "body_ko": (
            "공개 주간 YLWS/YLS 없음. 문헌 패널은 COOBANA(파나마) 내부 기록. "
            "확보 로그: scripts/yield_model/latam_banana/YLWS_ACQUISITION.md"
        ),
        "links": [
            {
                "label": "Olivares et al. 2022 (DOI)",
                "url": "https://doi.org/10.3390/su142114123",
            }
        ],
    })

    regions = {}
    for i, belt in enumerate(country.get("belts") or []):
        rkey = f"{key}_belt_{i + 1}"
        regions[rkey] = {
            "label": belt["name"],
            "label_ko": belt["name"],
            "forecast_available": False,
            "reason_ko": REASON,
            "coordinates": belt.get("coordinates"),
            "crops": {
                "banana": {
                    "label_ko": "바나나",
                    "unit": "kg/ha",
                }
            },
        }

    sources = list(country.get("sources") or [])
    sources.append({
        "name": "YLWS acquisition log (this repo)",
        "url": "",
        "supports": "documents absence of open weekly disease scores",
    })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": datetime.now(timezone.utc).year,
        "country": country["country"],
        "title_ko": f"{country['label_ko']} 바나나 참고·리스크",
        "forecast_available": False,
        "panel_mode": "reference",
        "reason_ko": REASON,
        "methodology_note": (
            "Reference panel only. No ridge/RF yield point. "
            "Risk: Black Sigatoka (YLWS proprietary), hurricane blowdown, TR4 area."
        ),
        "government_outlooks": [
            {
                "agency": "FAO / FAOSTAT framing",
                "agency_ko": "FAO 계열",
                "season": "see source vintage",
                "metric_ko": "생산·수출 참고 (헤드라인 숫자 미고정)",
                "value": None,
                "unit": None,
                "status_ko": "Compendium/FAOSTAT로 교차 — 패널에 임의 point 없음",
                "note_ko": " ".join(country.get("stat_notes_ko") or []),
                "url": "https://www.fao.org/markets-and-trade/commodities/bananas",
                "url_label": "FAO bananas",
            }
        ],
        "research_notes": research,
        "headline_risks_ko": country.get("headline_risks_ko") or [],
        "sources": sources,
        "regions": regions,
    }


def main() -> int:
    with open(PROFILES, encoding="utf-8") as handle:
        shared = json.load(handle)

    os.makedirs(PUBLIC, exist_ok=True)
    for key, country in shared["countries"].items():
        payload = build_one(key, country, shared)
        out = os.path.join(PUBLIC, FILE_FOR[key])
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
