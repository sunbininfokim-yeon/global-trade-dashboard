#!/usr/bin/env python3
"""Build the market-wide FreeSIS credit/deposit overlay JSON.

This is intentionally a separate output from investor price levels: price-bin
flows are ticker/index observations, while FreeSIS is a market-wide aggregate.
The UI must keep that scope label when it overlays these series.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fetch_kr_public_extras import fetch_deposit_credit

ROOT = Path(__file__).resolve().parent


def build_payload() -> dict:
    credit = fetch_deposit_credit()
    return {
        "schema": "deposit_credit_v1",
        "as_of": credit.get("as_of"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "market_scope_ko": "시장 전체 · 종목별/주체별 포지션 아님",
        "deposit_credit": credit,
        "ui_ko": (
            "표: components[] (담보 제외). 예탁·신용=조원, 미수·반대=억원+비율. "
            "Y오른쪽 기본 credit_over_deposit_pct. 시장 전체 배지 필수."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "../../public/data/deposit_credit_v1.json"
    )
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    if (payload.get("deposit_credit") or {}).get("quality") != "observed":
        print("ERROR: no observed FreeSIS/Naver credit data; refusing to write a demo snapshot")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} as_of={payload.get('as_of')}")
    if args.print_stats:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
