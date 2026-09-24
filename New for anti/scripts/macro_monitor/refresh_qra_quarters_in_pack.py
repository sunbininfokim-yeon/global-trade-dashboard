#!/usr/bin/env python3
"""Graft the latest QRA announcement onto the deployed macro pack.

Reads the engine file build_qra_engine.py writes and applies it to the USA
``qra_issuance`` indicator with the same function the full pack build uses
(engine._apply_qra_engine_file): compare bars (this quarter + next-quarter
estimate), issuance components, sources & uses, history, stances, and the TGA
maturity mirror. Does not rebuild the pack.

The note text comes from the engine (qra.compare.split_summary_ko) -- it used
to be hardcoded here with the August 2026 stances, which a scheduled run would
have stamped onto every later announcement.

    python3 build_qra_engine.py --download
    python3 refresh_qra_quarters_in_pack.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import _apply_qra_engine_file  # noqa: E402

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
    if not (engine.get("latest") or {}).get("compare"):
        print("engine file has no latest compare block", file=sys.stderr)
        return 1

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c.get("iso3") == "USA")
    by_id = {i["id"]: i for i in usa["indicators"]}
    if "qra_issuance" not in by_id:
        print("no qra_issuance indicator in the pack", file=sys.stderr)
        return 1

    _apply_qra_engine_file(by_id)
    ind = by_id["qra_issuance"]
    series = {s["id"]: s for s in (ind.get("compare") or {}).get("series") or []}
    current, nxt = series.get("current"), series.get("next_estimate")
    if not current:
        print("compare block has no current-quarter series", file=sys.stderr)
        return 1

    announced = current.get("announcement_date")
    # The maturity tab only carries real numbers when the Treasury's TBAC
    # recommended-financing table was parsed for this quarter; say which
    # quarter and that these are gross coupon auction sizes, not the net
    # borrowing the compare bars show (Guidebook rule: net != gross).
    latest_event = next((e for e in engine.get("events") or [] if e.get("id") == engine["latest"].get("id")), {})
    tbac = latest_event.get("tbac_financing") or {}
    if tbac.get("parse_ok") and tbac.get("qra_issuance_components"):
        ind["components_note_ko"] = (
            f"TBAC 권고 쿠폰 경매 규모의 분기 합계입니다 ({tbac.get('quarter_label')}, $B). "
            "순발행이 아니라 총 경매 규모이며 T-bill은 포함하지 않습니다."
        )
    else:
        ind.pop("components_note_ko", None)
    ind["data_status"] = "live"
    ind["asof"] = _iso_date(announced) or ind.get("asof")
    ind["qra_quarters"] = {
        "announcement_date": announced,
        "current": {
            "period": current.get("period"),
            "net_borrowing_bn": current["value"],
            "end_cash_bn": current.get("end_cash_bn"),
        },
        "next": (
            {
                "period": nxt.get("period"),
                "net_borrowing_bn": nxt["value"],
                "end_cash_bn": nxt.get("end_cash_bn"),
            }
            if nxt
            else None
        ),
    }
    for chips in (usa.get("categories") or {}).values():
        for chip in chips:
            if chip.get("id") == "qra_issuance":
                chip["value"] = ind["value"]
                chip["display"] = ind.get("display_chip") or ind["display"]
                chip["asof"] = ind["asof"]
                chip["compare"] = ind["compare"]
                chip["note_ko"] = ind.get("note_ko")

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(ind.get("note_ko"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
