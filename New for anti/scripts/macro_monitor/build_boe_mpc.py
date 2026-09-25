#!/usr/bin/env python3
"""Collect Bank of England MPC Summary and Minutes pages -> config/boe_mpc_v1.json.

One record per meeting since --from: Bank Rate, the vote (every member named, checked against the
stated tally), the Summary text, the Minutes by section, the attendance list and -- from November
2025 -- each member's own rationale. Plus the Bank's confirmed meeting dates.

Idempotent: a meeting already in the file is not fetched again. Months known to have no meeting
(the Bank answers 404) are remembered; a month whose page exists but whose meeting has not
happened yet is looked at again on the next run (one request).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect import boe  # noqa: E402
from macro_monitor.cb_collect.common import fetch_text  # noqa: E402

OUT = ROOT / "config" / "boe_mpc_v1.json"


def _load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="2024-01-01", help="earliest month to look at")
    ap.add_argument("--force", action="store_true", help="re-fetch meetings already stored")
    args = ap.parse_args()

    existing = _load()
    # copies: the change check at the end compares against `existing`, so it must not share objects with what we edit
    meetings = {m["meeting_date"]: copy.deepcopy(m) for m in existing.get("meetings", [])}
    have_pages = {m["page"] for m in meetings.values()}
    no_meeting = set(existing.get("no_meeting_months", []))
    errors: list[str] = []
    today = date.today()
    start = date.fromisoformat(args.start)

    for year in range(start.year, today.year + 1):
        for month in range(1, 13):
            first = date(year, month, 1)
            if first > today or (year, month) < (start.year, start.month):
                continue
            slug = boe.meeting_slug(year, month)
            if not args.force and (slug in have_pages or slug in no_meeting):
                continue
            try:
                html = boe.fetch_meeting(year, month)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{slug}: {exc}")
                continue
            if html is None:
                if (year, month) < (today.year, today.month):     # a past month with no page is not a meeting month
                    no_meeting.add(slug)
                continue
            try:
                rec = boe.parse_meeting(html, url=boe.meeting_url(year, month))
            except boe.NotHeld:
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{slug}: {exc}")
                continue
            rec["page"] = slug
            meetings[rec["meeting_date"]] = rec

    calendar = existing.get("calendar", {})
    try:
        calendar = boe.parse_calendar(fetch_text(boe.DATES_URL, min_size=5000)) or calendar
    except Exception as exc:  # noqa: BLE001
        errors.append(f"calendar: {exc}")

    if not meetings:
        print("no MPC meetings read; nothing written", file=sys.stderr)
        return 1
    doc = {
        "schema_version": "boe-mpc-v1",
        "retrieved_at": existing.get("retrieved_at"),
        "meetings": [meetings[d] for d in sorted(meetings)],
        "no_meeting_months": sorted(no_meeting),
        "calendar": calendar,
    }
    # retrieved_at moves only when the content does, so a quiet day leaves the file byte-identical
    if json.dumps({**doc, "retrieved_at": None}, sort_keys=True) != json.dumps({**existing, "retrieved_at": None}, sort_keys=True):
        doc["retrieved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        state = "written"
    else:
        state = "unchanged"
    last = doc["meetings"][-1]
    v = last["vote"]
    print(f"BoE: {len(doc['meetings'])} meetings ({state}) -> {OUT}")
    print(f"  latest {last['meeting_date']}: Bank Rate {last['rate_pct']}%, "
          f"{'unanimous' if last['unanimous'] else str(last['tally_for']) + '-' + str(last['tally_against'])}, votes read from {v['for_source']}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
