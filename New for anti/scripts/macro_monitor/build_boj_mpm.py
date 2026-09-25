#!/usr/bin/env python3
"""Collect Bank of Japan Monetary Policy Meeting statements -> config/boj_mpm_v1.json.

One record per meeting since --from (default 2024-07): the guideline rate, who
voted for and against (with the dissenters' reasons and the rate they proposed),
the assessment text, and -- at Outlook-Report meetings -- the Policy Board's
forecast table and the Bank's View summary. Plus the Bank's own meeting calendar
(planned release dates of the Summary of Opinions and the Minutes).

Idempotent: meetings already in the file are not fetched again, so a scheduled
run costs two index pages unless a meeting is new. A meeting whose Outlook
Report was not on the index yet is retried on the next run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect import boj  # noqa: E402
from macro_monitor.cb_collect.common import fetch_text  # noqa: E402

OUT = ROOT / "config" / "boj_mpm_v1.json"


def _load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="2024-07-01", help="earliest meeting date to keep (the rate was a 0-0.1% range before the 2024-07 hike; the guideline sentence changed)")
    ap.add_argument("--force", action="store_true", help="re-fetch meetings already stored")
    args = ap.parse_args()

    existing = _load()
    meetings = {m["meeting_date"]: m for m in existing.get("meetings", [])}
    errors: list[str] = []

    listed = []
    for year in range(int(args.start[:4]), datetime.now(timezone.utc).year + 1):
        try:
            listed += boj.parse_statements_index(fetch_text(boj.statements_index_url(year), min_size=3000))
        except Exception as exc:  # noqa: BLE001 -- a future year's index may not exist yet
            if year <= datetime.now(timezone.utc).year:
                errors.append(f"statement index {year}: {exc}")
    listed = [d for d in listed if d["meeting_date"] >= args.start]
    if not listed and not meetings:
        print("no statements found on the index pages; nothing written", file=sys.stderr)
        return 1

    outlook_urls: list[str] | None = None

    def outlook() -> list[str]:
        nonlocal outlook_urls
        if outlook_urls is None:
            outlook_urls = boj.parse_outlook_index(fetch_text(boj.OUTLOOK_INDEX, min_size=3000))
        return outlook_urls

    for doc in sorted(listed, key=lambda d: d["meeting_date"]):
        d = doc["meeting_date"]
        rec = meetings.get(d)
        if rec is None or args.force:
            try:
                rec = boj.parse_statement(boj.fetch_statement_text(doc["url"]), meeting_date=d,
                                          source_url=doc["url"], title=doc["title"])
                rec["bank_view"] = None
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d}: {exc}")
                continue
        if rec["narrative"] is None and rec.get("bank_view") is None:
            try:
                rec["bank_view"] = boj.fetch_bank_view(d, outlook())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d} outlook: {exc}")
        meetings[d] = rec

    calendar = existing.get("calendar", [])
    try:
        calendar = boj.parse_schedule(fetch_text(boj.SCHEDULE_URL, min_size=3000)) or calendar
    except Exception as exc:  # noqa: BLE001
        errors.append(f"calendar: {exc}")

    doc = {
        "schema_version": "boj-mpm-v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "meetings": [meetings[d] for d in sorted(meetings)],
        "calendar": calendar,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"BOJ: {len(doc['meetings'])} meetings, {len(calendar)} calendar rows -> {OUT}")
    if doc["meetings"]:
        last = doc["meetings"][-1]
        print(f"  latest {last['meeting_date']}: {last['guideline_rate_pct']}%, "
              f"{'unanimous' if last['unanimous'] else str(last['vote_for_count']) + '-' + str(last['vote_against_count'])}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
