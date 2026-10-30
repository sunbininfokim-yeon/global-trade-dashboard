#!/usr/bin/env python3
"""Replace the Singapore and Israel export-rate fixtures with export amounts (see export_public_series.py).

    python3 wire_export_series.py      # SingStat + FRED, keyless; graft into public/data/macro_monitor_v1.json

Idempotent: a series that cannot be read leaves its previous card, the pack is rewritten only when
something changed, and exit status 1 reports which series failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import export_public_series as eps  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    retrieved = ups.now_iso()
    changed, failures = [], []
    for e in eps.EXPORTS:
        try:
            patch = eps.build_patch(e, eps.series_for(e), retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the other
            failures.append(f"{e.iso3} {e.new_id}: {exc}")
            continue
        if eps.apply(by_iso[e.iso3], e, patch):
            changed.append(f"{e.iso3}:{e.new_id}")
        print(f"  {e.iso3} {e.new_id:10s} {patch['display']:>10s}  {patch['reference_period']}  (as of {patch['asof']})")
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"export amounts: changed {changed or 'none'}")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
