"""P1 deterministic disclosure calculations built on canonical filing facts.

This module is deliberately narrow.  It does not fetch filings, scrape note
prose, infer an amortisation charge from cash flow, or produce a valuation.
It accepts only P0 canonical facts plus *structured, reported* disclosure
rows.  Every result is JSON serialisable and carries the input fact(s) used
to produce it, so a later adapter can expose it without reimplementing
accounting policy.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "kfa-p1-disclosures/1"
LATEST_ENDPOINT_PRIORITY = ("Q3", "Q2", "Q1", "annual")
_QUARTER_BY_ENDPOINT = {"Q1": "Q1", "Q2": "Q2", "Q3": "Q3", "annual": None}
_ENDPOINT_ALIASES = {"H1": "Q2", "FY": "annual"}
_EBITDA_INPUTS = ("OPERATING_INCOME", "PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION")


class P1DisclosureError(ValueError):
    """Raised when a caller supplies a malformed P0/P1 boundary object."""


def _number(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _unavailable(reason: str, *, provenance: Mapping[str, Any] | None = None, unit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "value": None,
        "reason": reason,
        "unit": dict(unit) if unit else None,
        "provenance": deepcopy(dict(provenance or {})),
    }


def _reported_fact(canonical: Mapping[str, Any], account_id: str, endpoint: str) -> dict[str, Any] | None:
    series = (canonical.get("series") or {}).get(account_id)
    if not isinstance(series, Mapping):
        return None
    raw = series.get("annual") if endpoint == "annual" else (series.get("quarters") or {}).get(endpoint)
    return deepcopy(dict(raw)) if isinstance(raw, Mapping) else None


def _fact_reference(fact: Mapping[str, Any] | None, account_id: str) -> dict[str, Any]:
    if not fact:
        return {"account_id": account_id, "status": "missing", "reason": f"missing:account:{account_id}"}
    return {
        "account_id": account_id,
        "value": fact.get("value"),
        "availability": fact.get("availability"),
        "quality": fact.get("quality"),
        "reason": fact.get("reason"),
        "source": fact.get("source"),
        "source_concept": fact.get("source_concept"),
        "statement": fact.get("statement"),
        "nature": fact.get("nature"),
        "fiscal_year": fact.get("fiscal_year"),
        "fiscal_quarter": fact.get("fiscal_quarter"),
        "period_kind": fact.get("period_kind"),
        "period_start": fact.get("period_start"),
        "period_end": fact.get("period_end"),
        "report_code": fact.get("report_code"),
        "report_type": fact.get("report_type"),
        "fs_div": fact.get("fs_div"),
        "unit": deepcopy(dict(fact.get("unit") or {})),
        "provenance": deepcopy(dict(fact.get("provenance") or {})),
    }


def _period_descriptor(facts: Iterable[Mapping[str, Any] | None], endpoint: str) -> dict[str, Any]:
    materialized = [fact for fact in facts if isinstance(fact, Mapping)]
    first = next((fact for fact in materialized if fact.get("availability") == "available"), None)
    first = first or next(iter(materialized), None)
    if not first:
        return {
            "endpoint": endpoint,
            "fiscal_year": None,
            "fiscal_quarter": _QUARTER_BY_ENDPOINT[endpoint],
            "period_start": None,
            "period_end": None,
            "report_code": None,
            "report_type": None,
            "fs_div": None,
            "reason": "missing:reported_endpoint",
        }
    provenance = first.get("provenance") or {}
    report_ids: list[Any] = []
    if provenance.get("filing_id") is not None:
        report_ids.append(provenance.get("filing_id"))
    for source_fact in provenance.get("source_facts") or []:
        if isinstance(source_fact, Mapping) and source_fact.get("filing_id") is not None:
            report_ids.append(source_fact.get("filing_id"))
    report_ids = list(dict.fromkeys(report_ids))
    return {
        "endpoint": endpoint,
        "fiscal_year": first.get("fiscal_year"),
        "fiscal_quarter": first.get("fiscal_quarter"),
        "period_start": first.get("period_start"),
        "period_end": first.get("period_end"),
        "report_code": first.get("report_code"),
        "report_type": first.get("report_type"),
        "report_id": report_ids[0] if len(report_ids) == 1 else None,
        "report_ids": report_ids,
        "fs_div": first.get("fs_div"),
        "reason": None,
    }


def _flow_signature(fact: Mapping[str, Any]) -> tuple[Any, ...]:
    unit = fact.get("unit") or {}
    return (
        fact.get("fiscal_year"), fact.get("fiscal_quarter"), fact.get("period_kind"),
        fact.get("period_start"), fact.get("period_end"), fact.get("fs_div"),
        unit.get("kind"), unit.get("currency"), unit.get("scale"),
    )


def _usable_flow_fact(fact: Mapping[str, Any] | None) -> str | None:
    if not fact:
        return "missing:account"
    if fact.get("availability") != "available" or _number(fact.get("value")) is None:
        return str(fact.get("reason") or "missing:reported_fact")
    if fact.get("nature") != "flow":
        return "incompatible:nature_not_flow"
    if fact.get("quality") not in {"reported", "deterministic_derived"}:
        return f"incompatible:fact_quality:{fact.get('quality')}"
    return None


def compute_strict_ebitda(canonical: Mapping[str, Any], *, endpoint: str) -> dict[str, Any]:
    """Return only operating income + PPE depreciation + intangible amortisation.

    A combined D&A account, CFO, operating-income proxy, and any estimated
    value are intentionally not accepted.  Canonical interim facts may be
    deterministic YTD-to-quarter derivations, provided every input has the
    identical discrete flow signature.
    """
    if endpoint not in _QUARTER_BY_ENDPOINT:
        raise P1DisclosureError("unsupported_endpoint")
    facts = {account: _reported_fact(canonical, account, endpoint) for account in _EBITDA_INPUTS}
    provenance = {"formula": "OPERATING_INCOME + PPE_DEPRECIATION + INTANGIBLE_AMORTIZATION", "input_facts": {
        account: _fact_reference(fact, account) for account, fact in facts.items()
    }}
    failures = [(account, _usable_flow_fact(fact)) for account, fact in facts.items()]
    missing = [f"{account}:{reason}" for account, reason in failures if reason]
    if missing:
        return _unavailable("missing_or_incompatible:strict_ebitda_inputs:" + ";".join(missing), provenance=provenance)
    signatures = {_flow_signature(fact) for fact in facts.values() if fact}
    if len(signatures) != 1:
        return _unavailable("incompatible:strict_ebitda_period_scope_currency_or_unit", provenance=provenance)
    values = [_number(facts[account].get("value")) for account in _EBITDA_INPUTS]
    total = sum((value for value in values if value is not None), Decimal(0))
    first = facts[_EBITDA_INPUTS[0]]
    return {
        "status": "derived_deterministic",
        "value": _json_number(total),
        "reason": None,
        "unit": deepcopy(dict(first.get("unit") or {})),
        "period": _period_descriptor(facts.values(), endpoint),
        "provenance": provenance,
    }


def compute_receivables_to_sales(canonical: Mapping[str, Any], *, endpoint: str) -> dict[str, Any]:
    """Compute reported receivables / reported sales only at one endpoint."""
    if endpoint not in _QUARTER_BY_ENDPOINT:
        raise P1DisclosureError("unsupported_endpoint")
    receivables = _reported_fact(canonical, "TRADE_RECEIVABLES", endpoint)
    revenue = _reported_fact(canonical, "REVENUE", endpoint)
    provenance = {"formula": "TRADE_RECEIVABLES / REVENUE * 100", "input_facts": {
        "TRADE_RECEIVABLES": _fact_reference(receivables, "TRADE_RECEIVABLES"),
        "REVENUE": _fact_reference(revenue, "REVENUE"),
    }}
    if not receivables or not revenue:
        return _unavailable("missing:receivables_or_revenue", provenance=provenance, unit={"kind": "pct", "scale": 1})
    if receivables.get("availability") != "available" or _number(receivables.get("value")) is None:
        return _unavailable("missing:reported_trade_receivables", provenance=provenance, unit={"kind": "pct", "scale": 1})
    revenue_problem = _usable_flow_fact(revenue)
    if revenue_problem:
        return _unavailable("missing_or_incompatible:reported_revenue:" + revenue_problem, provenance=provenance, unit={"kind": "pct", "scale": 1})
    if receivables.get("nature") != "balance":
        return _unavailable("incompatible:trade_receivables_not_balance", provenance=provenance, unit={"kind": "pct", "scale": 1})
    r_unit, s_unit = receivables.get("unit") or {}, revenue.get("unit") or {}
    matching = (
        receivables.get("fiscal_year") == revenue.get("fiscal_year")
        and receivables.get("fiscal_quarter") == revenue.get("fiscal_quarter")
        and receivables.get("period_end") == revenue.get("period_end")
        and receivables.get("fs_div") == revenue.get("fs_div")
        and r_unit.get("kind") == s_unit.get("kind")
        and r_unit.get("currency") == s_unit.get("currency")
        and r_unit.get("scale") == s_unit.get("scale")
    )
    if not matching:
        return _unavailable("incompatible:receivables_sales_period_scope_currency_or_unit", provenance=provenance, unit={"kind": "pct", "scale": 1})
    sales = _number(revenue.get("value"))
    if sales == 0:
        return _unavailable("invalid:reported_revenue_zero", provenance=provenance, unit={"kind": "pct", "scale": 1})
    ratio = _number(receivables.get("value")) / sales * Decimal(100)
    return {
        "status": "derived_deterministic",
        "value": _json_number(ratio),
        "reason": None,
        "unit": {"kind": "pct", "scale": 1},
        "period": _period_descriptor((receivables, revenue), endpoint),
        "provenance": provenance,
    }


def _structured_metric(
    rows: Iterable[Mapping[str, Any]] | None,
    *,
    disclosure_type: str,
    period: Mapping[str, Any],
    expected_currency: str | None,
) -> dict[str, Any]:
    """Pass through only structured reported rows matching the selected period.

    The input is intentionally a small explicit interchange contract, rather
    than a prose parser.  A note excerpt, an LLM extraction, or a row without
    the reported-structure marker is not evidence for a public metric.
    """
    accepted: list[dict[str, Any]] = []
    rejected_unstructured = False
    for raw in rows or []:
        if not isinstance(raw, Mapping) or raw.get("disclosure_type") != disclosure_type:
            continue
        if raw.get("is_structured_reported") is not True:
            rejected_unstructured = True
            continue
        required = ("value", "fiscal_year", "period_end", "fs_div", "unit", "report_id", "report_type")
        if any(raw.get(key) is None for key in required) or _number(raw.get("value")) is None:
            continue
        unit = raw.get("unit") or {}
        if (
            raw.get("fiscal_year") != period.get("fiscal_year")
            or raw.get("period_end") != period.get("period_end")
            or raw.get("fs_div") != period.get("fs_div")
            or unit.get("kind") != "currency"
            or (expected_currency is not None and unit.get("currency") != expected_currency)
        ):
            continue
        accepted.append({
            "segment_id": raw.get("segment_id"),
            "segment_name": raw.get("segment_name"),
            "value": _json_number(_number(raw.get("value"))),
            "unit": deepcopy(dict(unit)),
            "period": {
                "fiscal_year": raw.get("fiscal_year"), "period_start": raw.get("period_start"),
                "period_end": raw.get("period_end"), "fs_div": raw.get("fs_div"),
            },
            "provenance": {
                "provider": raw.get("provider"),
                "report_id": raw.get("report_id"), "report_code": raw.get("report_code"), "report_type": raw.get("report_type"),
                "source_concept": raw.get("source_concept"), "mapping_id": raw.get("mapping_id"),
                "source_table": raw.get("source_table"), "source_row_id": raw.get("source_row_id"),
                "reported_structure": True,
            },
        })
    if accepted:
        return {"status": "reported", "value": accepted, "reason": None, "provenance": {"acceptance": "structured_reported_rows_only"}}
    reason = (
        "rejected:unstructured_note_evidence" if rejected_unstructured
        else f"missing:structured_reported_{disclosure_type}"
    )
    return _unavailable(reason, provenance={"acceptance": "structured_reported_rows_only"})


def _endpoint_has_reported_fact(canonical: Mapping[str, Any], endpoint: str) -> bool:
    for series in (canonical.get("series") or {}).values():
        if not isinstance(series, Mapping):
            continue
        fact = series.get("annual") if endpoint == "annual" else (series.get("quarters") or {}).get(endpoint)
        if isinstance(fact, Mapping) and fact.get("availability") == "available":
            return True
    return False


def resolve_latest_endpoint(canonical: Mapping[str, Any], *, requested: str = "latest") -> dict[str, Any]:
    """Choose Q3, then Q2, then Q1, then annual only when actually present."""
    requested = _ENDPOINT_ALIASES.get(requested, requested)
    allowed = set(LATEST_ENDPOINT_PRIORITY)
    if requested != "latest" and requested not in allowed:
        raise P1DisclosureError("requested_endpoint_must_be_latest_Q3_Q2_Q1_or_annual")
    candidates = []
    for endpoint in LATEST_ENDPOINT_PRIORITY:
        present = _endpoint_has_reported_fact(canonical, endpoint)
        candidates.append({"endpoint": endpoint, "available": present})
    selected = next((item["endpoint"] for item in candidates if item["available"]), None) if requested == "latest" else requested
    if requested != "latest" and not _endpoint_has_reported_fact(canonical, requested):
        selected = None
    return {
        "requested": requested,
        "priority": list(LATEST_ENDPOINT_PRIORITY),
        "candidates": candidates,
        "selected": selected,
        "reason": None if selected else "missing:reported_endpoint_for_requested_period",
    }


def _one_period_output(canonical: Mapping[str, Any], *, endpoint: str, rows: Iterable[Mapping[str, Any]] | None) -> dict[str, Any]:
    # Operating income is used only to describe the period.  No fallback to it
    # occurs if the other two strict EBITDA inputs are absent.
    descriptor = _period_descriptor(
        (_reported_fact(canonical, account, endpoint) for account in (*_EBITDA_INPUTS, "TRADE_RECEIVABLES", "REVENUE")),
        endpoint,
    )
    return {
        "period": descriptor,
        "ebitda": compute_strict_ebitda(canonical, endpoint=endpoint),
        "receivables_to_sales_pct": compute_receivables_to_sales(canonical, endpoint=endpoint),
        "segment_profit": _structured_metric(rows, disclosure_type="segment_profit", period=descriptor, expected_currency=canonical.get("currency")),
        "backlog_order_book": _structured_metric(rows, disclosure_type="backlog_order_book", period=descriptor, expected_currency=canonical.get("currency")),
    }


def build_p1_disclosures(
    canonical: Mapping[str, Any],
    *,
    structured_disclosures: Iterable[Mapping[str, Any]] | None = None,
    annual_history: Iterable[Mapping[str, Any]] | None = None,
    requested_endpoint: str = "latest",
) -> dict[str, Any]:
    """Build the P1 add-on without modifying the legacy company/UI shape.

    ``annual_history`` is a sequence of separately adapted canonical years.
    It is never inferred from interim facts, and is emitted separately from
    the current endpoint so annual comparisons cannot be mistaken for a QTD
    series.
    """
    if canonical.get("schema_version") != "canonical-financial-facts/1":
        raise P1DisclosureError("unsupported_canonical_schema")
    # Callers may pass a generator.  P1 evaluates the same structured evidence
    # for current and annual outputs, so materialise it once rather than making
    # later periods silently lose provenance rows.
    rows = list(structured_disclosures or [])
    selection = resolve_latest_endpoint(canonical, requested=requested_endpoint)
    current = (
        _one_period_output(canonical, endpoint=selection["selected"], rows=rows)
        if selection["selected"] else {
            "period": _period_descriptor((), "annual"),
            "ebitda": _unavailable(selection["reason"]),
            "receivables_to_sales_pct": _unavailable(selection["reason"], unit={"kind": "pct", "scale": 1}),
            "segment_profit": _unavailable(selection["reason"]),
            "backlog_order_book": _unavailable(selection["reason"]),
        }
    )
    annual = []
    for history_item in annual_history or []:
        if not isinstance(history_item, Mapping) or history_item.get("schema_version") != "canonical-financial-facts/1":
            raise P1DisclosureError("annual_history_requires_canonical_financial_facts")
        annual.append(_one_period_output(history_item, endpoint="annual", rows=rows))
    annual.sort(key=lambda item: (item["period"].get("fiscal_year") is None, item["period"].get("fiscal_year")))
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "p1_disclosure_addon",
        "policy": {
            "ebitda": "reported operating income + reported PPE depreciation + reported intangible amortization only",
            "prohibited_inputs": ["CFO proxy", "operating-income proxy", "estimated D&A", "combined D&A account"],
            "structured_disclosures": "segment profit and backlog/order book require structured reported rows; prose is rejected",
            "investment_recommendation": "not_provided",
        },
        "entity": {"entity_id": canonical.get("entity_id"), "source": canonical.get("source"), "fs_div": canonical.get("fs_div"), "currency": canonical.get("currency")},
        "period_selection": selection,
        "current": current,
        "annual_history": annual,
    }
