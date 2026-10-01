#!/usr/bin/env python3
"""Collect each SEP meeting's Table 1 (median projections + policy path).

Output: config/fomc_sep_v1.json -- one row per SEP meeting (March/June/
September/December, marked has_sep in fomc_calendar_v1.json). Raw collected
fact, kept apart from fomc_meetings_v1.json the same way the statement text
and Beige Book are; build_us_macro_quality_from_collect.py reshapes the
latest row for the panel.

Idempotent: only meetings not already collected are fetched (--force
re-fetches all). A meeting whose page isn't up yet (404) is skipped quietly;
a page whose table this parser can't read is reported and skipped rather
than stored half-parsed.
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
from macro_monitor.fomc_collect.sep import parse_sep_summary, sep_url  # noqa: E402

CALENDAR = ROOT / "config" / "fomc_calendar_v1.json"
OUT = ROOT / "config" / "fomc_sep_v1.json"


def collect(calendar: dict, existing: dict, *, force: bool) -> tuple[dict, list[str]]:
    rows = {r["meeting_date"]: r for r in existing.get("projections", [])}
    errors: list[str] = []
    today = date.today().isoformat()
    for m in calendar["meetings"]:
        d = m["decision_date"]
        if not m.get("has_sep") or d > today:
            continue
        if d in rows and not force:
            continue
        url = sep_url(d)
        try:
            row = parse_sep_summary(fetch_url(url), meeting_date=d, source_url=url)
        except HTTPError as exc:
            if exc.code != 404:
                errors.append(f"{d}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 -- one meeting must not block the others
            errors.append(f"{d}: {exc}")
            continue
        rows[d] = row
    doc = {
        "schema_version": "fomc-sep-v1",
        "source": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "projections": [rows[d] for d in sorted(rows)],
    }
    return doc, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch already-collected meetings")
    args = ap.parse_args()
    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    doc, errors = collect(calendar, existing, force=args.force)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"sep: {len(doc['projections'])} meetings -> {OUT}")
    for e in errors:
        print(f"  ERROR {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
