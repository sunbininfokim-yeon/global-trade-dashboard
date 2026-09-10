#!/usr/bin/env python3
"""Attach the real QE/QT monthly history to fed_ust_ops, and retire the stale bits.

fed_ust_ops' headline switched to real data earlier, but its 추이 tab kept
drawing a fixture `history` array frozen around -29B, and its 1M/1Y delta
badges (change_1m_pct/change_1y_pct) were fixture too. This wires the real
monthly series in as qe_qt_history (which macro.js now renders as its own
'매입 추이' tab instead of the generic history line), and drops the two now-
provably-wrong fields rather than leave a fixed number of zero informational
value sitting next to a real one.

The 1M/1Y percent deltas are dropped outright, not recomputed: a signed net
flow crosses zero every few months by construction, and "percent change" of a
number whose sign flips is not a meaningful figure -- there is no honest
substitute value to put there, only an absent one.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
QEQT = ROOT / "fed_qe_qt_history_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    qq = json.loads(QEQT.read_text(encoding="utf-8"))

    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    ops = next(i for i in usa["indicators"] if i["id"] == "fed_ust_ops")

    # refresh_tier says monthly and this view's own chart is one bar per
    # month, so the headline is the latest calendar month's total -- a reader
    # comparing the chip to the chart under it should find the chip matching
    # exactly one bar, not a multi-month window the chart doesn't draw.
    #
    # note_ko is written fresh from qq every run rather than read off the
    # existing ops and appended to: this script is meant to be re-run as new
    # months arrive (that's the point of keeping it instead of a one-off
    # patch), and appending to whatever note happened to already be sitting
    # there duplicated it on every re-run -- three copies of the same
    # sentence, worse each time this ran again.
    last = qq["rows"][-1]
    month_total = round(last["treasuries_bn"] + last["mbs_bn"], 1)
    ops["value"] = month_total
    ops["display"] = f"{month_total:+.1f}B"
    ops["display_chip"] = ops["display"]
    ops["asof"] = f"{last['month']}-28"
    ops["observed_at"] = ops["asof"]
    ops["reference_period"] = last["month"]
    ops["note_ko"] = (f"{last['month']} 한 달 순증감. 국채 {last['treasuries_bn']:+.1f}B, "
                      f"MBS {last['mbs_bn']:+.1f}B.")

    ops["qe_qt_history"] = {
        "source": qq["source"],
        "data_status": qq["data_status"],
        "frequency": qq["frequency"],
        "asof": qq["rows"][-1]["month"],
        "sign_convention_ko": qq["sign_convention_ko"],
        "rows": qq["rows"],
        "limitations": qq["limitations"],
    }
    # Per-row `buckets` (merge_qeqt_buckets.py) only covers the recent window
    # this repo has pulled CUSIP-level SOMA holdings for; bucket_detail
    # documents that coverage and the label/limitation text the rail's pie
    # chart cites, when present.
    if qq.get("bucket_detail"):
        ops["qe_qt_history"]["bucket_detail"] = qq["bucket_detail"]

    # Stale fixture fields this view replaces -- see module docstring for why
    # the deltas are dropped rather than recomputed.
    ops.pop("history", None)
    ops["change_1m_pct"] = None
    ops["change_1y_pct"] = None

    for chips in (usa.get("categories") or {}).values():
        for ch in chips:
            if ch.get("id") == "fed_ust_ops":
                for k in ("value", "display", "asof", "observed_at"):
                    ch[k] = ops.get(k)
                ch["change_1m_pct"] = None
                ch["change_1y_pct"] = None

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    last = qq["rows"][-1]
    print(f"wired qe_qt_history onto fed_ust_ops ({len(qq['rows'])} months, asof {last['month']})")
    print(f"  latest: treasuries {last['treasuries_bn']:+.1f}B, mbs {last['mbs_bn']:+.1f}B")
    print("  dropped fixture 'history' array and change_1m_pct/change_1y_pct (see docstring)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
