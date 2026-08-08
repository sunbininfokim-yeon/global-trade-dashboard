#!/usr/bin/env python3
"""Build real-data KOSPI investor×price tables.

Default: 시총 상위 N + 시총 100위 내 고변동 N (union). Live Naver/FDR only.

  python build_investor_price_levels.py --live --universe both --top 10 --pool 100
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
    p.add_argument("--live", action="store_true")
    p.add_argument("--page-size", type=int, default=60)
    p.add_argument("--bins", type=int, default=12)
    p.add_argument("--top", type=int, default=10, help="Marcap top-N and/or high-vol top-N")
    p.add_argument(
        "--pool",
        type=int,
        default=100,
        help="Marcap pool for high-vol screen (default 100)",
    )
    p.add_argument(
        "--universe",
        choices=["both", "high_vol", "marcap"],
        default="both",
        help="both=시총상위+시총pool내고변동 (default)",
    )
    p.add_argument(
        "--tickers",
        default=None,
        help="Optional override code:label,... (skips universe)",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if not args.live:
        print("Use --live (real fetch only; no demo).", file=sys.stderr)
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

    rep = build_investor_price_levels_report(
        pairs,
        page_size=args.page_size,
        n_bins=args.bins,
        kospi_top_n=args.top,
        universe_mode=args.universe if not pairs else "custom",
        high_vol_pool=args.pool,
    )
    # Refuse to ship if everything missing
    ok_n = sum(1 for t in (rep.get("tickers") or {}).values() if t.get("quality") == "observed")
    if ok_n == 0 and (rep.get("kospi_index_levels") or {}).get("quality") != "observed":
        print("ERROR: no observed data — refuse to write demo snapshot", file=sys.stderr)
        return 1

    pub = ROOT / "../../public/data"
    pub.mkdir(parents=True, exist_ok=True)
    out = pub / "investor_price_levels_v1.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = markdown_investor_price_levels(rep)
    (ROOT / "INVESTOR_PRICE_LEVELS.md").write_text(md + "\n", encoding="utf-8")
    print(f"Wrote {out} (observed tickers={ok_n})")
    print(f"Wrote {ROOT / 'INVESTOR_PRICE_LEVELS.md'}")
    if args.print_stats:
        print(md)
    return 0 if not rep.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
