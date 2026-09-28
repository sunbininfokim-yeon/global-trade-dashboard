#!/usr/bin/env python3
"""Replace South Africa's fixture indicators with observed series (see za_public_series.py).

    python3 wire_za_public_series.py      # SARB web API + FRED + World Bank Pink Sheet, all keyless

SARB answers are accumulated in config/za_sarb_series_v1.json; when the SARB site cannot be reached the
kept observations are used, so a blocked run keeps the cards. Idempotent: a series that cannot be read
leaves its previous card, the pack is rewritten only when something changed, and exit status 1 reports
which series failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import za_public_series as zas  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    zaf = next(c for c in pack["countries"] if c["iso3"] == "ZAF")
    retrieved = ups.now_iso()
    cache = zas.load_cache()
    updates: dict = {}
    src = zas.Sources(sarb=zas.sarb_reader(cache, updates))

    patches, failures = {}, []
    for spec_id in zas.SPECS:
        try:
            pts, last_day = zas.series_for(spec_id, src)
            patches[spec_id] = zas.build_patch(spec_id, pts, last_day, retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{spec_id}: {exc}")

    cache_written = zas.save_cache(cache, updates, retrieved)
    result = zas.apply_all(zaf, patches, retrieved_at=retrieved)
    if result["changed"] or result["summary_changed"]:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"ZAF public series: {len(patches)} read, changed {result['changed'] or 'none'}"
          f"{', SARB cache updated' if cache_written else ''}")
    for sid, p in patches.items():
        print(f"  {sid:20s} {p['display']:>12s}  {p['reference_period']}  (as of {p['asof']})")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
