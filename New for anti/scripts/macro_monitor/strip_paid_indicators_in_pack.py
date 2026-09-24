#!/usr/bin/env python3
"""Drop indicators that can only be bought from a data terminal.

    python3 strip_paid_indicators_in_pack.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.paid_only import strip_paid_only  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = Path(sys.argv[1]) if len(sys.argv) > 1 else PACK
    doc = json.loads(pack.read_text(encoding="utf-8"))
    removed = strip_paid_only(doc)
    pack.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"removed {len(removed)} paid-only cards")
    for row in removed:
        print(f"  {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
