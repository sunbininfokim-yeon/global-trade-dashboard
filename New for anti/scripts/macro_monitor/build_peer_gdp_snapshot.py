#!/usr/bin/env python3
"""Fetch World Bank real GDP growth (annual actuals only) for all monitor countries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.peer_gdp import build_snapshot  # noqa: E402

OUT = ROOT / "config" / "peer_gdp_v1.json"


def main() -> int:
    snapshot = build_snapshot()
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for iso3, row in snapshot["countries"].items():
        obs = row.get("observations") or []
        latest = obs[-1] if obs else None
        tail = f"latest {latest['date']} {latest['value']}%" if latest else row.get("status")
        print(f"  {iso3}: {row['status']} ({len(obs)} years) {tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
