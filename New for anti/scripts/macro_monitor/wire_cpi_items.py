#!/usr/bin/env python3
"""Item-level CPI movers (the "항목별" tab) for Korea, Japan, the euro area, the UK, Canada and Brazil.

    python3 wire_cpi_items.py            # read the sources, update the snapshot, attach to the pack
    python3 wire_cpi_items.py --offline  # attach from the stored snapshot only

Korea needs ECOS_API_KEY (env); without it the Korean items keep what the snapshot has. The other
sources are keyless. An item that cannot be read keeps its stored observations and is reported.
The pack is rewritten only when a movers block changed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import cpi_items as ci  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main(argv: list[str]) -> int:
    snap = ci.load_snapshot()
    if "--offline" not in argv:
        readers = ci.Readers()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for iso3, country in ci.COUNTRIES.items():
            prev = (snap["countries"].get(iso3) or {}).get("items") or {}
            items, errors = ci.collect(country, readers, prev)
            entry = snap["countries"].setdefault(iso3, {})
            if items != prev:
                entry["items"] = items
                entry["retrieved_at"] = now
            entry["source"] = country.source
            read_ok = len(country.items) - len(errors)
            print(f"{iso3}: {read_ok}/{len(country.items)} items read")
            for e in errors:
                print(f"  kept stored -- {e}")
        ci.save_snapshot(snap)

    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    done = ci.attach(pack, snap)
    for iso3, what in done.items():
        print(f"  {iso3}: movers {what}")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
        print(f"wrote {PACK}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
