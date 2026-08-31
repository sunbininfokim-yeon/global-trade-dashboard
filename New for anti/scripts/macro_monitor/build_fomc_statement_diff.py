#!/usr/bin/env python3
"""Build meeting-to-meeting FOMC statement wording diffs.

Two outputs, kept separate the same way fomc_meetings_v1.json (vote facts)
is separate from beige_book_v1.json:
  config/fomc_statement_text_v1.json  -- one row per meeting: operative text
  public/data/fomc_statement_diff_v1.json -- one row per consecutive pair: word diff

Idempotent: only meetings missing from the text cache are re-fetched, so a
scheduled run after a new FOMC meeting is one fetch and one new diff row, not
a full re-scrape. Reuses fomc_meetings_v1.json (already collected by
build_fomc_collect.py) for meeting dates/URLs rather than re-deriving them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.fomc_collect.fetch import fetch_url  # noqa: E402
from macro_monitor.fomc_collect.parse import extract_operative_text  # noqa: E402
from macro_monitor.fomc_collect.statement_diff import changed_word_count, diff_operative_text  # noqa: E402

MEETINGS_IN = ROOT / "config" / "fomc_meetings_v1.json"
TEXT_CACHE = ROOT / "config" / "fomc_statement_text_v1.json"
DIFF_OUT = ROOT.parent.parent / "public" / "data" / "fomc_statement_diff_v1.json"


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def collect_operative_text(meetings: list[dict], existing: dict, *, force: bool) -> tuple[dict, list[str]]:
    rows = {row["meeting_date"]: row for row in existing.get("statements", [])}
    errors: list[str] = []
    for m in meetings:
        d = m["meeting_date"]
        if d in rows and not force:
            continue
        try:
            html = fetch_url(m["source_url"])
        except HTTPError as exc:
            errors.append(f"{d}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{d}: {exc}")
            continue
        operative = extract_operative_text(html)
        if operative is None:
            errors.append(f"{d}: could not bound operative text at {m['source_url']}")
            continue
        rows[d] = {"meeting_date": d, "source_url": m["source_url"], "operative_text": operative}
    doc = {
        "schema_version": "fomc-statement-text-v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "statements": [rows[d] for d in sorted(rows)],
    }
    return doc, errors


def build_diffs(text_doc: dict) -> dict:
    rows = text_doc["statements"]
    diffs = []
    for previous, current in zip(rows, rows[1:]):
        segments = diff_operative_text(previous["operative_text"], current["operative_text"])
        diffs.append({
            "previous_meeting": previous["meeting_date"],
            "current_meeting": current["meeting_date"],
            "previous_source_url": previous["source_url"],
            "current_source_url": current["source_url"],
            "changed_word_count": changed_word_count(segments),
            "segments": segments,
        })
    return {
        "schema_version": "fomc-statement-diff-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "note_ko": "FOMC 성명서 본문(경제 진단 문단)만 비교합니다. 투표 명단·절차 문구는 제외했습니다.",
        "diffs": diffs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch even already-cached statement text")
    args = ap.parse_args()

    meetings_doc = json.loads(MEETINGS_IN.read_text(encoding="utf-8"))
    clean_meetings = [m for m in meetings_doc["meetings"] if m.get("parsed_ok")]

    text_doc, errors = collect_operative_text(clean_meetings, _load(TEXT_CACHE, {}), force=args.force)
    TEXT_CACHE.write_text(json.dumps(text_doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    diff_doc = build_diffs(text_doc)
    DIFF_OUT.parent.mkdir(parents=True, exist_ok=True)
    DIFF_OUT.write_text(json.dumps(diff_doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(f"statement text: {len(text_doc['statements'])} meetings -> {TEXT_CACHE}")
    print(f"diffs: {len(diff_doc['diffs'])} pairs -> {DIFF_OUT}")
    if diff_doc["diffs"]:
        latest = diff_doc["diffs"][-1]
        print(f"  latest: {latest['previous_meeting']} -> {latest['current_meeting']}, "
              f"{latest['changed_word_count']} word(s) changed")
    if errors:
        print(f"errors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
