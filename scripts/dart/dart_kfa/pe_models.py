"""PE models (max 3): delever_path, coverage_capacity, fcf_yield_entry."""

from __future__ import annotations

from typing import Any

from .model_contracts import DELEVER_DEFAULTS, COVERAGE_DEFAULTS, empty_model_result


def model_delever_path(
    net_debt: float | None,
    ebitda: float | None,
    fcf: float | None,
    fcf_retention: float | None = None,
    horizon_years: int | None = None,
) -> dict[str, Any]:
    result = empty_model_result("delever_path")
    ret = fcf_retention if fcf_retention is not None else DELEVER_DEFAULTS["fcf_retention"]
    years = horizon_years or DELEVER_DEFAULTS["horizon_years"]
    result["assumptions"] = {
        "fcf_retention": ret,
        "horizon_years": years,
        "note": "assumes constant FCF; no new debt / buybacks / M&A",
    }
    if net_debt is None or ebitda is None or ebitda <= 0 or fcf is None:
        result["status"] = "omitted"
        result["reasons"] = ["need net_debt, positive ebitda, fcf"]
        return result
    path = []
    nd = float(net_debt)
    annual_pay = float(fcf) * ret
    for y in range(0, years + 1):
        lev = nd / ebitda if ebitda else None
        path.append({"year": y, "net_debt": nd, "net_debt_to_ebitda": lev})
        nd = nd - annual_pay
    result["value"] = {
        "start_nd_ebitda": path[0]["net_debt_to_ebitda"],
        "end_nd_ebitda": path[-1]["net_debt_to_ebitda"],
        "annual_fcf_applied": annual_pay,
    }
    result["components"]["path"] = path
    result["series"] = path
    result["status"] = "ok"
    return result


def model_coverage_capacity(
    interest_coverage: float | None,
    net_debt: float | None,
    ebitda: float | None,
    target_interest_coverage: float | None = None,
    target_nd_ebitda: float | None = None,
) -> dict[str, Any]:
    result = empty_model_result("coverage_capacity")
    t_ic = target_interest_coverage if target_interest_coverage is not None else COVERAGE_DEFAULTS["target_interest_coverage"]
    t_nd = target_nd_ebitda if target_nd_ebitda is not None else COVERAGE_DEFAULTS["target_net_debt_ebitda"]
    result["assumptions"] = {
        "target_interest_coverage": t_ic,
        "target_net_debt_ebitda": t_nd,
        "note": "targets are user assumptions, not engine opinions",
    }
    nd_ebitda = None
    if net_debt is not None and ebitda and ebitda > 0:
        nd_ebitda = net_debt / ebitda
    if interest_coverage is None and nd_ebitda is None:
        result["status"] = "omitted"
        result["reasons"] = ["need interest_coverage and/or net_debt+ebitda"]
        return result
    result["value"] = {"interest_coverage": interest_coverage, "net_debt_to_ebitda": nd_ebitda}
    headroom = {}
    if t_ic is not None and interest_coverage is not None:
        headroom["interest_coverage_vs_target"] = interest_coverage - t_ic
    if t_nd is not None and nd_ebitda is not None:
        headroom["nd_ebitda_vs_target"] = t_nd - nd_ebitda
    result["components"]["headroom"] = headroom
    result["status"] = "ok"
    if not headroom:
        result["reasons"].append("no targets set — showing current levels only")
    return result


def model_fcf_yield_entry(
    fcf: float | None, market_cap: float | None, net_debt: float | None
) -> dict[str, Any]:
    result = empty_model_result("fcf_yield_entry")
    if fcf is None:
        result["status"] = "omitted"
        result["reasons"] = ["fcf missing"]
        return result
    ev = None
    if market_cap is not None:
        ev = market_cap + (net_debt or 0.0)
    result["value"] = {
        "fcf_to_equity": (fcf / market_cap) if market_cap else None,
        "fcf_to_ev": (fcf / ev) if ev and ev > 0 else None,
        "fcf": fcf,
        "equity": market_cap,
        "ev": ev,
    }
    if market_cap is None:
        result["reasons"].append("market_cap missing → equity yield omitted")
        if ev is None:
            result["status"] = "omitted"
            return result
    result["status"] = "ok"
    return result


def run_pe_models(pack: dict, market: dict | None = None) -> dict[str, Any]:
    market = market or {}
    ebitda = pack.get("pnl", {}).get("ebitda", {}).get("value")
    if ebitda is None:
        ebitda = pack.get("pnl", {}).get("operating_income", {}).get("value")
    net_debt = pack.get("debt_structure", {}).get("net_debt", {}).get("value")
    fcf = pack.get("cash_flow", {}).get("fcf", {}).get("value")
    ic = pack.get("liquidity", {}).get("interest_coverage", {}).get("value")
    mcap = market.get("market_cap")
    return {
        "models": {
            "delever_path": model_delever_path(net_debt, ebitda, fcf),
            "coverage_capacity": model_coverage_capacity(ic, net_debt, ebitda),
            "fcf_yield_entry": model_fcf_yield_entry(fcf, mcap, net_debt),
        }
    }
