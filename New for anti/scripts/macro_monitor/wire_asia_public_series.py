#!/usr/bin/env python3
"""Replace Hong Kong, Singapore and Taiwan fixture indicators with observed series (hk_public_series.py,
sg_public_series.py, tw_public_series.py). All keyless.

    python3 wire_asia_public_series.py

Idempotent: a series that cannot be read leaves its previous card, the pack is rewritten only when
something changed, and exit status 1 reports which series failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import hk_public_series as hks  # noqa: E402
from macro_monitor import sg_public_series as sgs  # noqa: E402
from macro_monitor import tw_public_series as tws  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def _run(iso3: str, country: dict, specs, read, build, apply, retrieved: str) -> tuple[bool, list[str]]:
    patches, failures = {}, []
    for spec_id in specs:
        try:
            patches[spec_id] = build(spec_id, read(spec_id), retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{iso3} {spec_id}: {exc}")
    result = apply(country, patches, retrieved_at=retrieved)
    print(f"{iso3}: {len(patches)} read, changed {result['changed'] or 'none'}")
    for sid, p in patches.items():
        print(f"  {sid:20s} {p['display']:>12s}  {p['reference_period']}  (as of {p['asof']})")
    return bool(result["changed"] or result["summary_changed"]), failures


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    retrieved = ups.now_iso()

    suppressed = hks.fetch_suppressed()
    files: dict[str, str] = {}

    def hk_read(spec_id: str):
        return hks.series_for(spec_id, lambda name: files.setdefault(name, hks.fetch_file(name)), suppressed)

    rows: dict[tuple[str, str], tuple] = {}

    def sg_fetch(table: str, row: str):
        if (table, row) not in rows:
            rows[(table, row)] = sgs.fetch_row(table, row)
        return rows[(table, row)]

    hk_changed, hk_fail = _run("HKG", by_iso["HKG"], hks.SPECS, hk_read, hks.build_patch, hks.apply_all, retrieved)
    sg_changed, sg_fail = _run("SGP", by_iso["SGP"], sgs.SPECS, lambda s: sgs.series_for(s, sg_fetch),
                               sgs.build_patch, sgs.apply_all, retrieved)
    tables: dict[str, dict] = {}

    def tw_table(code: str) -> dict:
        if code not in tables:
            tables[code] = tws.fetch_table(code)
        return tables[code]

    tw_changed, tw_fail = _run("TWN", by_iso["TWN"], tws.SPECS, lambda s: tws.series_for(s, tw_table),
                               tws.build_patch, tws.apply_all, retrieved)
    if hk_changed or sg_changed or tw_changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    failures = hk_fail + sg_fail + tw_fail
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
