#!/usr/bin/env python3
"""Attach the liability stack to the USA fed_total_assets indicator.

The card keeps its headline (total assets) and its history line; this adds the
composition behind it as a second panel, so the drawer can answer "made of
what" without a second chip competing for the same number.

The stack is downsampled to roughly one point per fortnight before it goes into
the pack. At weekly resolution ten years is 550 points per layer across five
layers, which is 2.7k numbers embedded in a document the map already pays to
download -- and the bands are 760px wide, so the extra points land inside the
same pixel column. The ratio series is downsampled on the same indices, so the
two panels stay on one shared date axis.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
BS = ROOT / "fed_balance_sheet_v1.json"

STEP = 2  # weeks per retained point


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    bs = json.loads(BS.read_text(encoding="utf-8"))

    dates = bs["dates"]
    keep = list(range(0, len(dates), STEP))
    # The most recent week is the one the headline quotes; dropping it to the
    # sampling grid would leave the panel ending before the number above it.
    if keep and keep[-1] != len(dates) - 1:
        keep.append(len(dates) - 1)

    pick = lambda arr: [arr[i] for i in keep]

    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    ind = next((i for i in usa["indicators"] if i["id"] == "fed_total_assets"), None)
    if ind is None:
        print("fed_total_assets not found in USA indicators -- nothing wired")
        return 1

    ind["balance_sheet"] = {
        "asof": bs["asof"],
        "source": bs["source"],
        "data_status": bs["data_status"],
        "frequency": bs["frequency"],
        "unit": bs["unit"],
        "sampling_note_ko": f"표시는 {STEP}주 간격으로 솎아낸 시계열입니다(원자료는 주간).",
        "stack_note_ko": bs["stack_note_ko"],
        "dates": pick(dates),
        "layers": [{
            "id": l["id"], "label_ko": l["label_ko"], "color": l["color"],
            "note_ko": l.get("note_ko"), "fred_series_id": l.get("fred_series_id"),
            "values": pick(l["values"]),
        } for l in bs["layers"]],
        "ratio": {**{k: v for k, v in bs["ratio"].items() if k != "values"},
                  "values": pick(bs["ratio"]["values"])},
        "limitations": bs["limitations"],
    }

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    r = ind["balance_sheet"]["ratio"]["values"][-1]
    th = ind["balance_sheet"]["ratio"]["threshold_pct"]
    print(f"wired balance_sheet onto fed_total_assets ({len(keep)} points, asof {bs['asof']})")
    for l in ind["balance_sheet"]["layers"]:
        print(f"    {l['label_ko']:<18} {l['values'][-1]}")
    print(f"  지급준비금/GDP {r}% ({'아래' if r < th else '위'} {th}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
