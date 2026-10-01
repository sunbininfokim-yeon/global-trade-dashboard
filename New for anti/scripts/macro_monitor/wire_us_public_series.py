#!/usr/bin/env python3
"""Replace the USA fixture indicators with observed public series (see us_public_series.py).

    python3 build_fima_repo.py            # H.4.1 FIMA repo history (first run backfills)
    python3 wire_us_public_series.py      # fetch FRED, graft into public/data/macro_monitor_v1.json

Idempotent and safe to run daily: a series that cannot be fetched leaves its previous card, the
pack is rewritten only when a value changed, and exit status 1 reports which series failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
FIMA = ROOT / "config" / "fima_repo_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    retrieved = ups.now_iso()

    cache: dict[str, ups.Points] = {}

    def fred(sid: str) -> ups.Points:
        if sid not in cache:
            cache[sid] = ups.fetch_fred(sid)
        return cache[sid]

    fima_weeks = None
    if FIMA.exists():
        fima_weeks = [(r["wednesday"], float(r["foreign_official_mn"])) for r in json.loads(FIMA.read_text(encoding="utf-8"))["weeks"]]

    patches, failures = {}, []
    for spec_id, spec in ups.SPECS.items():
        try:
            points = ups.series_for(spec_id, fred, fima_weeks)
            patches[spec_id] = ups.build_patch(spec, points, retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{spec_id}: {exc}")

    result = ups.apply_all(usa, patches, retrieved_at=retrieved)
    if result["changed"] or result["removed"] or result["summary_changed"]:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"USA public series: {len(patches)} fetched, changed {result['changed'] or 'none'}, removed {result['removed'] or 'none'}")
    for sid, p in patches.items():
        print(f"  {sid:18s} {p['display']:>10s}  {p['reference_period']}")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
