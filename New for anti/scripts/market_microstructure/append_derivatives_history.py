#!/usr/bin/env python3
"""Append observed derivatives/LETF snapshots to the three UI history logs.

Run after ``build_derivatives_board.py`` and ``build_market_microstructure.py``.
The script writes no synthetic backfill: if a source is missing or a market is
closed, that data set gets no row for the day.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.derivatives_history import (  # noqa: E402
    activity_record_from_board,
    append_jsonl,
    direction_record_from_micro,
    stock_records_from_micro,
    validate_activity_record,
    validate_direction_record,
    validate_stock_record,
)


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=ROOT / "../../public/data/derivatives_board_v1.json")
    parser.add_argument("--micro", type=Path, default=ROOT / "../../public/data/market_microstructure_v1.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "../../public/data")
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    board = _load(args.board)
    micro = _load(args.micro)

    activity = activity_record_from_board(board)
    direction = direction_record_from_micro(micro)
    stocks = stock_records_from_micro(micro)

    counts = {
        "activity": 0,
        "direction": 0,
        "stock_letf": 0,
    }
    if activity is not None:
        counts["activity"] = append_jsonl(
            args.out_dir / "derivatives_activity_history_v1.jsonl",
            [activity],
            validator=validate_activity_record,
            key_fields=("date",),
        )
    if direction is not None:
        counts["direction"] = append_jsonl(
            args.out_dir / "leverage_direction_history_v1.jsonl",
            [direction],
            validator=validate_direction_record,
            key_fields=("date",),
        )
    if stocks:
        counts["stock_letf"] = append_jsonl(
            args.out_dir / "stock_letf_history_v1.jsonl",
            stocks,
            validator=validate_stock_record,
            key_fields=("date", "ticker"),
        )

    print(
        "History append "
        + " · ".join(f"{name}={count}" for name, count in counts.items())
        + (" (0 means source unavailable; no placeholder written)" if not any(counts.values()) else "")
    )
    if args.print_stats:
        for name, record in (("activity", activity), ("direction", direction)):
            print(f"{name}: {record.get('date') if record else 'skipped'}")
        print("stock_letf: " + ", ".join(record["ticker"] for record in stocks) if stocks else "stock_letf: skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
