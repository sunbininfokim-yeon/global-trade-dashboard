"""Derived practitioner cards and a UI-snapshot adapter for the KFA engine.

The module consumes a normalised ``accounting_pack``.  It does not scrape,
guess a peer group, or infer missing D&A / interest expense.  Missing inputs
remain null with an explicit reason so the UI can distinguish unavailable data
from a calculated zero.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .model_contracts import (
    owner_earnings_from_inputs,
    run_deal_models,
    run_investor_models,
)
from .pe_models import run_pe_models


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _metric(pack: dict[str, Any], section: str, key: str) -> dict[str, Any]:
    value = pack.get(section, {}).get(key, {})
    return value if isinstance(value, dict) else {"value": value}


def _value(metric: dict[str, Any]) -> float | None:
    return _number(metric.get("value"))


def _cell(
    value: Any,
    *,
    series: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"value": value, "series": series or [], "reason": reason}
    result.update({key: val for key, val in extra.items() if val is not None})
    return result


def _series(metric: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in metric.get("series") or []:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        end = item.get("end")
        value = _number(item.get("value"))
        if isinstance(year, int) and isinstance(end, str) and value is not None:
            rows.append({"year": year, "end": end, "value": value})
    return sorted(rows, key=lambda row: (row["year"], row["end"]))


def _series_map(metric: dict[str, Any]) -> dict[int, dict[str, Any]]:
    # A duplicated year with two different ends is ambiguous (e.g. annual + Q4).
    # The newest date is not silently chosen; it is excluded by aligned helpers.
    rows: dict[int, dict[str, Any]] = {}
    duplicates: set[int] = set()
    for row in _series(metric):
        if row["year"] in rows and rows[row["year"]]["end"] != row["end"]:
            duplicates.add(row["year"])
        rows[row["year"]] = row
    return {year: row for year, row in rows.items() if year not in duplicates}


def _aligned_ratio_series(
    numerator: dict[str, Any],
    denominator: dict[str, Any],
    *,
    numerator_abs: bool = False,
    denominator_abs: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    left, right = _series_map(numerator), _series_map(denominator)
    if not left or not right:
        return [], "missing:aligned_series"
    output: list[dict[str, Any]] = []
    mismatched = False
    for year in sorted(set(left) & set(right)):
        a, b = left[year], right[year]
        if a["end"] != b["end"]:
            mismatched = True
            continue
        numerator_value = abs(a["value"]) if numerator_abs else a["value"]
        denominator_value = abs(b["value"]) if denominator_abs else b["value"]
        if denominator_value == 0:
            continue
        output.append({"year": year, "end": a["end"], "value": numerator_value / denominator_value})
    if not output:
        return [], "period_mismatch_or_zero_denominator"
    return output, "period_mismatch_rows_excluded" if mismatched else None


def _latest(series: list[dict[str, Any]]) -> float | None:
    return _number(series[-1]["value"]) if series else None


def _historical_cagr(metric: dict[str, Any]) -> tuple[float | None, str | None]:
    rows = _series(metric)
    if len(rows) < 2:
        return None, "missing:two_reported_revenue_periods"
    start, end = rows[0], rows[-1]
    if start["value"] <= 0 or end["value"] <= 0 or end["year"] <= start["year"]:
        return None, "invalid:revenue_history_for_cagr"
    periods = end["year"] - start["year"]
    return (end["value"] / start["value"]) ** (1.0 / periods) - 1.0, None


def _maintenance_capex(
    net_income: dict[str, Any], da: dict[str, Any], capex: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current = owner_earnings_from_inputs(_value(net_income), _value(da), _value(capex))
    ni_rows, da_rows, capex_rows = _series_map(net_income), _series_map(da), _series_map(capex)
    series: list[dict[str, Any]] = []
    for year in sorted(set(ni_rows) & set(da_rows) & set(capex_rows)):
        ni, da_row, capex_row = ni_rows[year], da_rows[year], capex_rows[year]
        if ni["end"] != da_row["end"] or ni["end"] != capex_row["end"]:
            continue
        value = owner_earnings_from_inputs(ni["value"], da_row["value"], capex_row["value"])
        if value["value"] is not None:
            series.append({"year": year, "end": ni["end"], "value": value["value"]})
    return current, series


def _ebitda_or_op(ebitda: dict[str, Any], operating_income: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    if _value(ebitda) is not None:
        return ebitda, ebitda.get("reason")
    if _value(operating_income) is not None:
        proxy = deepcopy(operating_income)
        proxy["reason"] = "proxy:operating_income_used_because_ebitda_unavailable"
        return proxy, proxy["reason"]
    return {"value": None, "series": []}, "missing:ebitda_and_operating_income"


def _format_margins(series: list[dict[str, Any]]) -> str:
    return " → ".join(f"{row['year']} {row['value'] * 100:.1f}%" for row in series)


def _nwc_change_to_sales_series(
    nwc: dict[str, Any], revenue: dict[str, Any]
) -> tuple[list[dict[str, Any]], str | None]:
    nwc_rows, revenue_rows = _series_map(nwc), _series_map(revenue)
    output: list[dict[str, Any]] = []
    common = sorted(set(nwc_rows) & set(revenue_rows))
    for prior_year, year in zip(common, common[1:]):
        prior, current, sales = nwc_rows[prior_year], nwc_rows[year], revenue_rows[year]
        if current["end"] != sales["end"] or sales["value"] == 0:
            continue
        output.append(
            {
                "year": year,
                "end": current["end"],
                "value": (current["value"] - prior["value"]) / sales["value"],
            }
        )
    if output:
        return output, None
    return [], "missing:aligned_two_year_nwc_and_revenue"


def _tax_rate(pack: dict[str, Any]) -> tuple[float | None, str | None]:
    effective = _metric(pack, "pnl", "effective_tax_rate")
    if _value(effective) is not None:
        return _value(effective), effective.get("reason")
    tax = _value(_metric(pack, "pnl", "income_tax_expense"))
    pbt = _value(_metric(pack, "pnl", "profit_before_tax"))
    if tax is None or pbt is None or pbt <= 0:
        return None, "missing:effective_tax_rate_or_positive_pbt_and_tax_expense"
    return abs(tax) / pbt, "derived:abs(income_tax_expense)/profit_before_tax"


def derive_interest_coverage(pack: dict[str, Any]) -> dict[str, Any]:
    """Return EBIT / abs(interest expense), only where the fiscal ends match."""
    existing = _metric(pack, "liquidity", "interest_coverage")
    if _value(existing) is not None:
        return _cell(_value(existing), series=_series(existing), reason=existing.get("reason"))
    operating_income = _metric(pack, "pnl", "operating_income")
    interest_expense = _metric(pack, "pnl", "interest_expense")
    series, series_reason = _aligned_ratio_series(
        operating_income, interest_expense, denominator_abs=True
    )
    current_op = _value(operating_income)
    current_interest = _value(interest_expense)
    if current_op is None or current_interest in (None, 0):
        missing = "missing:operating_income_or_nonzero_interest_expense"
        return _cell(None, series=series, reason=missing)
    return _cell(
        current_op / abs(current_interest),
        series=series,
        reason=series_reason if not series else None,
        definition="operating_income / abs(interest_expense)",
    )


def _nwc_to_sales(pack: dict[str, Any], revenue: dict[str, Any]) -> tuple[float | None, str | None]:
    direct = _metric(pack, "working_capital", "nwc_to_sales")
    if _value(direct) is not None:
        return _value(direct), direct.get("reason")
    nwc = _value(_metric(pack, "working_capital", "net_working_capital"))
    sales = _value(revenue)
    if nwc is None or sales is None or sales == 0:
        return None, "missing:net_working_capital_or_revenue"
    return nwc / sales, "derived:net_working_capital/revenue"


def _text_multiples(
    market_cap: float | None, net_debt: float | None, revenue: float | None,
    ebitda: float | None, net_income: float | None,
) -> tuple[str | None, str | None]:
    if market_cap is None or market_cap <= 0:
        return None, "missing:positive_market_cap"
    bits: list[str] = []
    if net_income is not None and net_income > 0:
        bits.append(f"P/E {market_cap / net_income:.2f}x")
    if revenue is not None and revenue > 0:
        bits.append(f"P/S {market_cap / revenue:.2f}x")
    if net_debt is not None and ebitda is not None and ebitda > 0:
        bits.append(f"EV/EBITDA {(market_cap + net_debt) / ebitda:.2f}x")
    if not bits:
        return None, "missing:income_statement_inputs_for_multiples"
    return " · ".join(bits), None


def build_expert_cards(
    pack: dict[str, Any], market: dict[str, Any] | None = None, segments: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return the 16 non-Basic cards plus the traceable input bag for models."""
    market = market or {}
    segments = segments or []
    revenue = _metric(pack, "pnl", "revenue")
    operating_income = _metric(pack, "pnl", "operating_income")
    ebitda = _metric(pack, "pnl", "ebitda")
    net_income = _metric(pack, "pnl", "net_income")
    cfo = _metric(pack, "cash_flow", "cfo")
    capex = _metric(pack, "cash_flow", "capex")
    da = _metric(pack, "cash_flow", "depreciation_and_amortization")
    fcf = _metric(pack, "cash_flow", "fcf")
    net_debt = _metric(pack, "debt_structure", "net_debt")
    interest_coverage = _metric(pack, "liquidity", "interest_coverage")
    nwc = _metric(pack, "working_capital", "net_working_capital")

    interest_coverage = derive_interest_coverage(pack)
    owner, owner_series = _maintenance_capex(net_income, da, capex)
    quality_series, quality_reason = _aligned_ratio_series(cfo, net_income)
    margin_series, margin_reason = _aligned_ratio_series(operating_income, revenue)
    capex_da_series, capex_da_reason = _aligned_ratio_series(
        capex, da, numerator_abs=True, denominator_abs=True
    )
    owner_cell = _cell(owner["value"], series=owner_series, reason=owner["reason"])

    ebitda_proxy, ebitda_reason = _ebitda_or_op(ebitda, operating_income)
    nd_ebitda_series, nd_ebitda_series_reason = _aligned_ratio_series(net_debt, ebitda_proxy)
    fcf_ebitda_series, fcf_ebitda_series_reason = _aligned_ratio_series(fcf, ebitda_proxy)
    maintenance = _number(owner.get("maintenance_capex"))
    maint_capex_series, maint_capex_reason = _aligned_ratio_series(
        {"series": [{**row, "value": None} for row in []]}, revenue
    )
    # Build the maintenance-capex burden explicitly: OE series does not reveal
    # the maintenance component, and each period must retain the same end date.
    capex_rows, da_rows, revenue_rows = _series_map(capex), _series_map(da), _series_map(revenue)
    maint_capex_series = []
    for year in sorted(set(capex_rows) & set(da_rows) & set(revenue_rows)):
        c, d, r = capex_rows[year], da_rows[year], revenue_rows[year]
        if c["end"] == d["end"] == r["end"] and r["value"] != 0:
            maint_capex_series.append(
                {"year": year, "end": r["end"], "value": min(abs(c["value"]), abs(d["value"])) / r["value"]}
            )
    if not maint_capex_series:
        maint_capex_reason = "missing:aligned_depreciation_capex_and_revenue"
    else:
        maint_capex_reason = "proxy:maintenance_capex=min(abs(D&A),abs(capex))"

    nwc_change_series, nwc_change_reason = _nwc_change_to_sales_series(nwc, revenue)
    nwc_sales_series, nwc_sales_reason = _aligned_ratio_series(nwc, revenue)
    nwc_sales_value, nwc_sales_value_reason = _nwc_to_sales(pack, revenue)

    current_net_debt = _value(net_debt)
    current_ebitda = _value(ebitda_proxy)
    current_fcf = _value(fcf)
    current_revenue = _value(revenue)
    current_ni = _value(net_income)
    current_cfo = _value(cfo)
    current_op = _value(operating_income)
    current_capex = _value(capex)
    current_da = _value(da)
    market_cap = _number(market.get("market_cap"))

    capex_da_value = None
    if current_capex is not None and current_da is not None and current_da != 0:
        capex_da_value = abs(current_capex) / abs(current_da)
    nd_ebitda_value = None if current_net_debt is None or current_ebitda in (None, 0) else current_net_debt / current_ebitda
    fcf_ebitda_value = None if current_fcf is None or current_ebitda in (None, 0) else current_fcf / current_ebitda
    maint_capex_value = None if maintenance is None or current_revenue in (None, 0) else maintenance / current_revenue
    nd_oe_value = None if current_net_debt is None or owner["value"] in (None, 0) else current_net_debt / owner["value"]

    quality_bits: list[str] = []
    if current_cfo is not None and current_ni not in (None, 0):
        quality_bits.append(f"CFO/순이익 {current_cfo / current_ni:.2f}x")
    if current_fcf is not None and current_ni not in (None, 0):
        quality_bits.append(f"FCF/순이익 {current_fcf / current_ni:.2f}x")
    qoe_value = "; ".join(quality_bits) if quality_bits else None
    qoe_reason = None if qoe_value else "missing:cfo_fcf_or_net_income"
    if qoe_value:
        qoe_reason = "limited_to_cash_conversion; one_off_items_and_note_reconciliations_unmapped"

    multiples, multiples_reason = _text_multiples(
        market_cap, current_net_debt, current_revenue, current_ebitda, current_ni
    )
    bridge_value = None
    bridge_reason = None
    if market_cap is None:
        bridge_reason = "missing:market_cap"
    elif current_net_debt is None:
        bridge_reason = "missing:net_debt"
    else:
        bridge_value = f"시가총액 {market_cap:.0f} + 순부채 {current_net_debt:.0f} = EV {market_cap + current_net_debt:.0f}"

    segment_names = [str(segment.get("name") or segment.get("id")) for segment in segments if segment.get("name") or segment.get("id")]
    segment_value = " · ".join(segment_names) if segment_names else None

    cards = {
        "owner_earnings": owner_cell,
        "earnings_quality": _cell(_latest(quality_series), series=quality_series, reason=quality_reason),
        "margins_trend": _cell(
            _format_margins(margin_series) if margin_series else None,
            series=margin_series,
            reason=margin_reason,
        ),
        "capex_to_da": _cell(capex_da_value, series=capex_da_series, reason=capex_da_reason),
        "net_debt_to_oe": _cell(nd_oe_value, series=[], reason=None if nd_oe_value is not None else "missing:net_debt_or_owner_earnings"),
        "ebitda_or_op": _cell(_value(ebitda_proxy), series=_series(ebitda_proxy), reason=ebitda_reason),
        "net_debt_to_ebitda": _cell(
            nd_ebitda_value,
            series=nd_ebitda_series,
            reason=ebitda_reason or (nd_ebitda_series_reason if nd_ebitda_value is None else None),
        ),
        "fcf_to_ebitda": _cell(
            fcf_ebitda_value,
            series=fcf_ebitda_series,
            reason=ebitda_reason or (fcf_ebitda_series_reason if fcf_ebitda_value is None else None),
        ),
        "maint_capex_burden": _cell(maint_capex_value, series=maint_capex_series, reason=maint_capex_reason),
        "nwc_change_to_sales": _cell(_latest(nwc_change_series), series=nwc_change_series, reason=nwc_change_reason),
        "ebitda": _cell(_value(ebitda_proxy), series=_series(ebitda_proxy), reason=ebitda_reason),
        "trading_multiples": _cell(multiples, reason=multiples_reason),
        "ev_bridge": _cell(bridge_value, reason=bridge_reason),
        "qoe_flags": _cell(qoe_value, reason=qoe_reason),
        "segment": _cell(segment_value, reason=None if segment_value else "missing:segment_disclosure"),
        "nwc_to_sales": _cell(
            nwc_sales_value,
            series=nwc_sales_series,
            reason=nwc_sales_value_reason or nwc_sales_reason,
        ),
    }
    revenue_cagr, revenue_cagr_reason = _historical_cagr(revenue)
    operating_margin = None if current_revenue in (None, 0) or current_op is None else current_op / current_revenue
    tax_rate, tax_rate_reason = _tax_rate(pack)
    capex_to_sales = None if current_capex is None or current_revenue in (None, 0) else abs(current_capex) / current_revenue
    da_to_sales = None if current_da is None or current_revenue in (None, 0) else abs(current_da) / current_revenue
    inputs = {
        "revenue": current_revenue,
        "net_income": current_ni,
        "ebitda": current_ebitda,
        "net_debt": current_net_debt,
        "fcf": current_fcf,
        "interest_coverage": _value(interest_coverage),
        "owner_earnings": owner["value"],
        "revenue_cagr": revenue_cagr,
        "revenue_cagr_reason": revenue_cagr_reason,
        "operating_margin": operating_margin,
        "tax_rate": tax_rate,
        "tax_rate_reason": tax_rate_reason,
        "capex_to_sales": capex_to_sales,
        "da_to_sales": da_to_sales,
        "nwc_to_sales": nwc_sales_value,
        "explicit_years": 5,
    }
    return cards, inputs


def run_kfa_analysis(
    pack: dict[str, Any], market: dict[str, Any] | None = None, segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One entry point for non-Basic cards and all nine model contracts."""
    market = market or {}
    cards, inputs = build_expert_cards(pack, market, segments)
    pe_pack = deepcopy(pack)
    pe_pack.setdefault("liquidity", {})["interest_coverage"] = derive_interest_coverage(pack)
    # The PE runner consumes the same normalised pack.  It deliberately uses
    # EBIT only as a marked proxy where reported EBITDA is absent.
    pe = run_pe_models(pe_pack, market).get("models", {})
    return {
        "cards": cards,
        "basic_updates": {"interest_coverage": derive_interest_coverage(pack)},
        "inputs": inputs,
        "models": {
            "investor": run_investor_models(inputs, market),
            "pe": pe,
            "deal": run_deal_models(inputs, market, segments),
        },
    }


def basic_cards_from_pack(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the flat UI `basic_cards` bag directly from an accounting_pack.

    This is the mirror of accounting_pack_from_snapshot (legacy snapshot ->
    pack): here a freshly-fetched pack (e.g. dart_facts.fetch_accounting_pack_kr)
    goes the other way, into the card bag the UI actually renders. A pack built
    from a single OpenDART fetch has one-point series and no prior period, so
    yoy is always None and CAGR/quality-trend expert cards resolve to
    null + reason downstream in run_kfa_analysis -- that is correct behaviour
    for one fiscal year, not a bug to work around here.
    """
    def card(section: str, key: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        metric = _metric(pack, section, key)
        out: dict[str, Any] = {"value": _value(metric), "series": _series(metric)}
        if extra:
            out.update(extra)
        if metric.get("reason"):
            out["reason"] = metric["reason"]
        return out

    rev_v = _value(_metric(pack, "pnl", "revenue"))
    op_v = _value(_metric(pack, "pnl", "operating_income"))
    ni_v = _value(_metric(pack, "pnl", "net_income"))

    revenue = card("pnl", "revenue", {"yoy": None})
    operating_income = card("pnl", "operating_income", {
        "margin": (op_v / rev_v) if op_v is not None and rev_v not in (None, 0) else None,
    })
    net_income = card("pnl", "net_income", {
        "margin": (ni_v / rev_v) if ni_v is not None and rev_v not in (None, 0) else None,
    })

    cfo_metric = _metric(pack, "cash_flow", "cfo")
    cfo_v = _value(cfo_metric)
    capex_v = _value(_metric(pack, "cash_flow", "capex"))
    cfo_rows = _series(cfo_metric)
    fcf_value = None if cfo_v is None or capex_v is None else cfo_v - abs(capex_v)
    fcf_series = [{**cfo_rows[-1], "value": fcf_value}] if fcf_value is not None and cfo_rows else []
    fcf = {"value": fcf_value, "definition": "cfo - abs(capex)", "series": fcf_series}
    if fcf_value is None:
        fcf["reason"] = "missing:cfo_or_capex"

    ccc_days = card("working_capital", "ccc_days")
    if ccc_days["value"] is None and not ccc_days.get("reason"):
        ccc_days["reason"] = "missing:dso_dio_dpo_inputs_not_fetched"

    return {
        "revenue": revenue,
        "operating_income": operating_income,
        "net_income": net_income,
        "cfo": card("cash_flow", "cfo"),
        "fcf": fcf,
        "cash": card("liquidity", "cash_and_equivalents"),
        "net_debt": card("debt_structure", "net_debt", {
            "definition": pack.get("debt_structure", {}).get("net_debt", {}).get("definition"),
        }),
        "current_ratio": card("liquidity", "current_ratio"),
        "debt_due_within_1y": deepcopy(pack.get("liquidity", {}).get("debt_due_within_1y", {})),
        "liquidity_coverage_1y": deepcopy(pack.get("liquidity", {}).get("liquidity_coverage_1y", {})),
        "interest_coverage": derive_interest_coverage(pack),
        "ccc_days": ccc_days,
    }


def accounting_pack_from_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt the legacy UI sample shape to the normalised calculation input.

    This is intentionally lossy: it can derive Capex from CFO−FCF only where
    the legacy sample itself declares that FCF definition.  It cannot recover
    D&A, taxes, interest expense, NWC or segment data absent from the sample.
    """
    cards = payload.get("basic_cards") or {}

    def card(name: str) -> dict[str, Any]:
        source = cards.get(name) or {}
        return {"value": source.get("value"), "series": deepcopy(source.get("series") or []), "reason": source.get("reason")}

    cfo, fcf = card("cfo"), card("fcf")
    cfo_rows, fcf_rows = _series_map(cfo), _series_map(fcf)
    capex_rows: list[dict[str, Any]] = []
    for year in sorted(set(cfo_rows) & set(fcf_rows)):
        c, f = cfo_rows[year], fcf_rows[year]
        if c["end"] == f["end"]:
            capex_rows.append({"year": year, "end": c["end"], "value": abs(c["value"] - f["value"])})
    capex_value = None
    if _value(cfo) is not None and _value(fcf) is not None:
        capex_value = abs(_value(cfo) - _value(fcf))

    interest = card("interest_coverage")
    if _value(interest) is None and not interest.get("reason"):
        interest["reason"] = "missing:interest_expense_unmapped_from_snapshot"
    pack = {
        "as_of": payload.get("as_of"),
        "currency": payload.get("currency"),
        "pnl": {
            "revenue": card("revenue"),
            "operating_income": card("operating_income"),
            "ebitda": {"value": None, "series": [], "reason": "missing:depreciation_and_amortization"},
            "net_income": card("net_income"),
            "profit_before_tax": {"value": None, "series": []},
            "income_tax_expense": {"value": None, "series": []},
            "effective_tax_rate": {"value": None, "series": []},
        },
        "cash_flow": {
            "cfo": cfo,
            "fcf": fcf,
            "capex": {
                "value": capex_value,
                "abs_value": capex_value,
                "series": capex_rows,
                "reason": "derived:cfo_minus_fcf_from_snapshot",
            },
            "depreciation_and_amortization": {
                "value": None,
                "series": [],
                "reason": "missing:source_snapshot_has_no_D&A",
            },
        },
        "liquidity": {
            "cash_and_equivalents": card("cash"),
            "current_ratio": card("current_ratio"),
            "debt_due_within_1y": card("debt_due_within_1y"),
            "liquidity_coverage_1y": card("liquidity_coverage_1y"),
            "interest_coverage": interest,
        },
        "debt_structure": {"net_debt": card("net_debt")},
        "working_capital": {
            "ccc_days": card("ccc_days"),
            "net_working_capital": {"value": None, "series": [], "reason": "missing:source_snapshot_has_no_NWC"},
            "nwc_to_sales": {"value": None, "series": [], "reason": "missing:source_snapshot_has_no_NWC"},
        },
    }
    return pack


def enrich_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Add cards/models to a deployed KFA snapshot without changing UI code."""
    output = deepcopy(payload)
    pack = accounting_pack_from_snapshot(output)
    analysis = run_kfa_analysis(pack, output.get("market") or {}, output.get("segments") or [])
    output.setdefault("basic_cards", {}).update(analysis["cards"])
    derived_interest = analysis["basic_updates"]["interest_coverage"]
    existing_interest_reason = pack.get("liquidity", {}).get("interest_coverage", {}).get("reason")
    if derived_interest.get("value") is None and existing_interest_reason:
        derived_interest["reason"] = existing_interest_reason
    output["basic_cards"]["interest_coverage"] = derived_interest

    revenue_rows = _series(output["basic_cards"].get("revenue") or {})
    fiscal_end = revenue_rows[-1]["end"] if revenue_rows else None
    original_as_of = output.get("as_of")
    previous_correction = (output.get("data_quality") or {}).get("as_of_corrected_from")
    corrected_from = previous_correction
    if fiscal_end and original_as_of != fiscal_end:
        output["as_of"] = fiscal_end
        if corrected_from is None:
            corrected_from = original_as_of
    # Keeping the normalised input beside the derived output makes this fixture
    # reproducible and lets a later run use full reported facts when supplied.
    # Do not claim the adapter reconstructed facts the old sample never carried.
    pack["as_of"] = output.get("as_of")
    output["accounting_pack"] = pack
    output["investor"] = {"models": analysis["models"]["investor"]}
    output["pe"] = {"models": analysis["models"]["pe"]}
    output["deal"] = {"models": analysis["models"]["deal"]}
    output["data_quality"] = {
        "input_kind": "snapshot_derived",
        "source_claim": (output.get("meta") or {}).get("source"),
        "raw_filing_facts_embedded": False,
        "period_alignment": "fiscal_end_normalized_from_revenue_series" if fiscal_end else "unverified_no_revenue_series",
        "as_of_corrected_from": corrected_from,
        "as_of_fiscal_end": fiscal_end,
    }
    return output
