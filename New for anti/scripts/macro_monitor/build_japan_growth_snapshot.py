#!/usr/bin/env python3
"""Refresh the official-source cache for Japan's three growth diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.japan_growth import ESRI_RELEASE_PAGE_URL, build_snapshot, write_snapshot  # noqa: E402

DEFAULT_OUT = ROOT / "config" / "japan_growth_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build official Japan growth-monitor snapshot")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--esri-release-page",
        default=ESRI_RELEASE_PAGE_URL,
        help="Cabinet Office English quarterly-release page (pins an ESRI vintage)",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(release_page_url=args.esri_release_page)
    write_snapshot(args.output, snapshot)
    print(f"wrote {args.output}")
    for series_id, row in snapshot["series"].items():
        last = row["observations"][-1]
        print(f"  {series_id}: {last['date']} {last['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
