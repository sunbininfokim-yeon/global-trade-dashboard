#!/usr/bin/env python3
"""Replace every non-USA country's headline strip with a fixed 6-field structure.

headlines used to be a per-country curated list -- Korea led with semiconductor
exports, China with credit impulse -- which is genuinely more informative per
country but meant no two countries could be compared at a glance, and made
"which 5/6 fields are these" impossible to answer without opening each one.
The user asked for one shape across every country except the US (which keeps
its benchmark-specific set): GDP YoY, inflation, policy rate, USD cross, the
main equity index, sovereign rating.

Not every country's policy rate lives under an id the others share -- BOJ's is
call_rate, ECB's is deposit_facility, RBI's is rbi_repo -- so this maps each
field per country rather than assuming one id works everywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "macro_monitor_v1.json"

# iso3 -> (gdp_id, inflation_id, policy_rate_id, fx_id, equity_id)
# sovereign_ratings id is the same everywhere and appended separately.
FIELD_MAP: dict[str, tuple[str, str, str, str, str]] = {
    "KOR": ("gdp_yoy", "cpi_yoy", "bok_base_rate", "usdkrw", "kospi"),
    "JPN": ("gdp_yoy", "core_cpi_jp", "call_rate", "usdjpy", "nikkei"),
    "CHN": ("gdp_yoy", "cpi_yoy", "lpr_1y", "usdcnh", "sse_composite"),
    "EMU": ("gdp_yoy", "hicp_yoy", "deposit_facility", "eurusd", "dax40"),
    "ZAF": ("gdp_yoy", "cpi_yoy", "sarb_repo", "usdzar", "jse_top40"),
    "SGP": ("gdp_yoy", "cpi_yoy", "sora", "usdsgd", "sti"),
    "HKG": ("gdp_yoy", "composite_cpi", "hk_base_rate", "usdhkd", "hsi"),
    "RUS": ("gdp_yoy", "cpi_yoy", "cbr_key_rate", "usdrub", "moex_index"),
    "GBR": ("gdp_yoy", "cpi_yoy", "bank_rate", "gbpusd", "ftse100"),
    "CAN": ("gdp_yoy", "cpi_yoy", "boc_overnight", "usdcad", "tsx"),
    "AUS": ("gdp_yoy", "cpi_yoy", "rba_cash_rate", "audusd", "asx200"),
    "CHE": ("gdp_yoy", "cpi_yoy", "snb_policy_rate", "usdchf", "smi"),
    "BRA": ("gdp_yoy", "ipca", "selic_rate", "usdbrl", "ibovespa"),
    "VNM": ("gdp_yoy", "cpi_yoy", "sbv_refinancing", "usdvnd", "vnindex"),
    "KAZ": ("gdp_yoy", "cpi_yoy", "nbk_base_rate", "usdkzt", "kase_index"),
    "TWN": ("gdp_yoy", "cpi_yoy", "cbc_discount", "usdtwd", "taiex"),
    "IND": ("gdp_yoy", "cpi_yoy", "rbi_repo", "usdinr", "sensex"),
    "ISR": ("gdp_yoy", "cpi_yoy", "boi_rate", "usdils", "ta125"),
}


def headline_from(by_id: dict[str, dict], ind_id: str) -> dict | None:
    ind = by_id.get(ind_id)
    if not ind:
        return None
    return {
        "id": ind["id"],
        "category": ind["category"],
        "label_ko": ind["label_ko"],
        "display": ind.get("display_chip") or ind.get("display"),
        "data_status": ind.get("data_status"),
    }


def main() -> int:
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    changed = []
    for c in doc.get("countries") or []:
        iso3 = c["iso3"]
        if iso3 == "USA" or iso3 not in FIELD_MAP:
            continue
        by_id = {i["id"]: i for i in c.get("indicators") or []}
        ids = [*FIELD_MAP[iso3], "sovereign_ratings"]
        rows = [h for h in (headline_from(by_id, i) for i in ids) if h]
        missing = [i for i in ids if i not in by_id]
        if missing:
            print(f"  {iso3}: missing {missing} -- kept those slots out rather than guess")
        c["headlines"] = rows
        changed.append(iso3)

    for idx in doc.get("countries_index") or []:
        hit = next((c for c in doc["countries"] if c["iso3"] == idx.get("iso3")), None)
        if hit:
            idx["headlines"] = hit.get("headlines") or []

    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"rebuilt headlines for {len(changed)} countries (USA untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
