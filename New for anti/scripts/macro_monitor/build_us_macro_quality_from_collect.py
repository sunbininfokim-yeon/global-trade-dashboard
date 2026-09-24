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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.us_quality.fed import (  # noqa: E402
    FedOfficialSourceError,
    FOMC_MEMBERS_URL,
    fetch_text,
    parse_fomc_members,
)
from macro_monitor.fomc_collect.decision import parse_decision  # noqa: E402
from macro_monitor.us_quality.fomc import compare_fomc_meetings  # noqa: E402

MEETINGS_IN = ROOT / "config" / "fomc_meetings_v1.json"
BEIGE_IN = ROOT / "config" / "beige_book_v1.json"
CALENDAR_IN = ROOT / "config" / "fomc_calendar_v1.json"
STATEMENT_TEXT_IN = ROOT / "config" / "fomc_statement_text_v1.json"
SEP_IN = ROOT / "config" / "fomc_sep_v1.json"
OUT = ROOT.parent.parent / "public" / "data" / "us_macro_quality_v1.json"

# Every 2026 Beige Book edition landed exactly 14 days before its paired
# FOMC decision date (always a Wednesday) -- confirmed against all 7 pairs
# collected so far. The Fed publishes no forward-looking Beige Book
# calendar the way it does for FOMC meetings, so this is a pattern-based
# projection, not an official date, and is labeled that way downstream.
BEIGE_BOOK_LEAD_DAYS = 14


def _decisions(text_doc: dict) -> list[dict]:
    """One row per collected statement whose decision sentence parses."""
    rows = []
    for row in text_doc.get("statements", []):
        decision = parse_decision(row.get("operative_text") or "")
        if decision is None:
            continue
        rows.append({"meeting_date": row["meeting_date"], "source_url": row["source_url"], **decision})
    return sorted(rows, key=lambda r: r["meeting_date"])


def _latest_sep(sep_doc: dict) -> dict | None:
    projections = sorted(sep_doc.get("projections", []), key=lambda r: r["meeting_date"])
    return projections[-1] if projections else None


def _next_meeting_schedule(calendar_doc: dict, *, today: date) -> dict | None:
    upcoming = [m for m in calendar_doc.get("meetings", []) if date.fromisoformat(m["decision_date"]) > today]
    if not upcoming:
        return None
    upcoming.sort(key=lambda m: m["decision_date"])
    next_meeting = upcoming[0]["decision_date"]
    projected_beige_book = (date.fromisoformat(next_meeting) - timedelta(days=BEIGE_BOOK_LEAD_DAYS)).isoformat()
    return {"next_meeting_date": next_meeting, "next_beige_book_estimate": projected_beige_book}


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


def _current_vote_roster(row: dict, roster_members: list[dict]) -> list[dict]:
    """Full for/against list for the most recent meeting, for display.

    Distinct from _to_fomc_meeting()'s output (used for the previous-vs-
    current transition diff, left untouched here): that one only tracks
    named voters, which is fine for a diff but shows an against-only list
    on a Format B meeting since the statement never names the "for" side.
    Here, when the statement didn't name them, the "for" side is filled in
    as the live committee roster minus the named dissenters -- only when
    that count matches the statement's own "N - N" tally exactly, so a
    roster that's drifted from who actually sat on this specific past vote
    is never silently papered over.
    """
    dissenters = row["dissenters"]
    dissenter_names = {d["name"] for d in dissenters}
    voters_for = row.get("voters_for") or []
    if not voters_for and roster_members:
        derived_for = [m["name"] for m in roster_members if m["name"] not in dissenter_names]
        if row.get("vote_for") is not None and len(derived_for) == row["vote_for"]:
            voters_for = derived_for
    entries = []
    for name in voters_for:
        entries.append({"name": name, "vote": "for", "dissent_direction": None, "inferred": name not in (row.get("voters_for") or [])})
    for d in dissenters:
        entries.append({"name": d["name"], "vote": "against", "dissent_direction": d["dissent_direction"], "inferred": False})
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    meetings_doc = json.loads(MEETINGS_IN.read_text(encoding="utf-8"))
    beige_doc = json.loads(BEIGE_IN.read_text(encoding="utf-8"))
    calendar_doc = json.loads(CALENDAR_IN.read_text(encoding="utf-8"))
    schedule = _next_meeting_schedule(calendar_doc, today=date.today())
    decisions = _decisions(json.loads(STATEMENT_TEXT_IN.read_text(encoding="utf-8"))) if STATEMENT_TEXT_IN.exists() else []
    latest_sep = _latest_sep(json.loads(SEP_IN.read_text(encoding="utf-8"))) if SEP_IN.exists() else None

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
            # Only the decision belonging to the meeting the panel calls
            # "current": a newer statement without a parseable decision
            # sentence must not leave the panel showing the previous
            # meeting's action under the new meeting's date.
            "decision": next((d for d in reversed(decisions) if d["meeting_date"] == current_row["meeting_date"]), None),
            "decision_history": [
                {k: d[k] for k in ("meeting_date", "action", "change_bp", "range_low", "range_high")}
                for d in decisions
            ],
            "sep": latest_sep,
            "current_votes": _current_vote_roster(current_row, roster_members),
            "meeting_count": len(clean),
            "current_roster": {
                "roster_year": int(roster_asof[:4]),
                "members": roster_members,
                "as_of": roster_asof,
                "source": roster_source,
            },
            "schedule": {
                **(schedule or {}),
                "beige_book_note_ko": (
                    "베이지북은 공식 발표 캘린더가 없어 다음 FOMC 결정일 14일 전(수요일) "
                    "패턴으로 추정한 날짜입니다. 실제 발표일이 아닙니다."
                ),
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
