"""Classify White House / EOP seats as filled, unconfirmed, or vacant.

Vacant is only when an official body says the seat is empty. A page without a
name is unconfirmed, not vacant. A single media report is not promoted; a name
backed by two independent reliable outlets (at least one citing an official)
fills the seat as source_grade "reported_reliable", labelled 보도 기준 and kept
out of the official name_en field.
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
    "언론 보도 하나로는 승격하지 않는다. 서로 다른 신뢰 매체 2곳 이상(그중 하나는 "
    "정부 관계자 확인 인용)이 같은 이름을 대면 '보도 기준'(reported_reliable)으로 채우고, "
    "공식 원문이 이름을 적으면 그쪽이 덮어쓴다."
)

REPORTED_FILLS: Dict[str, Dict[str, Any]] = {
    "vp_chief_of_staff": {
        "name_en": "Nick Luna",
        "role_en": "Assistant to the President and Chief of Staff to the Vice President",
        "status_ko": "보도 기준",
        "since": "2026-08",
        "predecessor": {
            "name_en": "Jacob B. Reses",
            "term": "2025-01-20 ~ 2026-08",
            "departure_source_url": "https://www.foxnews.com/politics/vice-president-jd-vances-chief-staff-set-depart-white-house-role",
        },
        "sources": [
            {
                "org": "Federal News Network (Leadership Connect)",
                "date": "2026-08-28",
                "url": "https://federalnewsnetwork.com/leadership-connect/2026/08/federal-movers-shakers-august-28/",
                "claim": "Assistant to the President and Chief of Staff to the Vice President, Presidential Appointment",
            },
            {
                "org": "Punchbowl News",
                "date": "2026-06-16",
                "url": "https://punchbowl.news/article/white-house/nick-luna-vance/",
                "claim": "Luna to replace Jacob Reses as Vance's chief of staff",
            },
        ],
        "note_ko": (
            "부통령실은 WHO 급여명부 밖이고 공식 부통령실 명부가 없다. "
            "Federal News Network(2026-08-28, Leadership Connect 인사 기록)와 Punchbowl(2026-06-16)이 "
            "Nick Luna 취임을 전한다. 전임 Jacob B. Reses는 2026-06-11 부통령 성명과 함께 여름 말 퇴임 발표. "
            "공식 원문이 아니므로 '보도 기준'."
        ),
    },
    "ceq": {
        "name_en": "Rachael McNitt",
        "role_en": "Acting Chair, Council on Environmental Quality",
        "status_ko": "직무대행 · 보도 기준",
        "since": "2026-07-07",
        "predecessor": {
            "name_en": "Katherine Scarlett",
            "term": "2025-09-18 ~ 2026-07-07",
            "confirmation_url": "https://www.whitehouse.gov/releases/2025/09/katherine-scarlett-confirmed-as-13th-chair-of-the-council-on-environmental-quality/",
            "last_official_roster_url": "https://www.whitehouse.gov/wp-content/uploads/2026/04/CEQ-Employee-List-April-2026-FINAL.pdf.pdf",
        },
        "sources": [
            {
                "org": "The Hill",
                "date": "2026-07-07",
                "url": "https://thehill.com/policy/energy-environment/5957787-ceq-white-house-environment/",
                "claim": "McNitt serving as acting chair, per an administration official",
            },
            {
                "org": "E&E News (POLITICO)",
                "date": "2026-07-07",
                "url": "https://www.eenews.net/articles/ceq-chair-leaving-the-administration/",
                "claim": "McNitt will perform the duties of chair, per a White House official",
            },
        ],
        "note_ko": (
            "Katherine Scarlett: 2025-09-18 상원 인준(백악관 발표), 2026-04 CEQ 공식 직원명단에 Chairman. "
            "2026-07-07 퇴임(The Hill·E&E News, 정부 관계자 확인). 그 뒤 비서실장 Rachael McNitt이 "
            "직무대행이라고 두 매체가 정부 관계자를 인용해 보도. 4월 이후 CEQ 공식 명단이 없어 '보도 기준'. "
            "후임 지명은 확인되지 않았다."
        ),
    },
}


def reported_fill(office_id: str) -> Optional[Dict[str, Any]]:
    fill = REPORTED_FILLS.get(office_id)
    if not fill or len(fill.get("sources") or []) < 2:
        return None
    return fill


def reported_ui_ko(fill: Dict[str, Any]) -> str:
    return f"{fill['name_en']} · {fill['status_ko']}"


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
    vp_fill = reported_fill("vp_chief_of_staff")
    ceq_fill = None if ceq_names_chair(ceq_html or "") else reported_fill("ceq")
    offices = [
        {
            "id": "vp_chief_of_staff",
            "office_ko": "부통령 비서실장",
            "seat_status": "filled_reported" if vp_fill else "incumbent_unconfirmed",
            "vacant": False,
            "ui_ko": reported_ui_ko(vp_fill) if vp_fill else "미확인 (공석 아님)",
            "display": "unconfirmed_not_vacant",
            "name_en": None,
            "source_grade": "reported_reliable" if vp_fill else None,
            "reported": vp_fill,
            "note_ko": vp_fill["note_ko"] if vp_fill else (
                "부통령실은 WHO 급여명부에 없다. 공식 부통령실 명부를 못 잡아 현직을 넣지 않는다. "
                "백악관이 공석이라고 밝힌 적은 없다."
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
            "seat_status": "filled_reported" if ceq_fill else "incumbent_unconfirmed",
            "vacant": False,
            "ui_ko": reported_ui_ko(ceq_fill) if ceq_fill else "미확인 (공석 아님)",
            "display": "unconfirmed_not_vacant",
            "name_en": None,
            "source_url": CEQ_URL,
            "source_grade": "reported_reliable" if ceq_fill else None,
            "reported": ceq_fill,
            "note_ko": ceq_fill["note_ko"] if ceq_fill else (
                "whitehouse.gov/ceq/ About에 의장 이름이 없다. 공석 선언은 없다."
                + ("" if not ceq_names_chair(ceq_html or "") else " (파서가 의장명을 봤다. 이 칸을 공식 이름으로 갱신해야 한다.)")
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
                "WHMO 국장은 WHO 2026-07-01 급여명부에 없다. 백악관 공식 국장 페이지도 없다. "
                "2025 이후 임명을 전한 신뢰 매체 보도를 찾지 못했다. 위키백과 표의 무출처 이름은 쓰지 않는다. "
                "공석으로 단정하지 않는다."
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

    ceq_row = by_id.get("ceq") or {}
    ceq_fill = ceq_row.get("reported")
    for head in heads:
        if head.get("id") == "ceq":
            head["vacant"] = False
            head["source"] = "wh_ceq"
            head["official_url"] = CEQ_URL
            head["note_ko"] = ceq_row.get("note_ko")
            if ceq_fill:
                if head.get("name_en") != ceq_fill["name_en"]:
                    changes.append(f"eop_office_heads.ceq -> {ceq_fill['name_en']} reported_reliable")
                head["name_en"] = ceq_fill["name_en"]
                head["status"] = ceq_fill["status_ko"]
                head["since"] = ceq_fill["since"]
                head["source_grade"] = "reported_reliable"
                head["reported"] = ceq_fill
            else:
                head["name_en"] = None
                head["status"] = "unconfirmed"
                head["source_grade"] = "official_page_no_incumbent"
                head.pop("reported", None)
                changes.append("eop_office_heads.ceq unconfirmed_not_vacant")

    missing = set(eop.get("missing") or [])
    missing.discard("official_cea_whitehouse_page")
    missing.add("official_vice_president_office_roster")
    missing.add("official_ceq_incumbent_page")
    missing.add("official_whmo_director_page")
    eop["missing"] = sorted(missing)

    vp = next((row for row in eop.get("core") or [] if row.get("id") == "vp_chief_of_staff"), None)
    if vp:
        vp_row = by_id.get("vp_chief_of_staff") or {}
        vp_fill = vp_row.get("reported")
        vp["vacant"] = False
        vp["ui_ko"] = vp_row.get("ui_ko") or "미확인 (공석 아님)"
        vp["note_ko"] = vp_row.get("note_ko")
        vp.pop("reported_successor_unconfirmed", None)
        if vp_fill:
            if vp.get("name_en") != vp_fill["name_en"]:
                changes.append(f"core.vp_chief_of_staff -> {vp_fill['name_en']} reported_reliable")
            vp["name_en"] = vp_fill["name_en"]
            vp["status"] = vp_fill["status_ko"]
            vp["since"] = vp_fill["since"]
            vp["source_grade"] = "reported_reliable"
            vp["official_url"] = None
            vp["reported"] = vp_fill
            vp["predecessor"] = vp_fill["predecessor"]
        else:
            vp["name_en"] = None
            vp["status"] = "unconfirmed"
            vp.pop("reported", None)
    return changes
