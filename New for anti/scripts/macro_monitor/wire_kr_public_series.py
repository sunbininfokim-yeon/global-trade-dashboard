#!/usr/bin/env python3
"""Replace the Korea fixture indicators with observed series (see kr_public_series.py).

    set -a; . ~/.config/ecos.env; set +a
    python3 wire_kr_public_series.py      # fetch ECOS (+FRED), graft into public/data/macro_monitor_v1.json

With ECOS_API_KEY set the series are read live and remembered in config/kr_ecos_series_v1.json; without
it the cached series are used, so a scheduled run without the secret keeps the cards. Idempotent: a series
that cannot be read leaves its previous card, the pack is rewritten only when something changed, and
exit status 1 reports which series failed.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ecos  # noqa: E402
from macro_monitor import kr_public_series as krs  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    kor = next(c for c in pack["countries"] if c["iso3"] == "KOR")
    retrieved = ups.now_iso()
    cache = krs.load_cache()
    updates: dict = {}
    src = krs.Sources(ecos_read=krs.ecos_reader(cache, updates, date.today()))

    patches, failures, skipped = {}, [], []
    for spec_id in krs.SPECS:
        try:
            patches[spec_id] = krs.build_patch(spec_id, krs.series_for(spec_id, src), retrieved_at=retrieved)
        except ecos.MissingKey as exc:
            skipped.append(f"{spec_id}: {exc} and nothing cached")
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{spec_id}: {exc}")

    cache_written = krs.save_cache(cache, updates, retrieved) if updates else False
    result = krs.apply_all(kor, patches, retrieved_at=retrieved)
    if result["changed"] or result["summary_changed"]:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"KOR public series: {len(patches)} read, changed {result['changed'] or 'none'}"
          f"{', ECOS cache updated' if cache_written else ''}")
    for sid, p in patches.items():
        print(f"  {sid:20s} {p['display']:>12s}  {p['reference_period']}  (as of {p['asof']})")
    for sk in skipped:
        print(f"  skipped {sk}")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
