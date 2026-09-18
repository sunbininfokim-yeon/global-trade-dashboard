"""Classify White House / EOP seats as filled, unconfirmed, or vacant.

Vacant is only when an official body says the seat is empty. A page without a
name is unconfirmed, not vacant. Media names are not promoted.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

CEA_URL = "https://www.whitehouse.gov/cea/"
CEQ_URL = "https://www.whitehouse.gov/ceq/"
ONDCP_URL = "https://www.whitehouse.gov/ondcp/"
ONDCP_CONFIRM_URL = "https://www.whitehouse.gov/releases/2026/01/sara-carter-confirmed-as-drug-czar/"
PIAB_APPOINT_URL = "https://www.whitehouse.gov/presidential-actions/2025/02/president-trump-announces-the-presidents-intelligence-advisory-board/"
PCLOB_BOARD_URL = "https://www.pclob.gov/Board"
MANION_NOMINATION_URL = "https://www.whitehouse.gov/presidential-actions/2026/07/nominations-and-withdrawals-sent-to-the-senate-e958/"

CEA_CHAIR_RE = re.compile(
    r"Under President Trump,\s+(.+?)\s+serves as (?:Acting )?Chair(?:man)?",
    re.IGNORECASE,
)

POLICY_KO = (
    "공석은 공식 기관이 공석·의장석 공석이라고 적을 때만. "
    "공식 페이지에 이름이 없으면 미확인이지 공석이 아니다. "
    "언론 보도 이름은 자동 승격하지 않는다."
)


def parse_cea_chair(html: str) -> Optional[Dict[str, Any]]:
    if not html:
        return None
    match = CEA_CHAIR_RE.search(html)
    if not match:
        return None
    name = re.sub(r"\s+", " ", match.group(1)).strip(" .")
    if not name or len(name) > 80:
        return None
    acting = bool(re.search(r"serves as Acting Chair", html, re.I))
    return {
        "name_en": name,
        "status": "acting" if acting else "incumbent",
        "source": "wh_cea",
        "source_grade": "official",
        "official_url": CEA_URL,
    }


def ceq_names_chair(html: str) -> bool:
    if not html:
        return False
    return bool(re.search(r"Chair(?:man)?(?: of the Council)?[:\s]+[A-Z]", html))


def classify_unscoped_kind(row: Dict[str, Any]) -> Dict[str, Any]:
    title_u = row.get("title_u") or str(row.get("office_en") or row.get("title") or "").upper()
    status = str(row.get("payroll_status") or row.get("status") or "")
    salary = float(row.get("wh_salary_usd") if row.get("wh_salary_usd") is not None else row.get("salary_usd") or 0)
    if re.search(r"DEPUTY ASSISTANT TO THE PRESIDENT AND ADVISOR$", title_u):
        kind = "political_deputy_unscoped"
        kind_ko = "정무특보(부보좌관급). 직함에 담당 주제가 없을 뿐 자리가 비어 있지 않다."
    elif status == "DETAILEE":
        kind = "detailee_unscoped"
        kind_ko = "타 기관 파견 Senior Advisor. 담당은 직함에 없다. 정무특보로 단정하지 않는다. 공석이 아니다."
    elif salary == 0:
        kind = "unpaid_senior_unscoped"
        kind_ko = "급여 $0 Senior Advisor(겸임·무급 형태). 담당은 직함에 없다. 공석이 아니다."
    else:
        kind = "staff_senior_unscoped"
        kind_ko = "백악관 직원 Senior Advisor. ATP/정무특보 급이 아니다. 담당은 직함에 없다. 공석이 아니다."
    extra: Dict[str, Any] = {
        "kind": kind,
        "kind_ko": kind_ko,
        "portfolio_in_title": False,
        "vacant": False,
    }
    if row.get("name_en") == "Jason D. Manion":
        extra["later_official_ko"] = (
            "급여명부 기준일 이후 2026-07-14 백악관이 연방 양형위원회 위원으로 상원 지명. "
            "그때도 WH 담당 주제는 직함에 없다."
        )
        extra["later_official_url"] = MANION_NOMINATION_URL
    return extra


def enrich_unscoped_senior_advisors(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        item = dict(row)
        item.update(classify_unscoped_kind(item))
        item["note_ko"] = item.get("kind_ko") or item.get("note_ko")
        out.append(item)
    return out


def build_office_status(
    *,
    as_of: str,
    cea: Optional[Dict[str, Any]] = None,
    ceq_html: Optional[str] = None,
) -> Dict[str, Any]:
    cea = cea or {}
    offices = [
        {
            "id": "vp_chief_of_staff",
            "office_ko": "부통령 비서실장",
            "seat_status": "incumbent_unconfirmed",
            "vacant": False,
            "ui_ko": "미확인 (공석 아님)",
            "display": "unconfirmed_not_vacant",
            "name_en": None,
            "note_ko": (
                "부통령실은 WHO 급여명부에 없다. 공식 부통령실 명부를 못 잡아 현직을 넣지 않는다. "
                "백악관이 공석이라고 밝힌 적은 없다. 언론 후임은 승격하지 않는다."
            ),
        },
        {
            "id": "cea",
            "office_ko": "경제자문위원회 의장",
            "seat_status": "filled_official" if cea.get("name_en") else "incumbent_unconfirmed",
            "vacant": False,
            "ui_ko": "현직" if cea.get("name_en") else "미확인 (공석 아님)",
            "display": "show_name" if cea.get("name_en") else "unconfirmed_not_vacant",
            "name_en": cea.get("name_en"),
            "status": cea.get("status"),
            "source_url": CEA_URL,
            "source_grade": "official" if cea.get("name_en") else None,
            "note_ko": "whitehouse.gov/cea/ About 문구의 Chairman." if cea.get("name_en") else "CEA 공식 페이지에서 의장을 못 읽음.",
        },
        {
            "id": "ceq",
            "office_ko": "환경품질위원회 의장",
            "seat_status": "incumbent_unconfirmed",
            "vacant": False,
            "ui_ko": "미확인 (공석 아님)",
            "display": "unconfirmed_not_vacant",
            "name_en": None,
            "source_url": CEQ_URL,
            "note_ko": (
                "whitehouse.gov/ceq/ About에 의장 이름이 없다. 공석 선언은 없다. "
                "언론 직무대행은 넣지 않는다."
                + ("" if not ceq_names_chair(ceq_html or "") else " (파서가 의장명을 본 경우 이 칸을 갱신해야 한다.)")
            ),
        },
        {
            "id": "ondcp",
            "office_ko": "국가마약통제국장",
            "seat_status": "filled_official",
            "vacant": False,
            "ui_ko": "현직",
            "display": "show_name",
            "name_en": "Sara Carter",
            "status": "incumbent",
            "source_url": ONDCP_CONFIRM_URL,
            "source_grade": "official",
            "as_of": "2026-01-06",
            "note_ko": (
                "2026-01-06 백악관 발표: 상원이 Sara Carter를 ONDCP 국장으로 인준. "
                "ondcp 소개 페이지는 이름을 안 적지만 공석이 아니다. "
                "2026-05 국가마약통제전략 서한도 Director Sara Carter."
            ),
        },
        {
            "id": "whmo",
            "office_ko": "백악관 군사실장",
            "seat_status": "out_of_who_payroll",
            "vacant": False,
            "ui_ko": "미확인 (공석 아님)",
            "display": "unconfirmed_not_vacant",
            "name_en": None,
            "note_ko": (
                "WHMO 국장은 군 파견 보직이라 WHO 민간 급여명부에 없다. "
                "백악관 공식 국장 페이지를 못 잡았다. 위키 이름은 쓰지 않는다. 공석으로 단정하지 않는다."
            ),
        },
        {
            "id": "piab",
            "office_ko": "대통령 정보자문위원회 의장",
            "seat_status": "filled_last_official_appointment",
            "vacant": False,
            "ui_ko": "현직 (2025 임명, 2026 명부 미갱신)",
            "display": "show_name_with_as_of",
            "name_en": "Devin Gerald Nunes",
            "status": "chair",
            "as_of": "2025-02-11",
            "source_url": PIAB_APPOINT_URL,
            "source_grade": "official",
            "note_ko": (
                "2025-02-11 백악관이 Devin Gerald Nunes를 PIAB Chair로 임명 발표. "
                "2026 갱신 명부는 없다. 공석 선언은 없다."
            ),
        },
        {
            "id": "pclob_chair",
            "office_ko": "사생활·시민자유 감독위원회 의장",
            "seat_status": "vacant_official",
            "vacant": True,
            "ui_ko": "공석",
            "display": "show_vacant",
            "name_en": None,
            "source_url": PCLOB_BOARD_URL,
            "source_grade": "official",
            "note_ko": (
                "PCLOB 공식 이사회: 의장 Sharon Bradford Franklin 임기 2022-02~2025-01로 끝. "
                "현 표기는 Board Member Beth A. Williams만 Present. "
                "2026-04 보고서도 Chair is Vacant 정책을 인용. 의장석은 공석. 위원회 자체 폐지는 아님."
            ),
            "sitting_member_en": "Beth A. Williams",
        },
    ]
    return {
        "schema": "usa_wh_office_status_v1",
        "as_of": as_of,
        "policy_ko": POLICY_KO,
        "offices": offices,
    }


def apply_office_status(eop: Dict[str, Any], status: Dict[str, Any]) -> List[str]:
    changes: List[str] = []
    eop["office_status"] = status
    by_id = {row["id"]: row for row in status.get("offices") or []}

    cea_status = by_id.get("cea") or {}
    if cea_status.get("name_en"):
        for head in eop.get("eop_office_heads") or []:
            if head.get("id") != "cea":
                continue
            if head.get("name_en") != cea_status["name_en"] or head.get("source_grade") != "official":
                changes.append(f"eop_office_heads.cea -> {cea_status['name_en']} official")
            head["name_en"] = cea_status["name_en"]
            head["status"] = cea_status.get("status") or "incumbent"
            head["source"] = "wh_cea"
            head["source_grade"] = "official"
            head["official_url"] = CEA_URL
            head.pop("note_ko", None)

    ondcp = by_id.get("ondcp") or {}
    heads = eop.setdefault("eop_office_heads", [])
    existing = next((h for h in heads if h.get("id") == "ondcp"), None)
    if ondcp.get("name_en"):
        payload = {
            "id": "ondcp",
            "office_ko": "국가마약통제국장",
            "office_en": "Director, Office of National Drug Control Policy",
            "name_en": ondcp["name_en"],
            "status": "incumbent",
            "source": "wh_ondcp_confirm",
            "source_grade": "official",
            "official_url": ONDCP_URL,
            "note_ko": ondcp.get("note_ko"),
        }
        if existing:
            if existing.get("name_en") != payload["name_en"]:
                changes.append(f"eop_office_heads.ondcp {existing.get('name_en')} -> {payload['name_en']}")
            existing.update(payload)
        else:
            heads.append(payload)
            changes.append("eop_office_heads.ondcp added Sara Carter")

    for head in heads:
        if head.get("id") == "ceq":
            head["name_en"] = None
            head["status"] = "unconfirmed"
            head["vacant"] = False
            head["source_grade"] = "official_page_no_incumbent"
            head["source"] = "wh_ceq"
            head["official_url"] = CEQ_URL
            head["note_ko"] = (by_id.get("ceq") or {}).get("note_ko")
            changes.append("eop_office_heads.ceq unconfirmed_not_vacant")

    missing = set(eop.get("missing") or [])
    missing.discard("official_cea_whitehouse_page")
    missing.add("official_vice_president_office_roster")
    missing.add("official_ceq_incumbent_page")
    missing.add("official_whmo_director_page")
    eop["missing"] = sorted(missing)

    vp = next((row for row in eop.get("core") or [] if row.get("id") == "vp_chief_of_staff"), None)
    if vp:
        vp["status"] = "unconfirmed"
        vp["vacant"] = False
        vp["ui_ko"] = "미확인 (공석 아님)"
        vp["note_ko"] = (by_id.get("vp_chief_of_staff") or {}).get("note_ko")
    return changes
