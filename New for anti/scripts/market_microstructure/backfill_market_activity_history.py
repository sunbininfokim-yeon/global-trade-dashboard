#!/usr/bin/env python3
"""Backfill KRX EOD activity/direction history without calendar filling.

Writes only the two market-wide JSONL logs:

* ``derivatives_activity_history_v1.jsonl`` — K200 futures/options activity;
* ``leverage_direction_history_v1.jsonl`` — Korean-listed levered/inverse ETF
  turnover by disclosed product-name direction, over KOSPI cash turnover.

No investor flow, OI, Naver snapshot, demo value, or held position is inferred.
The credential is read from ``KRX_API`` by the existing clients.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fetch_kr_derivatives import (  # noqa: E402
    aggregate_k200_futures_activity,
    aggregate_k200_options_activity,
    krx_drv,
)
from fetch_kr_public_extras import classify_letf_direction  # noqa: E402
from market_microstructure.derivatives_history import (  # noqa: E402
    activity_record_from_board,
    append_jsonl,
    validate_activity_record,
    validate_direction_record,
)
from market_microstructure.krx_client import (  # noqa: E402
    KRXAPIError,
    KRXAuthError,
    fetch_etf_daily,
    fetch_stock_daily,
)


DIRECTIONS = ("long", "inverse", "inverse_2x", "gobus_inverse_2x")


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"date must be YYYY-MM-DD, got {value!r}"
        ) from exc


def trading_day_candidates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end must be on or after start")
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    if len(days) > 250:
        raise ValueError("refusing more than 250 weekday candidates in one run")
    return days


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return None


def direction_record_from_krx_rows(
    day: date,
    stock_rows: list[dict[str, Any]],
    etf_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build the exact UI direction contract from one KRX EOD response."""
    if not stock_rows or not etf_rows:
        return None
    cash_tv = sum(
        _num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT") or 0.0
        for row in stock_rows
    )
    if cash_tv <= 0:
        return None

    by_direction: dict[str, dict[str, Any]] = {
        direction: {"n_products": 0, "trading_value_krw": 0.0}
        for direction in DIRECTIONS
    }
    for row in etf_rows:
        name = str(row.get("ISU_NM") or row.get("ISU_ABBRV") or "")
        if not any(token in name for token in ("레버리지", "인버스", "곱버스")):
            continue
        direction = classify_letf_direction(name)
        if direction not in by_direction:
            continue
        trading_value = _num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT")
        if trading_value is None:
            continue
        by_direction[direction]["n_products"] += 1
        by_direction[direction]["trading_value_krw"] += trading_value

    levered_tv = sum(
        float(row["trading_value_krw"]) for row in by_direction.values()
    )
    if levered_tv <= 0:
        return None
    for row in by_direction.values():
        value = float(row["trading_value_krw"])
        row["share_of_lev_tv_pct"] = round(value / levered_tv * 100.0, 6)
        row["share_of_kospi_tv_pct"] = round(value / cash_tv * 100.0, 6)

    iso = day.isoformat()
    record = {
        "date": iso,
        "as_of": iso,
        "source": (
            f"KRX OpenAPI sto/stk_bydd_trd + etp/etf_bydd_trd basDd={day:%Y%m%d}; "
            "ETF Name classify"
        ),
        "quality": "observed",
        "kospi_cash_tv_krw": cash_tv,
        "levered_inverse_etf_tv_over_kospi_cash_tv_pct": round(
            levered_tv / cash_tv * 100.0, 6
        ),
        "by_direction": by_direction,
    }
    validate_direction_record(record)
    return record


def activity_record_for_day(day: date) -> dict[str, Any] | None:
    compact = day.strftime("%Y%m%d")
    futures = aggregate_k200_futures_activity(krx_drv("fut_bydd_trd", compact))
    options = aggregate_k200_options_activity(krx_drv("opt_bydd_trd", compact))
    options["source"] = "KRX OpenAPI drv/opt_bydd_trd"
    board = {
        "kr": {
            "as_of": day.isoformat(),
            "kospi200_futures": futures,
            "kospi200_options": options,
        }
    }
    return activity_record_from_board(board)


def _auth_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, (KRXAuthError,)) or "401" in text or "403" in text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "../../public/data"
    )
    parser.add_argument("--activity-only", action="store_true")
    parser.add_argument("--direction-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.activity_only and args.direction_only:
        parser.error("choose at most one of --activity-only and --direction-only")

    do_activity = not args.direction_only
    do_direction = not args.activity_only
    counts = {"activity": 0, "direction": 0, "skipped_activity": 0, "skipped_direction": 0}

    for candidate in trading_day_candidates(args.start, args.end):
        if do_activity:
            try:
                activity = activity_record_for_day(candidate)
            except Exception as exc:  # noqa: BLE001
                if _auth_failure(exc):
                    raise
                activity = None
                print(f"skip activity {candidate}: {type(exc).__name__}: {exc}")
            if activity is None:
                counts["skipped_activity"] += 1
            elif args.dry_run:
                counts["activity"] += 1
                print(f"would append activity {candidate}")
            else:
                counts["activity"] += append_jsonl(
                    args.out_dir / "derivatives_activity_history_v1.jsonl",
                    [activity],
                    validator=validate_activity_record,
                    key_fields=("date",),
                )

        if do_direction:
            compact = candidate.strftime("%Y%m%d")
            try:
                direction = direction_record_from_krx_rows(
                    candidate,
                    fetch_stock_daily(compact),
                    fetch_etf_daily(compact),
                )
            except (KRXAuthError, KRXAPIError):
                raise
            except Exception as exc:  # noqa: BLE001
                direction = None
                print(f"skip direction {candidate}: {type(exc).__name__}: {exc}")
            if direction is None:
                counts["skipped_direction"] += 1
            elif args.dry_run:
                counts["direction"] += 1
                print(f"would append direction {candidate}")
            else:
                counts["direction"] += append_jsonl(
                    args.out_dir / "leverage_direction_history_v1.jsonl",
                    [direction],
                    validator=validate_direction_record,
                    key_fields=("date",),
                )

    print("market history backfill complete: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
