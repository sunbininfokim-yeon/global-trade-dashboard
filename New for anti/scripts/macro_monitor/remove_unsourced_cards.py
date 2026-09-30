#!/usr/bin/env python3
"""Drop indicator cards that were looked into for a real-amount source and came up empty, so they don't
sit as a permanent fake YoY rather than being decided one way or the other.

    python3 remove_unsourced_cards.py

Idempotent (removing an id that is already gone is a no-op) and safe to extend: add to REMOVE below
and re-run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"

# (iso3, indicator id, why): Vietnam's export card (export_yoy_vn) -- GSO's site does not resolve and
# Vietnam Customs renders blank; FRED/OECD MEI (the route that covered Israel) has no Vietnam goods-export
# series. Checked 2026-09-28; see docs/ops/handoff for the fuller source-by-source writeup.
REMOVE = [
    ("VNM", "export_yoy_vn", "no free export-amount source found (GSO unreachable, Customs blank, no FRED/OECD MEI series)"),
    # Singapore SORA (2026-09-29): only MAS publishes it, and the MAS API portal's terms forbid republishing
    # without prior written permission; SingStat and data.gov.sg carry no SORA. The spread needs SORA too.
    ("SGP", "sora", "MAS API terms forbid republishing; no open-licensed SORA source"),
    ("SGP", "sofr_sora_spread", "needs SORA (see above)"),
    # SIPMM PMI (2026-09-30): SIPMM publishes the PMI as a press-release PDF with no data feed or open
    # licence, and SingStat/data.gov.sg don't carry it.
    ("SGP", "sipmm_pmi", "no feed or open licence for the SIPMM PMI"),
]


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    changed = []
    for iso3, indicator_id, why in REMOVE:
        country = by_iso.get(iso3)
        if country is None:
            print(f"  SKIP {iso3}:{indicator_id} -- country not in pack", file=sys.stderr)
            continue
        if ups.remove_indicator(country, indicator_id):
            ups.refresh_status_summary(country)
            changed.append(f"{iso3}:{indicator_id}")
            print(f"  removed {iso3}:{indicator_id} ({why})")
        else:
            print(f"  {iso3}:{indicator_id} already gone")
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"removed: {changed or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
