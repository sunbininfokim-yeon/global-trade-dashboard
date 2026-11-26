#!/usr/bin/env python3
"""Build a review-only CPI movers and external-price sidebar payload."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from urllib.request import urlopen

from build_us_cpi_forward_validation import CONFIG, PUBLIC, read_json
from macro_monitor.cpi.forward_validation import monthly_changes, scan_lags, shift

ZORI_DATA = (
    "https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_sa_month.csv"
)
ZORI_PAGE = "https://www.zillow.com/research/data/"
SHELTER_RESEARCH = "https://www.frbsf.org/research-and-insights/publications/economic-letter/where-is-shelter-inflation-headed/"

EXTERNAL = [
    ("zori", ["shelter", "rent_primary", "owners_equivalent_rent"], "Zillow 시장 임대료",
     "중기 추세 참고", "신규 매물 임대료와 CPI 임차료의 방향이 갈리는지 확인", ZORI_PAGE),
    ("eia_gasoline", ["gasoline", "motor_fuel", "energy", "energy_commodities"], "EIA 주간 주유소 가격",
     "같은 달 참고", "주유소 가격의 월중 방향이 휘발유 CPI와 같은지 확인", "https://www.eia.gov/petroleum/gasdiesel/"),
    ("eia_jet", ["airline_fares"], "EIA 제트연료 현물가",
     "당월 나우캐스트 후보", "제트연료와 항공료가 같은 달에 같이 움직였는지 확인",
     "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=EER_EPJK_PF4_RGC_DPG"),
    ("manheim", ["used_cars_and_trucks"], "Manheim 중고차 도매가",
     "시장 참고", "월말 공표판뿐 아니라 월초 CPI 평가 시점 이전의 도매 움직임을 확인",
     "https://press.manheim.com/industry-resources"),
    ("food_inputs", ["food", "food_at_home"], "식품제조·운송 PPI와 브렌트유",
     "시차 후보", "가정식 CPI 반등에 앞서 가공·운송 가격도 올랐는지 확인",
     "https://fred.stlouisfed.org/series/PCU311311"),
]


def parse_zori(lines) -> dict[str, float]:
    match = [row for row in csv.DictReader(lines)
             if row.get("RegionName") == "United States" and row.get("RegionType") == "country"]
    if len(match) != 1:
        raise ValueError("ZORI national row missing or duplicated")
    points = {key[:7]: float(value) for key, value in match[0].items()
              if key and value and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", key)}
    return {month: value for month, value in points.items() if math.isfinite(value) and value > 0}


def rank_movers(movers: dict, basis: str) -> dict:
    key = basis + "_pct"
    source = ("up", "down") if basis == "mom" else ("yoy_up", "yoy_down")
    rows = {}
    for group in source:
        for row in movers.get(group, []):
            value = row.get(key)
            if isinstance(value, (int, float)) and math.isfinite(value):
                rows[row["id"]] = {"item_id": row["id"], "label_ko": row["label_ko"], "value_pct": value}
    up = sorted((v for v in rows.values() if v["value_pct"] > 0), key=lambda v: (-v["value_pct"], v["item_id"]))[:3]
    down = sorted((v for v in rows.values() if v["value_pct"] < 0), key=lambda v: (v["value_pct"], v["item_id"]))[:3]
    return {"basis": basis, "unit": "%", "scope": "tracked_movers_not_full_basket_or_contribution",
            "top3": up, "bottom3": down, "max_abs_pct": max((abs(r["value_pct"]) for r in up + down), default=None)}


def zori_observation(levels: dict[str, float]) -> dict:
    if not levels:
        return {"status": "unavailable"}
    month = max(levels)
    changes = monthly_changes(levels.items())
    year_ago = levels.get(shift(month, -12))
    return {"status": "observed", "reference_period": month, "published_at": None,
            "mom_pct": changes.get(month), "yoy_pct": (levels[month] / year_ago - 1) * 100 if year_ago else None}


def zori_diagnostic(history: dict, levels: dict[str, float], *, through: str) -> dict | None:
    target = next(row for row in history["series"] if row["series_id"] == "CUSR0000SEHA")
    target_mom = monthly_changes((row["date"], row["index"]) for row in target["observations"]
                                 if row["data_status"] == "observed")
    spec = {"id": "zillow_rent_to_cpi_rent", "relationship_map_id": None, "target": "cpi_rent",
            "controls": [], "terms": [("zori", i) for i in range(1, 13)], "minimum_train": 60,
            "calendar_effects": False, "mode": "lagged_inputs_only"}
    results = scan_lags(spec, {"cpi_rent": target_mom, "zori": monthly_changes(levels.items())},
                        cutoff="2026-07", through=through)
    return results[0] if results else None


def build(macro: dict, mapping: dict, history: dict, levels: dict[str, float]) -> dict:
    usa = next(country for country in macro["countries"] if country["iso3"] == "USA")
    cpi = next(ind for ind in usa["indicators"] if ind["id"] == "cpi_yoy")
    movers = cpi["movers"]
    ref = movers["reference_period"]
    external = [{"id": key, "item_ids": ids, "label_ko": label, "role_ko": role,
                 "watch_ko": watch, "source_url": url,
                 "observation": zori_observation(levels) if key == "zori" else {"status": "source_link_only"}}
                for key, ids, label, role, watch, url in EXTERNAL]
    return {
        "schema_version": "us-cpi-watch-v1", "reference_period": ref, "forecast_active": False,
        "movers": {basis: rank_movers(movers, basis) for basis in ("mom", "yoy")},
        "internal_pathways": [
            {**{k: row[k] for k in ("id", "type", "source_ids", "target_ids", "mechanism_ko")},
             "role_ko": "측정상 연결" if row["type"] == "measurement_link"
             else "공통 요인" if row["type"] == "common_driver" else "검토 후보"}
            for row in mapping["relationships"] if row["type"] != "external_input_required"
        ],
        "external_prices": external,
        "zori_research": {
            "source_url": SHELTER_RESEARCH, "status": "trend_watch_not_forecast",
            "vintage": "latest_vintage_replay_not_real_time",
            "training_cutoff": "2026-07", "screen_lags_months": [1, 12],
            "limitations_ko": "최신 개정 이력의 탐색이며 상한 시차 선택은 고정 시차의 근거가 아님. OER 별도 검정 아님.",
            "diagnostic": zori_diagnostic(history, levels, through=ref) if levels and ref > "2026-07" else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="build without fetching Zillow")
    args = parser.parse_args()
    levels: dict[str, float] = {}
    if not args.offline:
        try:
            with urlopen(ZORI_DATA, timeout=30) as response:
                levels = parse_zori(response.read().decode("utf-8-sig").splitlines())
        except (OSError, ValueError):
            print("Zillow observation unavailable; emitting source link only", file=sys.stderr)
    report = build(read_json(PUBLIC / "macro_monitor_v1.json"), read_json(CONFIG / "cpi_structure.map.json"),
                   read_json(PUBLIC / "us_cpi_api_history_v1.json"), levels)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
