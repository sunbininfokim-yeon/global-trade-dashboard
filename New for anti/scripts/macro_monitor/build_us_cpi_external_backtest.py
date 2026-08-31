#!/usr/bin/env python3
"""Build the external-input CPI pathway report without touching UI data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi.external_backtest import build_snapshot  # noqa: E402


DEFAULT_CONFIG = ROOT / "config" / "cpi_external_backtest_v1.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_cpi_external_backtest_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate two external U.S. CPI pathway candidates")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    doc = build_snapshot(
        config,
        bls_api_key=os.environ.get("BLS_API_KEY", ""),
        eia_api_key=os.environ.get("EIA_API_KEY", ""),
        fred_api_key=os.environ.get("FRED_API_KEY", ""),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for row in doc["relationships"]:
        oos = row["out_of_sample"]
        print(
            f"{row['id']}: coverage={row['coverage']['first_month']}..{row['coverage']['last_month']} "
            f"oos={row['coverage']['oos_months']} rmse_improvement={oos['rmse_improvement_pct']} "
            f"activation={row['activation']['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
