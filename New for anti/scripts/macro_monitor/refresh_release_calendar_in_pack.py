#!/usr/bin/env python3
"""Stamp when the next print is due, without touching indicator values.

Reads the already-built macro_monitor_v1.json and writes next_release_* on
every indicator and its chip. A failed idea of a date is left null with a
note, never filled with a guessed day.

Suggested GitHub Action (daily, after midnight Korea time so the next
business day rolls forward):

    cron: '5 15 * * *'
    python3 refresh_release_calendar_in_pack.py

cursor/* branches cannot commit .github/workflows without failing the
ownership guard, so the workflow file is added only when that check is
allowed to be bypassed or the file is copied onto a branch that owns it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.release_calendar import apply_release_calendar  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=PACK)
    ap.add_argument("--today", type=str, default=None)
    args = ap.parse_args()
    doc = json.loads(args.pack.read_text(encoding="utf-8"))
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    count = apply_release_calendar(doc, today=today)
    args.pack.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"release calendar: stamped {count} indicators as of {today.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
