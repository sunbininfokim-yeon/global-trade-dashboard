"""Standing committee chairs and member rosters from Clerk XML + Senate CVC.

Raw XML/JSON stay in election_watch/raw/usa (gitignored). This extract is the
public contract consumed by elections_board_v1.json and, via that board, by
the homepage 정책&정치 legislator sync.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "extracted"
HOUSE_XML = ROOT / "raw" / "usa" / "MemberData.xml"
SENATE_CVC = ROOT / "raw" / "usa" / "senate-cvc-memberships.json"
USA_CONGRESS = OUT / "usa_congress.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _senate_name_index() -> Dict[str, Dict[str, Any]]:
    congress = json.loads(USA_CONGRESS.read_text(encoding="utf-8")) if USA_CONGRESS.exists() else {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in congress.get("members") or []:
        bio = row.get("bioguideId")
        if bio:
            out[bio] = row
    return out


def _house_standing_from_xml() -> Dict[str, Any]:
    root = ET.parse(HOUSE_XML).getroot()
    meta = {
        "publish_date": root.attrib.get("publish-date"),
        "congress": root.findtext("title-info/congress-num"),
        "url": "https://clerk.house.gov/xml/lists/MemberData.xml",
        "grade": "official",
        "org": "Clerk of the House",
    }
    names = {
        node.attrib["comcode"]: (node.findtext("committee-fullname") or "").strip()
        for node in root.findall("committees/committee")
        if node.attrib.get("type") == "standing" and node.attrib.get("comcode")
    }
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for member in root.findall("members/member"):
        info = member.find("member-info")
        if info is None:
            continue
        state_el = info.find("state")
        person = {
            "name": (info.findtext("official-name") or info.findtext("namelist") or "").strip(),
            "bioguide": info.findtext("bioguideID"),
            "party": info.findtext("party"),
            "state": state_el.get("postal-code") if state_el is not None else None,
        }
        for assignment in member.findall("committee-assignments/committee"):
            code = assignment.attrib.get("comcode")
            if code not in names:
                continue
            rank = assignment.attrib.get("rank")
            row = {
                **person,
                "rank": int(rank) if rank and rank.isdigit() else None,
                "leadership": assignment.attrib.get("leadership"),
            }
            buckets[code].append(row)

    standing = []
    for code, title in sorted(names.items(), key=lambda item: item[1]):
        members = sorted(
            buckets.get(code) or [],
            key=lambda row: (row.get("rank") is None, row.get("rank") or 0, row.get("name") or ""),
        )
        chairs = [
            row for row in members if (row.get("leadership") or "").lower() in {"chair", "chairman"}
        ]
        minority = [row for row in members if row.get("party") == "D"]
        ranking = min(minority, key=lambda row: row.get("rank") or 10_000) if minority else None
        standing.append(
            {
                "code": code,
                "name": title,
                "type": "standing",
                "chair": chairs[0] if chairs else None,
                "ranking_member": ranking,
                "member_count": len(members),
                "members": members,
            }
        )
    return {"meta": meta, "standing": standing}


def _senate_standing_from_cvc() -> Dict[str, Any]:
    payload = json.loads(SENATE_CVC.read_text(encoding="utf-8"))
    names = _senate_name_index()
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        code = row.get("committee_code") or ""
        if not code.startswith("SS"):
            continue
        bucket = buckets.setdefault(
            code,
            {"code": code, "name": row.get("committee_name"), "members": []},
        )
        bio = row.get("bioguide_id")
        person = names.get(bio) or {}
        bucket["members"].append(
            {
                "name": person.get("name"),
                "bioguide": bio,
                "party": person.get("abbr") or person.get("party"),
                "state": person.get("state"),
                "position": row.get("position"),
            }
        )
    standing = []
    for code, bucket in sorted(buckets.items(), key=lambda item: item[1]["name"] or item[0]):
        members = bucket["members"]
        chairs = [row for row in members if (row.get("position") or "").lower() in {"chairman", "chair"}]
        ranking = [row for row in members if (row.get("position") or "").lower() in {"ranking", "ranking member"}]
        standing.append(
            {
                "code": code,
                "name": bucket["name"],
                "type": "standing",
                "chair": chairs[0] if chairs else None,
                "ranking_member": ranking[0] if ranking else None,
                "member_count": len(members),
                "members": members,
            }
        )
    return {
        "meta": {
            "last_update": payload.get("lastUpdate"),
            "senator_count": payload.get("senatorCount"),
            "url": "https://www.senate.gov/legislative/LIS_MEMBER/cvc_member_data.xml",
            "grade": "official",
            "org": "U.S. Senate",
        },
        "standing": standing,
    }


def usa_committees() -> Dict[str, Any]:
    house = _house_standing_from_xml()
    senate = _senate_standing_from_cvc()
    house_chairs = [
        {
            "committee": row["name"],
            "chair": (row.get("chair") or {}).get("name"),
            "party": (row.get("chair") or {}).get("party"),
            "bioguide": (row.get("chair") or {}).get("bioguide"),
        }
        for row in house["standing"]
        if row.get("chair")
    ]
    senate_chairs = [
        {
            "committee": row["name"],
            "chair": (row.get("chair") or {}).get("name"),
            "party": (row.get("chair") or {}).get("party"),
            "bioguide": (row.get("chair") or {}).get("bioguide"),
        }
        for row in senate["standing"]
        if row.get("chair")
    ]
    missing: List[str] = []
    if not house["standing"]:
        missing.append("standing_committees")
    if not house_chairs or not senate_chairs:
        missing.append("committee_chairs")
    if any(not row.get("members") for row in house["standing"] + senate["standing"]):
        missing.append("committee_member_rosters")
    return {
        "as_of": now_iso(),
        "congress": int(house["meta"].get("congress") or 119),
        "source": {
            "house": house["meta"],
            "senate": senate["meta"],
        },
        "house": {
            "standing_committees": house["standing"],
            "standing_committee_chairs": house_chairs,
        },
        "senate": {
            "standing_committees": senate["standing"],
            "standing_committee_chairs": senate_chairs,
        },
        "missing_fields": missing,
        "shared_with": ["elections_module", "homepage_policy_politics"],
    }


def public_usa_committees(doc: Optional[Dict[str, Any]]) -> Any:
    if not doc:
        return "불명"
    house = doc.get("house") or {}
    senate = doc.get("senate") or {}
    return {
        "as_of": doc.get("as_of"),
        "congress": doc.get("congress"),
        "source": doc.get("source"),
        "house": {
            "standing_committees": house.get("standing_committees"),
            "standing_committee_chairs": house.get("standing_committee_chairs"),
        },
        "senate": {
            "standing_committees": senate.get("standing_committees"),
            "standing_committee_chairs": senate.get("standing_committee_chairs"),
        },
        "missing_fields": usa_committees_missing(doc),
        "shared_with": doc.get("shared_with") or ["elections_module", "homepage_policy_politics"],
    }


def usa_committees_missing(doc: Optional[Dict[str, Any]]) -> List[str]:
    if not doc:
        return [
            "standing_committees",
            "committee_chairs",
            "committee_member_rosters",
        ]
    if "missing_fields" in doc:
        return list(doc.get("missing_fields") or [])
    return ["house_committee_member_rosters"]


def main() -> int:
    if not HOUSE_XML.exists() or not SENATE_CVC.exists():
        print(
            json.dumps(
                {
                    "skipped": True,
                    "reason": "missing_raw_cache",
                    "house_xml": str(HOUSE_XML),
                    "senate_cvc": str(SENATE_CVC),
                },
                indent=2,
            )
        )
        return 0
    doc = usa_committees()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "usa_committees.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "house_standing": len(doc["house"]["standing_committees"]),
                "senate_standing": len(doc["senate"]["standing_committees"]),
                "missing_fields": doc["missing_fields"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
