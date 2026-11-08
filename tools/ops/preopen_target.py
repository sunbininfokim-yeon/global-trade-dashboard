#!/usr/bin/env python3
"""Pick the KRX session the pre-open direction run should forecast.

Used by .github/workflows/us_kr_direction_preopen.yml (gate step). Run from
`New for anti/scripts/market_microstructure` so the reviewed KRX calendar
imports resolve.

Rules (user request 2026-11-08: show the next session as soon as its inputs
exist, weekends and holidays included):
- A requested target (workflow_dispatch input) is used as given.
- Otherwise the target is the first KRX session on or after today (KST).
  Weekday -> today; Saturday/Sunday/holiday -> the next session.
- A target that is today is skipped once it is 08:30 KST or later: the
  runner would refuse it as no longer pre-open.
- A target whose public JSON already holds a pre-open forecast is skipped,
  so later runs never replace the first forecast. An `unavailable` result is
  retried.

Writes `target`, `run` and `valid` to $GITHUB_OUTPUT when it is set.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
CUTOFF = "08:30"
LOOKAHEAD_DAYS = 21


def next_session(today, is_session):
    for i in range(LOOKAHEAD_DAYS):
        day = (today + timedelta(days=i)).isoformat()
        if is_session(day):
            return day
    return None


def resolve(now, requested, doc, is_session):
    """Return (target, run, valid, reason). `now` must be KST-aware."""
    today = now.date()
    if requested:
        target = requested
    else:
        target = next_session(today, is_session)
        if target is None:
            return None, False, False, f"no KRX session within {LOOKAHEAD_DAYS} days of {today}"
    valid = is_session(target)
    if not valid:
        return target, False, False, f"{target} is not a KRX session"
    if not requested and target == today.isoformat() and now.strftime("%H:%M") >= CUTOFF:
        return target, False, False, f"started {now:%H:%M} KST, after the {CUTOFF} cutoff"
    if doc and doc.get("target_date") == target and doc.get("status") == "research_preopen_forecast":
        return target, False, False, f"{target} already has a pre-open forecast"
    return target, True, True, ""


def main():
    from option_direction_model import calendar
    from research_direction_diagnostics import ReviewedCalendar

    cal = ReviewedCalendar(calendar())
    path = Path(os.environ["PUBLIC_JSON"])
    doc = json.loads(path.read_text()) if path.exists() else None
    now = datetime.now(KST)
    target, run, valid, why = resolve(now, os.environ.get("REQUESTED_TARGET", "").strip(), doc, cal.is_session)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"target={target or ''}\nrun={str(run).lower()}\nvalid={str(valid).lower()}\n")
    print(f"now={now:%Y-%m-%d %H:%M} KST target={target} run={run} {why}".rstrip())
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    sys.exit(main())
