#!/usr/bin/env python3
"""Fetch BLS CPI index histories with BLS_API_KEY and write a public snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi.api import build_cpi_api_history, fetch_series  # noqa: E402


DEFAULT_CONFIG = ROOT / "config" / "cpi_api_series.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_cpi_api_history_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch observed U.S. CPI indexes from BLS API")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    key = os.environ.get("BLS_API_KEY", "")
    raw = fetch_series(
        [row["series_id"] for row in config["series"]],
        registration_key=key,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    doc = build_cpi_api_history(config, raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.print_stats:
        print(f"wrote {args.out}")
        print(f"series={doc['coverage']['returned_series']} latest={doc['coverage']['latest_reference_period']}")
        by_id = {row["id"]: row for row in doc["series"]}
        for item_id in ("all_items", "core", "shelter", "motor_vehicle_insurance"):
            point = by_id[item_id]["observations"][-1]
            print(f"  {item_id}: {point['date']} MoM {point['mom_pct']:+.2f}% YoY {point['yoy_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
