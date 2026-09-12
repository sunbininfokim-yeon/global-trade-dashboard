"""Classify White House topical advisors from the WHO payroll PDF.

This is the NSA-style list: named-portfolio advisors, czars, envoys, and faith
staff. It is not EOP office heads (OMB, ONDCP, CEA, CEQ, OSTP) and not the
generic 'policy advisor' pool.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

STAFF_FUNCTION_SKIP = (
    "PRESS ADVISOR",
    "COMMUNICATIONS ADVISOR",
    "TECHNICAL ADVISOR",
    "RECORDS MANAGEMENT",
    "DIRECTOR OF OPERATIONS TO THE SPECIAL ENVOY",
    "LEGISLATIVE AFFAIRS LIAISON",
    "ASSOCIATE COUNSEL",
    "PUBLIC LIAISON",
)

# First matching rule wins. Needles are uppercase.
DOMAIN_RULES: List[Tuple[str, str, str]] = [
    ("national_security", "국가안보", "NATIONAL SECURITY ADVISOR"),
    ("homeland_security", "국토안보", "HOMELAND SECURITY ADVISOR"),
    ("peace", "평화 특사", "SPECIAL ENVOY FOR PEACE"),
    ("ukraine", "우크라이나 특사", "SPECIAL ENVOY TO UKRAINE"),
    ("border", "국경", "BORDER CZAR"),
    ("pardon", "사면", "PARDON CZAR"),
    ("faith", "신앙", "FAITH"),
    ("jewish_outreach", "유대인 아웃리치", "JEWISH OUTREACH"),
    ("trade", "무역·제조", "TRADE AND MANUFACTURING"),
    ("trade", "무역·제조", "INTERNATIONAL TRADE"),
    ("international_economy", "국제경제", "INTERNATIONAL ECONOMIC RELATIONS"),
    ("coalition", "연대·연합", "COALITION POLICY"),
    ("economic_policy", "경제정책", "ASSISTANT TO THE PRESIDENT FOR ECONOMIC POLICY"),
    ("presidential_policy", "정책", "ASSISTANT TO THE PRESIDENT FOR POLICY"),
    ("digital_assets", "디지털자산", "DIGITAL ASSETS"),
]

JUNIOR_POLICY_SKIP = (
    "SENIOR POLICY ADVISOR",
    "ASSOCIATE POLICY ADVISOR",
    "DOMESTIC POLICY ADVISOR",
    "POLICY ADVISOR",
)

INCLUSION_KO = (
    "WHO 연례 직원보고서에서 담당 주제가 직함에 적힌 보좌관·특보·차르·특사·신앙 라인만 넣는다. "
    "국가안보보좌관과 같은 급의 주제별 보좌와, 직함에 주제가 있는 디지털자산 자문위 사무 책임자를 포함한다."
)
EXCLUSION_KO = (
    "OMB·ONDCP·CEA·CEQ·OSTP 국실장, NEC/DPC/NEDC 실장 전용 직함, "
    "일반 Policy Advisor, 대변·기록·기술·의회 연락 보좌는 제외. "
    "직함에 담당 주제가 없는 Senior Advisor는 unscoped_senior_advisors에만 둔다."
)


def _slug(domain: str, name_en: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name_en or "").lower()).strip("-")
    return f"{domain}-{base}" if base else domain


def payroll_rank(title_u: str) -> str:
    if "DEPUTY ASSISTANT TO THE PRESIDENT" in title_u:
        return "deputy_assistant"
    if "SPECIAL ASSISTANT TO THE PRESIDENT" in title_u:
        return "special_assistant"
    if "ASSISTANT TO THE PRESIDENT" in title_u:
        return "assistant_to_the_president"
    if "SENIOR ADVISOR" in title_u:
        return "senior_advisor"
    if "CZAR" in title_u or "ENVOY" in title_u:
        return "special_role"
    if "DEPUTY DIRECTOR" in title_u:
        return "deputy_director"
    if "EXECUTIVE DIRECTOR" in title_u:
        return "executive_director"
    return "other"


def _domain_for(title_u: str) -> Optional[Tuple[str, str]]:
    for domain, domain_ko, needle in DOMAIN_RULES:
        if needle not in title_u:
            continue
        if domain == "presidential_policy" and "ECONOMIC POLICY" in title_u:
            continue
        if domain in {"economic_policy", "presidential_policy"} and (
            "DEPUTY ASSISTANT" in title_u or "SPECIAL ASSISTANT" in title_u
        ):
            continue
        return domain, domain_ko
    return None


def classify_topical_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title_u = row.get("title_u") or str(row.get("title") or "").upper()
    if any(skip in title_u for skip in STAFF_FUNCTION_SKIP):
        return None
    if any(skip in title_u for skip in JUNIOR_POLICY_SKIP) and "FAITH" not in title_u:
        return None
    matched = _domain_for(title_u)
    if not matched:
        return None
    domain, domain_ko = matched
    return {
        "id": _slug(domain, row.get("name_en") or ""),
        "domain": domain,
        "domain_ko": domain_ko,
        "office_en": row.get("title"),
        "name_en": row.get("name_en"),
        "rank": payroll_rank(title_u),
        "wh_salary_usd": row.get("salary_usd"),
        "payroll_status": row.get("status"),
        "source": "wh_staff_report",
    }


def classify_unscoped_senior(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title_u = row.get("title_u") or str(row.get("title") or "").upper()
    if any(skip in title_u for skip in STAFF_FUNCTION_SKIP):
        return None
    if "SENIOR POLICY ADVISOR" in title_u:
        return None
    if _domain_for(title_u):
        return None
    unscoped = False
    if "SENIOR ADVISOR" in title_u and not re.search(r"SENIOR ADVISOR (FOR|TO THE) ", title_u):
        unscoped = True
    if re.search(r"DEPUTY ASSISTANT TO THE PRESIDENT AND ADVISOR$", title_u):
        unscoped = True
    if not unscoped:
        return None
    return {
        "id": _slug("unscoped", row.get("name_en") or ""),
        "office_en": row.get("title"),
        "name_en": row.get("name_en"),
        "rank": payroll_rank(title_u),
        "wh_salary_usd": row.get("salary_usd"),
        "note_ko": "직함에 담당 주제가 없어 주제별 보좌관 명단에 넣지 않음.",
        "source": "wh_staff_report",
    }


def classify_topical_advisors(payroll_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    topical: List[Dict[str, Any]] = []
    unscoped: List[Dict[str, Any]] = []
    seen = set()
    for row in payroll_rows:
        item = classify_topical_row(row)
        if item:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            topical.append(item)
            continue
        leftover = classify_unscoped_senior(row)
        if leftover and leftover["id"] not in seen:
            seen.add(leftover["id"])
            unscoped.append(leftover)
    topical.sort(key=lambda row: (row["domain"], row.get("rank") or "", row.get("name_en") or ""))
    unscoped.sort(key=lambda row: row.get("name_en") or "")
    return {
        "schema": "usa_wh_topical_advisors_v1",
        "inclusion_ko": INCLUSION_KO,
        "exclusion_ko": EXCLUSION_KO,
        "members": topical,
        "unscoped_senior_advisors": unscoped,
        "counts": {
            "topical": len(topical),
            "unscoped_senior_advisors": len(unscoped),
            "by_domain": _count_by(topical, "domain"),
        },
    }


def _count_by(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "")
        out[label] = out.get(label, 0) + 1
    return dict(sorted(out.items()))
