#!/usr/bin/env python3
"""Build a public-safe Panama rainfall monitor from NASA GPM IMERG only."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from shipping_capacity.panama_public_monitor import build_public_monitor, fetch_gpm_monitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of-date", help="UTC YYYY-MM-DD upper bound; defaults to today.")
    parser.add_argument("--recent-days", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(tempfile.gettempdir()) / "panama_climate_monitor_v1.json",
        help="Defaults to a local temporary path; publishing is a separate UI/deployment decision.",
    )
    args = parser.parse_args()
    if not 1 <= args.recent_days <= 31:
        parser.error("--recent-days must be between 1 and 31")
    try:
        as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else date.today()
    except ValueError as exc:
        parser.error(f"invalid --as-of-date: {exc}")
    start = as_of - timedelta(days=args.recent_days - 1)
    current = fetch_gpm_monitor(start.isoformat(), as_of.isoformat())
    first = date.fromisoformat(current[0].observation_date)
    last = date.fromisoformat(current[-1].observation_date)
    try:
        previous = fetch_gpm_monitor(
            first.replace(year=first.year - 1).isoformat(), last.replace(year=last.year - 1).isoformat()
        )
    except ValueError as exc:
        parser.error(f"cannot construct prior-year comparison: {exc}")
    report = build_public_monitor(current, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
