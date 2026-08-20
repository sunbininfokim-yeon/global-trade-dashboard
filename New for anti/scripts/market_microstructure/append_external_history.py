#!/usr/bin/env python3
"""Append dated HK/US leveraged ETF observations from an external snapshot.

This is deliberately separate from the KR LETF/derivatives history writer.
Yahoo rows are kept as ``partial`` because AUM is a current, unstamped
snapshot and volume×close is a turnover proxy.  No Bloomberg data is required
to start accumulating the archive, and no missing market day is fabricated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.external_history import (  # noqa: E402
    append_external_history,
    external_records_from_snapshot,
)


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external",
        type=Path,
        default=ROOT / "../../public/data/external_venues_v1.json",
        help="one external_venues snapshot produced by build_market_microstructure.py",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/external_leverage_history_v1.jsonl",
    )
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    if not args.external.is_file():
        print(f"External snapshot unavailable; no history row written: {args.external}")
        return 0
    records = external_records_from_snapshot(_load(args.external))
    count = append_external_history(args.out, records) if records else 0
    print(
        f"External leverage history append={count}"
        + (" (no dated Yahoo bars; no placeholder written)" if not records else "")
    )
    if args.print_stats:
        print(
            "rows: "
            + ", ".join(f"{r['venue']}:{r['ticker']}@{r['date']}" for r in records)
            if records
            else "rows: skipped"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
