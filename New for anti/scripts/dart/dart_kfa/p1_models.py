"""P1 role-based models with an explicit accounting and assumption boundary.

These models are deliberately separate from the legacy view-engine models.
They use P1 strict EBITDA where EBITDA is required, keep all calculation
amounts in the filing currency, and never create an implicit market input or
forecast.  They are JSON-only outputs for a future Worker/UI adapter.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Mapping

from .entity_policy import is_financial
from .ma_metrics import compute_ma_metrics
from .valuation import fcff_dcf


SCHEMA_VERSION = "kfa-p1-models/1"
MODEL_GROUPS = {
    "fundamental_investor": ("oe_hurdle", "reverse_dcf", "oe_yield"),
    "private_equity": ("delever_path", "coverage_capacity", "fcf_yield_entry"),
    "investment_banking": ("fcff_dcf", "trading_comps", "sotp_or_ev_bridge"),
}
_FLOW_ACCOUNTS = ("CFO", "CAPEX", "INTEREST_EXPENSE", "REVENUE")


def _number(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        result = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return float(result) if result.is_finite() else None


def _model(
    model_id: str,
    status: str,
    *,
    value: Any = None,
    reason: str | None = None,
    required_inputs: list[str] | None = None,
    components: Mapping[str, Any] | None = None,
    assumptions: Mapping[str, Any] | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "id": model_id,
        "status": status,
        "value": value,
        "reason": reason,
        "required_inputs": list(required_inputs or []),
        "components": deepcopy(dict(components or {})),
        "assumptions": deepcopy(dict(assumptions or {})),
        "calculation_currency": currency,
        "presentation_currency": currency,
        "currency_policy": "filing_currency_only",
        "investment_recommendation": "not_provided",
    }


def _fact(canonical: Mapping[str, Any], account_id: str, endpoint: str) -> dict[str, Any] | None:
    series = (canonical.get("series") or {}).get(account_id)
    if not isinstance(series, Mapping):
        return None
    item = series.get("annual") if endpoint == "annual" else ((series.get("quarters") or {}).get(endpoint))
    return dict(item) if isinstance(item, Mapping) else None


def _endpoint(p1_disclosures: Mapping[str, Any]) -> str | None:
    value = ((p1_disclosures.get("period_selection") or {}).get("selected"))
    return str(value) if value in {"Q1", "Q2", "Q3", "annual"} else None


def _flow_signature(fact: Mapping[str, Any]) -> tuple[Any, ...]:
    unit = fact.get("unit") or {}
    return (
        fact.get("fiscal_year"), fact.get("fiscal_quarter"), fact.get("period_kind"),
        fact.get("period_start"), fact.get("period_end"), fact.get("fs_div"),
        unit.get("kind"), unit.get("currency"), unit.get("scale"),
    )


def _usable_flow(fact: Mapping[str, Any] | None) -> str | None:
    if not isinstance(fact, Mapping):
        return "missing:account"
    if fact.get("availability") != "available" or _number(fact.get("value")) is None:
        return str(fact.get("reason") or "missing:reported_fact")
    if fact.get("nature") != "flow":
        return "incompatible:nature_not_flow"
    if fact.get("quality") not in {"reported", "deterministic_derived"}:
        return f"incompatible:fact_quality:{fact.get('quality')}"
    return None


def _strict_ebitda(p1_disclosures: Mapping[str, Any]) -> tuple[float | None, str | None]:
    cell = ((p1_disclosures.get("current") or {}).get("ebitda") or {})
    if cell.get("status") != "derived_deterministic" or _number(cell.get("value")) is None:
        return None, str(cell.get("reason") or "missing:strict_ebitda")
    return _number(cell.get("value")), None


def _amounts(canonical: Mapping[str, Any], endpoint: str) -> dict[str, float | None]:
    return {
        str(account_id): _number((_fact(canonical, str(account_id), endpoint) or {}).get("value"))
        for account_id in (canonical.get("series") or {})
    }


def _reported_flow_set(
    canonical: Mapping[str, Any], *, endpoint: str, account_ids: tuple[str, ...]
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    facts = {account_id: _fact(canonical, account_id, endpoint) for account_id in account_ids}
    problems = [f"{account_id}:{_usable_flow(fact)}" for account_id, fact in facts.items() if _usable_flow(fact)]
    if problems:
        return None, "missing_or_incompatible:" + ";".join(problems)
    signatures = {_flow_signature(fact) for fact in facts.values() if fact}
    if len(signatures) != 1:
        return None, "incompatible:period_scope_currency_or_unit"
    return {key: value for key, value in facts.items() if value}, None


def _market_cap(
    market: Mapping[str, Any] | None, *, currency: str | None
) -> tuple[float | None, str | None, dict[str, Any]]:
    market = market or {}
    value = _number(market.get("market_cap"))
    if value is None or value <= 0:
        return None, "missing:verified_market_cap", {}
    if str(market.get("currency") or "").upper() != str(currency or "").upper():
        return None, "incompatible:market_cap_currency_requires_explicit_fx_contract", {}
    if not market.get("as_of") or not market.get("source"):
        return None, "missing:market_cap_source_or_as_of", {}
    return value, None, {
        "market_cap": value, "currency": market.get("currency"),
        "as_of": market.get("as_of"), "source": market.get("source"),
    }


def _owner_earnings(
    canonical: Mapping[str, Any],
    *,
    endpoint: str,
    maintenance_capex: Any,
) -> tuple[float | None, str | None, dict[str, Any]]:
    flows, reason = _reported_flow_set(canonical, endpoint=endpoint, account_ids=("CFO", "CAPEX"))
    if flows is None:
        return None, reason, {}
    maintenance = _number(maintenance_capex)
    if maintenance is None or maintenance < 0:
        return None, "input:explicit_maintenance_capex_required", {}
    capex = abs(_number(flows["CAPEX"].get("value")) or 0.0)
    if maintenance > capex:
        return None, "invalid:maintenance_capex_exceeds_reported_capex", {}
    cfo = _number(flows["CFO"].get("value"))
    return cfo - maintenance, None, {
        "reported_cfo": cfo,
        "reported_capex": capex,
        "maintenance_capex": maintenance,
        "formula": "owner_earnings = CFO - explicit_maintenance_capex",
    }


def _oe_models(
    canonical: Mapping[str, Any],
    *,
    endpoint: str | None,
    assumptions: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    currency: str | None,
) -> dict[str, dict[str, Any]]:
    if endpoint is None:
        reason = "missing:reported_endpoint"
        return {model_id: _model(model_id, "omitted", reason=reason, currency=currency) for model_id in MODEL_GROUPS["fundamental_investor"]}
    owner, owner_reason, components = _owner_earnings(
        canonical, endpoint=endpoint, maintenance_capex=assumptions.get("maintenance_capex"),
    )
    if owner is None:
        required = ["maintenance_capex"] if owner_reason == "input:explicit_maintenance_capex_required" else []
        base = _model("oe_hurdle", "needs_input" if required else "omitted", reason=owner_reason, required_inputs=required, currency=currency)
        yield_model = _model("oe_yield", "needs_input" if required else "omitted", reason=owner_reason, required_inputs=required, currency=currency)
    else:
        hurdle = _number(assumptions.get("owner_earnings_hurdle"))
        if hurdle is None:
            base = _model("oe_hurdle", "needs_input", reason="input:owner_earnings_hurdle_required", required_inputs=["owner_earnings_hurdle"], components=components, currency=currency)
        elif not 0 < hurdle < 1:
            base = _model("oe_hurdle", "omitted", reason="invalid:owner_earnings_hurdle", components=components, currency=currency)
        else:
            base = _model("oe_hurdle", "computed", value=owner / hurdle, components=components, assumptions={"owner_earnings_hurdle": hurdle}, currency=currency)
        market_cap, market_reason, market_meta = _market_cap(market, currency=currency)
        if market_cap is None:
            yield_model = _model("oe_yield", "needs_input" if market_reason.startswith("missing:") else "omitted", reason=market_reason, required_inputs=["market_cap"] if market_reason.startswith("missing:") else [], components=components, currency=currency)
        else:
            yield_model = _model("oe_yield", "computed", value=owner / market_cap, components={**components, **market_meta}, currency=currency)
    return {
        "oe_hurdle": base,
        "reverse_dcf": _reverse_dcf(canonical, endpoint=endpoint, assumptions=assumptions, market=market, currency=currency),
        "oe_yield": yield_model,
    }


def _reverse_dcf(
    canonical: Mapping[str, Any], *, endpoint: str | None, assumptions: Mapping[str, Any], market: Mapping[str, Any] | None, currency: str | None
) -> dict[str, Any]:
    if endpoint != "annual":
        return _model("reverse_dcf", "omitted", reason="blocked_quality:reverse_dcf_requires_annual_base", currency=currency)
    revenue_fact = _fact(canonical, "REVENUE", endpoint)
    if _usable_flow(revenue_fact):
        return _model("reverse_dcf", "omitted", reason="missing:reported_annual_revenue", currency=currency)
    amounts = _amounts(canonical, endpoint)
    net_debt = (compute_ma_metrics(amounts).get("net_debt") or {}).get("value")
    if net_debt is None:
        return _model("reverse_dcf", "omitted", reason="missing:verified_net_debt", currency=currency)
    market_cap, market_reason, market_meta = _market_cap(market, currency=currency)
    if market_cap is None:
        return _model("reverse_dcf", "needs_input" if market_reason.startswith("missing:") else "omitted", reason=market_reason, required_inputs=["market_cap"] if market_reason.startswith("missing:") else [], currency=currency)
    required_keys = ("projection_years", "ebit_margin", "tax_rate", "operating_nwc_to_sales", "capex_to_sales", "da_to_sales", "wacc", "terminal_growth")
    missing = [key for key in required_keys if _number(assumptions.get(key)) is None]
    if missing:
        return _model("reverse_dcf", "needs_input", reason="input:explicit_dcf_assumptions_required", required_inputs=missing, components=market_meta, currency=currency)
    wacc, g = float(assumptions["wacc"]), float(assumptions["terminal_growth"])
    if not (0 < wacc and g < wacc and g <= 0.03):
        return _model("reverse_dcf", "omitted", reason="invalid:wacc_or_terminal_growth", components=market_meta, currency=currency)
    lo, hi = float(assumptions.get("reverse_cagr_min", -0.20)), float(assumptions.get("reverse_cagr_max", 0.40))
    if lo >= hi:
        return _model("reverse_dcf", "omitted", reason="invalid:reverse_cagr_bounds", components=market_meta, currency=currency)
    base = {key: assumptions[key] for key in required_keys}
    base["net_debt"] = net_debt

    def equity(growth: float) -> float | None:
        result = fcff_dcf(revenue0=float(revenue_fact["value"]), assumptions={**base, "revenue_cagr": growth})
        return _number(result.get("equity_value")) if result.get("ok") else None

    low, high = equity(lo), equity(hi)
    if low is None or high is None:
        return _model("reverse_dcf", "omitted", reason="invalid:dcf_at_search_bounds", components=market_meta, currency=currency)
    if market_cap < low or market_cap > high:
        return _model("reverse_dcf", "partial", value=lo if market_cap < low else hi, reason="market_cap_outside_explicit_search_range", components={**market_meta, "search_min_equity": low, "search_max_equity": high}, assumptions={**base, "search_min": lo, "search_max": hi}, currency=currency)
    left, right = lo, hi
    solved = (left + right) / 2.0
    calculated = None
    for _ in range(60):
        solved = (left + right) / 2.0
        calculated = equity(solved)
        if calculated is None:
            return _model("reverse_dcf", "omitted", reason="invalid:dcf_during_search", components=market_meta, currency=currency)
        if abs(calculated - market_cap) / max(abs(market_cap), 1.0) < 0.0001:
            break
        if calculated < market_cap:
            left = solved
        else:
            right = solved
    return _model("reverse_dcf", "computed", value=solved, components={**market_meta, "model_equity_value": calculated}, assumptions={**base, "search_min": lo, "search_max": hi}, currency=currency)


def _pe_models(
    canonical: Mapping[str, Any], *, endpoint: str | None, p1_disclosures: Mapping[str, Any], assumptions: Mapping[str, Any], market: Mapping[str, Any] | None, currency: str | None
) -> dict[str, dict[str, Any]]:
    ids = MODEL_GROUPS["private_equity"]
    if endpoint != "annual":
        return {model_id: _model(model_id, "omitted", reason="blocked_quality:pe_models_require_annual_base", currency=currency) for model_id in ids}
    strict_ebitda, ebitda_reason = _strict_ebitda(p1_disclosures)
    flows, flow_reason = _reported_flow_set(canonical, endpoint=endpoint, account_ids=("CFO", "CAPEX"))
    amounts = _amounts(canonical, endpoint)
    net_debt = (compute_ma_metrics(amounts).get("net_debt") or {}).get("value")
    fcf = None if flows is None else (_number(flows["CFO"].get("value")) - abs(_number(flows["CAPEX"].get("value")) or 0.0))
    common_reason = ebitda_reason or flow_reason or ("missing:verified_net_debt" if net_debt is None else None)
    if common_reason:
        delever = _model("delever_path", "omitted", reason=common_reason, currency=currency)
    else:
        retention, horizon = _number(assumptions.get("fcf_retention")), _number(assumptions.get("horizon_years"))
        if retention is None or horizon is None:
            delever = _model("delever_path", "needs_input", reason="input:fcf_retention_and_horizon_required", required_inputs=[key for key, value in (("fcf_retention", retention), ("horizon_years", horizon)) if value is None], currency=currency)
        elif not 0 <= retention <= 1 or int(horizon) != horizon or not 1 <= horizon <= 10:
            delever = _model("delever_path", "omitted", reason="invalid:fcf_retention_or_horizon", currency=currency)
        else:
            debt = float(net_debt)
            path = []
            for year in range(int(horizon) + 1):
                path.append({"year": year, "net_debt": debt, "net_debt_to_strict_ebitda": debt / strict_ebitda})
                debt -= fcf * retention
            delever = _model("delever_path", "computed", value={"start": path[0]["net_debt_to_strict_ebitda"], "end": path[-1]["net_debt_to_strict_ebitda"]}, components={"path": path, "strict_ebitda": strict_ebitda, "fcf": fcf}, assumptions={"fcf_retention": retention, "horizon_years": int(horizon)}, currency=currency)

    interest_flows, interest_reason = _reported_flow_set(canonical, endpoint=endpoint, account_ids=("INTEREST_EXPENSE",))
    if strict_ebitda is None or interest_flows is None:
        coverage = _model("coverage_capacity", "omitted", reason=ebitda_reason or interest_reason, currency=currency)
    else:
        interest = abs(_number(interest_flows["INTEREST_EXPENSE"].get("value")) or 0.0)
        coverage = _model("coverage_capacity", "omitted", reason="invalid:interest_expense_zero", currency=currency) if interest == 0 else _model("coverage_capacity", "computed", value=strict_ebitda / interest, components={"strict_ebitda": strict_ebitda, "interest_expense": interest}, currency=currency)

    market_cap, market_reason, market_meta = _market_cap(market, currency=currency)
    if fcf is None:
        yield_model = _model("fcf_yield_entry", "omitted", reason=flow_reason, currency=currency)
    elif market_cap is None:
        yield_model = _model("fcf_yield_entry", "needs_input" if market_reason.startswith("missing:") else "omitted", reason=market_reason, required_inputs=["market_cap"] if market_reason.startswith("missing:") else [], currency=currency)
    else:
        ev = None if net_debt is None else market_cap + net_debt
        yield_model = _model("fcf_yield_entry", "computed" if ev not in (None, 0) else "partial", value={"fcf_to_equity": fcf / market_cap, "fcf_to_ev": None if ev in (None, 0) else fcf / ev}, reason=None if ev not in (None, 0) else "missing:verified_net_debt_for_ev", components={**market_meta, "fcf": fcf, "enterprise_value": ev}, currency=currency)
    return {"delever_path": delever, "coverage_capacity": coverage, "fcf_yield_entry": yield_model}


def _ib_models(
    canonical: Mapping[str, Any], *, endpoint: str | None, assumptions: Mapping[str, Any], market: Mapping[str, Any] | None, inputs: Mapping[str, Any], currency: str | None
) -> dict[str, dict[str, Any]]:
    if endpoint != "annual":
        return {model_id: _model(model_id, "omitted", reason="blocked_quality:ib_models_require_annual_base", currency=currency) for model_id in MODEL_GROUPS["investment_banking"]}
    revenue = _fact(canonical, "REVENUE", endpoint)
    amounts = _amounts(canonical, endpoint)
    net_debt = (compute_ma_metrics(amounts).get("net_debt") or {}).get("value")
    dcf_keys = ("projection_years", "revenue_cagr", "ebit_margin", "tax_rate", "operating_nwc_to_sales", "capex_to_sales", "da_to_sales", "wacc", "terminal_growth")
    missing = [key for key in dcf_keys if _number(assumptions.get(key)) is None]
    if _usable_flow(revenue):
        dcf = _model("fcff_dcf", "omitted", reason="missing:reported_annual_revenue", currency=currency)
    elif missing:
        dcf = _model("fcff_dcf", "needs_input", reason="input:explicit_dcf_assumptions_required", required_inputs=missing, currency=currency)
    elif net_debt is None:
        dcf = _model("fcff_dcf", "omitted", reason="missing:verified_net_debt", currency=currency)
    else:
        result = fcff_dcf(revenue0=float(revenue["value"]), assumptions={**{key: assumptions[key] for key in dcf_keys}, "net_debt": net_debt})
        dcf = _model("fcff_dcf", "computed" if result.get("ok") else "omitted", value={"enterprise_value": result.get("enterprise_value"), "equity_value": result.get("equity_value")}, reason=result.get("reason"), components={"free_cash_flow": result.get("free_cash_flow"), "terminal_value": result.get("terminal_value")}, assumptions={key: assumptions[key] for key in dcf_keys}, currency=currency)

    peers = inputs.get("verified_peer_multiples") or []
    valid: list[dict[str, Any]] = []
    for peer in peers:
        if not isinstance(peer, Mapping) or not peer.get("source") or not peer.get("as_of"):
            continue
        values = {key: _number(peer.get(key)) for key in ("pe", "ev_ebitda")}
        if any(value is not None and value > 0 for value in values.values()):
            valid.append({"id": peer.get("id"), "source": peer.get("source"), "as_of": peer.get("as_of"), **values})
    if not valid:
        comps = _model("trading_comps", "omitted", reason="missing:verified_peer_multiples", currency=currency)
    else:
        comps = _model("trading_comps", "computed", value={key: median([row[key] for row in valid if row.get(key) is not None]) if any(row.get(key) is not None for row in valid) else None for key in ("pe", "ev_ebitda")}, components={"observations": valid}, currency=currency)

    market_cap, market_reason, market_meta = _market_cap(market, currency=currency)
    segments = inputs.get("verified_segments") or []
    valid_segments = [segment for segment in segments if isinstance(segment, Mapping) and _number(segment.get("enterprise_value")) is not None and str(segment.get("currency") or "").upper() == str(currency or "").upper() and segment.get("source") and segment.get("as_of")]
    if valid_segments:
        gross_ev = sum(_number(segment.get("enterprise_value")) or 0.0 for segment in valid_segments)
        bridge = _model("sotp_or_ev_bridge", "computed" if net_debt is not None else "partial", value={"gross_segment_ev": gross_ev, "equity_value": None if net_debt is None else gross_ev - net_debt}, reason=None if net_debt is not None else "missing:verified_net_debt", components={"segments": [dict(item) for item in valid_segments]}, currency=currency)
    elif market_cap is not None and net_debt is not None:
        bridge = _model("sotp_or_ev_bridge", "computed", value={"market_cap": market_cap, "net_debt": net_debt, "enterprise_value": market_cap + net_debt}, components=market_meta, currency=currency)
    else:
        bridge = _model("sotp_or_ev_bridge", "needs_input" if market_reason and market_reason.startswith("missing:") else "omitted", reason="missing:verified_segments_or_market_cap_and_net_debt", required_inputs=["verified_segments_or_market_cap"] if market_reason and market_reason.startswith("missing:") else [], currency=currency)
    return {"fcff_dcf": dcf, "trading_comps": comps, "sotp_or_ev_bridge": bridge}


def build_p1_models(
    canonical: Mapping[str, Any],
    *,
    p1_disclosures: Mapping[str, Any],
    entity_policy: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build role-based models without mutating P0/P1 reported facts."""
    if canonical.get("schema_version") != "canonical-financial-facts/1":
        raise ValueError("unsupported_canonical_schema")
    inputs = dict(inputs or {})
    currency = canonical.get("currency")
    if is_financial(dict(entity_policy or {})):
        models = {
            model_id: _model(model_id, "not_applicable", reason="not_applicable:financial_entity_industrial_model", currency=currency)
            for ids in MODEL_GROUPS.values() for model_id in ids
        }
    else:
        endpoint = _endpoint(p1_disclosures)
        assumptions = dict(inputs.get("assumptions") or {})
        market = inputs.get("market") if isinstance(inputs.get("market"), Mapping) else {}
        models = {
            **_oe_models(canonical, endpoint=endpoint, assumptions=assumptions, market=market, currency=currency),
            **_pe_models(canonical, endpoint=endpoint, p1_disclosures=p1_disclosures, assumptions=assumptions, market=market, currency=currency),
            **_ib_models(canonical, endpoint=endpoint, assumptions=assumptions, market=market, inputs=inputs, currency=currency),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "p1_role_models",
        "calculation_currency": currency,
        "policy": {
            "ebitda": "PE EBITDA models require P1 strict EBITDA; combined D&A proxy is prohibited",
            "market": "market inputs require source, as_of, and calculation-currency match",
            "valuation": "DCF and reverse DCF require explicit assumptions; no automatic target price",
            "recommendation": "not_provided",
        },
        "groups": {key: list(value) for key, value in MODEL_GROUPS.items()},
        "models": models,
    }
