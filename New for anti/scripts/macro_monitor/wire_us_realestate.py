#!/usr/bin/env python3
"""US '부동산' tab: fetch the series in macro_monitor/us_realestate.py (FRED, keyless) and graft them into
public/data/macro_monitor_v1.json as their own category.

    python3 wire_us_realestate.py

Idempotent: creates the tab and cards on the first run, afterwards only rewrites the pack when a value
changed. A series that cannot be fetched keeps its previous card; exit status 1 names it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import us_realestate as ure  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    retrieved = ups.now_iso()
    cache: dict[str, ups.Points] = {}

    def fred(sid: str) -> ups.Points:
        if sid not in cache:
            cache[sid] = ups.fetch_fred(sid)
        return cache[sid]

    patches, failures = {}, []
    for sid, spec in ure.SPECS.items():
        try:
            pts = ure.series_for(sid, fred)
            patches[sid] = ups.build_patch(spec, pts, retrieved_at=retrieved)
            patches[sid]["note_ko"] += ure.extra_note(sid, pts)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{sid}: {exc}")
    changed = ure.apply(pack, patches)
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"US real estate: {len(patches)} fetched, changed {changed or 'none'}")
    for sid, p in patches.items():
        print(f"  {sid:22s} {p['display']:>10s}  {p['reference_period']}")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
