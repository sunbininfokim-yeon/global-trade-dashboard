#!/usr/bin/env python3
"""Assemble us_macro_quality_v1.json from the FOMC/Beige Book collectors.

Modular on purpose: config/fomc_meetings_v1.json and config/beige_book_v1.json
(build_fomc_collect.py) are raw collected fact, re-fetched and re-parsed on
every run; this script only reshapes the two most recent, cleanly-parsed
meetings plus the latest Beige Book edition into the document
mmUsPolicyQuality() already reads. It does not touch macro_monitor_v1.json --
this panel has always been its own fetch (mmQualityFetch), independent of the
country pack.

Reuses macro_monitor.us_quality.fomc.compare_fomc_meetings() for the
previous-vs-current comparison rather than recomputing dissent deltas here,
so that logic has one implementation whether the meeting data behind it came
from a hand-curated input or this collector.

Only meetings with parsed_ok: true are used. A meeting the collector flagged
(a compound or qualified dissent it couldn't fully categorize) is skipped
rather than assembled with a placeholder -- the previous/current comparison
falls back to the two most recent *clean* meetings instead, and that skip is
reported so it doesn't go unnoticed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.us_quality.fed import (  # noqa: E402
    FedOfficialSourceError,
    FOMC_MEMBERS_URL,
    fetch_text,
    parse_fomc_members,
)
from macro_monitor.us_quality.fomc import compare_fomc_meetings  # noqa: E402

MEETINGS_IN = ROOT / "config" / "fomc_meetings_v1.json"
BEIGE_IN = ROOT / "config" / "beige_book_v1.json"
OUT = ROOT.parent.parent / "public" / "data" / "us_macro_quality_v1.json"


def _person_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _to_fomc_meeting(row: dict) -> dict:
    voters = row.get("voters_for") or []
    dissenter_names = {d["name"] for d in row["dissenters"]}
    # Format B (has an explicit vote count but no named "Voting for" roster)
    # only ever names the dissenters -- the "for" side's identities aren't
    # in the statement at all, so eligible_voters is dissenters-only for
    # those rows rather than invented up to vote_for's count.
    all_names = list(voters) + [d["name"] for d in row["dissenters"] if d["name"] not in voters]
    votes = []
    for name in all_names:
        is_against = name in dissenter_names
        direction = next((d["dissent_direction"] for d in row["dissenters"] if d["name"] == name), None)
        votes.append({
            "person_id": _person_id(name), "name": name,
            "vote": "against" if is_against else "for",
            "dissent_direction": direction,
        })
    return {
        "meeting_date": row["meeting_date"],
        "eligible_voters": [v["person_id"] for v in votes],
        "votes": votes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    meetings_doc = json.loads(MEETINGS_IN.read_text(encoding="utf-8"))
    beige_doc = json.loads(BEIGE_IN.read_text(encoding="utf-8"))

    clean = [m for m in meetings_doc["meetings"] if m.get("parsed_ok")]
    clean.sort(key=lambda m: m["meeting_date"])
    skipped = [m["meeting_date"] for m in meetings_doc["meetings"] if not m.get("parsed_ok")]
    if len(clean) < 2:
        print(f"refusing to assemble: need at least 2 cleanly-parsed meetings, have {len(clean)}")
        return 1

    previous_row, current_row = clean[-2], clean[-1]
    comparison = compare_fomc_meetings(_to_fomc_meeting(previous_row), _to_fomc_meeting(current_row))

    # Roster: fetched live from the Fed's own Committee Members page, not
    # inferred from a statement's "Voting for..." clause. That clause is no
    # longer reliable for this: since the 2026-05-22 chair transition, FOMC
    # statements only name dissenters for split votes and name no one at all
    # for unanimous ones (previously they always spelled out the full "for"
    # roster), so deriving "who's currently on the committee" from vote text
    # silently went stale at the exact meeting where the chair changed. Only
    # fall back to the old vote-derived roster if the live page is down.
    roster_source = "official_current_voting_members_only"
    roster_asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        live_roster = parse_fomc_members(fetch_text(FOMC_MEMBERS_URL))
        roster_members = [
            {"name": m["name"], "role": m["role"]} for m in live_roster["members"]
        ]
    except (FedOfficialSourceError, OSError) as exc:
        roster_row = next((m for m in reversed(clean) if m.get("voters_for")), current_row)
        roster_voters = (roster_row.get("voters_for") or []) + [d["name"] for d in roster_row["dissenters"]]
        roster_members = [{"name": n, "role": ""} for n in dict.fromkeys(roster_voters)]  # de-dup, keep order
        roster_source = f"fallback_vote_roster_live_fetch_failed:{exc}"
        roster_asof = roster_row["meeting_date"]

    documents = []
    for row in clean:
        documents.append({
            "document_type": "fomc_statement",
            "reference_period": row["meeting_date"],
            "source_url": row["source_url"],
        })
    for ed in beige_doc.get("editions", []):
        documents.append({
            "document_type": "beige_book",
            "reference_period": f"{ed['edition']}-01",
            "source_url": ed["source_url"],
            "extracted_evidence": {"national_sections": ed["national_sections"], "districts": []},
        })
    # Newest first: mmUsPolicyQuality() (macro.js) picks the first matching
    # document via .find() to show as "the latest statement" / "the latest
    # Beige Book" -- an ascending sort here handed it January 2025's Beige
    # Book instead of the most recent one.
    documents.sort(key=lambda d: d["reference_period"], reverse=True)

    doc = {
        "schema_version": "us-macro-quality-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {"kind": "collected_official_releases", "quality": "observed"},
        "contract_audit": {"release_count": len(documents), "invalid_release_count": 0, "invalid_releases": []},
        "collector_note_ko": (
            f"FOMC 성명서·Beige Book을 federalreserve.gov에서 직접 수집·파싱합니다 "
            f"(scripts/macro_monitor/build_fomc_collect.py). "
            f"{len(skipped)}개 회의는 정형화되지 않은 복합 반대의견 문구라 자동 분류를 건너뛰고 "
            f"수동 확인 대상으로 남겼습니다: {', '.join(skipped) or '없음'}."
        ),
        "policy_committee": {
            "comparison": comparison,
            "meeting_count": len(clean),
            "current_roster": {
                "roster_year": int(roster_asof[:4]),
                "members": roster_members,
                "as_of": roster_asof,
                "source": roster_source,
            },
            "collector": "build_fomc_collect.py",
        },
        "official_documents": {"items": documents},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"  {len(clean)} clean meetings ({clean[0]['meeting_date']} .. {clean[-1]['meeting_date']}), "
          f"{len(skipped)} skipped: {skipped}")
    print(f"  comparison: {previous_row['meeting_date']} -> {current_row['meeting_date']}, "
          f"{comparison['current_dissents']['count']} current dissent(s)")
    print(f"  documents: {len(documents)} ({sum(1 for d in documents if d['document_type']=='fomc_statement')} statements, "
          f"{sum(1 for d in documents if d['document_type']=='beige_book')} beige book)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
