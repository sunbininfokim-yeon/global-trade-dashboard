#!/usr/bin/env python3
"""Split the assets stack's 국채(SOMA) band into four maturity sub-bands.

The band showed one solid colour over a total that used to come from four
maturity-bucket indicators -- but those were seeded fixtures, no live source
was ever wired. build_soma_maturity.py now pulls the actual NY Fed CUSIP-level
holdings and buckets them by remaining maturity for real.

The bucket *shares* come from that CUSIP data; the bucket *totals* are those
shares applied to the balance sheet's own treasuries figure (FRED TREAST,
already the basis for the assets stack's total). Two reasons: first, CUSIP
parValue sums run a couple percent below TREAST's TIPS-inflation-adjusted
total, and swapping in the raw CUSIP sum would make the assets stack stop
summing to total assets. Second, TREAST is already what the rest of this
stack is built from -- reusing it here means the four new sub-bands add up to
exactly the one band they replace, not a slightly different number nobody
asked for.

Also replaces fed_ust_ops (previously fixture_synth) with the real net change
by bucket over the same window build_soma_maturity.py computed.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
SOMA = ROOT / "soma_maturity_v1.json"

BUCKET_IDS = ["le_1y", "1_5y", "5_10y", "gt_10y"]


def step_fill(dates: list[str], src_dates: list[str], src_vals: list[float]) -> list[float | None]:
    """Value in effect on `date`: the latest src observation on or before it."""
    out: list[float | None] = []
    for d in dates:
        i = bisect_right(src_dates, d) - 1
        out.append(src_vals[i] if i >= 0 else None)
    return out


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    soma = json.loads(SOMA.read_text(encoding="utf-8"))

    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    ind = next(i for i in usa["indicators"] if i["id"] == "fed_total_assets")
    bs = ind["balance_sheet"]
    dates = bs["dates"]

    assets = next(s for s in bs["sides"] if s["id"] == "assets")
    tre_idx = next(k for k, l in enumerate(assets["layers"]) if l["id"] == "treasuries")
    tre_total = assets["layers"][tre_idx]["values"]

    soma_dates = soma["dates"]
    bucket_by_id = {b["id"]: b for b in soma["buckets"]}

    # Step-filled bucket totals on the pack's own date axis, then converted to
    # shares -- the totals themselves are discarded, only the split matters.
    filled = {bid: step_fill(dates, soma_dates, bucket_by_id[bid]["values"]) for bid in BUCKET_IDS}

    sub_layers = []
    for bid in BUCKET_IDS:
        b = bucket_by_id[bid]
        vals: list[float | None] = []
        for i, d in enumerate(dates):
            parts = {k: filled[k][i] for k in BUCKET_IDS}
            denom = sum(v for v in parts.values() if v is not None)
            share = parts[bid] / denom if (denom and parts[bid] is not None) else None
            t = tre_total[i]
            vals.append(round(share * t, 4) if (share is not None and t is not None) else None)
        sub_layers.append({
            "id": f"treasuries_{bid}", "label_ko": f"국채 {b['label_ko']} (SOMA)",
            "color": b["color"], "unit": "tn_usd", "fred_series_id": None,
            "derived": "NY Fed SOMA CUSIP maturity share x FRED TREAST total",
            "note_ko": f"만기 {b['label_ko']} 구간. 비중은 뉴욕 연준 SOMA 실측, 총액은 TREAST 기준.",
            "values": vals,
        })

    assets["layers"] = assets["layers"][:tre_idx] + sub_layers + assets["layers"][tre_idx + 1:]
    bs["soma_maturity_note_ko"] = (
        "국채 만기 구간 비중은 뉴욕 연준 SOMA 개별 보유 데이터(실측)에서, "
        "구간별 금액은 그 비중을 대차대조표 국채 총액에 적용해 계산합니다."
    )

    # fed_ust_ops: swap the fixture for the real net-change-by-bucket.
    ops = next((i for i in usa["indicators"] if i["id"] == "fed_ust_ops"), None)
    nc = soma["net_change"]
    if ops is not None:
        label_ko = {"le_1y": "≤1년", "1_5y": "1–5년", "5_10y": "5–10년", "gt_10y": ">10년"}
        ops["components"] = [
            {"id": bid, "label_ko": label_ko[bid], "value": nc["by_bucket"][bid],
             "display": f"{nc['by_bucket'][bid]:+.1f}B"}
            for bid in BUCKET_IDS
        ]
        ops["value"] = nc["total_bn"]
        ops["display"] = f"{nc['total_bn']:+.1f}B"
        ops["display_chip"] = ops["display"]
        ops["asof"] = soma["asof"]
        ops["observed_at"] = soma["asof"]
        ops["reference_period"] = nc["period"]
        ops["source"] = soma["source"]
        ops["quality"] = "live"
        ops["data_status"] = "live"
        ops["note_ko"] = nc["period_note_ko"] + " " + nc["finding_ko"]

        for chips in (usa.get("categories") or {}).values():
            for ch in chips:
                if ch.get("id") == "fed_ust_ops":
                    for k in ("value", "display", "asof", "observed_at", "source", "data_status", "note_ko"):
                        ch[k] = ops.get(k)

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    latest = dates[-1]
    print(f"wired SOMA maturity split onto assets stack (asof {latest})")
    for l in sub_layers:
        print(f"  {l['label_ko']:<28} {l['values'][-1]}")
    check = sum(l['values'][-1] for l in sub_layers if l['values'][-1] is not None)
    print(f"  sum {check:.4f} vs original treasuries {tre_total[-1]}")
    if ops is not None:
        print(f"  fed_ust_ops -> {ops['display']} ({nc['period']}) -- {nc['finding_ko']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
