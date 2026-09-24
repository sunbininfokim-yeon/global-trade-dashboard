#!/usr/bin/env python3
"""Split one QRA announcement into the current quarter and the next-quarter estimate.

Reads the already parsed engine file (Treasury financing estimates + Sources & Uses).
Does not rebuild the pack. Writes the same compare block the drawer already lists.

    python3 refresh_qra_quarters_in_pack.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.qra.compare import build_net_borrowing_compare  # noqa: E402

ENGINE = ROOT.parent.parent / "public" / "data" / "qra_engine_v1.json"
PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def _iso_date(text):
    if not text:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def main() -> int:
    engine = json.loads(ENGINE.read_text(encoding="utf-8"))
    latest_id = (engine.get("latest") or {}).get("id")
    event = next((e for e in engine.get("events") or [] if e.get("id") == latest_id), None)
    if event is None:
        print(f"no event {latest_id}", file=sys.stderr)
        return 1
    compare = build_net_borrowing_compare(event)
    by = {s["id"]: s for s in compare.get("series") or []}
    current = by.get("current")
    nxt = by.get("next_estimate")
    if not current or not nxt:
        print("announcement did not split into current and next quarter", file=sys.stderr)
        return 1

    announced = current.get("announcement_date")
    note = (
        f"{announced} 발표. 당기 {current.get('period')} 순발행 {current['value']:.0f}B, "
        f"기말현금 {float(current.get('end_cash_bn')):.0f}B. "
        f"다음 분기 {nxt.get('period')} 예상 순발행 {nxt['value']:.0f}B, "
        f"기말현금 {float(nxt.get('end_cash_bn')):.0f}B. "
        "T-bill 스탠스=maintain · 쿠폰 스탠스=change_bias"
    )
    engine["latest"]["compare"] = compare
    engine["latest"]["summary_ko"] = note
    ENGINE.write_text(json.dumps(engine, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c.get("iso3") == "USA")
    ind = next(i for i in usa["indicators"] if i.get("id") == "qra_issuance")
    ind["compare"] = compare
    ind["value"] = current["value"]
    ind["display"] = f"{current['value']:.1f}"
    ind["source"] = "qra_engine_v1"
    ind["quality"] = "engine"
    ind["data_status"] = "live"
    ind["asof"] = _iso_date(announced) or ind.get("asof")
    ind["qra_quarters"] = {
        "announcement_date": announced,
        "current": {
            "period": current.get("period"),
            "net_borrowing_bn": current["value"],
            "end_cash_bn": current.get("end_cash_bn"),
        },
        "next": {
            "period": nxt.get("period"),
            "net_borrowing_bn": nxt["value"],
            "end_cash_bn": nxt.get("end_cash_bn"),
        },
    }
    ind["note_ko"] = note
    for chips in (usa.get("categories") or {}).values():
        for ch in chips:
            if ch.get("id") == "qra_issuance":
                ch["value"] = ind["value"]
                ch["display"] = ind["display"]
                ch["asof"] = ind["asof"]
                ch["compare"] = compare
                ch["note_ko"] = note
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
