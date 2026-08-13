"""Build race_progress_*_v1.json for in-progress races (KOR tour, USA rolling primaries)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "extracted"
PUB = ROOT.parents[1] / "public" / "data"
RAW_MIDTERM = ROOT / "raw" / "usa" / "themidtermproject_results_2026-08-08.txt"

STATE_KO = {
    "AL": "앨라배마",
    "AK": "알래스카",
    "AZ": "애리조나",
    "AR": "아칸소",
    "CA": "캘리포니아",
    "CO": "콜로라도",
    "CT": "코네티컷",
    "DE": "델라웨어",
    "FL": "플로리다",
    "GA": "조지아",
    "HI": "하와이",
    "ID": "아이다호",
    "IL": "일리노이",
    "IN": "인디애나",
    "IA": "아이오와",
    "KS": "캔자스",
    "KY": "켄터키",
    "LA": "루이지애나",
    "ME": "메인",
    "MD": "메릴랜드",
    "MA": "매사추세츠",
    "MI": "미시간",
    "MN": "미네소타",
    "MS": "미시시피",
    "MO": "미주리",
    "MT": "몬태나",
    "NE": "네브래스카",
    "NV": "네바다",
    "NH": "뉴햄프셔",
    "NJ": "뉴저지",
    "NM": "뉴멕시코",
    "NY": "뉴욕",
    "NC": "노스캐롤라이나",
    "ND": "노스다코타",
    "OH": "오하이오",
    "OK": "오클라호마",
    "OR": "오리건",
    "PA": "펜실베이니아",
    "RI": "로드아일랜드",
    "SC": "사우스캐롤라이나",
    "SD": "사우스다코타",
    "TN": "테네시",
    "TX": "텍사스",
    "UT": "유타",
    "VT": "버몬트",
    "VA": "버지니아",
    "WA": "워싱턴",
    "WV": "웨스트버지니아",
    "WI": "위스콘신",
    "WY": "와이오밍",
    "DC": "워싱턴DC",
}

# FEC-style primary date waves (2026 midterms). Not presidential-primary calendar.
PRIMARY_DATES: List[Tuple[str, List[str]]] = [
    ("2026-03-03", ["AR", "NC", "TX"]),
    ("2026-03-10", ["MS"]),
    ("2026-03-17", ["IL"]),
    ("2026-05-05", ["IN", "OH"]),
    ("2026-05-12", ["NE", "WV"]),
    ("2026-05-16", ["LA"]),
    ("2026-05-19", ["AL", "ID", "GA", "KY", "OR", "PA"]),
    ("2026-06-02", ["CA", "IA", "MT", "NJ", "NM", "SD"]),
    ("2026-06-09", ["ME", "NV", "ND", "SC"]),
    ("2026-06-16", ["DC", "OK"]),
    ("2026-06-23", ["MD", "NY", "UT"]),
    ("2026-06-30", ["CO"]),
    ("2026-07-21", ["AZ"]),
    ("2026-08-04", ["KS", "MI", "MO", "VA", "WA"]),
    ("2026-08-06", ["TN"]),
    ("2026-08-08", ["HI"]),
    ("2026-08-11", ["CT", "MN", "VT", "WI"]),
    ("2026-08-18", ["AK", "FL", "WY"]),
    ("2026-09-01", ["MA"]),
    ("2026-09-08", ["NH"]),
    ("2026-09-09", ["RI"]),
    ("2026-09-15", ["DE"]),
]


def _write(name: str, doc: Dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PUB.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    (OUT / name).write_text(text, encoding="utf-8")
    (PUB / name).write_text(text, encoding="utf-8")


def parse_midterm_winners(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Assign statewide winners to state via next House XX-## code in the scrape."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    house_pos: List[Tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        m = re.search(r"House — District \d+([A-Z]{2})-(\d+)", ln)
        if m:
            house_pos.append((i, m.group(1), m.group(2)))

    months = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    date_at: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = re.match(
            r"## (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (.+)$",
            ln,
        )
        if not m:
            continue
        dm = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})",
            m.group(1),
        )
        if dm:
            d = f"{int(dm.group(3)):04d}-{months[dm.group(1)]:02d}-{int(dm.group(2)):02d}"
            date_at.append((i, d))

    def date_for(line_i: int) -> Optional[str]:
        d = None
        for di, dd in date_at:
            if di <= line_i:
                d = dd
            else:
                break
        return d

    def next_state_from(line_i: int) -> Optional[str]:
        for hi, st, _ in house_pos:
            if hi > line_i:
                return st
        return None

    contests: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    office: Optional[str] = None
    for i, ln in enumerate(lines):
        strip = ln.strip()
        if strip == "U.S. Senate":
            office = "senate"
            continue
        if strip == "Governor":
            office = "governor"
            continue
        hm = re.search(r"House — District \d+([A-Z]{2})-(\d+)", ln)
        if hm:
            office = f"house_{hm.group(1)}-{hm.group(2)}"
            continue
        wm = re.match(r"✓([A-Za-z\'\-\. ]+?)([DR])(?:·inc)?(?:\+|\b)", strip)
        if not wm or not office:
            continue
        name = wm.group(1).strip()
        party = wm.group(2)
        d = date_for(i)
        if office.startswith("house_"):
            st = office.split("_")[1].split("-")[0]
            contests[st].append(
                {
                    "office": office.replace("house_", "house "),
                    "office_kind": "house",
                    "party": party,
                    "winner": name,
                    "date": d,
                    "status": "called",
                }
            )
        elif office in ("senate", "governor"):
            st = next_state_from(i)
            if not st:
                continue
            contests[st].append(
                {
                    "office": office,
                    "office_kind": office,
                    "party": party,
                    "winner": name,
                    "date": d,
                    "status": "called",
                }
            )
    return contests


def build_usa(as_of: str, now: str) -> Dict[str, Any]:
    contests = parse_midterm_winners(RAW_MIDTERM) if RAW_MIDTERM.exists() else {}
    units: List[Dict[str, Any]] = []
    for d, states in PRIMARY_DATES:
        for st in states:
            cs = contests.get(st, [])
            seen = set()
            uniq: List[Dict[str, Any]] = []
            for c in sorted(
                cs, key=lambda x: 0 if x["office_kind"] in ("senate", "governor") else 1
            ):
                k = (c["office"], c["party"])
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(c)
            statewide = [c for c in uniq if c["office_kind"] in ("senate", "governor")]
            house = [c for c in uniq if c["office_kind"] == "house"][:8]
            show = statewide + house
            parts = []
            for c in statewide:
                lab = "상원" if c["office"] == "senate" else "주지사"
                parts.append(f"{c['party']}:{c['winner']}({lab})")
            done = d <= as_of
            units.append(
                {
                    "id": st,
                    "name_en": st,
                    "name_ko": STATE_KO.get(st, st),
                    "date": d,
                    "status": "completed" if done else "scheduled",
                    "contests": show,
                    "contests_statewide": statewide,
                    "headline": (
                        " · ".join(parts)
                        if parts
                        else (
                            "프라이머리 실시 완료 — 하원 등 세부 확장 중"
                            if done
                            else "미실시"
                        )
                    ),
                    "ui_click": "show contests list for this state",
                }
            )

    completed = [u for u in units if u["status"] == "completed"]
    pending = [u for u in units if u["status"] == "scheduled"]
    with_sw = [u for u in completed if u["contests_statewide"]]
    aggregation = {
        "model_id": "independent_jurisdiction_first_past_post",
        "model_label_ko": "주·선거구 독립 · 다수결 공천",
        "like_usa_equal_units": True,
        "summary_ko": (
            "2026 중간선거 프라이머리는 전국 단일 점수가 없다. 주(또는 하원 선거구)마다 "
            "후보자 명부를 따로 뽑고, 그 승자가 11/3 총선 후보가 된다. "
            "대시보드 누적 states_completed 은 “실시한 주 개수”이지, "
            "대선 선거인단처럼 주를 가중 합산한 점수가 아니다."
        ),
        "components": [
            {
                "id": "state_or_district_primary",
                "label_ko": "주·선거구 프라이머리",
                "final_weight_pct": None,
                "unit": "해당 관할 유권자 표",
                "equal_weight_across_regions": False,
                "notes_ko": [
                    "관할 간 표 합산 없음",
                    "상원·주지사: 주 전역 / 하원: 선거구",
                ],
            },
            {
                "id": "dashboard_progress_counter",
                "label_ko": "진행률 카운터(UI)",
                "final_weight_pct": None,
                "unit": "주 개수",
                "equal_weight_across_regions": True,
                "notes_ko": [
                    "1주=1 카운트는 일정 진척용",
                    "전국 공천 지지율 평균 산출에 쓰지 않음",
                ],
            },
        ],
        "interim_display": {
            "what_we_show": "per_state_winners_running_calendar",
            "is_final_score": False,
            "national_weighted_score": False,
            "user_caution_ko": "주 클릭 = 그 주 공천 승자. 누적 바는 전국 가중이 아님.",
        },
        "unit_aggregation": {
            "unit": "state (primary date wave)",
            "cross_unit_method": "none_independent",
            "progress_counter": "equal_weight_per_state_for_schedule_only",
            "not": "electoral_college_or_delegate_math",
        },
        "not_in_scope_2026": {
            "presidential_primary_delegates": {
                "when": "2028 cycle",
                "model_id": "delegate_allocation_by_party_state_rules",
                "summary_ko": (
                    "대선 경선은 주·당 규칙으로 대표(delegate) 배분. "
                    "주 균등 1표가 아님. 2026 중간 보드 미적용."
                ),
            }
        },
        "general_election_note_ko": (
            "11/3 총선 의석은 seat count(이긴 관할 수). 전국 표 비중≠의석 비중."
        ),
    }
    return {
        "schema": "race_progress_v1",
        "iso3": "USA",
        "as_of": as_of,
        "as_of_iso": now,
        "mode": "rolling_state_primary_midterms",
        "status": "ongoing",
        "race": {
            "id": "usa-2026-midterm-primaries",
            "label_ko": "중간선거 주별 프라이머리 (누적)",
            "label_en": "2026 rolling state primaries",
            "general_date": "2026-11-03",
            "note_ko": (
                "2026은 대선 경선 해 아님(대선 프라이머리 2028). "
                "주마다 상·하원·주지사 공천자를 뽑고 누적. 주 클릭 → 당별 승자. "
                "누적은 일정 진척(주 개수)이지 전국 가중 점수가 아님."
            ),
            "ui_hint": "map_or_timeline_click_state",
        },
        "aggregation": aggregation,
        "rules": {
            "aggregation_model": "independent_jurisdiction_first_past_post",
            "equal_weight_states_for_progress_only": True,
            "national_hybrid_score": False,
            "presidential_delegate_math": "없음_2026",
        },
        "cumulative": {
            "as_of": as_of,
            "states_in_calendar": len(units),
            "states_completed": len(completed),
            "states_pending": len(pending),
            "states_with_statewide_winners_parsed": len(with_sw),
            "general_election": "2026-11-03",
            "next_waves": pending[:6],
        },
        "units": sorted(units, key=lambda u: (u["date"], u["id"])),
        "ui": {
            "summary_card": "states_completed / states_in_calendar",
            "list": "units sorted by date; completed dimmed green",
            "detail_on_click": "contests_statewide + contests (house sample)",
            "null_policy": {"없음": "해당 없음", "불명": "미집계"},
        },
        "sources": [
            {
                "id": "fec_primary_dates",
                "url": "https://www.fec.gov/resources/cms-content/documents/2026pdates.pdf",
            },
            {
                "id": "themidtermproject",
                "url": "https://themidtermproject.org/results",
                "grade": "aggregator",
                "parse_note": "statewide winners linked via next House state code",
                "raw": str(RAW_MIDTERM.relative_to(ROOT)) if RAW_MIDTERM.exists() else "없음",
            },
        ],
    }


def main() -> int:
    as_of = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    # Prefer existing KOR snapshot; do not invent tour numbers here.
    kor_path = OUT / "race_progress_kor_v1.json"
    if kor_path.exists():
        kor = json.loads(kor_path.read_text(encoding="utf-8"))
    else:
        kor = {
            "schema": "race_progress_v1",
            "iso3": "KOR",
            "status": "불명",
            "note": "extract_kor / manual tour interim required",
        }
    usa = build_usa(as_of=as_of, now=now)
    _write("race_progress_usa_v1.json", usa)
    _write("race_progress_kor_v1.json", kor)
    bundle = {
        "schema": "race_progress_bundle_v1",
        "as_of": as_of,
        "generated_at": now,
        "races": [kor, usa],
        "ui_contract": {
            "ongoing_races": "show progress UI",
            "korea": "권역 리스트 + 클릭 시 %/득표 · 시도 서브",
            "usa": "주 롤링 타임라인 + 클릭 시 당 공천 승자",
        },
    }
    _write("race_progress_bundle_v1.json", bundle)
    print(
        json.dumps(
            {
                "usa_completed": usa["cumulative"]["states_completed"],
                "usa_pending": usa["cumulative"]["states_pending"],
                "with_statewide": usa["cumulative"]["states_with_statewide_winners_parsed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
