#!/usr/bin/env python3
"""Collect FOMC statements + Beige Book national summaries into their own files.

Two outputs, kept separate from each other and from us_macro_quality_v1.json:
  config/fomc_meetings_v1.json  -- one row per meeting: date, vote, dissenters
  config/beige_book_v1.json     -- one row per edition: national summary sections

Modular on purpose: this is raw collected fact, re-fetched and re-parsed on
each run; assembling it into the shape the drawer's panel actually reads
(policy_committee comparison, official_documents list) is a separate step
(build_us_macro_quality.py), same split as fetch.py/parse.py above it.

Idempotent: re-running only fetches meetings not already recorded (or all of
them with --force), so a scheduled run after a new FOMC meeting is a small
diff, not a full re-scrape.
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

from macro_monitor.fomc_collect.fetch import beige_book_url, fetch_url, statement_url  # noqa: E402
from macro_monitor.fomc_collect.parse import parse_beige_book_summary, parse_statement  # noqa: E402

CALENDAR = ROOT / "config" / "fomc_calendar_v1.json"
MEETINGS_OUT = ROOT / "config" / "fomc_meetings_v1.json"
BEIGE_OUT = ROOT / "config" / "beige_book_v1.json"


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def collect_meetings(calendar: dict, existing: dict, *, force: bool) -> tuple[dict, list[str]]:
    have = {m["meeting_date"] for m in existing.get("meetings", [])}
    rows = list(existing.get("meetings", []))
    errors = []
    today = date.today().isoformat()
    for m in calendar["meetings"]:
        d = m["decision_date"]
        if d > today:
            continue  # meeting hasn't happened yet, nothing to fetch
        if d in have and not force:
            continue
        url = statement_url(d)
        try:
            html = fetch_url(url)
        except HTTPError as exc:
            if exc.code == 404:
                continue  # decision day known from the calendar but not yet published
            errors.append(f"{d}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{d}: {exc}")
            continue
        try:
            row = parse_statement(html, meeting_date=d, source_url=url)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not row["parsed_ok"]:
            # No vote-count sentence found at all -- distinct from a real
            # unanimous vote (which parses fine and just has an empty
            # dissenters list). Flagged, not silently stored: a caller
            # printing "만장일치" for a None/None row would report a fact
            # that was never actually read off the page.
            errors.append(f"{d}: fetched but found no vote-count sentence at {url}")
            continue
        row["has_sep"] = m.get("has_sep", False)
        rows = [r for r in rows if r["meeting_date"] != d] + [row]
    rows.sort(key=lambda r: r["meeting_date"])
    return {
        "schema_version": "fomc-meetings-v1",
        "source": "https://www.federalreserve.gov/newsevents/pressreleases/",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "meetings": rows,
    }, errors


def collect_beige_book(calendar: dict, existing: dict, *, force: bool) -> tuple[dict, list[str]]:
    have = {b["edition"] for b in existing.get("editions", [])}
    rows = list(existing.get("editions", []))
    errors = []
    # Beige Book editions cluster near meeting months but don't line up
    # one-to-one with them, and there's no published calendar of edition
    # dates to read the way there is for meetings -- so each meeting month
    # and the month before it are tried, and whichever 404s is just skipped
    # rather than guessed at.
    candidates: list[str] = []
    for m in calendar["meetings"]:
        d = date.fromisoformat(m["decision_date"])
        if d.isoformat() > date.today().isoformat():
            continue
        for offset in (0, -1):
            month = d.month + offset
            year = d.year
            if month < 1:
                month += 12
                year -= 1
            ym = f"{year:04d}-{month:02d}"
            if ym not in candidates:
                candidates.append(ym)

    for ym in candidates:
        if ym in have and not force:
            continue
        url = beige_book_url(ym)
        try:
            html = fetch_url(url)
        except HTTPError as exc:
            if exc.code == 404:
                continue
            errors.append(f"{ym}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{ym}: {exc}")
            continue
        row = parse_beige_book_summary(html, edition=ym, source_url=url)
        if not row["parsed_ok"]:
            errors.append(f"{ym}: fetched but found no known section headers")
            continue
        rows = [r for r in rows if r["edition"] != ym] + [row]
    rows.sort(key=lambda r: r["edition"])
    return {
        "schema_version": "beige-book-v1",
        "source": "https://www.federalreserve.gov/monetarypolicy/",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "editions": rows,
    }, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch even already-collected dates/editions")
    args = ap.parse_args()

    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    meetings_doc, meeting_errs = collect_meetings(calendar, _load(MEETINGS_OUT, {}), force=args.force)
    beige_doc, beige_errs = collect_beige_book(calendar, _load(BEIGE_OUT, {}), force=args.force)

    MEETINGS_OUT.write_text(json.dumps(meetings_doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    BEIGE_OUT.write_text(json.dumps(beige_doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(f"meetings: {len(meetings_doc['meetings'])} collected -> {MEETINGS_OUT}")
    for r in meetings_doc["meetings"][-3:]:
        names = ", ".join(d["name"] for d in r["dissenters"]) or "만장일치"
        print(f"  {r['meeting_date']}: {r['vote_for']}-{r['vote_against']} ({names})")
    print(f"beige book: {len(beige_doc['editions'])} editions -> {BEIGE_OUT}")
    if meeting_errs:
        print(f"meeting errors ({len(meeting_errs)}):")
        for e in meeting_errs:
            print(f"  {e}")
    if beige_errs:
        print(f"beige book errors ({len(beige_errs)}):")
        for e in beige_errs:
            print(f"  {e}")
    return 1 if (meeting_errs or beige_errs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
