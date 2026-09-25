#!/usr/bin/env python3
"""Collect Bank of Korea Monetary Policy Board decisions -> config/bok_mpc_v1.json.

One record per 통화정책방향 meeting since --from (default 2024-11): the base-rate
decision, the statement paragraphs, the vote sentence (2026-02 onward), and once
the minutes are out (about 19 days later) their release date and the attendee
list. Also the yearly meeting calendar and the current members.

Idempotent: a stored meeting is not fetched again; only meetings still missing
their minutes are looked up on each run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect import bok  # noqa: E402
from macro_monitor.cb_collect.common import fetch_text  # noqa: E402

OUT = ROOT / "config" / "bok_mpc_v1.json"
MAX_PAGES = 8


def _load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def _search_all(keyword: str, oldest: str, pick) -> list[dict]:
    """Rows of a search, page by page, until a page reaches back past `oldest`."""
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        rows = pick(bok.parse_search(fetch_text(bok.search_url(keyword, page), min_size=3000)))
        out += rows
        if not rows or min(r["meeting_date"] for r in rows) < oldest:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="2024-11-01", help="earliest meeting date to keep")
    ap.add_argument("--force", action="store_true", help="re-fetch meetings already stored")
    args = ap.parse_args()

    existing = _load()
    meetings = {m["meeting_date"]: m for m in existing.get("meetings", [])}
    errors: list[str] = []

    try:
        rows = [r for r in _search_all("통화정책방향(", args.start, bok.decision_rows) if r["meeting_date"] >= args.start]
    except Exception as exc:  # noqa: BLE001
        print(f"decision list failed: {exc}", file=sys.stderr)
        return 1
    for row in sorted({r["meeting_date"]: r for r in rows}.values(), key=lambda r: r["meeting_date"]):
        d = row["meeting_date"]
        if d in meetings and not args.force:
            continue
        url = bok.detail_url(bok.PRESS_BOARD, row["ntt_id"], bok.PRESS_MENU)
        try:
            rec = bok.parse_decision(fetch_text(url, min_size=100000), meeting_date=d, source_url=url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{d}: {exc}")
            continue
        rec["registered_on"] = row["registered_on"]
        rec["outlook_sentences"] = bok.outlook_sentences(rec["paragraphs"])
        rec["minutes"] = (meetings.get(d) or {}).get("minutes")
        meetings[d] = rec

    # minutes: found by search for meetings that have none yet; a stored meeting whose minutes
    # predate the discussion/vote fields is upgraded from the page it already points at
    pending = [d for d, m in meetings.items() if not m.get("minutes")]
    if pending:
        try:
            found = {r["meeting_date"]: r for r in _search_all("금융통화위원회 의사록", min(pending), bok.minutes_rows)}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"minutes list: {exc}")
            found = {}
        for d in pending:
            row = found.get(d)
            if row:
                meetings[d]["minutes"] = {"released_on": row["registered_on"], "session_no": row["session_no"],
                                          "page_url": bok.detail_url(bok.MINUTES_BOARD, row["ntt_id"], bok.MINUTES_MENU)}
    for d, m in sorted(meetings.items()):
        mi = m.get("minutes")
        if not mi or ("discussion" in mi and not args.force):
            continue
        try:
            got = bok.fetch_minutes(page_url=mi["page_url"], prior_rate=m["prior_rate_pct"], rate=m["rate_pct"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{d} minutes: {exc}")
            continue
        m["minutes"] = {**mi, **got}

    # the forecast tables of the quarterly 경제전망 (Feb/May/Aug/Nov), published as a press release
    # the same day as the decision; only meetings that carry one are looked up
    due = [d for d, m in meetings.items() if int(d[5:7]) in (2, 5, 8, 11) and not m.get("outlook_table")]
    if due:
        try:
            releases = {r["meeting_date"]: r for r in bok.outlook_release_rows(
                [row for page in (1, 2) for row in bok.parse_search(fetch_text(bok.search_url("경제전망(", page), min_size=3000))])}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"outlook list: {exc}")
            releases = {}
        for d in sorted(due):
            row = releases.get(d)
            if not row:
                continue
            try:
                meetings[d]["outlook_table"] = bok.fetch_outlook_table(row["ntt_id"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d} outlook table: {exc}")

    calendar = dict(existing.get("calendar", {}))
    for year in (datetime.now(timezone.utc).year, datetime.now(timezone.utc).year + 1):
        try:
            dates = bok.parse_schedule(fetch_text(bok.schedule_url(year), min_size=100000), year)
            if dates:
                calendar[str(year)] = dates
        except Exception as exc:  # noqa: BLE001
            errors.append(f"calendar {year}: {exc}")

    roster = existing.get("roster", [])
    try:
        roster = bok.parse_roster(fetch_text(bok.ROSTER_URL, min_size=100000)) or roster
    except Exception as exc:  # noqa: BLE001
        errors.append(f"roster: {exc}")

    doc = {
        "schema_version": "bok-mpc-v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "meetings": [meetings[d] for d in sorted(meetings)],
        "calendar": calendar,
        "roster": roster,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"BOK: {len(doc['meetings'])} meetings, calendar {sorted(calendar)}, roster {len(roster)} -> {OUT}")
    if doc["meetings"]:
        last = doc["meetings"][-1]
        print(f"  latest {last['meeting_date']}: {last['prior_rate_pct']}% -> {last['rate_pct']}% "
              f"(minutes {'out' if last.get('minutes') else 'pending'})")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
