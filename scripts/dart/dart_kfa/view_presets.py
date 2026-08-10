"""View presets: Basic + Investor + PE + Deal.

Cards may overlap across views. Basic is the default tab.
Valuation models: max 3 per non-basic view.
"""

from __future__ import annotations

from typing import Any

DEFAULT_VIEW = "basic"

CARDS: dict[str, list[str]] = {
    "basic": [
        "revenue", "operating_income", "net_income", "cfo", "fcf", "cash",
        "net_debt", "current_ratio", "debt_due_within_1y", "liquidity_coverage_1y",
        "interest_coverage", "ccc_days",
    ],
    "investor": [
        "revenue", "operating_income", "net_income", "fcf", "owner_earnings",
        "earnings_quality", "margins_trend", "capex_to_da", "net_debt_to_oe", "interest_coverage",
    ],
    "pe": [
        "revenue", "ebitda_or_op", "fcf", "net_debt_to_ebitda", "fcf_to_ebitda",
        "interest_coverage", "maint_capex_burden", "nwc_change_to_sales",
        "debt_due_within_1y", "liquidity_coverage_1y",
    ],
    "deal": [
        "revenue", "operating_income", "ebitda", "trading_multiples", "ev_bridge",
        "qoe_flags", "segment", "nwc_to_sales", "net_debt",
    ],
}

MODELS: dict[str, list[str]] = {
    "basic": [],
    "investor": ["oe_hurdle", "reverse_dcf", "oe_yield"],
    "pe": ["delever_path", "coverage_capacity", "fcf_yield_entry"],
    "deal": ["fcff_dcf", "trading_comps", "sotp_or_ev_bridge"],
}


def get_view_presets() -> dict[str, Any]:
    return {
        "default_view": DEFAULT_VIEW,
        "views": {
            vid: {"cards": CARDS[vid], "models": MODELS[vid]}
            for vid in ("basic", "investor", "pe", "deal")
        },
        "rules": {
            "overlap_allowed": True,
            "max_models_per_non_basic_view": 3,
            "no_price_target": True,
            "null_with_reason": True,
        },
    }
