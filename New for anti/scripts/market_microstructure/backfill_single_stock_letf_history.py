#!/usr/bin/env python3
"""Backfill observed Hynix/Samsung LETF history from KRX EOD data.

The KRX credential is read only by ``market_microstructure.krx_client`` from
``KRX_API``.  Past dates deliberately omit Naver investor flows.  Weekends and
KRX holidays produce no row; no values are interpolated or demo-seeded.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fetch_kr_live import build_day_from_krx  # noqa: E402
from market_microstructure.derivatives_history import (  # noqa: E402
    append_jsonl,
    stock_records_from_micro,
    validate_stock_record,
)
from market_microstructure.engine import build_snapshot  # noqa: E402
from market_microstructure.krx_client import KRXAPIError, KRXAuthError  # noqa: E402


DEFAULT_START = "2026-05-27"
TARGET_TICKERS = {"000660", "005930"}


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"date must be YYYY-MM-DD, got {value!r}"
        ) from exc


def trading_day_candidates(start: date, end: date) -> list[date]:
    """Return weekdays only; the KRX response determines exchange holidays."""
    if end < start:
        raise ValueError("end must be on or after start")
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def records_for_day(day: date) -> list[dict]:
    live_day = build_day_from_krx(
        bas_dd=day.strftime("%Y%m%d"),
        include_naver_flows=False,
    )
    snapshot = build_snapshot(live_day)
    return [
        record
        for record in stock_records_from_micro(snapshot)
        if record["ticker"] in TARGET_TICKERS
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_day, default=_parse_day(DEFAULT_START))
    parser.add_argument("--end", type=_parse_day, required=True, help="inclusive KST date")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/stock_letf_history_v1.jsonl",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    written = 0
    skipped = 0
    for candidate in trading_day_candidates(args.start, args.end):
        try:
            records = records_for_day(candidate)
        except KRXAuthError:
            raise
        except (KRXAPIError, RuntimeError) as exc:
            skipped += 1
            print(f"skip {candidate.isoformat()}: {exc}")
            continue
        if not records:
            skipped += 1
            print(f"skip {candidate.isoformat()}: no target LETF observation")
            continue
        if args.dry_run:
            print(
                "would append "
                + candidate.isoformat()
                + " "
                + ",".join(record["ticker"] for record in records)
            )
            written += len(records)
            continue
        written += append_jsonl(
            args.out,
            records,
            validator=validate_stock_record,
            key_fields=("date", "ticker"),
        )
        print(
            "appended "
            + candidate.isoformat()
            + " "
            + ",".join(record["ticker"] for record in records)
        )

    print(f"single-stock LETF backfill complete: rows={written} skipped_dates={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
