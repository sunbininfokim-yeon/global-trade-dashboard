#!/usr/bin/env python3
"""Graft verified peer yields, policy rates, FX, and equity prints.

Does not rebuild the pack. A series that fails or is stale keeps its card.

    python3 refresh_peer_macro_in_pack.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.keyless_prints import retrieved_now  # noqa: E402
from macro_monitor.peer_macro import apply_peer_macro  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=PACK)
    ap.add_argument("--today", type=str, default=None)
    args = ap.parse_args()
    doc = json.loads(args.pack.read_text(encoding="utf-8"))
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    stats = apply_peer_macro(doc, today=today, retrieved_at=retrieved_now())
    args.pack.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"peer macro as of {today.isoformat()}")
    for key in ("ok", "fail", "skip"):
        print(f"  {key} {len(stats[key])}")
        for row in stats[key]:
            print(f"    {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
