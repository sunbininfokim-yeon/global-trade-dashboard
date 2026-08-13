"""OpenDART XBRL facts → accounting_pack.

Fetches consolidated P&L, cash flow, balance sheet from OpenDART.

Ownership: UI/engine boundary is drawn in the repo's OWNERS doc, not in this
file. This module is a live-data *source adapter* (parallel to sec_facts.py
for US filings) -- whoever owns the KFA calculation engine can pick it up
without needing to know anything Claude-specific: it has no UI coupling, no
hardcoded secrets, and its only external contract is the function signature
`__init__.py` already imports (`fetch_accounting_pack_kr`).

Tag mapping verified 2026-08-13 against live OpenDART responses for two
companies (Samsung Electronics 00126380, SK Hynix 00164779, FY2024 CFS).
The endpoint below (fnlttSinglAcntAll.json) is the real one -- an earlier
draft of this file called a non-existent `/api/xbrlTaxonomy` path that
returns HTTP-level "invalid URL", and separately built its lookup dict keyed
by the Korean `account_nm` while querying it with English field names, so it
could never have returned a value even with a working endpoint and a valid
key. Both bugs are fixed here.
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

# account_id (XBRL taxonomy element) candidates per field, in priority order.
# Verified against real filings, not guessed: Samsung and SK Hynix agree on
# every id below except where noted. A field with an empty candidate list is
# a documented gap, not an oversight -- see the notes after the table.
XBRL_TAGS: dict[str, list[str]] = {
    # P&L
    "revenue": ["ifrs-full_Revenue"],
    "gross_profit": ["ifrs-full_GrossProfit"],
    # dart_OperatingIncomeLoss is DART's own (non-IFRS-standard) tag; both
    # verified companies file operating income under it, not the IFRS one.
    # ifrs-full_OperatingIncomeLoss is kept as a fallback for filers that do
    # use the standard tag.
    "operating_income": ["dart_OperatingIncomeLoss", "ifrs-full_OperatingIncomeLoss"],
    "net_income": ["ifrs-full_ProfitLoss"],
    "profit_before_tax": ["ifrs-full_ProfitLossBeforeTax"],
    "income_tax_expense": ["ifrs-full_IncomeTaxExpenseContinuingOperations"],
    # IFRS FinanceCosts is broader than "interest expense" (FX losses on
    # borrowings, unwind of discount, etc. can be bundled in) -- it is the
    # closest available P&L proxy, not a clean interest-expense figure. Kept
    # as an explicit approximation; see reason string set below.
    "interest_expense": ["ifrs-full_FinanceCosts"],
    "eps": ["ifrs-full_BasicEarningsLossPerShare"],

    # CF
    "cfo": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
    "capex": ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    # Neither verified company discloses D&A as a separate XBRL fact (K-IFRS
    # filers using a by-function P&L often fold it into COGS/SG&A with no
    # standalone tag). Left empty on purpose -- do not guess a tag here.
    "depreciation_and_amortization": [],

    # Balance Sheet
    "cash": ["ifrs-full_CashAndCashEquivalents"],
    "current_assets": ["ifrs-full_CurrentAssets"],
    "current_liabilities": ["ifrs-full_CurrentLiabilities"],
    # Short/long-term borrowings are the least standardised tags in the whole
    # set. Samsung's 단기차입금 (short-term borrowings) ships with
    # account_id "-표준계정코드 미사용-" -- OpenDART itself has no XBRL id
    # for that line in Samsung's filing, so it is not fetchable by id at all
    # for that company. SK Hynix uses a completely different pair of ids.
    # All observed candidates are listed; a company matching none of them
    # must resolve to null + reason, not a wrong number.
    "short_term_debt": ["ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
    "long_term_debt": ["ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "ifrs-full_LongtermBorrowings"],
    # Never reported as a single fact by any filer -- always derive from
    # operating current assets/liabilities elsewhere, never fetch here.
    "nwc": [],
}

# Rows filed under this sj_div are Statement of Changes in Equity: the same
# account_id repeats once per equity column (share capital, retained
# earnings, NCI, ...) with genuinely different values, so keying a flat dict
# by account_id on this section silently picks whichever column happened to
# be inserted last. Every other section (BS/IS/CIS/CF) either has one row per
# id or repeats the same figure consistently (e.g. net income cross-referenced
# from CF), so excluding only SCE is sufficient.
_COLLIDING_SJ_DIV = {"SCE"}


def fetch_xbrl_facts(corp_code: str, year: int, fs_div: str = "CFS") -> dict[str, str]:
    """Fetch XBRL facts for a given corp_code and fiscal year.

    Returns {account_id: thstrm_amount} for the current-period column of the
    annual report (사업보고서, reprt_code 11011). fs_div defaults to CFS
    (consolidated); pass "OFS" for separate/standalone statements on filers
    with no consolidated subsidiaries.

    Returns {} without a network call if DART_API_KEY is not set, and {} on
    any API- or network-level failure -- callers must treat an empty dict as
    "no live data", not distinguish it from "company has no operations".
    """
    if not OPENDART_API_KEY:
        return {}
    url = f"{OPENDART_BASE}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": OPENDART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011",  # 사업보고서 (annual report)
        "fs_div": fs_div,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "000":
            return {}
        facts: dict[str, str] = {}
        for item in data.get("list", []):
            if item.get("sj_div") in _COLLIDING_SJ_DIV:
                continue
            account_id = item.get("account_id")
            amount = item.get("thstrm_amount")
            # "-표준계정코드 미사용-" means OpenDART has no XBRL id for this
            # company-specific line; it is not a usable lookup key.
            if not account_id or account_id.startswith("-") or amount is None:
                continue
            facts.setdefault(account_id, amount)
        return facts
    except Exception as e:
        print(f"DART fnlttSinglAcntAll fetch failed: {e}")
        return {}


def _pick(facts: dict[str, str], candidates: list[str]) -> float | None:
    for tag in candidates:
        raw = facts.get(tag)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def map_facts_to_pack(facts: dict[str, str], year: int, currency: str = "KRW") -> dict[str, Any]:
    """Map XBRL facts → accounting_pack structure.

    Missing facts remain null with reason="missing:not_in_opendart". `year` is
    the fiscal year the facts were fetched for -- a single OpenDART call only
    ever returns one period, so every populated field gets a single-point
    `series` (not a multi-year history; that needs one fetch per year, done by
    a caller that loops, not by this function).
    """
    pack = empty_accounting_pack(currency)
    end = f"{year}-12-31"

    def set_value(section: dict[str, Any], field: str, key: str, reason: str | None = None) -> float | None:
        value = _pick(facts, XBRL_TAGS[key])
        section[field]["value"] = value
        if value is not None:
            section[field]["series"] = [{"year": year, "end": end, "value": value}]
        elif reason:
            section[field]["reason"] = reason
        return value

    # P&L
    set_value(pack["pnl"], "revenue", "revenue", "missing:not_in_opendart")
    set_value(pack["pnl"], "gross_profit", "gross_profit", "missing:not_in_opendart")
    set_value(pack["pnl"], "operating_income", "operating_income", "missing:not_in_opendart")
    set_value(pack["pnl"], "net_income", "net_income", "missing:not_in_opendart")
    set_value(pack["pnl"], "profit_before_tax", "profit_before_tax", "missing:not_in_opendart")
    set_value(pack["pnl"], "income_tax_expense", "income_tax_expense", "missing:not_in_opendart")
    set_value(pack["pnl"], "eps", "eps", "missing:not_in_opendart")

    interest = _pick(facts, XBRL_TAGS["interest_expense"])
    pack["pnl"]["interest_expense"]["value"] = interest
    if interest is not None:
        pack["pnl"]["interest_expense"]["series"] = [{"year": year, "end": end, "value": interest}]
        pack["pnl"]["interest_expense"]["reason"] = "approx:ifrs_finance_costs_not_pure_interest"
    else:
        pack["pnl"]["interest_expense"]["reason"] = "missing:not_in_opendart"

    # CF
    cfo = set_value(pack["cash_flow"], "cfo", "cfo", "missing:not_in_opendart")
    capex = set_value(pack["cash_flow"], "capex", "capex", "missing:not_in_opendart")
    pack["cash_flow"]["depreciation_and_amortization"]["value"] = None
    pack["cash_flow"]["depreciation_and_amortization"]["reason"] = "missing:not_disclosed_separately"

    # Liquidity
    cash = set_value(pack["liquidity"], "cash_and_equivalents", "cash", "missing:not_in_opendart")

    current_assets = _pick(facts, XBRL_TAGS["current_assets"])
    current_liabilities = _pick(facts, XBRL_TAGS["current_liabilities"])
    if current_assets is not None and current_liabilities not in (None, 0):
        pack["liquidity"]["current_ratio"]["value"] = current_assets / current_liabilities
    else:
        pack["liquidity"]["current_ratio"]["reason"] = "missing:current_assets_or_current_liabilities"

    # Debt -- least standardised fields; see XBRL_TAGS comment.
    short_term = _pick(facts, XBRL_TAGS["short_term_debt"])
    long_term = _pick(facts, XBRL_TAGS["long_term_debt"])
    pack["debt_structure"]["short_term_borrowings"] = short_term
    pack["debt_structure"]["long_term_debt"] = long_term

    # debt_due_within_1y only ever gets the short-term-borrowings component from
    # this endpoint -- current_portion_lt_debt and lease_current have no
    # verified tag yet, so summing what we have would understate the true
    # figure. Leave .value null rather than present a partial sum as complete.
    pack["liquidity"]["debt_due_within_1y"]["components"]["short_term_borrowings"] = short_term
    pack["liquidity"]["debt_due_within_1y"]["reason"] = (
        "missing:current_portion_lt_debt_and_lease_current_not_separately_tagged"
        if short_term is not None else "missing:not_in_opendart"
    )

    interest_bearing = None
    if short_term is not None or long_term is not None:
        interest_bearing = (short_term or 0.0) + (long_term or 0.0)
    if interest_bearing is not None and cash is not None:
        pack["debt_structure"]["net_debt"]["value"] = interest_bearing - cash
        pack["debt_structure"]["net_debt"]["definition"] = (
            "short_term_borrowings + long_term_debt - cash_and_equivalents "
            "(marketable_securities not fetched by this adapter)"
        )
    else:
        pack["debt_structure"]["net_debt"]["reason"] = "missing:interest_bearing_debt_or_cash"

    return pack


def fetch_accounting_pack_kr(corp_code: str, year: int = 2025, fs_div: str = "CFS") -> dict[str, Any]:
    """One-shot: corp_code → full accounting_pack from OpenDART.

    This is the symbol `dart_kfa/__init__.py` imports as an optional source
    adapter. Renaming it breaks that import silently (caught by ImportError,
    degrades to None) -- keep the name in sync with __init__.py if it moves.

    Returns dict with:
    - accounting_pack: normalised P&L/CF/Balance
    - as_of: fiscal year end (e.g. 2025-12-31)
    - meta: source info, including whether a live key was present
    """
    facts = fetch_xbrl_facts(corp_code, year, fs_div)
    pack = map_facts_to_pack(facts, year)

    # Default FYE to Dec 31 (한국 일반기업 표준)
    pack["as_of"] = f"{year}-12-31"

    return {
        "accounting_pack": pack,
        "as_of": f"{year}-12-31",
        "meta": {
            "source": "opendart",
            "corp_code": corp_code,
            "year": year,
            "fs_div": fs_div,
            "live_key_present": bool(OPENDART_API_KEY),
            "facts_fetched": len(facts),
        },
    }
