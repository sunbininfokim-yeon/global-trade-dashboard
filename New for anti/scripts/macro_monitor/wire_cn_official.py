"""China cards from China's own statistics office (keyless): real GDP growth by quarter from the NBS.

    python3 wire_cn_official.py

The World Bank annual series stays as the fallback in refresh_peer_gdp_in_pack.py, which leaves a
card alone once it is 'live'. A read that fails leaves the previous card and exits 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import cn_official as cn  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    chn = next(c for c in pack["countries"] if c["iso3"] == "CHN")
    by_id = {i["id"]: i for i in chn["indicators"]}
    retrieved = ups.now_iso()
    try:
        points, url = cn.fetch_gdp(cn.http_get)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED gdp_yoy: {exc}", file=sys.stderr)
        return 1
    patch = cn.build_gdp_patch(points, url, retrieved_at=retrieved)
    changed = ups.apply_patch(by_id["gdp_yoy"], patch) if "gdp_yoy" in by_id else False
    if changed:
        by_id["gdp_yoy"].pop("analog_ko", None)
        ups.sync_chips(chn, by_id, {"gdp_yoy"})
        ups.refresh_status_summary(chn)
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"CHN gdp_yoy {patch['display']} {patch['reference_period']} ({len(points)} quarters, {url}) "
          f"{'changed' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
