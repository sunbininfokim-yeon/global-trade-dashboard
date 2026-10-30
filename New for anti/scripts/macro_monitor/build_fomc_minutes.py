#!/usr/bin/env python3
"""Collect FOMC minutes (named votes + participant-count wording) per meeting.

Output: config/fomc_minutes_v1.json -- one row per meeting whose minutes are
out, with the release date read off the Fed's own calendar page ("Minutes:
PDF | HTML (Released August 19, 2026)"). Kept apart from fomc_meetings_v1.json
the same way the statement text, SEP and Beige Book are; the assembler
reshapes the latest row for the panel.

Idempotent: only meetings not already collected are fetched (--force
re-fetches all). Minutes not out yet (404) are skipped quietly; a page whose
structure this parser can't read is reported and skipped rather than stored
half-parsed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.fomc_collect.fetch import fetch_url  # noqa: E402
from macro_monitor.fomc_collect.minutes import minutes_url, parse_minutes, parse_release_dates  # noqa: E402

CALENDAR = ROOT / "config" / "fomc_calendar_v1.json"
OUT = ROOT / "config" / "fomc_minutes_v1.json"
CALENDAR_PAGE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


def collect(calendar: dict, existing: dict, release_dates: dict[str, str], *, force: bool) -> tuple[dict, list[str]]:
    rows = {r["meeting_date"]: r for r in existing.get("minutes", [])}
    errors: list[str] = []
    today = date.today().isoformat()
    for m in calendar["meetings"]:
        d = m["decision_date"]
        if d > today:
            continue
        if d in rows and not force:
            # The printed release date can appear on the calendar page after
            # the minutes themselves; fill it in on a later run.
            if not rows[d].get("released_on") and release_dates.get(d):
                rows[d]["released_on"] = release_dates[d]
            continue
        url = minutes_url(d)
        try:
            row = parse_minutes(fetch_url(url), meeting_date=d, source_url=url)
        except HTTPError as exc:
            if exc.code != 404:
                errors.append(f"{d}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 -- one meeting must not block the others
            errors.append(f"{d}: {exc}")
            continue
        row["released_on"] = release_dates.get(d)
        rows[d] = row
    doc = {
        "schema_version": "fomc-minutes-v1",
        "source": CALENDAR_PAGE,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "minutes": [rows[d] for d in sorted(rows)],
    }
    return doc, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch already-collected meetings")
    args = ap.parse_args()
    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    try:
        release_dates = parse_release_dates(fetch_url(CALENDAR_PAGE))
    except Exception as exc:  # noqa: BLE001 -- release dates are a label, not a reason to skip the minutes
        print(f"  calendar page unavailable ({exc}); release dates left as-is")
        release_dates = {}
    doc, errors = collect(calendar, existing, release_dates, force=args.force)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"minutes: {len(doc['minutes'])} meetings -> {OUT}")
    for e in errors:
        print(f"  ERROR {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
