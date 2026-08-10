"""Accounting pack: basic P&L, cash flow, liquidity, working capital.

Designed for click → series chart / components table.
"""

from __future__ import annotations

from typing import Any


def _series_placeholder() -> list[dict[str, Any]]:
    return []


def empty_accounting_pack(currency: str | None = None) -> dict[str, Any]:
    return {
        "as_of": None,
        "currency": currency,
        "years": [],
        "pnl": {
            "revenue": {"value": None, "yoy": None, "series": _series_placeholder()},
            "gross_profit": {"value": None, "margin": None, "series": _series_placeholder()},
            "operating_income": {"value": None, "margin": None, "series": _series_placeholder()},
            "ebitda": {"value": None, "margin": None, "series": _series_placeholder()},
            "net_income": {"value": None, "margin": None, "series": _series_placeholder()},
            "eps": {"value": None, "series": _series_placeholder()},
        },
        "cash_flow": {
            "cfo": {"value": None, "series": _series_placeholder()},
            "capex": {
                "value": None,
                "abs_value": None,
                "series": _series_placeholder(),
                "sign_note": "stored as reported; FCF uses abs",
            },
            "fcf": {"value": None, "definition": "cfo - abs(capex)", "series": _series_placeholder()},
            "fcf_conversion_ni": {"value": None, "series": _series_placeholder()},
        },
        "liquidity": {
            "cash_and_equivalents": {"value": None, "series": _series_placeholder()},
            "marketable_securities_current": {"value": None, "series": _series_placeholder()},
            "undrawn_revolver": {"value": None, "reason": None},
            "liquidity_buffer": {"value": None, "components": {}},
            "debt_due_within_1y": {
                "value": None,
                "components": {
                    "short_term_borrowings": None,
                    "current_portion_lt_debt": None,
                    "leases_current": None,
                },
                "reason": None,
            },
            "liquidity_coverage_1y": {
                "value": None,
                "status": None,
                "rule": "buffer / debt_due_within_1y; <1 stressed, 1–1.5 tight, >2 comfortable",
            },
            "current_ratio": {"value": None, "series": _series_placeholder()},
            "interest_coverage": {"value": None, "series": _series_placeholder()},
        },
        "debt_structure": {
            "short_term_borrowings": None,
            "current_portion_lt_debt": None,
            "long_term_debt": None,
            "lease_liabilities_current": None,
            "lease_liabilities_noncurrent": None,
            "total_interest_bearing": None,
            "net_debt": {
                "value": None,
                "definition": "interest_bearing - (cash + marketable_securities)",
                "series": _series_placeholder(),
            },
            "maturity_ladder": {
                "due_1y": None,
                "due_1_3y": None,
                "due_3_5y": None,
                "due_after_5y": None,
                "source": None,
                "reason": None,
            },
        },
        "working_capital": {
            "dso": {"value": None, "series": _series_placeholder()},
            "dio": {"value": None, "series": _series_placeholder()},
            "dpo": {"value": None, "series": _series_placeholder()},
            "ccc_days": {"value": None, "series": _series_placeholder()},
            "nwc_to_sales": {"value": None, "series": _series_placeholder()},
        },
        "reasons": [],
    }


def coverage_status(coverage: float | None) -> str | None:
    if coverage is None:
        return None
    if coverage < 1.0:
        return "stressed"
    if coverage <= 1.5:
        return "tight"
    if coverage > 2.0:
        return "comfortable"
    return "adequate"
