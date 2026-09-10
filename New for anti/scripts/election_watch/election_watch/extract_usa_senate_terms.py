"""Attach Senate class I/II/III and term-end dates onto usa_congress.json.

Congress.gov current-member list has no class field. Seat class is constitutional;
this overlay maps current bioguides to class using congress-legislators (secondary)
and the known 2026=Class II cycle. Unknown stays null.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "extracted"
CONGRESS_PATH = OUT / "usa_congress.json"
TERMS_PATH = OUT / "usa_senate_terms.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_senate_terms(congress: Dict[str, Any], terms: Dict[str, Any]) -> Dict[str, Any]:
    by_bio = {
        row["bioguide_id"]: row
        for row in (terms.get("members") or [])
        if row.get("bioguide_id")
    }
    attached = 0
    missing = []
    for row in congress.get("members") or []:
        if row.get("chamber") != "senate":
            continue
        extra = by_bio.get(row.get("bioguideId"))
        if not extra:
            row["senate_class"] = None
            row["senate_class_roman"] = None
            row["term_end"] = None
            row["next_election_year"] = None
            row["up_in_2026"] = None
            missing.append(row.get("bioguideId"))
            continue
        row["senate_class"] = extra.get("senate_class")
        row["senate_class_roman"] = extra.get("senate_class_roman")
        row["term_end"] = extra.get("term_end")
        row["next_election_year"] = extra.get("next_election_year")
        row["up_in_2026"] = extra.get("up_in_2026")
        attached += 1
    summary = congress.setdefault("summary", {})
    summary["senate_with_class"] = attached
    summary["senate_up_in_2026"] = sum(
        1
        for row in congress.get("members") or []
        if row.get("chamber") == "senate" and row.get("up_in_2026")
    )
    congress["senate_terms_source"] = terms.get("source")
    congress["senate_terms_missing_bioguides"] = missing
    return congress


def main() -> int:
    congress = json.loads(CONGRESS_PATH.read_text(encoding="utf-8"))
    terms = json.loads(TERMS_PATH.read_text(encoding="utf-8"))
    apply_senate_terms(congress, terms)
    congress["senate_terms_applied_at"] = now_iso()
    CONGRESS_PATH.write_text(json.dumps(congress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "senate_with_class": congress["summary"].get("senate_with_class"),
                "senate_up_in_2026": congress["summary"].get("senate_up_in_2026"),
                "missing": congress.get("senate_terms_missing_bioguides"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
