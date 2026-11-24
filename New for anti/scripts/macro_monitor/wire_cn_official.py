"""China cards from China's own agencies (keyless): real GDP growth by quarter from the NBS, and
month-end official reserve assets from SAFE.

    python3 wire_cn_official.py

The World Bank annual series stays as the GDP fallback in refresh_peer_gdp_in_pack.py, which leaves a
card alone once it is 'live'. The reserves card is first written from the IMF by
wire_world_public_series.py; this runs after it and lays SAFE's months over that history. A read that
fails leaves the previous card and exits 1 (the other card is still written).
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
    touched: set[str] = set()
    failed = 0

    try:
        points, url = cn.fetch_gdp(cn.http_get)
        patch = cn.build_gdp_patch(points, url, retrieved_at=retrieved)
        changed = ups.apply_patch(by_id["gdp_yoy"], patch) if "gdp_yoy" in by_id else False
        if changed:
            by_id["gdp_yoy"].pop("analog_ko", None)
            touched.add("gdp_yoy")
        print(f"CHN gdp_yoy {patch['display']} {patch['reference_period']} ({len(points)} quarters, {url}) "
              f"{'changed' if changed else 'unchanged'}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED gdp_yoy: {exc}", file=sys.stderr)
        failed += 1

    try:
        safe, urls = cn.fetch_reserves(cn.http_get, cn.http_get_bytes)
        card = by_id.get("fx_reserves")
        if card is None:
            raise ValueError("no fx_reserves card on CHN")
        points = cn.merge_history(card, safe)
        patch = cn.build_reserves_patch(points, urls, retrieved_at=retrieved)
        changed = ups.apply_patch(card, patch)
        if changed:
            touched.add("fx_reserves")
        print(f"CHN fx_reserves {patch['display']} {patch['reference_period']} (SAFE {safe[0][0][:7]}..{safe[-1][0][:7]}) "
              f"{'changed' if changed else 'unchanged'}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED fx_reserves: {exc}", file=sys.stderr)
        failed += 1

    if touched:
        ups.sync_chips(chn, by_id, touched)
        ups.refresh_status_summary(chn)
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
