#!/usr/bin/env python3
"""Build the historical end-of-day LETF trading-share JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.letf_history import (  # noqa: E402
    append_point,
    business_dates,
    point_from_krx_rows,
    point_from_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Backfill business days via KRX OpenAPI")
    parser.add_argument("--append-only", action="store_true", help="Append current market snapshot")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--out", type=Path, default=ROOT / "../../public/data/market_microstructure_history_v1.json")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "../../public/data/market_microstructure_v1.json")
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    history = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {
        "schema_version": "market-microstructure-history-v1", "points": []
    }
    if args.append_only:
        point = None
        # On Actions, prefer the same KRX daily rows used by the history
        # backfill.  The snapshot fallback keeps local/demo runs explicit.
        if os.environ.get("KRX_API") or os.environ.get("KRX_OPENAPI_KEY"):
            from market_microstructure.krx_client import fetch_etf_daily, fetch_stock_daily, recent_bas_dd

            day = recent_bas_dd()
            point = point_from_krx_rows(
                date=f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                stock_rows=fetch_stock_daily(day),
                etf_rows=fetch_etf_daily(day),
            )
        if point is None:
            point = point_from_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")))
        if point is None:
            print("ERROR: current snapshot has no observed trading-share point")
            return 1
        history = append_point(history, point)
    elif args.live:
        if not (os.environ.get("KRX_API") or os.environ.get("KRX_OPENAPI_KEY")):
            print("ERROR: --live requires KRX_API for historical KRX daily turnover")
            return 1
        from market_microstructure.krx_client import fetch_etf_daily, fetch_stock_daily

        for day in business_dates(args.months):
            try:
                point = point_from_krx_rows(
                    date=f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                    stock_rows=fetch_stock_daily(day),
                    etf_rows=fetch_etf_daily(day),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"skip {day}: {type(exc).__name__}: {exc}")
                continue
            if point is not None:
                history = append_point(history, point)
    else:
        parser.error("pass --live or --append-only")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({history.get('n_points', 0)} points)")
    if args.print_stats:
        print(json.dumps(history, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
