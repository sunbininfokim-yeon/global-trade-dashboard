"""OpenDART XBRL facts → accounting_pack.

Fetches consolidated P&L, cash flow, balance sheet from OpenDART.

Ownership: UI/engine boundary is drawn in the repo's OWNERS doc, not in this
file. This module is a live-data *source adapter* (parallel to sec_facts.py
for US filings) -- whoever owns the KFA calculation engine can pick it up
without needing to know anything Claude-specific: it has no UI coupling, no
hardcoded secrets, and its only external contract is the function signature
`__init__.py` already imports (`fetch_accounting_pack_kr`).
"""

from __future__ import annotations

import os
from typing import Any

import requests

from .accounting_pack import empty_accounting_pack


OPENDART_BASE = "https://opendart.fss.or.kr/api"
# Never hardcode this: __init__.py already documents the contract as "uses
# DART_API_KEY at runtime only". Missing key must degrade to empty facts, not
# raise -- a UI snapshot without a live key still has to render.
OPENDART_API_KEY = os.environ.get("DART_API_KEY", "")

# XBRL 태그 매핑: corp_code → P&L/CF/Balance sheet facts
XBRL_TAGS = {
    # P&L
    "revenue": ["ifrs_Revenue", "dart_Revenue"],
    "gross_profit": ["ifrs_GrossProfitLoss"],
    "operating_income": ["ifrs_OperatingProfitLoss"],
    "ebitda": ["dart_EBITDA"],  # if available, else derive
    "net_income": ["ifrs_ProfitLoss"],
    "profit_before_tax": ["ifrs_ProfitLossBeforeTax"],
    "income_tax_expense": ["ifrs_IncomeTaxExpense"],
    "interest_expense": ["ifrs_FinanceCostsExclusive"],
    "eps": ["ifrs_BasicEarningsPerShare"],

    # CF
    "cfo": ["ifrs_CashFlowsFromOperatingActivities"],
    "capex": ["ifrs_PurchasesOfPropertyPlantAndEquipment"],
    "depreciation_and_amortization": ["ifrs_DepreciationAndAmortisationExpense"],

    # Balance Sheet
    "cash": ["ifrs_CashAndCashEquivalents"],
    "current_assets": ["ifrs_CurrentAssets"],
    "current_liabilities": ["ifrs_CurrentLiabilities"],
    "short_term_debt": ["ifrs_ShortTermBorrowings"],
    "long_term_debt": ["ifrs_LongTermBorrowings"],
    "nwc": ["dart_NetWorkingCapital"],
}


def fetch_xbrl_facts(corp_code: str, year: int) -> dict[str, Any]:
    """Fetch XBRL facts for a given corp_code and fiscal year.

    Returns dict of {tag: value} for the fiscal year end (일반기업).
    Returns {} without a network call if DART_API_KEY is not set.
    """
    if not OPENDART_API_KEY:
        return {}
    url = f"{OPENDART_BASE}/xbrlTaxonomy"
    params = {
        "crtfc_key": OPENDART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011",  # 일반기업 정기보고
        "lang": "ko",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "000":
            return {}
        # API returns list of facts; flatten to {tag: {value, unit}}
        facts = {}
        for item in data.get("list", []):
            facts[item.get("account_nm", "")] = item.get("thstrm_amount")  # 당기 금액
        return facts
    except Exception as e:
        print(f"DART XBRL fetch failed: {e}")
        return {}


def map_facts_to_pack(facts: dict[str, Any], currency: str = "KRW") -> dict[str, Any]:
    """Map XBRL facts → accounting_pack structure.

    Missing facts remain null with reason="missing:not_in_opendart".
    """
    pack = empty_accounting_pack(currency)

    # P&L
    pack["pnl"]["revenue"]["value"] = facts.get("revenue")
    pack["pnl"]["operating_income"]["value"] = facts.get("operating_income")
    pack["pnl"]["net_income"]["value"] = facts.get("net_income")
    pack["pnl"]["profit_before_tax"]["value"] = facts.get("profit_before_tax")
    pack["pnl"]["income_tax_expense"]["value"] = facts.get("income_tax_expense")
    pack["pnl"]["interest_expense"]["value"] = facts.get("interest_expense")
    pack["pnl"]["interest_expense"]["reason"] = (
        None if facts.get("interest_expense") else "missing:not_in_opendart"
    )

    # CF
    pack["cash_flow"]["cfo"]["value"] = facts.get("cfo")
    pack["cash_flow"]["capex"]["value"] = facts.get("capex")
    pack["cash_flow"]["depreciation_and_amortization"]["value"] = facts.get(
        "depreciation_and_amortization"
    )
    pack["cash_flow"]["depreciation_and_amortization"]["reason"] = (
        None if facts.get("depreciation_and_amortization") else "missing:not_in_opendart"
    )

    # Liquidity
    pack["liquidity"]["cash_and_equivalents"]["value"] = facts.get("cash")

    # Debt
    pack["debt_structure"]["short_term_borrowings"] = facts.get("short_term_debt")
    pack["debt_structure"]["long_term_debt"] = facts.get("long_term_debt")

    return pack


def fetch_accounting_pack_kr(corp_code: str, year: int = 2025) -> dict[str, Any]:
    """One-shot: corp_code → full accounting_pack from OpenDART.

    This is the symbol `dart_kfa/__init__.py` imports as an optional source
    adapter. Renaming it breaks that import silently (caught by ImportError,
    degrades to None) -- keep the name in sync with __init__.py if it moves.

    Returns dict with:
    - accounting_pack: normalised P&L/CF/Balance
    - as_of: fiscal year end (e.g. 2025-12-31)
    - meta: source info, including whether a live key was present
    """
    facts = fetch_xbrl_facts(corp_code, year)
    pack = map_facts_to_pack(facts)

    # Default FYE to Dec 31 (한국 일반기업 표준)
    pack["as_of"] = f"{year}-12-31"

    return {
        "accounting_pack": pack,
        "as_of": f"{year}-12-31",
        "meta": {
            "source": "opendart",
            "corp_code": corp_code,
            "year": year,
            "live_key_present": bool(OPENDART_API_KEY),
        },
    }
