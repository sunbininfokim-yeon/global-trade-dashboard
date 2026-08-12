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
    # A transparent starting point only. A source-specific WACC supplied by the
    # caller always wins, and the full 7–11% sensitivity is emitted either way.
    "base_wacc": 0.09,
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


def _number(value: Any) -> float | None:
    """Return a finite float, without treating zero as missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _omitted(model_id: str, *reasons: str) -> dict[str, Any]:
    result = empty_model_result(model_id)
    result["status"] = "omitted"
    result["reasons"] = list(reasons)
    return result


def _require(inputs: dict[str, Any], keys: list[str]) -> tuple[dict[str, float], list[str]]:
    values: dict[str, float] = {}
    missing: list[str] = []
    for key in keys:
        value = _number(inputs.get(key))
        if value is None:
            missing.append(f"missing:{key}")
        else:
            values[key] = value
    return values, missing


def owner_earnings_from_inputs(
    net_income: float | None,
    depreciation_and_amortization: float | None,
    capex: float | None,
    *,
    maintenance_capex_method: str = "min_da_capex",
) -> dict[str, Any]:
    """Calculate a filing-based Owner Earnings proxy without invented Capex.

    Maintenance Capex is not normally a reported line.  The only automatic
    method supported by this engine is min(|D&A|, |Capex|), which is surfaced
    in the output rather than presented as a management disclosure.
    """
    ni = _number(net_income)
    da = _number(depreciation_and_amortization)
    cap = _number(capex)
    if ni is None:
        return {"value": None, "maintenance_capex": None, "reason": "missing:net_income"}
    if da is None:
        return {
            "value": None,
            "maintenance_capex": None,
            "reason": "missing:depreciation_and_amortization",
        }
    if cap is None:
        return {"value": None, "maintenance_capex": None, "reason": "missing:capex"}
    if maintenance_capex_method != "min_da_capex":
        return {
            "value": None,
            "maintenance_capex": None,
            "reason": f"unsupported:maintenance_capex_method:{maintenance_capex_method}",
        }
    maintenance_capex = min(abs(da), abs(cap))
    return {
        "value": ni + abs(da) - maintenance_capex,
        "maintenance_capex": maintenance_capex,
        "reason": "proxy:maintenance_capex=min(abs(D&A),abs(capex))",
    }


def model_oe_hurdle(
    owner_earnings: float | None,
    market_cap: float | None = None,
    *,
    hurdle_rate: float | None = None,
    terminal_growth: float | None = None,
) -> dict[str, Any]:
    """Capitalise Owner Earnings at an explicit hurdle; never emits a price target."""
    oe = _number(owner_earnings)
    if oe is None:
        return _omitted("oe_hurdle", "missing:owner_earnings")

    hurdle = _number(hurdle_rate)
    hurdle = OE_HURDLE_DEFAULTS["hurdle_rate"] if hurdle is None else hurdle
    growth = _number(terminal_growth)
    growth = FCFF_DCF_DEFAULTS["terminal_g_base"] if growth is None else growth
    if growth > FCFF_DCF_DEFAULTS["terminal_g_cap"]:
        return _omitted("oe_hurdle", "terminal_growth_exceeds_3pct_cap")
    if hurdle <= growth:
        return _omitted("oe_hurdle", "hurdle_must_exceed_terminal_growth")

    def capitalise(rate: float) -> float | None:
        if rate <= growth:
            return None
        return oe * (1.0 + growth) / (rate - growth)

    equity_value = capitalise(hurdle)
    sensitivity = [
        {"hurdle_rate": rate, "equity_value": capitalise(rate)}
        for rate in OE_HURDLE_DEFAULTS["hurdle_sensitivity"]
    ]
    result = empty_model_result("oe_hurdle")
    result["value"] = equity_value
    result["components"] = {
        "owner_earnings": oe,
        "market_cap": _number(market_cap),
        "market_cap_gap": None,
        "hurdle_sensitivity": sensitivity,
    }
    mcap = _number(market_cap)
    if mcap is not None and mcap > 0 and equity_value is not None:
        result["components"]["market_cap_gap"] = equity_value / mcap - 1.0
    else:
        result["status"] = "partial"
        result["reasons"].append("missing:market_cap_for_comparison")
    result["assumptions"] = {
        "hurdle_rate": hurdle,
        "terminal_growth": growth,
        "terminal_growth_cap": FCFF_DCF_DEFAULTS["terminal_g_cap"],
        "maintenance_capex_method": OE_HURDLE_DEFAULTS["maintenance_capex_method"],
    }
    return result


def model_oe_yield(owner_earnings: float | None, market_cap: float | None) -> dict[str, Any]:
    oe = _number(owner_earnings)
    mcap = _number(market_cap)
    if oe is None or mcap is None or mcap <= 0:
        missing = []
        if oe is None:
            missing.append("missing:owner_earnings")
        if mcap is None or mcap <= 0:
            missing.append("missing:positive_market_cap")
        return _omitted("oe_yield", *missing)
    result = empty_model_result("oe_yield")
    result["value"] = oe / mcap
    result["components"] = {"owner_earnings": oe, "market_cap": mcap}
    result["assumptions"] = {"definition": "owner_earnings / market_cap"}
    return result


def _fcff_value(
    inputs: dict[str, Any],
    *,
    revenue_cagr: float,
    operating_margin: float,
    wacc: float,
    terminal_growth: float,
) -> dict[str, Any]:
    """Pure FCFF projection returning enterprise/equity value, never per-share value."""
    required, missing = _require(
        inputs,
        ["revenue", "tax_rate", "capex_to_sales", "da_to_sales", "nwc_to_sales"],
    )
    if missing:
        return {"ok": False, "reason": ",".join(missing)}
    if wacc <= terminal_growth:
        return {"ok": False, "reason": "wacc_must_exceed_terminal_growth"}
    if terminal_growth > FCFF_DCF_DEFAULTS["terminal_g_cap"]:
        return {"ok": False, "reason": "terminal_growth_exceeds_3pct_cap"}

    years = int(inputs.get("explicit_years") or FCFF_DCF_DEFAULTS["explicit_years"])
    revenue = required["revenue"]
    nwc_previous = revenue * required["nwc_to_sales"]
    pv_explicit = 0.0
    projected: list[dict[str, Any]] = []
    for year in range(1, years + 1):
        revenue *= 1.0 + revenue_cagr
        ebit = revenue * operating_margin
        nopat = ebit * (1.0 - required["tax_rate"])
        da = revenue * required["da_to_sales"]
        capex = revenue * required["capex_to_sales"]
        nwc = revenue * required["nwc_to_sales"]
        delta_nwc = nwc - nwc_previous
        fcff = nopat + da - capex - delta_nwc
        pv = fcff / ((1.0 + wacc) ** year)
        pv_explicit += pv
        projected.append(
            {
                "year": year,
                "revenue": revenue,
                "ebit": ebit,
                "fcff": fcff,
                "pv_fcff": pv,
            }
        )
        nwc_previous = nwc

    final_fcff = projected[-1]["fcff"]
    terminal_value = final_fcff * (1.0 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** years)
    enterprise_value = pv_explicit + pv_terminal
    net_debt = _number(inputs.get("net_debt")) or 0.0
    return {
        "ok": True,
        "enterprise_value": enterprise_value,
        "equity_value": enterprise_value - net_debt,
        "pv_explicit_fcff": pv_explicit,
        "pv_terminal": pv_terminal,
        "projected": projected,
    }


def model_fcff_dcf(inputs: dict[str, Any]) -> dict[str, Any]:
    """Three-scenario FCFF DCF seeded from reported history and explicit inputs."""
    cagr = _number(inputs.get("revenue_cagr"))
    margin = _number(inputs.get("operating_margin"))
    if cagr is None or margin is None:
        missing = []
        if cagr is None:
            missing.append("missing:reported_revenue_cagr")
        if margin is None:
            missing.append("missing:reported_operating_margin")
        return _omitted("fcff_dcf", *missing)

    base_wacc = _number(inputs.get("wacc"))
    wacc_source = "caller_input"
    if base_wacc is None:
        base_wacc = FCFF_DCF_DEFAULTS["base_wacc"]
        wacc_source = "engine_default_not_company_specific"
    terminal_growth = _number(inputs.get("terminal_growth"))
    terminal_growth = FCFF_DCF_DEFAULTS["terminal_g_base"] if terminal_growth is None else terminal_growth
    if terminal_growth > FCFF_DCF_DEFAULTS["terminal_g_cap"]:
        return _omitted("fcff_dcf", "terminal_growth_exceeds_3pct_cap")

    scenario_specs = (
        ("bear", cagr + FCFF_DCF_DEFAULTS["bear_delta_cagr"], margin + FCFF_DCF_DEFAULTS["bear_delta_margin"]),
        ("base", cagr, margin),
        ("bull", cagr + FCFF_DCF_DEFAULTS["bull_delta_cagr"], margin + FCFF_DCF_DEFAULTS["bull_delta_margin"]),
    )
    scenarios: list[dict[str, Any]] = []
    for scenario_id, scenario_cagr, scenario_margin in scenario_specs:
        value = _fcff_value(
            inputs,
            revenue_cagr=scenario_cagr,
            operating_margin=scenario_margin,
            wacc=base_wacc,
            terminal_growth=terminal_growth,
        )
        scenarios.append(
            {
                "id": scenario_id,
                "revenue_cagr": scenario_cagr,
                "operating_margin": scenario_margin,
                **value,
            }
        )
    failures = list(dict.fromkeys(s.get("reason") for s in scenarios if not s.get("ok")))
    if failures:
        return _omitted("fcff_dcf", *[str(reason) for reason in failures])

    sensitivity: list[dict[str, Any]] = []
    for sensitivity_wacc in FCFF_DCF_DEFAULTS["wacc_sensitivity"]:
        value = _fcff_value(
            inputs,
            revenue_cagr=cagr,
            operating_margin=margin,
            wacc=sensitivity_wacc,
            terminal_growth=terminal_growth,
        )
        sensitivity.append(
            {
                "wacc": sensitivity_wacc,
                "enterprise_value": value.get("enterprise_value"),
                "equity_value": value.get("equity_value"),
                "reason": value.get("reason"),
            }
        )

    base = next(s for s in scenarios if s["id"] == "base")
    result = empty_model_result("fcff_dcf")
    result["value"] = base["equity_value"]
    result["components"] = {"scenarios": scenarios, "wacc_sensitivity": sensitivity}
    result["assumptions"] = {
        "explicit_years": int(inputs.get("explicit_years") or FCFF_DCF_DEFAULTS["explicit_years"]),
        "terminal_growth": terminal_growth,
        "terminal_growth_cap": FCFF_DCF_DEFAULTS["terminal_g_cap"],
        "base_wacc": base_wacc,
        "wacc_source": wacc_source,
        "seed": "reported_annual_revenue_cagr_and_operating_margin",
        "bear_delta_cagr": FCFF_DCF_DEFAULTS["bear_delta_cagr"],
        "bull_delta_cagr": FCFF_DCF_DEFAULTS["bull_delta_cagr"],
        "bear_delta_margin": FCFF_DCF_DEFAULTS["bear_delta_margin"],
        "bull_delta_margin": FCFF_DCF_DEFAULTS["bull_delta_margin"],
    }
    if wacc_source != "caller_input":
        result["reasons"].append("wacc_uses_engine_default_not_company_specific")
    return result


def model_reverse_dcf(inputs: dict[str, Any], market_cap: float | None) -> dict[str, Any]:
    """Solve the revenue CAGR required for the FCFF inputs to equal market cap."""
    mcap = _number(market_cap)
    if mcap is None or mcap <= 0:
        return _omitted("reverse_dcf", "missing:positive_market_cap")
    margin = _number(inputs.get("operating_margin"))
    if margin is None:
        return _omitted("reverse_dcf", "missing:reported_operating_margin")
    _, missing = _require(
        inputs,
        ["revenue", "tax_rate", "capex_to_sales", "da_to_sales", "nwc_to_sales"],
    )
    if missing:
        return _omitted("reverse_dcf", *missing)
    wacc = _number(inputs.get("wacc")) or FCFF_DCF_DEFAULTS["base_wacc"]
    terminal_growth = _number(inputs.get("terminal_growth"))
    terminal_growth = FCFF_DCF_DEFAULTS["terminal_g_base"] if terminal_growth is None else terminal_growth
    if terminal_growth > FCFF_DCF_DEFAULTS["terminal_g_cap"]:
        return _omitted("reverse_dcf", "terminal_growth_exceeds_3pct_cap")

    def equity_at(cagr: float) -> float | None:
        value = _fcff_value(
            inputs,
            revenue_cagr=cagr,
            operating_margin=margin,
            wacc=wacc,
            terminal_growth=terminal_growth,
        )
        return _number(value.get("equity_value")) if value.get("ok") else None

    lo = REVERSE_DCF_DEFAULTS["min_cagr_search"]
    hi = REVERSE_DCF_DEFAULTS["max_cagr_search"]
    value_lo = equity_at(lo)
    value_hi = equity_at(hi)
    if value_lo is None or value_hi is None:
        return _omitted("reverse_dcf", "missing:fcff_inputs")

    result = empty_model_result("reverse_dcf")
    result["assumptions"] = {
        "fixed": REVERSE_DCF_DEFAULTS["fixed"],
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "search_min_cagr": lo,
        "search_max_cagr": hi,
    }
    if mcap <= value_lo:
        result["status"] = "partial"
        result["value"] = lo
        result["components"] = {"market_cap": mcap, "model_equity_value": value_lo, "bound": "lower"}
        result["reasons"].append("market_cap_at_or_below_search_lower_bound")
        return result
    if mcap >= value_hi:
        result["status"] = "partial"
        result["value"] = hi
        result["components"] = {"market_cap": mcap, "model_equity_value": value_hi, "bound": "upper"}
        result["reasons"].append("market_cap_at_or_above_search_upper_bound")
        return result

    left, right = lo, hi
    for _ in range(60):
        midpoint = (left + right) / 2.0
        value_mid = equity_at(midpoint)
        if value_mid is None:
            return _omitted("reverse_dcf", "fcff_failed_during_search")
        if abs(value_mid - mcap) / max(abs(mcap), 1.0) < 0.0001:
            result["value"] = midpoint
            result["components"] = {
                "market_cap": mcap,
                "model_equity_value": value_mid,
                "bound": "interior",
            }
            return result
        if value_mid < mcap:
            left = midpoint
        else:
            right = midpoint
    midpoint = (left + right) / 2.0
    result["value"] = midpoint
    result["components"] = {
        "market_cap": mcap,
        "model_equity_value": equity_at(midpoint),
        "bound": "max_iterations",
    }
    return result


def model_trading_comps(inputs: dict[str, Any], market_cap: float | None, peers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Emit the issuer's observed multiples; peer values are never invented."""
    mcap = _number(market_cap)
    if mcap is None or mcap <= 0:
        return _omitted("trading_comps", "missing:positive_market_cap")
    revenue = _number(inputs.get("revenue"))
    ebitda = _number(inputs.get("ebitda"))
    net_income = _number(inputs.get("net_income"))
    net_debt = _number(inputs.get("net_debt"))
    enterprise_value = None if net_debt is None else mcap + net_debt
    current = {
        "market_cap": mcap,
        "enterprise_value": enterprise_value,
        "pe": None if net_income is None or net_income <= 0 else mcap / net_income,
        "ps": None if revenue is None or revenue <= 0 else mcap / revenue,
        "ev_to_ebitda": None if enterprise_value is None or ebitda is None or ebitda <= 0 else enterprise_value / ebitda,
    }
    result = empty_model_result("trading_comps")
    result["value"] = current
    result["components"] = {"issuer_multiples": current, "peer_multiples": peers or []}
    result["assumptions"] = {"peer_values": "only supplied peer observations are used"}
    if not peers:
        result["status"] = "partial"
        result["reasons"].append("missing:peer_multiples; issuer_snapshot_only")
    if enterprise_value is None:
        result["status"] = "partial"
        result["reasons"].append("missing:net_debt_for_ev_multiples")
    return result


def model_sotp_or_ev_bridge(
    market_cap: float | None,
    net_debt: float | None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate an EV bridge and SOTP only from supplied segment observations."""
    mcap = _number(market_cap)
    nd = _number(net_debt)
    provided_segments = segments or []
    bridge = None
    if mcap is not None and nd is not None:
        bridge = {"market_cap": mcap, "net_debt": nd, "enterprise_value": mcap + nd}

    parts: list[dict[str, Any]] = []
    for segment in provided_segments:
        direct_ev = _number(segment.get("enterprise_value"))
        multiple = _number(segment.get("multiple"))
        metric = _number(segment.get("metric"))
        implied_ev = direct_ev
        reason = None
        if implied_ev is None and multiple is not None and metric is not None:
            implied_ev = multiple * metric
        elif implied_ev is None:
            reason = "missing:enterprise_value_or_metric_and_multiple"
        parts.append(
            {
                "id": segment.get("id"),
                "name": segment.get("name"),
                "enterprise_value": implied_ev,
                "reason": reason,
            }
        )

    valid_parts = [p["enterprise_value"] for p in parts if p["enterprise_value"] is not None]
    result = empty_model_result("sotp_or_ev_bridge")
    result["components"] = {"ev_bridge": bridge, "segments": parts}
    result["assumptions"] = {
        "conglomerate_discount": SOTP_DEFAULTS["conglomerate_discount"],
        "segment_values": "only source/user supplied segment values or multiples",
    }
    if valid_parts:
        gross_ev = sum(valid_parts)
        result["value"] = gross_ev * (1.0 - SOTP_DEFAULTS["conglomerate_discount"])
        result["components"]["gross_segment_ev"] = gross_ev
        result["components"]["after_conglomerate_discount_ev"] = result["value"]
        if nd is not None:
            result["components"]["equity_value_after_net_debt"] = result["value"] - nd
        return result
    if bridge is not None:
        result["status"] = "partial"
        result["value"] = bridge["enterprise_value"]
        result["reasons"].append("missing:segment_values; ev_bridge_only")
        return result
    return _omitted("sotp_or_ev_bridge", "missing:market_cap_or_segment_values")


def run_investor_models(inputs: dict[str, Any], market: dict[str, Any] | None = None) -> dict[str, Any]:
    market = market or {}
    market_cap = _number(market.get("market_cap"))
    return {
        "oe_hurdle": model_oe_hurdle(
            inputs.get("owner_earnings"),
            market_cap,
            terminal_growth=inputs.get("terminal_growth"),
        ),
        "reverse_dcf": model_reverse_dcf(inputs, market_cap),
        "oe_yield": model_oe_yield(inputs.get("owner_earnings"), market_cap),
    }


def run_deal_models(
    inputs: dict[str, Any],
    market: dict[str, Any] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    market = market or {}
    market_cap = _number(market.get("market_cap"))
    return {
        "fcff_dcf": model_fcff_dcf(inputs),
        "trading_comps": model_trading_comps(inputs, market_cap, market.get("peer_multiples")),
        "sotp_or_ev_bridge": model_sotp_or_ev_bridge(market_cap, inputs.get("net_debt"), segments),
    }


# Compatibility entry points kept for callers that imported the former stubs.
# They now report missing inputs rather than claiming the model is unimplemented.
def investor_models_stub() -> dict[str, Any]:
    return run_investor_models({}, {})


def pe_models_stub() -> dict[str, Any]:
    from .pe_models import run_pe_models

    return run_pe_models({}, {}).get("models", {})


def deal_models_stub() -> dict[str, Any]:
    return run_deal_models({}, {}, None)
