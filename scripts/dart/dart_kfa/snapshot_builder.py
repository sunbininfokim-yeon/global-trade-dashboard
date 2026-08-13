"""Assemble a full kfa_<code>_v1.json snapshot from a live OpenDART fetch.

Wires dart_facts (source adapter) into derived_cards (pure calculation) to
produce the same schema enrich_snapshot outputs from a legacy sample -- but
starting from a fresh single-fiscal-year OpenDART fetch instead of an existing
UI snapshot. A single-year fetch means every basic_cards series is one point
and every history-dependent expert card (CAGR, quality trend, aligned ratios)
resolves to null + reason downstream -- that degrades correctly per the
"null + reason, never estimate" rule, it is not a bug. Multi-year history
(looping fetch_xbrl_facts over prior years) is future work, not attempted here.
"""

from __future__ import annotations

from typing import Any

from .dart_facts import fetch_accounting_pack_kr
from .derived_cards import basic_cards_from_pack, run_kfa_analysis
from .view_presets import get_view_presets


def build_kfa_snapshot(
    corp_code: str,
    stock_code: str,
    name_ko: str,
    name_eng: str,
    year: int,
    fs_div: str = "CFS",
) -> dict[str, Any]:
    """corp_code (OpenDART's 8-digit id, not the 6-digit KRX ticker) -> full snapshot."""
    fetched = fetch_accounting_pack_kr(corp_code, year, fs_div)
    pack = fetched["accounting_pack"]

    basic_cards = basic_cards_from_pack(pack)
    analysis = run_kfa_analysis(pack)
    basic_cards.update(analysis["cards"])
    basic_cards["interest_coverage"] = analysis["basic_updates"]["interest_coverage"]

    return {
        "schema": "kfa_engine_v1",
        "label": stock_code,
        "view_presets": get_view_presets(),
        "as_of": fetched["as_of"],
        "currency": "KRW",
        "meta": {
            "ticker": stock_code,
            "corp_code": corp_code,
            "entity": name_ko,
            "entity_eng": name_eng,
            "stock_code": stock_code,
            "source": "opendart",
            "fs_div": fs_div,
            "acc_mt": "12",
            "shares_outstanding": None,
        },
        "basic_cards": basic_cards,
        "accounting_pack": pack,
        "investor": {"models": analysis["models"]["investor"]},
        "pe": {"models": analysis["models"]["pe"]},
        "deal": {"models": analysis["models"]["deal"]},
        "data_quality": {
            "input_kind": "live_fetch_single_fiscal_year",
            "source_claim": "opendart",
            "raw_filing_facts_embedded": True,
            "period_alignment": "single_fiscal_year_no_history",
            "facts_fetched": fetched["meta"]["facts_fetched"],
            "live_key_present": fetched["meta"]["live_key_present"],
        },
    }
