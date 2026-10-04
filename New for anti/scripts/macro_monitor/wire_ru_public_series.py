#!/usr/bin/env python3
"""Replace Russia's fixture indicators with observed series (see ru_public_series.py).

    python3 wire_ru_public_series.py      # Bank of Russia + Moscow Exchange, keyless

The 10-year OFZ point is one date per request; its month-end values are kept in
config/ru_cbr_series_v1.json (the first run backfills them). Idempotent: a series that cannot be read
leaves its previous card, the pack is rewritten only when something changed, and exit status 1 reports
which series failed.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ru_public_series as rus  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    rus_pack = next(c for c in pack["countries"] if c["iso3"] == "RUS")
    retrieved = ups.now_iso()
    src = rus.Sources(today=date.today(), cache=rus.load_cache())

    patches, failures = {}, []
    for spec_id in rus.SPECS:
        try:
            pts, last_day = rus.series_for(spec_id, src)
            patches[spec_id] = rus.build_patch(spec_id, pts, last_day, retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{spec_id}: {exc}")

    if src.cache_changed:
        rus.save_cache(src.cache, retrieved)
    result = rus.apply_all(rus_pack, patches, retrieved_at=retrieved)
    if result["changed"] or result["summary_changed"]:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"RUS public series: {len(patches)} read, changed {result['changed'] or 'none'}"
          f"{', OFZ cache updated' if src.cache_changed else ''}")
    for sid, p in patches.items():
        print(f"  {sid:20s} {p['display']:>12s}  {p['reference_period']}  (as of {p['asof']})")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
