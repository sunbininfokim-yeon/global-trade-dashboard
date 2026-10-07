#!/usr/bin/env python3
"""Write each country's source/licence footnotes (config/source_notices_v1.json) onto the pack as
``source_notices``; the macro panel prints them under the cards.

    python3 apply_source_notices.py

Idempotent: the pack is rewritten only when a country's notices changed. A country missing from the
config keeps whatever it has, so a hand-maintained country (e.g. Indonesia's BPS notice) is left alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
NOTICES = ROOT / "config" / "source_notices_v1.json"


def apply(pack: dict, notices: dict) -> list[str]:
    changed = []
    for country in pack["countries"]:
        want = notices.get(country["iso3"])
        if want is not None and country.get("source_notices") != want:
            country["source_notices"] = want
            changed.append(country["iso3"])
    return changed


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    notices = {k: v for k, v in json.loads(NOTICES.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    changed = apply(pack, notices)
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"source notices: {changed or 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
