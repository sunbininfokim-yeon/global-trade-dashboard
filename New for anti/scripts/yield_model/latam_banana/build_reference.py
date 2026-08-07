"""
Build LatAm banana reference JSON (no yield point).

Merges static FAO export refs + optional POWER risk CSVs from collect_risk.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd

from .regions import BY_COUNTRY

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "reference", "banana_country_profiles.json")
FAOSTAT = os.path.join(HERE, "reference", "faostat_banana_national.json")
TRAINING = os.path.join(HERE, "training")
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data"))

FILE_FOR = {
    "ecuador": "ecuador_yield_forecast.json",
    "guatemala": "guatemala_yield_forecast.json",
    "costa_rica": "costa_rica_yield_forecast.json",
    "honduras": "honduras_yield_forecast.json",
}

REASON = (
    "캐번디시 수출은 시가토카·폭풍·TR4가 지배적입니다. "
    "주간 YLWS/YLS(가능하면 3–4년+)가 오기 전에는 수량성 point를 내지 않고, "
    "국가 생산·면적(FAOSTAT)과 수출 참고·POWER 기상 리스크 프록시만 표시합니다."
)


def log(message: str) -> None:
    print(f"[banana-ref] {message}", flush=True)


def latest_risk(belt_key: str) -> dict | None:
    path = os.path.join(TRAINING, f"{belt_key}_risk.csv")
    if not os.path.isfile(path):
        return None
    frame = pd.read_csv(path).dropna(subset=["year"]).sort_values("year")
    if frame.empty:
        return None
    # Prefer last completed calendar year (current year is partial until Dec).
    now = datetime.now(timezone.utc)
    complete = frame[frame.year < now.year] if now.month < 12 else frame
    row = (complete if not complete.empty else frame).iloc[-1]
    out = {"year": int(row["year"])}
    for col in ("sigatoka_rh_days", "humid_spell_max", "rain_wet",
                "wet_days", "wind_storm_days", "wind_max_daily",
                "rain_year", "tmean_year", "heat_days_34"):
        if col in frame.columns and pd.notna(row[col]):
            out[col] = round(float(row[col]), 2)
    return out


def risk_note(risk: dict | None, hurricane: bool) -> str:
    if not risk:
        return ("POWER 리스크 테이블 없음 — "
                "`python3 -m latam_banana.collect_risk` 후 재생성.")
    parts = [
        f"{risk['year']}년 벨트 가중 POWER 프록시:",
        f"시가토카형 고습일(RH≥90%) {risk.get('sigatoka_rh_days', 'n/a')}일",
        f"최장 고습 연속 {risk.get('humid_spell_max', 'n/a')}일",
        f"우기 강수 {risk.get('rain_wet', 'n/a')} mm",
    ]
    if hurricane:
        parts.append(
            f"강풍일(일평균≥12 m/s) {risk.get('wind_storm_days', 'n/a')}일 "
            f"(blowdown 하드컷은 IBTrACS 최대풍 별도)"
        )
    parts.append("→ 환경 압력 지표이며 박스/ha 예측이 아님.")
    return " · ".join(parts)


def build_one(key: str, meta: dict, shared: dict, faostat: dict) -> dict:
    export = shared["export_reference"]["latest"][key]
    nat = (faostat.get("latest") or {}).get(key) or {}
    belts = BY_COUNTRY[key]
    regions = {}
    research = [
        {
            "title_ko": item["label_ko"],
            "body_ko": item["summary_ko"],
            "links": [],
        }
        for item in shared["risk_framework"]
    ]
    research.append({
        "title_ko": "YLWS 없이 운영",
        "body_ko": (
            "병 점수 시계열이 오면 그때 재검토. "
            "지금은 국가 생산·면적(FAOSTAT) + 수출 참고 + POWER 리스크 프록시. "
            f"대시보드: {shared.get('dashboard_url', '')}"
        ),
        "links": [
            {"label": "dashboard", "url": shared.get("dashboard_url", "")},
            {"label": "Olivares et al. 2022",
             "url": "https://doi.org/10.3390/su142114123"},
        ],
    })

    for belt in belts:
        risk = latest_risk(belt.key)
        banana_crop = {
            "label_ko": "바나나",
            "unit": "kg/ha",
        }
        if nat.get("yield_t_ha") is not None:
            banana_crop["last_actual"] = {
                "year": nat["year"],
                "yield": round(nat["yield_t_ha"] * 1000, 1),
                "note_ko": "국가 FAOSTAT 단수(kg/ha). 벨트 라벨 아님.",
            }
        regions[belt.key] = {
            "label": belt.label,
            "label_ko": belt.label_ko,
            "forecast_available": False,
            "reason_ko": REASON,
            "weather_risk": risk,
            "weather_risk_note_ko": risk_note(risk, belt.hurricane_prone),
            "crops": {"banana": banana_crop},
        }
        research.append({
            "title_ko": f"기상 리스크 — {belt.label_ko}",
            "body_ko": risk_note(risk, belt.hurricane_prone),
            "links": [],
        })

    outlooks = []
    if nat:
        outlooks.extend([
            {
                "agency": "FAOSTAT (via OWID)",
                "agency_ko": "FAOSTAT",
                "season": str(nat["year"]),
                "metric_ko": "국가 바나나 생산량",
                "value": round(nat["production_t"]),
                "unit": "tonnes",
                "status_ko": "달력연도 국가 합계 · 벨트/농장 아님",
                "note_ko": faostat.get("note_ko", ""),
                "url": "https://ourworldindata.org/grapher/banana-production",
                "url_label": "OWID banana production",
            },
            {
                "agency": "FAOSTAT (via OWID)",
                "agency_ko": "FAOSTAT",
                "season": str(nat["year"]),
                "metric_ko": "국가 수확면적 (생산÷단수)",
                "value": round(nat["area_ha"]),
                "unit": "ha",
                "status_ko": "달력연도 국가 합계",
                "note_ko": "area_ha = production_t / yield_t_ha",
                "url": "https://ourworldindata.org/grapher/banana-yields",
                "url_label": "OWID banana yields",
            },
            {
                "agency": "FAOSTAT (via OWID)",
                "agency_ko": "FAOSTAT",
                "season": str(nat["year"]),
                "metric_ko": "국가 평균 단수",
                "value": round(nat["yield_t_ha"], 2),
                "unit": "t/ha",
                "status_ko": "국가 평균 · 수출 농장 단수와 다를 수 있음",
                "note_ko": "",
                "url": "https://ourworldindata.org/grapher/banana-yields",
                "url_label": "OWID banana yields",
            },
        ])
    outlooks.append({
        "agency": "FAO Banana Statistical Compendium",
        "agency_ko": "FAO 바나나 통계 요약",
        "season": str(export["year"]),
        "metric_ko": "신선 바나나 수출 (참고)",
        "value": export["value"],
        "unit": "1000 tonnes",
        "status_ko": shared["export_reference"]["vintage_note_ko"],
        "note_ko": "수출 ≠ 생산. " + meta.get("role_ko", ""),
        "url": shared["export_reference"]["url"],
        "url_label": "FAO bananas",
    })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": nat.get("year") or export["year"],
        "country": meta["country"],
        "title_ko": f"{meta['label_ko']} 바나나 참고·리스크",
        "forecast_available": False,
        "panel_mode": "reference",
        "reason_ko": REASON,
        "methodology_note": (
            "No YLWS. National FAOSTAT production/area via OWID + Compendium "
            "exports + optional POWER risk proxies. Never writes forecast point."
        ),
        "dashboard_url": shared.get("dashboard_url"),
        "government_outlooks": outlooks,
        "research_notes": research,
        "headline_risks_ko": meta.get("headline_risks_ko") or [],
        "sources": [
            {
                "name": "FAOSTAT bananas via Our World in Data",
                "url": "https://ourworldindata.org/grapher/banana-production",
                "supports": "national production / yield / implied area",
            },
            {
                "name": shared["export_reference"]["source"],
                "url": shared["export_reference"]["url"],
                "supports": "national export reference",
            },
            {
                "name": "NASA POWER",
                "url": "https://power.larc.nasa.gov/",
                "supports": "optional weather-risk proxies only",
            },
        ],
        "regions": regions,
    }


def main() -> int:
    with open(PROFILES, encoding="utf-8") as handle:
        shared = json.load(handle)
    with open(FAOSTAT, encoding="utf-8") as handle:
        faostat = json.load(handle)
    os.makedirs(PUBLIC, exist_ok=True)
    for key, meta in shared["countries"].items():
        payload = build_one(key, meta, shared, faostat)
        out = os.path.join(PUBLIC, FILE_FOR[key])
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
