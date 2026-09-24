#!/usr/bin/env python3
"""Refresh verified non-US rates, ECB policy rates, and leftover market cards.

Does not run build_macro_monitor.py. Reads the already-built
public/data/macro_monitor_v1.json and replaces only the indicator ids in
macro_monitor.peer_macro. A series that fails to download keeps its previous
value.

Suggested schedule for a workflow (do not add the YAML here; that path is
owned separately):

- Daily, after macro_live_overlay_refresh. FRED long-term rates are monthly,
  so most days are a no-op refresh of the same print. Yahoo cards move daily.
- ECB policy rates (deposit facility, MRO, MLF) can change on decision days;
  a daily job covers that without a separate calendar.

Not in this job, on purpose:

- CPI, GDP, and most policy rates (SARB repo, BOK, BOJ call, BoE Bank Rate,
  and the rest). The FRED OECD mirrors checked on 2026-09-23 still ended in
  2023–2025. They are not grafted.
- US FX watch. No API; update the hand table when Treasury publishes the
  next semiannual report.
- Japan growth diagnostics. japan_growth_refresh.yml already exists and has
  been failing on a missing openpyxl import.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.peer_macro import apply_peer_macro  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=PACK)
    ap.add_argument("--today", type=str, default=None, help="YYYY-MM-DD, default today")
    args = ap.parse_args()

    doc = json.loads(args.pack.read_text(encoding="utf-8"))
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stats = apply_peer_macro(doc, today=today, retrieved_at=retrieved_at)
    if stats["ok"]:
        args.pack.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    print(f"peer macro: ok={len(stats['ok'])} fail={len(stats['fail'])} skip={len(stats['skip'])}")
    for row in stats["ok"]:
        print("  OK", row)
    for row in stats["fail"]:
        print("  FAIL", row)
    for row in stats["skip"]:
        print("  SKIP", row)
    return 0 if stats["ok"] or not stats["fail"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
