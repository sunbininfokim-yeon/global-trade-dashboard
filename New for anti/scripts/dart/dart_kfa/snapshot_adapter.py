"""Static KFA JSON adapter for the canonical financial-facts engine.

The public calculator already consumes ``basic_cards.<key>.value`` / ``series``
/ ``reason``.  This module deliberately preserves that small UI contract while
adding the audit information needed by the P0 engine.  It is an output adapter:
it does not fetch, interpolate, estimate, or calculate a valuation target.

``build_kfa_snapshot`` accepts annual outputs from :func:`analyze_canonical_facts`
in chronological order.  A caller may provide one to five annual reports.  The
adapter never manufactures a missing annual or quarter; the caller receives an
explicit data-quality reason instead.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SNAPSHOT_SCHEMA = "kfa_engine_v1"
SNAPSHOT_CONTRACT = "kfa-static-snapshot/2"
_MIN_HISTORY_POINTS = 3

# The key names on the left are the deployed UI's legacy keys.  The right side
# names canonical engine cells.  ``derived`` means a deterministic arithmetic
# metric, not a forecast or an analyst estimate.
CARD_SOURCES: dict[str, tuple[str, str, str]] = {
    "revenue": ("accounts", "REVENUE", "direct"),
    "operating_income": ("accounts", "OPERATING_INCOME", "direct"),
    "net_income": ("accounts", "NET_INCOME", "direct"),
    "cfo": ("accounts", "CFO", "direct"),
    "cash": ("accounts", "CASH", "direct"),
    "fcf": ("ma_metrics", "fcf", "derived"),
    "net_debt": ("ma_metrics", "net_debt", "derived"),
    "current_ratio": ("metrics", "current_ratio", "derived"),
    "debt_ratio": ("metrics", "debt_ratio", "derived"),
    "interest_coverage": ("ma_metrics", "interest_coverage", "derived"),
}

# A bank or insurer may report lines with names that resemble cash, debt, or
# revenue, but those labels are not interchangeable with the industrial
# working-capital / enterprise-value chain.  Keep only reported profit lines
# in this legacy-card surface until a dedicated financial-issuer view exists.
_FINANCIAL_UNSAFE_CARDS = frozenset({
    "revenue", "cfo", "cash", "fcf", "net_debt", "current_ratio", "debt_ratio", "interest_coverage",
})
_INDUSTRIAL_HISTORY_CARDS = ("revenue", "operating_income", "net_income", "cfo")
_FINANCIAL_HISTORY_CARDS = ("operating_income", "net_income")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value == value else None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _as_list(annual_companies: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [deepcopy(dict(company)) for company in annual_companies]
    if not rows:
        raise ValueError("missing:annual_company_outputs")
    years: set[int] = set()
    for row in rows:
        year = (row.get("period") or {}).get("year")
        if not isinstance(year, int):
            raise ValueError("invalid:annual_company_missing_period_year")
        if (row.get("period") or {}).get("selected") != "annual":
            raise ValueError("invalid:snapshot_requires_annual_company_outputs")
        if year in years:
            raise ValueError(f"invalid:duplicate_fiscal_year:{year}")
        years.add(year)
    return sorted(rows, key=lambda row: row["period"]["year"])


def _same_or_none(values: Iterable[Any]) -> Any:
    present = [value for value in values if value is not None]
    return present[0] if present and all(value == present[0] for value in present) else None


def _source_cell(company: Mapping[str, Any], source: str, key: str) -> dict[str, Any]:
    value = (company.get(source) or {}).get(key) or {}
    return dict(value) if isinstance(value, Mapping) else {"value": value}


def _annual_lineage(company: Mapping[str, Any], cell: Mapping[str, Any], value_kind: str) -> dict[str, Any]:
    period = company.get("period") or {}
    source = company.get("source") or period.get("source")
    provenance = cell.get("provenance")
    return {
        "year": period.get("year"),
        "start": period.get("start"),
        "end": period.get("end"),
        "period_kind": "annual",
        "scope": period.get("fs_div"),
        "source": source,
        "source_report": "business_report" if source in {"dart", "opendart"} else "annual_report",
        "observation_kind": value_kind,
        "method": "reported_filing_fact" if value_kind == "direct" else "deterministic_engine_metric",
        "provenance": provenance,
        "quality": cell.get("quality") or ("reported" if value_kind == "direct" else "derived"),
        "reason": cell.get("reason"),
    }


def _card_from_history(
    card_id: str,
    annual_companies: list[dict[str, Any]],
    *,
    entity_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source, key, value_kind = CARD_SOURCES[card_id]
    financial = bool(entity_policy.get("is_financial_entity"))
    if financial and card_id in _FINANCIAL_UNSAFE_CARDS:
        reason = (
            "not_applicable:financial_entity_industrial_revenue"
            if card_id == "revenue"
            else f"not_applicable:financial_entity_industrial_{card_id}"
        )
        return ({"value": None, "series": [], "reason": reason, "value_kind": "not_applicable"}, [])

    lineage: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    latest_cell: dict[str, Any] = {}
    for company in annual_companies:
        cell = _source_cell(company, source, key)
        latest_cell = cell
        line = _annual_lineage(company, cell, value_kind)
        lineage.append(line)
        value = _number(cell.get("value"))
        if value is not None:
            series.append({"year": line["year"], "end": line["end"], "value": value})

    latest_value = _number(latest_cell.get("value"))
    reason = latest_cell.get("reason")
    history_reason = None
    if len(series) < _MIN_HISTORY_POINTS:
        history_reason = f"insufficient:reported_annual_history:{len(series)}_of_{_MIN_HISTORY_POINTS}"
    card = {
        "value": latest_value,
        "series": series,
        "reason": reason,
        "value_kind": value_kind if latest_value is not None else "unavailable",
        "provenance": lineage[-1].get("provenance") if lineage else None,
        "period_lineage": lineage,
    }
    if history_reason:
        card["history_reason"] = history_reason
    return card, lineage


def _safe_models(company: Mapping[str, Any], entity_policy: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only the engine model registry; never synthesise assumptions."""
    unified = deepcopy((company.get("unified_views") or {}))
    registry = unified.get("model_registry")
    if not isinstance(registry, dict):
        return unified
    for model in registry.values():
        if not isinstance(model, dict):
            continue
        # A static export must not turn filed historical values into an
        # automatic valuation output.  Even if an upstream registry supports
        # a mechanical snapshot model, it remains omitted here until a caller
        # supplies explicit, auditable assumptions or verified market inputs.
        if model.get("status") in {"computed", "ready"} and not model.get("assumptions"):
            model.update({
                "status": "omitted",
                "value": None,
                "reason": "omitted:static_snapshot_requires_explicit_assumptions_or_verified_market_data",
            })
        elif model.get("status") not in {"computed", "ready"}:
            model.setdefault("reason", "needs_input:explicit_assumptions_or_verified_market_data")
    if entity_policy.get("is_financial_entity"):
        for model in registry.values():
            if isinstance(model, dict):
                model.update({"status": "not_applicable", "reason": "not_applicable:financial_entity_industrial_model"})
    return unified


def assess_snapshot_service_readiness(
    snapshot: Mapping[str, Any],
    *,
    requested_years: int | None = None,
) -> dict[str, Any]:
    """State whether a static asset is safe to prefer over a live response.

    The decision deliberately separates *renderable* from *authoritative*:
    migrated legacy samples can remain inspectable, but a one-point history or
    incomplete currency contract must trigger a live lookup when the Worker is
    available.  This makes the Hynix-style stale-snapshot failure observable
    without deleting useful offline samples.
    """
    years_required = requested_years if requested_years is not None else _MIN_HISTORY_POINTS
    if not isinstance(years_required, int) or years_required < 1:
        raise ValueError("invalid:requested_history_years")

    policy = snapshot.get("entity_policy") or {}
    financial = bool(policy.get("is_financial_entity"))
    expected_cards = _FINANCIAL_HISTORY_CARDS if financial else _INDUSTRIAL_HISTORY_CARDS
    cards = snapshot.get("basic_cards") or {}
    reasons: list[str] = []
    history: dict[str, int] = {}
    for card_id in expected_cards:
        card = cards.get(card_id) if isinstance(cards, Mapping) else None
        points = len(card.get("series") or []) if isinstance(card, Mapping) else 0
        history[card_id] = points
        if points < years_required:
            reasons.append(f"insufficient:reported_annual_history:{card_id}:{points}_of_{years_required}")

    contract = snapshot.get("currency_contract") or {}
    calculation = contract.get("calculation_currency")
    display = contract.get("display_currency")
    if not calculation or not display:
        reasons.append("missing:consistent_calculation_and_display_currency")

    snapshot_contract = snapshot.get("snapshot_contract")
    if snapshot_contract != SNAPSHOT_CONTRACT:
        reasons.append("invalid:snapshot_contract")

    quality = snapshot.get("data_quality") or {}
    legacy_unverified = not bool(quality.get("raw_filing_facts_embedded"))
    fallback_required = bool(reasons)
    return {
        "schema": "kfa-snapshot-service-readiness/1",
        "status": (
            "fallback_required" if fallback_required
            else "legacy_unverified" if legacy_unverified
            else "ready"
        ),
        "static_eligible": not fallback_required,
        "live_fallback_required": fallback_required,
        "legacy_unverified": legacy_unverified,
        "requested_annual_years": years_required,
        "observed_annual_history": history,
        "reasons": reasons,
    }


def build_kfa_snapshot(
    annual_companies: Iterable[Mapping[str, Any]],
    *,
    label: str | None = None,
    requested_years: int = _MIN_HISTORY_POINTS,
) -> dict[str, Any]:
    """Build a backwards-compatible static snapshot from canonical outputs.

    ``annual_companies`` must already have been calculated through the P0
    canonical pipeline.  This keeps data collection (DART/SEC) separate from
    JSON serialization and makes the output safe to hand to a Worker/UI.
    """
    companies = _as_list(annual_companies)
    latest = companies[-1]
    corp = dict(latest.get("corp") or {})
    entity_policy = dict(latest.get("entity_policy") or corp.get("entity_policy") or {})
    # canonical_audit.currency is already a string, unlike an account cell.
    calculation_currency = _same_or_none([(company.get("canonical_audit") or {}).get("currency") for company in companies])
    if not calculation_currency:
        calculation_currency = _same_or_none([
            ((company.get("accounts") or {}).get("REVENUE") or {}).get("currency")
            for company in companies
        ])
    if not calculation_currency:
        calculation_currency = "KRW" if str(latest.get("source") or "").lower() in {"dart", "opendart"} else None

    cards: dict[str, dict[str, Any]] = {}
    all_lineage: dict[str, list[dict[str, Any]]] = {}
    for card_id in CARD_SOURCES:
        card, lineage = _card_from_history(card_id, companies, entity_policy=entity_policy)
        cards[card_id] = card
        all_lineage[card_id] = lineage

    period = latest.get("period") or {}
    observed_years = len({row["year"] for card in cards.values() for row in card.get("series") or []})
    quality_reasons: list[str] = []
    if observed_years < requested_years:
        quality_reasons.append(f"insufficient:reported_annual_history:{observed_years}_of_{requested_years}")
    if calculation_currency is None:
        quality_reasons.append("missing:consistent_calculation_currency")

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_contract": SNAPSHOT_CONTRACT,
        "label": label or corp.get("stock_code") or corp.get("code") or corp.get("corp_code"),
        "as_of": period.get("end"),
        "currency": calculation_currency,
        "currency_contract": {
            "calculation_currency": calculation_currency,
            "display_currency": calculation_currency,
            "fx": None,
            "policy": "filing_currency_only_without_explicit_fx",
        },
        "meta": {
            "ticker": corp.get("stock_code") or corp.get("code"),
            "corp_code": corp.get("corp_code"),
            "entity": corp.get("name") or corp.get("entity"),
            "source": latest.get("source"),
            "fs_div": period.get("fs_div"),
            "scope": "consolidated" if period.get("fs_div") == "CFS" else "separate",
            "fiscal_year": period.get("year"),
        },
        "entity_policy": entity_policy,
        "basic_cards": cards,
        "period_lineage": {
            "policy": "annual_report_only_for_static_history; direct_filing_observation_before_derived_metric",
            "annual_cards": all_lineage,
            "quarterly": {
                "schema": "kfa-quarter-lineage/1",
                "policy": "direct_quarter_first; ytd_subtraction_for_flow_only; balance_point_in_time",
                "status": "not_materialized_in_annual_snapshot",
                "reason": "missing:quarterly_filing_inputs",
            },
        },
        "unified_views": _safe_models(latest, entity_policy),
        "data_quality": {
            "input_kind": "canonical_annual_history",
            "source_claim": latest.get("source"),
            "raw_filing_facts_embedded": True,
            "annual_years_requested": requested_years,
            "annual_years_observed": observed_years,
            "no_interpolation": True,
            "reasons": quality_reasons,
            "generated_at": _now_iso(),
        },
        "disclaimer_ko": "공시 기반 수치와 명시적 입력만 사용하며 투자 권유 또는 자동 목표주가가 아닙니다.",
    }
    snapshot["service_readiness"] = assess_snapshot_service_readiness(
        snapshot,
        requested_years=requested_years,
    )
    return snapshot


def build_kfa_snapshot_from_dart_filings(
    filings_by_year: Mapping[int, Mapping[str, list[Mapping[str, Any]]]],
    *,
    account_specs: Mapping[str, Mapping[str, Any]],
    fiscal_year_ends: Mapping[int, str],
    corp: Mapping[str, Any],
    requested_years: int = _MIN_HISTORY_POINTS,
) -> dict[str, Any]:
    """Bridge raw DART filing observations to the static JSON contract.

    The fetch layer owns acquiring and caching the four report payloads for a
    year (Q1/H1/Q3/FY).  This adapter owns only the deterministic conversion:
    raw observations -> canonical facts -> annual analysis -> JSON.  It is
    intentionally key-free and network-free so a Worker adapter and fixtures
    can call exactly the same path.
    """
    from .canonical_analysis import analyze_canonical_facts
    from .canonical_facts import adapt_dart_filings

    analyses: list[dict[str, Any]] = []
    for year in sorted(filings_by_year):
        fiscal_year_end = fiscal_year_ends.get(year)
        if not fiscal_year_end:
            raise ValueError(f"missing:fiscal_year_end:{year}")
        canonical = adapt_dart_filings(
            filings_by_year[year],
            account_specs=account_specs,
            fiscal_year_end=fiscal_year_end,
        )
        analyses.append(analyze_canonical_facts(canonical, corp=dict(corp), selected_period="annual"))
    return build_kfa_snapshot(
        analyses,
        label=str(corp.get("stock_code") or corp.get("code") or corp.get("corp_code") or ""),
        requested_years=requested_years,
    )


def enrich_legacy_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Add P0 audit contracts to an existing checked-in UI sample.

    This is intentionally a metadata migration.  It never creates a missing
    historical value.  Legacy EBITDA proxies are removed because P0 defines
    EBITDA strictly as operating income plus reported PPE depreciation plus
    reported intangible amortisation.
    """
    out = deepcopy(dict(snapshot))
    meta = dict(out.get("meta") or {})
    source = str(meta.get("source") or "").lower()
    currency = str(out.get("currency") or "").upper() or None
    entity_policy = out.get("entity_policy")
    if not isinstance(entity_policy, dict):
        from .entity_policy import classify_entity
        entity_policy = classify_entity({**meta, "source": source})

    out["snapshot_contract"] = SNAPSHOT_CONTRACT
    out["entity_policy"] = entity_policy
    out["currency_contract"] = {
        "calculation_currency": currency,
        "display_currency": currency,
        "fx": None,
        "policy": "legacy_snapshot_filing_currency_only_without_explicit_fx",
    }
    lineage: dict[str, list[dict[str, Any]]] = {}
    for card_id, card in (out.get("basic_cards") or {}).items():
        if not isinstance(card, dict):
            continue
        rows = []
        for row in card.get("series") or []:
            if not isinstance(row, dict):
                continue
            rows.append({
                "year": row.get("year"),
                "end": row.get("end"),
                "period_kind": "annual",
                "scope": meta.get("fs_div"),
                "source": source or None,
                "source_report": "legacy_static_snapshot",
                "observation_kind": "unknown_legacy",
                "method": "not_revalidated_in_p0_json_migration",
                "quality": "legacy_unverified",
                "reason": None,
            })
        lineage[card_id] = rows
        card["period_lineage"] = rows
        if card.get("value") is not None and not card.get("value_kind"):
            card["value_kind"] = "unknown_legacy"
        if len(card.get("series") or []) < _MIN_HISTORY_POINTS:
            card["history_reason"] = f"insufficient:reported_annual_history:{len(card.get('series') or [])}_of_{_MIN_HISTORY_POINTS}"

    # Do not pass an operating-income proxy off as EBITDA.  The required D&A
    # split is absent in the legacy assets, so the honest result is unavailable.
    ebitda_reason = "missing:reported_ppe_depreciation_and_intangible_amortization"
    for card_id in ("ebitda", "ebitda_or_op", "net_debt_to_ebitda", "fcf_to_ebitda"):
        card = (out.get("basic_cards") or {}).get(card_id)
        if isinstance(card, dict):
            card.update({"value": None, "series": [], "reason": ebitda_reason, "value_kind": "unavailable"})
    if entity_policy.get("is_financial_entity"):
        for card_id in _FINANCIAL_UNSAFE_CARDS | {"ebitda", "ebitda_or_op", "net_debt_to_ebitda", "fcf_to_ebitda"}:
            card = (out.get("basic_cards") or {}).get(card_id)
            if isinstance(card, dict):
                reason = (
                    "not_applicable:financial_entity_industrial_revenue"
                    if card_id == "revenue"
                    else f"not_applicable:financial_entity_industrial_{card_id}"
                )
                card.update({"value": None, "series": [], "reason": reason, "value_kind": "not_applicable"})

    # The old sample embeds prototype model results.  Preserve their IDs and
    # shape for the UI, but never expose a computed-looking valuation or
    # underwriting answer without a separately supplied, auditable assumption
    # block.  This migration does not create one.
    for lens in ("investor", "pe", "deal"):
        models = ((out.get(lens) or {}).get("models") or {})
        if not isinstance(models, dict):
            continue
        for model in models.values():
            if not isinstance(model, dict):
                continue
            if model.get("status") not in {"omitted", "needs_input", "not_applicable"}:
                model.update({
                    "status": "omitted",
                    "value": None,
                    "reason": "omitted:static_snapshot_requires_explicit_assumptions_or_verified_market_data",
                })

    existing_quality = dict(out.get("data_quality") or {})
    existing_quality.update({
        "p0_json_contract": SNAPSHOT_CONTRACT,
        "legacy_values_recalculated": False,
        # The checked-in samples retain their former calculation packs, but do
        # not retain receipt numbers / source-line identifiers for each public
        # card.  They are therefore not raw-filing fixtures for P0 purposes.
        "raw_filing_facts_embedded": False,
        "raw_filing_provenance": "not_embedded_in_legacy_static_asset",
        "no_interpolation": True,
        "quarterly_status": "not_materialized_in_legacy_static_asset",
        "sample_limitations": [
            "legacy values were retained without live API refetch in this PR",
            "annual history is not backfilled when absent",
            "EBITDA remains unavailable without reported PPE depreciation and intangible amortization",
        ],
    })
    out["data_quality"] = existing_quality
    out["period_lineage"] = {
        "policy": "legacy_static_snapshot_no_interpolation",
        "annual_cards": lineage,
        "quarterly": {
            "schema": "kfa-quarter-lineage/1",
            "policy": "direct_quarter_first; ytd_subtraction_for_flow_only; balance_point_in_time",
            "status": "not_materialized_in_legacy_static_asset",
            "reason": "missing:quarterly_filing_inputs",
        },
    }
    out["service_readiness"] = assess_snapshot_service_readiness(out)
    return out
