#!/usr/bin/env python3
"""Build/refresh Indonesia from observed series (see idn_public_series.py).

    BPS_API_KEY=... python3 wire_idn_public_series.py     # or the key in ~/.config/bps.env

The BPS key is a secret (public repository): it is read from the environment or ~/.config/bps.env and
never printed. Without it the run changes nothing. Indonesia is created on the first run with only
cards that have an observation; USD/IDR and the JCI come from the Yahoo overlay run here for Indonesia
alone (the daily overlay workflow keeps them current afterwards). Idempotent; exit 1 names failed series.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import idn_public_series as idn  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    src = idn.Sources()
    if not src.key:
        print("IDN: BPS_API_KEY not set -- Indonesia left as it is")
        return 0
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    country = idn.ensure_country(pack)
    retrieved = ups.now_iso()

    patches, failures = {}, []
    for spec_id in idn.SPECS:
        try:
            patches[spec_id] = idn.build_patch(spec_id, idn.series_for(spec_id, src), retrieved_at=retrieved)
        except Exception as exc:  # noqa: BLE001 -- one series failing must not block the others
            failures.append(f"{spec_id}: {exc}")
    result = idn.apply_all(country, patches, retrieved_at=retrieved)

    if any(i.get("value") is None for i in country["indicators"] if i["id"] in (*idn.YAHOO_CARDS, "sovereign_ratings")):
        from macro_monitor.live_overlay import overlay_live
        overlay_live({"countries": [country]})
    gone = idn.prune_empty(country)
    idn.sync_headlines(country)
    ups.refresh_status_summary(country)

    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"IDN public series: {len(patches)} read, changed {result['changed'] or 'none'}"
          f"{f', removed empty {gone}' if gone else ''}")
    for sid, p in patches.items():
        print(f"  {sid:16s} {p['display']:>10s}  {p['reference_period']}  (as of {p['asof']})")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
