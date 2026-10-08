#!/usr/bin/env python3
"""Attach contributions to real GDP growth (consumption / investment / government / net exports) to the
`gdp` card of each country in gdp_contrib.COUNTRIES. Keyless (FRED, Eurostat).

    python3 wire_gdp_contrib.py

Idempotent: the pack is rewritten only when a breakdown changed; a country that cannot be read keeps
its previous breakdown and is reported (exit 1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import gdp_contrib as gc  # noqa: E402
from macro_monitor.world_public_series import Fetch  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    fetch, failures = Fetch(), []
    for iso3 in gc.COUNTRIES:
        try:
            contrib = gc.build(iso3, lambda kind, key: fetch.get(kind, key) if kind == "fred"
                               else fetch.get("eurostat", "namq_10_gdp", key))
        except Exception as exc:  # noqa: BLE001 -- one country failing must not block the others
            failures.append(f"{iso3}: {str(exc)[:150]}")
            continue
        changed = gc.apply(by_iso[iso3], contrib)
        lt = contrib["latest"]
        parts = ", ".join(f"{p['label_ko']} {p['values'][-1]:+.2f}" for p in contrib["parts"])
        print(f"{iso3} {lt['period']}: GDP {lt['total']:+.2f} = {parts} (잔차 {lt['residual']:+.2f})"
              f"{'' if changed else ' -- unchanged'}")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
