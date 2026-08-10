"""Contracts for the max-3 valuation models per Investor / PE / Deal.

All models: numbers from filings/quotes only; missing → null + reason.
No target price / recommendation fields.
"""

from __future__ import annotations

from typing import Any

OE_HURDLE_DEFAULTS = {
    "hurdle_rate": 0.10,
    "hurdle_sensitivity": [0.08, 0.10, 0.12],
    "mos_wide_threshold": 0.30,
    "maintenance_capex_method": "min_da_capex",
}

REVERSE_DCF_DEFAULTS = {
    "solve_for": "revenue_cagr",
    "fixed": ["margin", "wacc", "tax", "capex_ratio"],
    "max_cagr_search": 0.40,
    "min_cagr_search": -0.20,
}

DELEVER_DEFAULTS = {"fcf_retention": 1.0, "horizon_years": 5}

COVERAGE_DEFAULTS = {
    "target_interest_coverage": None,
    "target_net_debt_ebitda": None,
}

FCFF_DCF_DEFAULTS = {
    "explicit_years": 5,
    "terminal_g_base": 0.02,
    "terminal_g_cap": 0.03,
    "bear_delta_cagr": -0.02,
    "bull_delta_cagr": 0.02,
    "bear_delta_margin": -0.01,
    "bull_delta_margin": 0.01,
    "wacc_sensitivity": [0.07, 0.08, 0.09, 0.10, 0.11],
}

SOTP_DEFAULTS = {"conglomerate_discount": 0.25}


def empty_model_result(model_id: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "id": model_id,
        "status": "omitted" if reason else "ok",
        "value": None,
        "components": {},
        "series": [],
        "assumptions": {},
        "reasons": [reason] if reason else [],
    }


def investor_models_stub() -> dict[str, Any]:
    return {
        "oe_hurdle": empty_model_result("oe_hurdle", "not_computed"),
        "reverse_dcf": empty_model_result("reverse_dcf", "not_computed"),
        "oe_yield": empty_model_result("oe_yield", "not_computed"),
    }


def pe_models_stub() -> dict[str, Any]:
    return {
        "delever_path": empty_model_result("delever_path", "not_computed"),
        "coverage_capacity": empty_model_result("coverage_capacity", "not_computed"),
        "fcf_yield_entry": empty_model_result("fcf_yield_entry", "not_computed"),
    }


def deal_models_stub() -> dict[str, Any]:
    return {
        "fcff_dcf": empty_model_result("fcff_dcf", "not_computed"),
        "trading_comps": empty_model_result("trading_comps", "not_computed"),
        "sotp_or_ev_bridge": empty_model_result("sotp_or_ev_bridge", "not_computed"),
    }
