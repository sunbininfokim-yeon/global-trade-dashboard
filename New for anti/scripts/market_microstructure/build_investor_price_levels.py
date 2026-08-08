#!/usr/bin/env python3
"""Build Infomax-style KOSPI investor×price tables.

1) KOSPI index level × market 개인/외인/기관 (억원)
2) High-vol (or marcap) stocks: close-bin nets + same-day close table (주/원)

  python build_investor_price_levels.py --live --universe high_vol --top 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.investor_price_levels import (  # noqa: E402
    build_investor_price_levels_report,
    default_kospi_universe,
    high_vol_kospi_universe,
    markdown_investor_price_levels,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--page-size", type=int, default=60)
    p.add_argument("--bins", type=int, default=12)
    p.add_argument("--top", type=int, default=10)
    p.add_argument(
        "--universe",
        choices=["high_vol", "marcap"],
        default="high_vol",
        help="high_vol=realized-vol liquid commons (default); marcap=시총상위",
    )
    p.add_argument(
        "--tickers",
        default=None,
        help="Optional override code:label,... (skips universe)",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if not args.live:
        print("Use --live to fetch.", file=sys.stderr)
        return 2

    pairs: list[tuple[str, str]] | None = None
    if args.tickers:
        pairs = []
        for part in args.tickers.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                code, label = part.split(":", 1)
            else:
                code, label = part, part
            pairs.append((code.strip(), label.strip()))
    elif args.universe == "marcap":
        pairs = default_kospi_universe(top_n=args.top)
    else:
        pairs = high_vol_kospi_universe(top_n=args.top)

    rep = build_investor_price_levels_report(
        pairs,
        page_size=args.page_size,
        n_bins=args.bins,
        kospi_top_n=args.top,
        universe_mode=args.universe,
    )
    pub = ROOT / "../../public/data"
    pub.mkdir(parents=True, exist_ok=True)
    out = pub / "investor_price_levels_v1.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = markdown_investor_price_levels(rep)
    (ROOT / "INVESTOR_PRICE_LEVELS.md").write_text(md + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {ROOT / 'INVESTOR_PRICE_LEVELS.md'}")
    if args.print_stats:
        # Keep stdout shorter: index + day table + first ticker only if huge
        print(md)
    return 0 if not rep.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
