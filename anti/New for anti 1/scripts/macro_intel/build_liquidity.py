#!/usr/bin/env python3
"""CLI: build liquidity_intel_v1 snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_intel.build import build_liquidity_intel, write_json  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Build liquidity / official macro intel JSON")
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "liquidity_intel_v1.json",
    )
    p.add_argument("--fixtures", type=Path, default=None)
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument(
        "--qra-url",
        default=None,
        help="Explicit Treasury press URL (e.g. sb0584 Marketable Borrowing Estimates)",
    )
    p.add_argument(
        "--enrich-reporter-bodies",
        action="store_true",
        help="Fetch full article pages for priority reporters (slower; better FIMA/TGA recall)",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    doc = build_liquidity_intel(
        fetch_live=not args.no_fetch and args.fixtures is None,
        fixture_dir=args.fixtures,
        explicit_qra_url=args.qra_url,
        enrich_reporter_bodies=args.enrich_reporter_bodies,
    )
    write_json(doc, args.output)
    if args.print_stats:
        print(doc["stats"])
        liq = doc["liquidity"]
        print("bias", liq.get("bias"), liq.get("headline_ko"))
        print("panel", liq.get("finance_panel_fields"))
        rl = liq.get("reporter_liquidity") or []
        if rl:
            print("reporter top indicators:", (rl[0].get("top_indicators") or [])[:5])
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
