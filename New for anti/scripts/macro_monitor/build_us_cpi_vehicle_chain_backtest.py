#!/usr/bin/env python3
"""Write a minimal BLS-only vehicle CPI relationship report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi.vehicle_chain_backtest import build_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "cpi_vehicle_chain_backtest_v1.json")
    parser.add_argument("--out", type=Path, required=True, help="Minimal result JSON; no raw series are written")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    document = build_snapshot(config, bls_api_key=os.environ.get("BLS_API_KEY", ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for row in document["relationships"]:
        print(f"{row['id']}: best_lag={row['best_lag_out_of_sample_exploratory']['lag_months']} activation={row['activation']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
