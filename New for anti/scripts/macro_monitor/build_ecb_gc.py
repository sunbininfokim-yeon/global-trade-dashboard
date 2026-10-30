#!/usr/bin/env python3
"""Collect ECB Governing Council monetary policy documents -> config/ecb_gc_v1.json.

Per meeting since --from (default 2024-06, the first cut): the press release (three key rates,
staff projections quoted in prose), the introductory statement, and -- once published, about four
weeks after the meeting -- the account (discussion, attendance with voting members marked, the
sentence saying how far members agreed with the proposal). Plus the Council's meeting calendar.

Idempotent: what is stored is not fetched again; a meeting whose account is not out yet is
picked up on the run after it appears.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect import ecb  # noqa: E402
from macro_monitor.cb_collect.common import fetch_text  # noqa: E402

OUT = ROOT / "config" / "ecb_gc_v1.json"


def _load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="2024-06-01",
                    help="earliest decision date to keep (the deposit rate was cut for the first time on 2024-06-06)")
    ap.add_argument("--force", action="store_true", help="re-fetch documents already stored")
    args = ap.parse_args()

    existing = _load()
    # copies: the change check at the end compares against `existing`, so it must not share objects with what we edit
    meetings = {m["meeting_date"]: copy.deepcopy(m) for m in existing.get("meetings", [])}
    errors: list[str] = []
    this_year = datetime.now(timezone.utc).year

    rows: dict[str, dict] = {}
    for year in range(int(args.start[:4]), this_year + 1):
        for url_fn in (ecb.mopo_listing_url, ecb.statement_listing_url, ecb.accounts_listing_url):
            try:
                for row in ecb.parse_listing(fetch_text(url_fn(year), min_size=2000)):
                    rows[row["url"]] = row
            except Exception as exc:  # noqa: BLE001 -- a year's listing may not exist yet in January
                errors.append(f"listing {url_fn.__name__} {year}: {exc}")

    listed = sorted(rows.values(), key=lambda r: (r["date"], r["kind"]))
    statements = {r["date"]: r for r in listed if r["kind"] == "statement"}
    accounts = {ecb.account_decision_date(r["title"]): r for r in listed if r["kind"] == "account"}

    for row in (r for r in listed if r["kind"] == "press_release" and r["date"] >= args.start):
        d = row["date"]
        rec = meetings.get(d)
        if rec is None or args.force:
            try:
                fresh = ecb.parse_press_release(fetch_text(row["url"], min_size=20000), url=row["url"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d} press release: {exc}")
                continue
            rec = {**fresh, "statement": (rec or {}).get("statement"), "account": (rec or {}).get("account")}
        st = statements.get(d)
        if st and (rec.get("statement") is None or args.force):
            try:
                rec["statement"] = ecb.parse_statement(fetch_text(st["url"], min_size=20000), url=st["url"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d} statement: {exc}")
        ac = accounts.get(d)
        if ac and (rec.get("account") is None or args.force):
            try:
                account = ecb.parse_account(fetch_text(ac["url"], min_size=20000), url=ac["url"])
                if account["meeting_date"] != d:
                    raise ValueError(f"account is for {account['meeting_date']}, not {d}")
                rec["account"] = account
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{d} account: {exc}")
        meetings[d] = rec

    calendar = existing.get("calendar", [])
    try:
        calendar = ecb.parse_calendar(fetch_text(ecb.CALENDAR_URL, min_size=5000)) or calendar
    except Exception as exc:  # noqa: BLE001
        errors.append(f"calendar: {exc}")

    if not meetings:
        print("no ECB meetings read; nothing written", file=sys.stderr)
        return 1
    doc = {
        "schema_version": "ecb-gc-v1",
        "retrieved_at": existing.get("retrieved_at"),
        "meetings": [meetings[d] for d in sorted(meetings)],
        "calendar": calendar,
    }
    if json.dumps({**doc, "retrieved_at": None}, sort_keys=True) != json.dumps({**existing, "retrieved_at": None}, sort_keys=True):
        doc["retrieved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        state = "written"
    else:
        state = "unchanged"
    last = doc["meetings"][-1]
    print(f"ECB: {len(doc['meetings'])} meetings ({state}) -> {OUT}")
    print(f"  latest {last['meeting_date']}: deposit rate {last['dfr_pct']}% ({last['action']}), "
          f"statement {'yes' if last.get('statement') else 'no'}, account {'yes' if last.get('account') else 'not yet'}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
