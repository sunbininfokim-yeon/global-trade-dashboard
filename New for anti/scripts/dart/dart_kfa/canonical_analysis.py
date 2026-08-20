"""Calculate one annual or discrete-quarter view from canonical filing facts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from .entity_policy import classify_entity, is_financial
from .fundamental_pack import build_fundamental_pack
from .industry import apply_industry_layer
from .ma_metrics import compute_ma_metrics
from .metrics import compute_metrics, load_metrics_spec
from .narrative import narratives_ko
from .validate import validate_accounts
from .valuation import build_seeded_scenarios, run_valuation_bundle, seed_from_statements
from .view_engine import build_unified_views


PERIODS = ("annual", "Q1", "Q2", "Q3", "Q4")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cell(series: Mapping[str, Any], period: str) -> dict[str, Any]:
    return dict(series.get("annual") or {}) if period == "annual" else dict((series.get("quarters") or {}).get(period) or {})


def _period_bags(canonical: Mapping[str, Any]) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, Any]]]:
    amount_bags = {period: {} for period in PERIODS}
    fact_bags = {period: {} for period in PERIODS}
    for account_id, series in (canonical.get("series") or {}).items():
        for period in PERIODS:
            fact = _cell(series, period)
            amount_bags[period][str(account_id)] = fact.get("value")
            fact_bags[period][str(account_id)] = fact
    return amount_bags, fact_bags


def _series(cells: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for period in PERIODS:
        cell = cells.get(period) or {}
        out.append({
            "period": period,
            "period_kind": cell.get("period_kind"),
            "start": cell.get("period_start"),
            "end": cell.get("period_end"),
            "value": cell.get("value"),
            "availability": cell.get("availability"),
            "quality": cell.get("quality"),
            "reason": cell.get("reason"),
        })
    return out


def analyze_canonical_facts(
    canonical: Mapping[str, Any],
    *,
    corp: Mapping[str, Any] | None = None,
    selected_period: str = "annual",
    valuation_assumptions: dict[str, Any] | None = None,
    shares_out: float | None = None,
    share_basis: str | None = None,
    share_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the common metric/view engine without mixing annual and interim data."""
    if canonical.get("schema_version") != "canonical-financial-facts/1":
        raise ValueError("unsupported_canonical_schema")
    if selected_period not in PERIODS:
        raise ValueError("selected_period_must_be_annual_or_Q1_Q2_Q3_Q4")
    corp_in = dict(corp or {})
    entity_policy = classify_entity(corp_in)
    amounts_by_period, facts_by_period = _period_bags(canonical)

    # A financial issuer's industrial revenue/FCF chain is never activated by
    # a similarly named filing line.
    if is_financial(entity_policy):
        for period in PERIODS:
            amounts_by_period[period]["REVENUE"] = None
            if "REVENUE" in facts_by_period[period]:
                facts_by_period[period]["REVENUE"] = {
                    **facts_by_period[period]["REVENUE"],
                    "value": None,
                    "availability": "not_applicable",
                    "reason": "not_applicable:financial_entity_industrial_revenue",
                }

    spec = load_metrics_spec()
    metrics_by_period = {
        period: compute_metrics(amounts, spec, entity_policy=entity_policy)
        for period, amounts in amounts_by_period.items()
    }
    ma_by_period = {
        period: compute_ma_metrics(amounts_by_period[period], metrics_by_period[period], entity_policy=entity_policy)
        for period in PERIODS
    }
    current = amounts_by_period[selected_period]
    metrics = deepcopy(metrics_by_period[selected_period])
    ma = deepcopy(ma_by_period[selected_period])

    for metric_id, cell in metrics.items():
        cell["series"] = [
            {"period": period, "value": (metrics_by_period[period].get(metric_id) or {}).get("value")}
            for period in PERIODS
        ]
    for metric_id, cell in ma.items():
        if not isinstance(cell, dict):
            continue
        cell["series"] = [
            {
                "period": period,
                "value": (
                    (ma_by_period[period].get(metric_id) or {}).get("value")
                    if isinstance(ma_by_period[period].get(metric_id), dict)
                    else None
                ),
            }
            for period in PERIODS
        ]

    account_output: dict[str, dict[str, Any]] = {}
    for account_id in (canonical.get("series") or {}):
        selected = facts_by_period[selected_period].get(account_id) or {}
        account_output[str(account_id)] = {
            "value": selected.get("value"),
            "reason": selected.get("reason"),
            "match": selected.get("source_concept"),
            "account_nm": selected.get("source_concept"),
            "unit": selected.get("unit"),
            "currency": (selected.get("unit") or {}).get("currency"),
            "period_kind": selected.get("period_kind"),
            "availability": selected.get("availability"),
            "quality": selected.get("quality"),
            "provenance": selected.get("provenance"),
            "series": _series({period: facts_by_period[period].get(account_id) or {} for period in PERIODS}),
        }

    industry = apply_industry_layer(corp=corp_in, metrics=metrics, amounts=current, entity_policy=entity_policy)
    selected_fact = next((fact for fact in facts_by_period[selected_period].values() if fact), {})
    period = {
        "year": canonical.get("fiscal_year"),
        "selected": selected_period,
        "period_kind": selected_fact.get("period_kind"),
        "start": selected_fact.get("period_start"),
        "end": selected_fact.get("period_end") or canonical.get("fiscal_year_end"),
        "fs_div": canonical.get("fs_div"),
        "source": canonical.get("source"),
    }
    corp_out = {
        **corp_in,
        "corp_code": corp_in.get("corp_code") or canonical.get("entity_id"),
        "entity_policy": entity_policy,
        "industry_kit": industry.get("industry_kit"),
    }

    if is_financial(entity_policy):
        valuation = {"status": "not_applicable", "reason": "not_applicable:financial_entity_industrial_valuation", "models": {}}
        seed = {"notes_ko": ["금융업에는 산업기업 DCF 시드를 만들지 않습니다."]}
    else:
        seed = seed_from_statements(current, operating_margin_pct=(metrics.get("operating_margin") or {}).get("value"))
        scenarios = []
        revenue0 = current.get("REVENUE")
        if selected_period == "annual" and valuation_assumptions and revenue0 is not None:
            scenarios = build_seeded_scenarios(
                operating_margin_pct=(metrics.get("operating_margin") or {}).get("value") or 0.0,
                seed=seed,
                explicit_assumptions=valuation_assumptions,
            )
        if revenue0 is None:
            valuation = {
                "schema_version": "dart-valuation-v2",
                "status": "inputs_required",
                "reason": "missing:reported_annual_revenue_for_industrial_dcf",
                "models": {},
                "scenarios": [],
                "value_band": None,
                "sensitivity_wacc_g": [],
            }
        else:
            valuation = run_valuation_bundle(
                revenue0=float(revenue0),
                ebitda0=(ma.get("ebitda_proxy") or {}).get("value"),
                net_debt=(ma.get("net_debt") or {}).get("value"),
                shares_out=shares_out,
                share_basis=share_basis,
                share_metadata=share_metadata,
                scenarios=scenarios,
            )
        if selected_period != "annual":
            valuation.update({
                "status": "inputs_required",
                "reason": "blocked_quality:valuation_requires_annual_or_ttm_base",
                "scenarios": [],
                "value_band": None,
                "sensitivity_wacc_g": [],
            })
        valuation["historical_seed"] = seed

    gate = validate_accounts(current)
    fundamental = build_fundamental_pack(
        corp=corp_out,
        period=period,
        metrics=metrics,
        ma=ma,
        industry=industry,
        valuation=valuation,
        market=None,
        amounts_current=current,
        amounts_prior={},
        amounts_prior2={},
        entity_policy=entity_policy,
    )
    output = {
        "schema_version": "dart-company-v2",
        "generated_at": _now_iso(),
        "source": canonical.get("source"),
        "corp": corp_out,
        "entity_policy": entity_policy,
        "period": period,
        "period_options": list(PERIODS),
        "parse_status": gate["parse_status"],
        "validation": gate,
        "accounts": account_output,
        "metrics": metrics,
        "ma_metrics": ma,
        "industry": industry,
        "valuation": valuation,
        "fundamental_pack": fundamental,
        "shares_out": shares_out,
        "share_basis": share_basis,
        "share_metadata": dict(share_metadata or {}),
        "narrative": narratives_ko(metrics, parse_status=gate["parse_status"], industry=industry, ma=ma),
        "disclaimer_ko": "공시 기반 계산 및 명시적 사용자 시나리오이며 투자 권유가 아닙니다.",
        "canonical_audit": {
            "schema_version": canonical.get("schema_version"),
            "currency": canonical.get("currency"),
            "fiscal_year_start": canonical.get("fiscal_year_start"),
            "fiscal_year_end": canonical.get("fiscal_year_end"),
            "reconciliation": {
                account_id: (series.get("reconciliation") or {})
                for account_id, series in (canonical.get("series") or {}).items()
            },
        },
    }
    view_inputs = {"valuation_assumptions": valuation_assumptions} if valuation_assumptions else {}
    output["unified_views"] = build_unified_views(output, user_inputs=view_inputs)
    return output
