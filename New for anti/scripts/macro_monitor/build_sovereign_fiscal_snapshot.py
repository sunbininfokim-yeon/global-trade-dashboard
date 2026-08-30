#!/usr/bin/env python3
"""Refresh the official-source sovereign debt and interest snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.sovereign_fiscal import build_snapshot, write_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build IMF/Treasury sovereign fiscal snapshot")
    parser.add_argument("--output", type=Path, default=ROOT / "config" / "sovereign_fiscal_v1.json")
    args = parser.parse_args()
    snapshot = build_snapshot()
    write_snapshot(args.output, snapshot)
    print(f"wrote {args.output}")
    for iso3, row in snapshot["countries"].items():
        print(f"  {iso3}: {row['status']} {row.get('asof') or ''}")
    print(f"  USA interest/defense: {snapshot['us_defense_ratio']['status']} {snapshot['us_defense_ratio'].get('asof') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
