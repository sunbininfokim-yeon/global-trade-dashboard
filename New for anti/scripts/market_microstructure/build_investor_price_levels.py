#!/usr/bin/env python3
"""Build investor×price-level bins (retail / foreign / institution).

  ../../.venv/bin/python build_investor_price_levels.py --live --print-stats
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
    markdown_investor_price_levels,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="Fetch Naver trend + FDR OHLC")
    p.add_argument("--page-size", type=int, default=60)
    p.add_argument("--bins", type=int, default=12)
    p.add_argument(
        "--tickers",
        default="000660:SK하이닉스,005930:삼성전자",
        help="code:label pairs comma-separated",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if not args.live:
        print("Use --live to fetch; fixture mode not shipped yet.", file=sys.stderr)
        return 2

    pairs: list[tuple[str, str]] = []
    for part in args.tickers.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            code, label = part.split(":", 1)
        else:
            code, label = part, part
        pairs.append((code.strip(), label.strip()))

    rep = build_investor_price_levels_report(
        pairs, page_size=args.page_size, n_bins=args.bins
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
        print(md)
    return 0 if not rep.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
