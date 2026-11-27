#!/usr/bin/env python3
"""Fold each country's delinquency cards into one (see macro_monitor/credit_merge.py).

    python3 wire_credit_merge.py

Runs after wire_free_cards.py and the Korean bank / non-bank wires (it reads the cards they build) and before
apply_hidden_flags.py (which hides the absorbed cards listed in config/hidden_cards_v1.json). A failed US read
keeps the US card's previous panels; the Korean panels need no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import credit_merge as cm  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
HIDDEN = ROOT / "config" / "hidden_cards_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    us, failed = None, None
    try:
        us = cm.us_panels(ups.fetch_fred)
    except Exception as exc:  # noqa: BLE001
        failed = exc
    changed = cm.apply(pack, us)
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    hidden = json.loads(HIDDEN.read_text(encoding="utf-8"))
    missing = [k for k in cm.hide_keys() if k not in hidden.get("hide", [])]
    if missing:
        print(f"note: not hidden yet (add to {HIDDEN.name}): {', '.join(missing)}", file=sys.stderr)
    print(f"credit merge: changed {changed or 'none'}")
    if failed:
        print(f"FAILED US delinquency panels: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
