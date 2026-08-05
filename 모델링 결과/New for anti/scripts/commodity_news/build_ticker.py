#!/usr/bin/env python3
"""CLI: build commodity news ticker snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_news.build import build_ticker, write_ticker  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Build commodity/diplomacy ticker_v1 JSON")
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "ticker_v1.json",
        help="Output snapshot path",
    )
    p.add_argument("--limit", type=int, default=40)
    p.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="Directory of {source_id}.xml fixtures (offline)",
    )
    p.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not hit live RSS (use with --fixtures)",
    )
    p.add_argument(
        "--translate",
        action="store_true",
        help="Translate titles to Korean via MyMemory free API",
    )
    p.add_argument(
        "--translate-email",
        default=None,
        help="Optional email for higher MyMemory free quota",
    )
    p.add_argument(
        "--print-stats",
        action="store_true",
        help="Print feed/score stats to stdout",
    )
    args = p.parse_args()

    doc = build_ticker(
        limit=args.limit,
        fetch_live=not args.no_fetch and args.fixtures is None,
        translate=args.translate,
        translate_email=args.translate_email,
        fixture_dir=args.fixtures,
    )
    write_ticker(doc, args.output)
    if args.print_stats:
        stats = doc["stats"]
        print(
            f"sources_ok={stats['sources_ok']} failed={stats['sources_failed']} "
            f"raw={stats['raw_items']} scored={stats['scored_items']} "
            f"selected={stats['selected_items']}"
        )
        print("regions:", stats.get("region_histogram"))
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
