#!/usr/bin/env python3
"""Fold the balance sheet composition into fed_total_assets and tidy the chips.

Both sides of the sheet now live behind the 연준 총자산 card, so the liquidity
row no longer needs a chip per component: SOMA Treasuries and MBS were their
own chips showing a slice of a total that sits two chips away, and the drawer
shows the same numbers in the context that makes them mean something.

What stays a chip is what the stack cannot show: TGA, ON RRP and FIMA are
watched as their own levels rather than as bands, and net liquidity, QRA
issuance and the M2 pair are not balance sheet lines at all. Flows stay too --
fed_ust_ops is what the Fed did in a period, not what it holds.

Removed chips keep their indicator entries. The drawer reads the maturity
buckets off fed_ust_holdings, and dropping the indicator to hide the chip
would take that panel with it.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
BS = ROOT / "fed_balance_sheet_v1.json"
HF = ROOT / "hedge_fund_ust_v1.json"

STEP = 2  # weeks per retained point

# Components that the stack now shows in context. The indicators survive; only
# their chips go.
FOLDED_CHIPS = {"fed_ust_holdings", "fed_mbs", "discount_window"}


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    bs = json.loads(BS.read_text(encoding="utf-8"))
    hf = json.loads(HF.read_text(encoding="utf-8")) if HF.exists() else None

    dates = bs["dates"]
    keep = list(range(0, len(dates), STEP))
    # The last week is the one the headline quotes; dropping it to the sampling
    # grid would leave the panel ending before the number above it.
    if keep and keep[-1] != len(dates) - 1:
        keep.append(len(dates) - 1)
    pick = lambda arr: [arr[i] for i in keep]

    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    by_id = {i["id"]: i for i in usa["indicators"]}
    ind = by_id.get("fed_total_assets")
    if ind is None:
        print("fed_total_assets not found -- nothing wired")
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
        "total": {**bs["total"], "values": pick(bs["total"]["values"])},
        "sides": [{
            "id": s["id"], "label_ko": s["label_ko"], "note_ko": s.get("note_ko"),
            "layers": [{
                "id": l["id"], "label_ko": l["label_ko"], "color": l["color"],
                "note_ko": l.get("note_ko"), "fred_series_id": l.get("fred_series_id"),
                "values": pick(l["values"]),
            } for l in s["layers"]],
        } for s in bs["sides"]],
        "ratio": {**{k: v for k, v in bs["ratio"].items() if k != "values"},
                  "values": pick(bs["ratio"]["values"])},
        "limitations": bs["limitations"],
    }

    # The SOMA maturity split was reachable only from the fed_ust_holdings chip.
    # With that chip folded in, carry the buckets over so the panel survives.
    soma = by_id.get("fed_ust_holdings")
    if soma and soma.get("components"):
        ind["components"] = soma["components"]
        ind["ui"] = {**(ind.get("ui") or {}), "secondary_view": "maturity_components"}

    liq = usa.setdefault("categories", {}).setdefault("liquidity", [])
    before = len(liq)
    liq[:] = [c for c in liq if c.get("id") not in FOLDED_CHIPS]
    dropped = before - len(liq)

    # Hedge fund Treasuries go beside ON RRP: same trade, opposite end.
    added = None
    if hf:
        hid = "hedge_fund_ust"
        usa["indicators"] = [i for i in usa["indicators"] if i["id"] != hid]
        liq[:] = [c for c in liq if c.get("id") != hid]

        hf_ind = {
            "id": hid, "category": "liquidity", "label_ko": hf["label_ko"],
            "unit": "bn_usd", "format": "bn1", "refresh_tier": "quarterly",
            "value": hf["value_bn"], "display": f"${hf['value_bn']:,.1f}B",
            "display_chip": f"${hf['value_bn']:,.1f}B",
            "asof": hf["asof"], "observed_at": hf["asof"],
            "reference_period": hf["asof"],
            "source": hf["source"], "quality": "live", "data_status": "live",
            "chart_type": "line",
            "note_ko": hf["rrp_link_note_ko"],
            "history": {"5y": {"dates": hf["series"]["dates"][-20:],
                               "values": hf["series"]["values"][-20:]},
                        "10y": {"dates": hf["series"]["dates"][-40:],
                                "values": hf["series"]["values"][-40:]}},
            "hedge_fund_ust": {
                "share_of_assets": hf["share_of_assets"],
                "limitations": hf["limitations"],
                "frequency_note_ko": ("Z.1 분기 자료로, 옆의 주간 대차대조표보다 "
                                      "항상 한 분기 정도 뒤처집니다."),
            },
        }
        anchor = next((k for k, i in enumerate(usa["indicators"])
                       if i["id"] == "on_rrp"), len(usa["indicators"]) - 1)
        usa["indicators"].insert(anchor + 1, hf_ind)

        pos = next((k for k, c in enumerate(liq) if c.get("id") == "on_rrp"), len(liq) - 1)
        liq.insert(pos + 1, {
            "id": hid, "label_ko": hf_ind["label_ko"], "unit": hf_ind["unit"],
            "value": hf_ind["value"], "display": hf_ind["display"],
            "change_1m_pct": None, "change_1y_pct": None,
            "asof": hf_ind["asof"], "note_ko": hf_ind["note_ko"],
            "data_status": "live", "source": hf_ind["source"],
        })
        added = hf_ind["display"]

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    print(f"balance_sheet -> fed_total_assets ({len(keep)} points, asof {bs['asof']})")
    for s in ind["balance_sheet"]["sides"]:
        print(f"  [{s['label_ko']}] " + ", ".join(
            f"{l['label_ko']} {l['values'][-1]}" for l in s["layers"]))
    r = ind["balance_sheet"]["ratio"]
    print(f"  reserves/GDP {r['values'][-1]}% vs {r['threshold_pct']}%")
    print(f"  folded {dropped} chips: {', '.join(sorted(FOLDED_CHIPS))}")
    print(f"  SOMA buckets carried: {len(ind.get('components') or [])}")
    if added:
        print(f"  hedge_fund_ust chip after on_rrp: {added} ({hf['asof']})")
    print(f"  liquidity chips now: {[c['id'] for c in liq]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
