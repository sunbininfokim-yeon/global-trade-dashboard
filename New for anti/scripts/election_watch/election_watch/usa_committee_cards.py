"""Pre-join standing-committee cards for 정책-미국.

Leadership comes from Clerk XML / Senate CVC (via usa_committees.json).
Agency rows come only from data/policy/committee-agency-jurisdictions.json
(House Rule X / Senate Rule XXV clauses that name a department). URLs use
official ID templates — never lastname.house.gov / lastname.senate.gov.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

EW_ROOT = Path(__file__).resolve().parents[1]
OUT = EW_ROOT / "config" / "extracted"

# 2026-09-06 https://www.congress.gov/committees — clerk comcode → system code.
# Standing House parents only. Joint / select codes are not emitted as cards.
HOUSE_CLERK_TO_CONGRESS = {
    "AG00": ("house", "hsag00"),
    "AP00": ("house", "hsap00"),
    "AS00": ("house", "hsas00"),
    "BA00": ("house", "hsba00"),
    "BU00": ("house", "hsbu00"),
    "ED00": ("house", "hsed00"),
    "FA00": ("house", "hsfa00"),
    "GO00": ("house", "hsgo00"),
    "HA00": ("house", "hsha00"),
    "HM00": ("house", "hshm00"),
    "IF00": ("house", "hsif00"),
    "II00": ("house", "hsii00"),
    "JU00": ("house", "hsju00"),
    "PW00": ("house", "hspw00"),
    "RU00": ("house", "hsru00"),
    "SM00": ("house", "hssm00"),
    "SO00": ("house", "hsso00"),
    "SY00": ("house", "hssy00"),
    "VR00": ("house", "hsvr00"),
    "WM00": ("house", "hswm00"),
}

# Congress.gov Senate standing system codes (lowercase), 2026-09-08 directory.
SENATE_STANDING_CODES = {
    "ssaf00",
    "ssap00",
    "ssas00",
    "ssbk00",
    "ssbu00",
    "sscm00",
    "sseg00",
    "ssev00",
    "ssfi00",
    "ssfr00",
    "ssga00",
    "sshr00",
    "ssju00",
    "ssra00",
    "sssb00",
    "ssva00",
}

# Committees whose Rule X/XXV numbered lists do not name a cabinet department.
# Empty agencies[] is correct — do not infer Treasury/DOJ/State/etc.
NO_NAMED_DEPARTMENT_SYSTEM_CODES = {
    "hswm00",  # Ways and Means
    "hsju00",  # Judiciary
    "hsfa00",  # Foreign Affairs
    "ssfi00",  # Finance
    "ssfr00",  # Foreign Relations
    "ssju00",  # Judiciary
}

URL_TEMPLATES = {
    "house_member_office": "https://clerk.house.gov/members/{bioguide}",
    "member_bioguide": "https://bioguide.congress.gov/search/bio/{bioguide}",
    "house_committee": "https://clerk.house.gov/Committees/{clerk_code}",
    "congress_committee": "https://www.congress.gov/committee/{system_code}",
}

ALLOWED_URL_PREFIXES = (
    "https://clerk.house.gov/members/",
    "https://clerk.house.gov/Committees/",
    "https://bioguide.congress.gov/search/bio/",
    "https://www.congress.gov/committee/",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "policy" / "committee-agency-jurisdictions.json").exists():
            return parent
    raise FileNotFoundError("data/policy/committee-agency-jurisdictions.json")


def jurisdictions_path() -> Path:
    return repo_root() / "data" / "policy" / "committee-agency-jurisdictions.json"


def load_jurisdictions(path: Optional[Path] = None) -> Dict[str, Any]:
    src = path or jurisdictions_path()
    if not src.exists():
        return {"records": [], "coverage": {"complete": False}, "notes": []}
    return json.loads(src.read_text(encoding="utf-8"))


def agencies_by_committee(jurisdictions: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for record in jurisdictions.get("records") or []:
        committee_id = str(record.get("committee_id") or "").strip()
        agency_id = str(record.get("agency_id") or "").strip()
        if not committee_id or not agency_id:
            continue
        if str(record.get("mapping_source") or "") not in {"official", "verified_manual"}:
            continue
        out.setdefault(committee_id, []).append(
            {
                "agency_id": agency_id,
                "relationship_type": record.get("relationship_type") or "oversight",
                "mapping_source": record.get("mapping_source"),
                "rule_cite": record.get("rule_cite"),
                "source_url": record.get("source_url"),
                "verified_at": record.get("verified_at"),
            }
        )
    return out


def bioguide_url(bioguide: Optional[str]) -> Optional[str]:
    bio = (bioguide or "").strip()
    if not bio:
        return None
    return URL_TEMPLATES["member_bioguide"].format(bioguide=bio)


def member_office_url(chamber: str, bioguide: Optional[str]) -> Optional[str]:
    bio = (bioguide or "").strip()
    if not bio:
        return None
    if chamber == "house":
        return URL_TEMPLATES["house_member_office"].format(bioguide=bio)
    # Senate has no bioguide-keyed office host. Do not invent lastname.senate.gov.
    return bioguide_url(bio)


def committee_homepage_url(
    chamber: str, clerk_code: Optional[str], system_code: Optional[str]
) -> Optional[str]:
    if chamber == "house" and clerk_code:
        return URL_TEMPLATES["house_committee"].format(clerk_code=clerk_code)
    if system_code:
        return URL_TEMPLATES["congress_committee"].format(system_code=system_code)
    return None


def assert_official_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if not url.startswith(ALLOWED_URL_PREFIXES):
        raise ValueError(f"invented or unofficial URL blocked: {url}")
    return url


def leadership_person(chamber: str, row: Optional[Dict[str, Any]], role: str, role_ko: str) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    bio = row.get("bioguide")
    return {
        "name": row.get("name"),
        "bioguide": bio,
        "party": row.get("party"),
        "state": row.get("state"),
        "role": role,
        "role_ko": role_ko,
        "member_office_url": assert_official_url(member_office_url(chamber, bio)),
        "bioguide_url": assert_official_url(bioguide_url(bio)),
    }


def house_ids(clerk_code: str, congress: int) -> Dict[str, Any]:
    mapped = HOUSE_CLERK_TO_CONGRESS.get(clerk_code)
    if not mapped:
        raise KeyError(f"unknown House standing clerk code: {clerk_code}")
    chamber, system_code = mapped
    return {
        "chamber": chamber,
        "system_code": system_code,
        "clerk_code": clerk_code,
        "committee_id": f"{congress}-{chamber}-{system_code}",
    }


def senate_ids(cvc_code: str, congress: int) -> Dict[str, Any]:
    system_code = (cvc_code or "").strip().lower()
    if system_code not in SENATE_STANDING_CODES:
        raise KeyError(f"unknown Senate standing CVC code: {cvc_code}")
    return {
        "chamber": "senate",
        "system_code": system_code,
        "clerk_code": None,
        "committee_id": f"{congress}-senate-{system_code}",
    }


def card_from_roster(
    chamber: str,
    row: Dict[str, Any],
    congress: int,
    agencies: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    ids = house_ids(row["code"], congress) if chamber == "house" else senate_ids(row["code"], congress)
    homepage = assert_official_url(
        committee_homepage_url(ids["chamber"], ids.get("clerk_code"), ids["system_code"])
    )
    return {
        "committee_id": ids["committee_id"],
        "chamber": ids["chamber"],
        "system_code": ids["system_code"],
        "clerk_code": ids.get("clerk_code"),
        "name": row.get("name"),
        "type": row.get("type") or "standing",
        "member_count": row.get("member_count"),
        "chair": leadership_person(ids["chamber"], row.get("chair"), "chair", "위원장"),
        "ranking_member": leadership_person(
            ids["chamber"], row.get("ranking_member"), "ranking_member", "간사"
        ),
        "committee_url": homepage,
        "agencies": list(agencies.get(ids["committee_id"]) or []),
    }


def build_committee_cards(
    usa_committees: Optional[Dict[str, Any]] = None,
    jurisdictions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    doc = usa_committees or {}
    juris = jurisdictions if jurisdictions is not None else load_jurisdictions()
    congress = int(doc.get("congress") or juris.get("congress_number") or 119)
    agency_index = agencies_by_committee(juris)
    house = [
        card_from_roster("house", row, congress, agency_index)
        for row in ((doc.get("house") or {}).get("standing_committees") or [])
    ]
    senate = [
        card_from_roster("senate", row, congress, agency_index)
        for row in ((doc.get("senate") or {}).get("standing_committees") or [])
    ]
    return {
        "schema_version": 1,
        "as_of": doc.get("as_of") or now_iso(),
        "congress": congress,
        "url_templates": dict(URL_TEMPLATES),
        "source": doc.get("source"),
        "jurisdiction_source": {
            "path": "data/policy/committee-agency-jurisdictions.json",
            "source_name": juris.get("source_name"),
            "coverage_complete": bool((juris.get("coverage") or {}).get("complete")),
            "note_ko": "규칙 조항이 내각급 부처 이름을 직접 적은 행만 조인한다. 빈 agencies[]는 추정이 아니라 규칙에 부처명이 없다는 뜻이다.",
        },
        "roles": {
            "chair": {"en": "chair", "ko": "위원장"},
            "ranking_member": {"en": "ranking_member", "ko": "간사"},
        },
        "house": house,
        "senate": senate,
        "standing": house + senate,
        "counts": {
            "house": len(house),
            "senate": len(senate),
            "standing": len(house) + len(senate),
            "with_named_department": sum(1 for card in house + senate if card.get("agencies")),
        },
        "shared_with": ["homepage_policy_politics", "elections_module"],
    }


def public_committee_cards(doc: Optional[Dict[str, Any]]) -> Any:
    if not doc:
        return "불명"
    return {
        "schema_version": doc.get("schema_version"),
        "as_of": doc.get("as_of"),
        "congress": doc.get("congress"),
        "url_templates": doc.get("url_templates"),
        "source": doc.get("source"),
        "jurisdiction_source": doc.get("jurisdiction_source"),
        "roles": doc.get("roles"),
        "house": doc.get("house"),
        "senate": doc.get("senate"),
        "standing": doc.get("standing"),
        "counts": doc.get("counts"),
        "shared_with": doc.get("shared_with"),
    }


def write_committee_cards(doc: Dict[str, Any]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "usa_committee_cards.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    committees_path = OUT / "usa_committees.json"
    if not committees_path.exists():
        print(json.dumps({"skipped": True, "reason": "missing_usa_committees.json"}))
        return 0
    committees = json.loads(committees_path.read_text(encoding="utf-8"))
    cards = build_committee_cards(committees)
    path = write_committee_cards(cards)
    print(
        json.dumps(
            {
                "wrote": str(path),
                "counts": cards["counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
