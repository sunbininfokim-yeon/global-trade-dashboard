#!/usr/bin/env python3
"""Refresh only the live FRED/Yahoo/BOK overlay in the deployed macro pack.

build_macro_monitor.py --live applies this same overlay_live() step, but only
after a full build_universe() rebuild -- and nothing has ever scheduled that
combination in CI (confirmed 2026-09-16: no workflow references
build_macro_monitor.py at all). The result: every "quality": "live_latest"
indicator (TGA, DXY, UST yields, SOFR, Fed balance sheet, world equity
indices/FX, ...) was frozen at whatever a human last ran locally, with no
automation and no visible staleness signal -- TGA sat 16+ days behind FRED's
own published WTREGEN print before this was noticed.

This instead loads the already-built macro_monitor_v1.json and overlays live
values directly onto it in place, the same graft-not-rebuild shape as
refresh_sovereign_fiscal_in_pack.py / refresh_japan_growth_in_pack.py: it
never re-derives the base country packs (which would require re-running
every other attach layer wired into engine.py) and only touches the specific
indicator IDs overlay_live() knows about.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.live_overlay import overlay_live  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=PACK)
    ap.add_argument("--asof", type=str, default=None, help="YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    doc = json.loads(args.pack.read_text(encoding="utf-8"))
    asof = date.fromisoformat(args.asof) if args.asof else date.today()

    stats = overlay_live(doc, asof=asof)
    doc["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    args.pack.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(f"live overlay: ok={len(stats['ok'])} fail={len(stats['fail'])} skip={len(stats['skip'])}")
    for x in stats["ok"]:
        print("  OK", x)
    for x in stats["fail"]:
        print("  FAIL", x)
    # A failure here is a single series that didn't refresh (stays at its
    # last known value) -- not a reason to fail the whole job and skip
    # committing every series that DID refresh successfully.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
