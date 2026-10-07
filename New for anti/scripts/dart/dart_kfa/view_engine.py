"""Source-neutral unified views for DART and SEC company analyses.

Both source adapters already normalize into ``dart-company-v1``.  This module
is deliberately downstream of that shared schema: it resolves one card
registry, computes supported models once, then gives Basic / Finance Team / PE
/ IB views references to registry IDs.  No view embeds a private copy.
"""

from __future__ import annotations

from copy import deepcopy
from statistics import median
from typing import Any

from .entity_policy import is_financial
from .currency import (
    build_currency_contract,
    convert_currency_value,
    convert_monetary_input_to_calculation_currency,
)
from .model_availability import card_decision, model_decision
from .valuation import build_seeded_scenarios, fcff_dcf, run_valuation_bundle


SCHEMA = "kfa-unified-views-v1"
DEFINITIONS_VERSION = "2026-08-20"
DEFAULT_VIEW = "basic"
VIEW_ORDER = ("basic", "finance_team", "pe", "ib")


def _definition(
    label_ko: str,
    explain_ko: str,
    source: str,
    key: str,
    unit: str,
    category: str,
) -> dict[str, str]:
    return {
        "label_ko": label_ko,
        "explain_ko": explain_ko,
        "source": source,
        "key": key,
        "unit": unit,
        "category": category,
    }


# This catalog is the single source of truth for both SEC and OpenDART output.
CARD_DEFINITIONS: dict[str, dict[str, str]] = {
    "revenue": _definition("매출", "고객에게 제품·서비스를 팔아 번 금액입니다.", "accounts", "REVENUE", "currency", "fundamental"),
    "operating_income": _definition("영업이익", "본업의 수익에서 영업비용을 빼고 남은 이익입니다.", "accounts", "OPERATING_INCOME", "currency", "fundamental"),
    "net_income": _definition("순이익", "이자와 세금까지 반영한 최종 이익입니다.", "accounts", "NET_INCOME", "currency", "fundamental"),
    "total_assets": _definition("총자산", "회사가 보유하거나 통제하는 경제적 자원입니다.", "accounts", "TOTAL_ASSETS", "currency", "fundamental"),
    "equity": _definition("자본", "자산에서 부채를 빼고 주주에게 귀속되는 장부가치입니다.", "accounts", "EQUITY", "currency", "fundamental"),
    "cash": _definition("현금", "즉시 사용할 수 있는 현금성 자산입니다.", "accounts", "CASH", "currency", "liquidity"),
    "cfo": _definition("영업현금흐름", "본업이 실제 현금을 얼마나 만들었는지 보여줍니다.", "accounts", "CFO", "currency", "cash_flow"),
    "capex": _definition("설비투자", "유형자산 취득에 사용한 현금입니다.", "accounts", "CAPEX", "currency", "cash_flow"),
    "operating_margin": _definition("영업이익률", "매출 100원 중 본업 이익이 얼마나 남는지 보여줍니다.", "metrics", "operating_margin", "pct", "profitability"),
    "net_margin": _definition("순이익률", "매출 100원 중 최종 이익이 얼마나 남는지 보여줍니다.", "metrics", "net_margin", "pct", "profitability"),
    "roe": _definition("ROE", "주주가 맡긴 자본으로 얼마의 이익을 냈는지 봅니다.", "metrics", "roe", "pct", "returns"),
    "roa": _definition("ROA", "전체 자산으로 얼마의 이익을 냈는지 봅니다.", "metrics", "roa", "pct", "returns"),
    "current_ratio": _definition("유동비율", "단기자산이 단기부채를 얼마나 덮는지 봅니다.", "metrics", "current_ratio", "pct", "liquidity"),
    "debt_ratio": _definition("부채비율", "자본 대비 총부채 규모를 봅니다.", "metrics", "debt_ratio", "pct", "leverage"),
    "earnings_quality": _definition("이익의 현금전환", "영업현금흐름이 순이익을 얼마나 뒷받침하는지 봅니다.", "metrics", "earnings_quality", "x", "cash_flow"),
    "inventory_turnover": _definition("재고회전율", "재고가 매출원가로 전환되는 속도입니다.", "metrics", "inventory_turnover", "x", "working_capital"),
    "fcf": _definition("잉여현금흐름", "영업현금에서 설비투자를 빼고 남은 현금입니다.", "ma_metrics", "fcf", "currency", "cash_flow"),
    "fcf_margin": _definition("FCF 마진", "매출 중 잉여현금으로 남은 비율입니다.", "ma_metrics", "fcf_margin", "pct", "cash_flow"),
    "ebitda_proxy": _definition("EBITDA 대용", "영업이익에 공시 감가상각을 더한 명시적 프록시입니다.", "ma_metrics", "ebitda_proxy", "currency", "leverage"),
    "gross_debt": _definition("이자부 총차입금", "명시된 단기·장기 이자부 차입의 합계입니다.", "ma_metrics", "gross_interest_bearing_debt", "currency", "leverage"),
    "net_debt": _definition("순차입금", "이자부 차입에서 현금과 시장성유가증권을 뺀 금액입니다.", "ma_metrics", "net_debt", "currency", "leverage"),
    "net_debt_to_ebitda": _definition("순차입금 / EBITDA", "현재 EBITDA 대용 대비 순차입 부담입니다.", "ma_metrics", "net_debt_to_ebitda", "x", "leverage"),
    "interest_coverage": _definition("이자보상배율", "영업이익이 이자비용을 몇 배 감당하는지 봅니다.", "ma_metrics", "interest_coverage", "x", "coverage"),
    "cfo_to_ebitda": _definition("CFO / EBITDA", "EBITDA 대용이 영업현금으로 전환되는 정도입니다.", "ma_metrics", "cfo_to_ebitda", "x", "cash_flow"),
    "maintenance_capex_burden": _definition("유지투자 부담 프록시", "공시 D&A와 Capex 중 작은 금액을 유지투자 프록시로 봅니다.", "computed", "maintenance_capex_burden", "pct", "cash_flow"),
    "ev_bridge": _definition("EV 브리지", "시가총액에 검증된 순차입금을 더해 기업가치로 연결합니다.", "computed", "ev_bridge", "currency", "valuation"),
    "trading_comps": _definition("거래비교", "출처·기준일이 확인된 비교기업 배수만 요약합니다.", "verified_input", "verified_peer_multiples", "mixed", "valuation"),
    "segment": _definition("사업부", "출처·기준일이 확인된 사업부 정보만 표시합니다.", "verified_input", "verified_segments", "mixed", "due_diligence"),
    "full_qoe": _definition("전체 이익의 질", "주석 수준에서 검증된 정상화·현금전환 항목만 표시합니다.", "verified_input", "verified_qoe", "mixed", "due_diligence"),
}

MODEL_DEFINITIONS: dict[str, dict[str, str]] = {
    "liquidity_coverage": {"label_ko": "유동성·커버리지", "kind": "snapshot"},
    "delever_path": {"label_ko": "디레버리징 경로", "kind": "assumption"},
    "fcf_yield_snapshot": {"label_ko": "FCF 수익률", "kind": "snapshot"},
    "reverse_dcf": {"label_ko": "역 DCF", "kind": "reverse_solve"},
    "scenario_dcf_ev_bridge": {"label_ko": "시나리오 DCF / EV 브리지", "kind": "assumption"},
    "trading_comps": {"label_ko": "검증된 거래비교", "kind": "verified_input"},
    "sotp": {"label_ko": "검증된 SOTP", "kind": "verified_input"},
}

VIEW_DEFINITIONS: dict[str, dict[str, Any]] = {
    "basic": {
        "label_ko": "기초",
        "audience": "beginner",
        "goal_ko": "규모·이익·수익성·기본 재무안전성을 쉬운 설명으로 봅니다.",
        "card_refs": [
            "revenue", "operating_income", "net_income", "total_assets", "equity",
            "operating_margin", "net_margin", "roe", "roa", "current_ratio", "debt_ratio", "cash",
        ],
        "model_refs": [],
    },
    "finance_team": {
        "label_ko": "Finance Team",
        "audience": "finance_team",
        "goal_ko": "현금전환·운전자본·차입·이자상환 여력을 공시 기준으로 점검합니다.",
        "card_refs": [
            "revenue", "operating_income", "net_income", "cfo", "capex", "fcf", "fcf_margin",
            "earnings_quality", "inventory_turnover", "cash", "gross_debt", "net_debt",
            "interest_coverage", "cfo_to_ebitda",
        ],
        "model_refs": ["liquidity_coverage", "fcf_yield_snapshot", "reverse_dcf"],
    },
    "pe": {
        "label_ko": "PE",
        "audience": "private_equity",
        "goal_ko": "진입 현금수익률과 레버리지·상환 경로를 점검합니다.",
        "card_refs": [
            "revenue", "operating_income", "cfo", "fcf", "fcf_margin", "cash",
            "ebitda_proxy", "gross_debt", "net_debt", "net_debt_to_ebitda",
            "interest_coverage", "maintenance_capex_burden",
        ],
        "model_refs": ["liquidity_coverage", "delever_path", "fcf_yield_snapshot"],
    },
    "ib": {
        "label_ko": "IB",
        "audience": "investment_banking",
        "goal_ko": "검증된 입력으로 기업가치 브리지·시나리오·거래비교를 봅니다.",
        "card_refs": [
            "revenue", "operating_income", "net_income", "ebitda_proxy", "net_debt",
            "ev_bridge", "trading_comps", "segment", "full_qoe",
        ],
        "model_refs": ["reverse_dcf", "scenario_dcf_ev_bridge", "trading_comps", "sotp"],
    },
}


def get_view_definitions() -> dict[str, Any]:
    """Static adapter-independent definitions for SEC and OpenDART callers."""
    return {
        "schema": SCHEMA,
        "definitions_version": DEFINITIONS_VERSION,
        "default_view": DEFAULT_VIEW,
        "view_order": list(VIEW_ORDER),
        "cards": deepcopy(CARD_DEFINITIONS),
        "models": deepcopy(MODEL_DEFINITIONS),
        "views": deepcopy(VIEW_DEFINITIONS),
    }


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _account_card(company: dict[str, Any], definition: dict[str, str]) -> dict[str, Any]:
    source = (company.get("accounts") or {}).get(definition["key"]) or {}
    return {
        "value": _number(source.get("value")),
        "unit": definition["unit"],
        "trend_3y": [],
        "series": list(source.get("series") or []),
        "reason": source.get("reason"),
        "provenance": {"kind": "filing_account", "match": source.get("match")},
    }


def _catalog_card(company: dict[str, Any], definition: dict[str, str]) -> dict[str, Any]:
    source = (company.get(definition["source"]) or {}).get(definition["key"]) or {}
    value = source.get("value") if isinstance(source, dict) else source
    return {
        "value": value,
        "unit": source.get("unit") or definition["unit"] if isinstance(source, dict) else definition["unit"],
        "trend_3y": list(source.get("trend_3y") or []) if isinstance(source, dict) else [],
        "series": list(source.get("series") or []) if isinstance(source, dict) else [],
        "reason": source.get("reason") if isinstance(source, dict) else None,
        "provenance": {"kind": definition["source"], "key": definition["key"]},
    }


def _market_cap(
    company: dict[str, Any],
    user_inputs: dict[str, Any],
    currency_contract: dict[str, Any],
) -> tuple[float | None, dict[str, Any]]:
    """Return market cap in filing/model currency, never an inferred unit.

    Price × shares is a monetary input just as much as a manually supplied
    market cap.  The quote adapter therefore has to retain quote currency;
    callers without that metadata receive an actionable omission instead of a
    potentially mixed-currency EV bridge.
    """
    market = company.get("market") or {}
    multiples = market.get("multiples") or {}
    value = _number(multiples.get("market_cap"))
    if value is not None:
        quote = market.get("quote") or {}
        input_currency = multiples.get("currency") or market.get("currency") or quote.get("currency")
        normalized, reason = convert_monetary_input_to_calculation_currency(
            value, input_currency=input_currency, contract=currency_contract
        )
        meta = {
            "kind": "market_snapshot",
            "source": quote.get("source") or "market_adapter",
            "as_of": quote.get("asof"),
            "confidence": "high",
            "input_currency": input_currency,
            "calculation_currency": currency_contract.get("calculation_currency"),
        }
        if reason:
            meta["reason"] = reason
        return normalized, meta
    supplied = user_inputs.get("market_cap")
    if isinstance(supplied, dict):
        normalized, reason = convert_monetary_input_to_calculation_currency(
            supplied.get("value"), input_currency=supplied.get("currency"), contract=currency_contract
        )
        meta = {
            "kind": "user_input",
            "source": supplied.get("source") or "user_input",
            "as_of": supplied.get("as_of"),
            "confidence": supplied.get("confidence") or "medium",
            "input_currency": supplied.get("currency"),
            "calculation_currency": currency_contract.get("calculation_currency"),
        }
        if reason:
            meta["reason"] = reason
        return normalized, meta
    if _number(supplied) is not None:
        return None, {
            "kind": "user_input",
            "source": "user_input_unverified",
            "as_of": None,
            "confidence": "low",
            "reason": "missing:monetary_input_currency",
            "calculation_currency": currency_contract.get("calculation_currency"),
        }
    return None, {}


def _verified_items(user_inputs: dict[str, Any], key: str) -> list[dict[str, Any]]:
    block = user_inputs.get(key)
    if not isinstance(block, dict) or block.get("status") != "verified":
        return []
    items = block.get("items") or []
    if not isinstance(items, list) or not items:
        return []
    verified = []
    for item in items:
        if not isinstance(item, dict) or not item.get("source") or not item.get("as_of"):
            return []
        verified.append(item)
    return verified


def _computed_cards(
    company: dict[str, Any], user_inputs: dict[str, Any], currency_contract: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Resolve every card once; views later keep references only."""
    cards: dict[str, dict[str, Any]] = {}
    for card_id, definition in CARD_DEFINITIONS.items():
        if definition["source"] == "accounts":
            cards[card_id] = _account_card(company, definition)
        elif definition["source"] in {"metrics", "ma_metrics"}:
            cards[card_id] = _catalog_card(company, definition)

    # The engine only creates this proxy from verified, resolved filing inputs.
    accounts = company.get("accounts") or {}
    revenue = _number((accounts.get("REVENUE") or {}).get("value"))
    da = _number((accounts.get("DEPRECIATION") or {}).get("value"))
    capex = _number((accounts.get("CAPEX") or {}).get("value"))
    verified_filing_inputs = (
        company.get("parse_status") == "verified"
        and (accounts.get("DEPRECIATION") or {}).get("match")
        and (accounts.get("CAPEX") or {}).get("match")
    )
    maintenance = None
    if verified_filing_inputs and revenue not in (None, 0) and da is not None and capex is not None:
        maintenance = 100.0 * min(abs(da), abs(capex)) / revenue
    cards["maintenance_capex_burden"] = {
        "value": None if maintenance is None else round(maintenance, 4),
        "unit": "pct",
        "trend_3y": [],
        "reason": None if maintenance is not None else "missing:verified_depreciation_capex_and_revenue",
        "estimate": {
            "kind": "proxy",
            "estimate_policy_id": "min_da_capex_maintenance_v1",
            "formula": "min(abs(reported_D&A), abs(reported_Capex)) / revenue",
            "confidence": "medium",
            "is_reported_value": False,
            "visibility": "expert",
            "source_refs": [
                (accounts.get("DEPRECIATION") or {}).get("match"),
                (accounts.get("CAPEX") or {}).get("match"),
                (accounts.get("REVENUE") or {}).get("match"),
            ],
        } if maintenance is not None else None,
    }

    market_cap, market_meta = _market_cap(company, user_inputs, currency_contract)
    net_debt = _number(((company.get("ma_metrics") or {}).get("net_debt") or {}).get("value"))
    bridge = None if market_cap is None or net_debt is None else market_cap + net_debt
    cards["ev_bridge"] = {
        "value": None if bridge is None else {
            "market_cap": market_cap,
            "net_debt": net_debt,
            "enterprise_value": bridge,
        },
        "unit": "currency",
        "trend_3y": [],
        "reason": None if bridge is not None else (
            market_meta.get("reason") or "missing:market_cap_or_verified_net_debt"
        ),
        "provenance": market_meta,
    }

    peers = _verified_items(user_inputs, "verified_peer_multiples")
    comparable_metrics = ("pe", "pbr", "ev_ebitda", "psr")
    peer_medians: dict[str, float] = {}
    for metric in comparable_metrics:
        values = [_number(item.get(metric)) for item in peers]
        usable = [value for value in values if value is not None]
        if usable:
            peer_medians[metric] = median(usable)
    cards["trading_comps"] = {
        "value": {"peer_count": len(peers), "median": peer_medians} if peers and peer_medians else None,
        "unit": "mixed",
        "trend_3y": [],
        "reason": None if peers and peer_medians else "missing:verified_peer_multiples",
        "provenance": {"kind": "verified_input", "sources": sorted({str(item["source"]) for item in peers})} if peers else {},
    }

    segments = _verified_items(user_inputs, "verified_segments")
    cards["segment"] = {
        "value": deepcopy(segments) if segments else None,
        "unit": "mixed",
        "trend_3y": [],
        "reason": None if segments else "missing:verified_segment_inputs",
        "provenance": {"kind": "verified_input"} if segments else {},
    }
    qoe = user_inputs.get("verified_qoe")
    qoe_ok = isinstance(qoe, dict) and qoe.get("status") == "verified" and qoe.get("source") and qoe.get("as_of") and qoe.get("items")
    cards["full_qoe"] = {
        "value": deepcopy(qoe.get("items")) if qoe_ok else None,
        "unit": "mixed",
        "trend_3y": [],
        "reason": None if qoe_ok else "missing:verified_note_level_qoe_inputs",
        "provenance": {"kind": "verified_input", "source": qoe.get("source"), "as_of": qoe.get("as_of")} if qoe_ok else {},
    }

    for card_id, card in cards.items():
        card["id"] = card_id
        card["definition"] = deepcopy(CARD_DEFINITIONS[card_id])
        if card_id in {"fcf", "fcf_margin", "earnings_quality"} and card.get("value") is not None:
            card["estimate"] = {
                "kind": "derived",
                "formula": {
                    "fcf": "CFO - abs(Capex)",
                    "fcf_margin": "FCF / revenue",
                    "earnings_quality": "CFO / net_income",
                }[card_id],
                "confidence": "high",
                "is_reported_value": False,
            }
        elif card_id == "ebitda_proxy" and card.get("value") is not None:
            card["estimate"] = {
                "kind": "proxy",
                "formula": "operating_income + abs(reported_D&A)",
                "confidence": "medium",
                "is_reported_value": False,
            }
    return cards


def _model(
    model_id: str,
    status: str,
    *,
    value: Any = None,
    components: dict[str, Any] | None = None,
    required_inputs: list[str] | None = None,
    reason: str | None = None,
    estimate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "id": model_id,
        "status": status,
        "value": value,
        "components": components or {},
        "required_inputs": required_inputs or [],
        "reason": reason,
        "definition": deepcopy(MODEL_DEFINITIONS[model_id]),
    }
    if estimate:
        result["estimate"] = estimate
    return result


def _liquidity_model(cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ("current_ratio", "cash", "gross_debt", "net_debt", "interest_coverage")
    values = {card_id: cards[card_id]["value"] for card_id in ids if cards.get(card_id, {}).get("value") is not None}
    if not values:
        return _model("liquidity_coverage", "omitted", reason="missing:liquidity_or_coverage_inputs")
    return _model(
        "liquidity_coverage",
        "computed" if len(values) >= 2 else "partial",
        value=values,
        components={"available_metrics": list(values)},
        reason=None if len(values) >= 2 else "only_one_coverage_metric_available",
        estimate={"kind": "snapshot", "confidence": "high", "is_forecast": False},
    )


def _delever_model(cards: dict[str, dict[str, Any]], user_inputs: dict[str, Any]) -> dict[str, Any]:
    net_debt = _number(cards.get("net_debt", {}).get("value"))
    ebitda = _number(cards.get("ebitda_proxy", {}).get("value"))
    fcf = _number(cards.get("fcf", {}).get("value"))
    if net_debt is not None and net_debt <= 0:
        return _model("delever_path", "not_applicable", reason="not_applicable:net_cash_no_deleveraging_path")
    if net_debt is None or ebitda is None or ebitda <= 0 or fcf is None:
        return _model("delever_path", "omitted", reason="missing:net_debt_positive_ebitda_or_fcf")
    assumptions = user_inputs.get("delever_assumptions") or {}
    retention = _number(assumptions.get("fcf_retention"))
    if retention is None or assumptions.get("horizon_years") is None:
        return _model(
            "delever_path",
            "needs_input",
            required_inputs=[
                key for key in ("fcf_retention", "horizon_years")
                if assumptions.get(key) is None
            ],
            reason="input:explicit_fcf_retention_and_horizon_required",
        )
    try:
        years = int(assumptions["horizon_years"])
    except (TypeError, ValueError):
        return _model("delever_path", "omitted", reason="invalid:fcf_retention_or_horizon")
    if not 0 <= retention <= 1 or not 1 <= years <= 10:
        return _model("delever_path", "omitted", reason="invalid:fcf_retention_or_horizon")
    path = []
    debt = net_debt
    annual_paydown = fcf * retention
    for year in range(years + 1):
        path.append({"year": year, "net_debt": debt, "net_debt_to_ebitda": debt / ebitda})
        debt -= annual_paydown
    return _model(
        "delever_path",
        "computed",
        value={"start": path[0]["net_debt_to_ebitda"], "end": path[-1]["net_debt_to_ebitda"]},
        components={"path": path, "annual_fcf_applied": annual_paydown},
        estimate={
            "kind": "assumption",
            "formula": "net_debt[t+1] = net_debt[t] - FCF * retention",
            "assumptions": {"constant_fcf": fcf, "fcf_retention": retention, "horizon_years": years},
            "confidence": "low",
        },
    )


def _fcf_yield_model(
    cards: dict[str, dict[str, Any]], market_cap: float | None, market_meta: dict[str, Any]
) -> dict[str, Any]:
    fcf = _number(cards.get("fcf", {}).get("value"))
    if fcf is None:
        return _model("fcf_yield_snapshot", "omitted", reason="missing:fcf")
    if market_cap is None or market_cap <= 0:
        return _model(
            "fcf_yield_snapshot",
            "needs_input",
            required_inputs=["market_cap"],
            reason="input:market_cap_required_for_fcf_yield",
        )
    net_debt = _number(cards.get("net_debt", {}).get("value"))
    ev = None if net_debt is None else market_cap + net_debt
    return _model(
        "fcf_yield_snapshot",
        "computed" if ev not in (None, 0) else "partial",
        value={
            "fcf_to_equity": fcf / market_cap,
            "fcf_to_ev": None if ev in (None, 0) else fcf / ev,
        },
        components={"fcf": fcf, "market_cap": market_cap, "enterprise_value": ev},
        reason=None if ev not in (None, 0) else "missing:verified_net_debt_for_ev_yield",
        estimate={"kind": "snapshot_ratio", "confidence": market_meta.get("confidence") or "medium", "is_forecast": False},
    )


def _dcf_inputs(company: dict[str, Any], user_inputs: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    seed = ((company.get("assumption_defaults") or {}).get("seeded_from_statements") or {})
    assumptions = dict(user_inputs.get("valuation_assumptions") or {})
    operating_margin_pct = _number(((company.get("metrics") or {}).get("operating_margin") or {}).get("value"))
    filing = {
        "revenue": _number(((company.get("accounts") or {}).get("REVENUE") or {}).get("value")),
        "ebit_margin": None if operating_margin_pct is None else operating_margin_pct / 100.0,
        "tax_rate": _number(seed.get("tax_rate")),
        "operating_nwc_to_sales": _number(seed.get("operating_nwc_to_sales")),
        "capex_to_sales": _number(seed.get("capex_to_sales")),
        "da_to_sales": _number(seed.get("da_to_sales")),
        "net_debt": _number(((company.get("ma_metrics") or {}).get("net_debt") or {}).get("value")),
    }
    combined = {**filing, **assumptions}
    missing = [
        key
        for key in ("revenue", "ebit_margin", "tax_rate", "operating_nwc_to_sales", "capex_to_sales", "da_to_sales")
        if combined.get(key) is None
    ]
    return combined, missing


def _reverse_dcf_model(
    company: dict[str, Any], user_inputs: dict[str, Any], market_cap: float | None
) -> dict[str, Any]:
    inputs, missing_filing = _dcf_inputs(company, user_inputs)
    if inputs.get("net_debt") is None:
        missing_filing.append("net_debt")
    if missing_filing:
        return _model("reverse_dcf", "omitted", reason="missing:filing_inputs:" + ",".join(missing_filing))
    required = [
        key for key in ("projection_years", "wacc", "terminal_growth")
        if _number(inputs.get(key)) is None
    ]
    if market_cap is None:
        required.append("market_cap")
    if required:
        return _model(
            "reverse_dcf",
            "needs_input",
            required_inputs=required,
            reason="input:explicit_market_and_discount_assumptions_required",
        )
    wacc = float(inputs["wacc"])
    terminal_growth = float(inputs["terminal_growth"])
    if terminal_growth > 0.03 or wacc <= terminal_growth:
        return _model("reverse_dcf", "omitted", reason="invalid:wacc_or_terminal_growth")

    base = {
        "projection_years": int(inputs["projection_years"]),
        "ebit_margin": inputs["ebit_margin"],
        "tax_rate": inputs["tax_rate"],
        "operating_nwc_to_sales": inputs["operating_nwc_to_sales"],
        "capex_to_sales": inputs["capex_to_sales"],
        "da_to_sales": inputs["da_to_sales"],
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "net_debt": inputs["net_debt"],
    }
    lo = float(inputs.get("reverse_cagr_min", -0.20))
    hi = float(inputs.get("reverse_cagr_max", 0.40))

    def equity_at(growth: float) -> float | None:
        try:
            result = fcff_dcf(revenue0=float(inputs["revenue"]), assumptions={**base, "revenue_cagr": growth})
        except (TypeError, ValueError):
            return None
        return _number(result.get("equity_value")) if result.get("ok") else None

    value_lo, value_hi = equity_at(lo), equity_at(hi)
    if value_lo is None or value_hi is None:
        return _model("reverse_dcf", "omitted", reason="invalid:dcf_failed_at_search_bounds")
    bound = "interior"
    if market_cap <= value_lo:
        solved, modeled, bound = lo, value_lo, "lower"
    elif market_cap >= value_hi:
        solved, modeled, bound = hi, value_hi, "upper"
    else:
        left, right = lo, hi
        modeled = None
        for _ in range(60):
            solved = (left + right) / 2.0
            modeled = equity_at(solved)
            if modeled is None:
                return _model("reverse_dcf", "omitted", reason="invalid:dcf_failed_during_search")
            if abs(modeled - market_cap) / max(abs(market_cap), 1.0) < 0.0001:
                break
            if modeled < market_cap:
                left = solved
            else:
                right = solved
    return _model(
        "reverse_dcf",
        "computed" if bound == "interior" else "partial",
        value=solved,
        components={"implied_revenue_cagr": solved, "market_cap": market_cap, "model_equity_value": modeled, "bound": bound},
        reason=None if bound == "interior" else "market_cap_outside_explicit_search_range",
        estimate={
            "kind": "reverse_solve",
            "formula": "solve revenue CAGR where FCFF equity value equals market cap",
            "assumptions": {**base, "search_min": lo, "search_max": hi},
            "confidence": "medium",
        },
    )


def _scenario_model(
    company: dict[str, Any],
    user_inputs: dict[str, Any],
    ev_bridge: dict[str, Any] | None,
) -> dict[str, Any]:
    valuation = company.get("valuation") or {}
    if valuation.get("status") != "scenario":
        revenue = _number(((company.get("accounts") or {}).get("REVENUE") or {}).get("value"))
        if revenue is None:
            if ev_bridge:
                return _model(
                    "scenario_dcf_ev_bridge",
                    "partial",
                    value={"enterprise_value_bridge": ev_bridge.get("enterprise_value")},
                    components={"ev_bridge": ev_bridge},
                    reason="missing:reported_revenue_for_scenario_dcf",
                    estimate={"kind": "derived_bridge", "confidence": "high", "is_forecast": False},
                )
            return _model("scenario_dcf_ev_bridge", "omitted", reason="missing:reported_revenue_for_scenario_dcf")

        explicit = dict(user_inputs.get("valuation_assumptions") or {})
        seed = ((company.get("assumption_defaults") or {}).get("seeded_from_statements") or {})
        operating_margin_pct = _number(((company.get("metrics") or {}).get("operating_margin") or {}).get("value"))
        scenarios = []
        if explicit and operating_margin_pct is not None:
            scenarios = build_seeded_scenarios(
                operating_margin_pct=operating_margin_pct,
                seed=seed,
                explicit_assumptions=explicit,
            )
        if not scenarios:
            required_keys = [
                "projection_years", "revenue_cagr", "ebit_margin", "tax_rate",
                "operating_nwc_to_sales", "capex_to_sales", "da_to_sales", "wacc", "terminal_growth",
            ]
            base = explicit
            raw_scenarios = explicit.get("scenarios")
            if isinstance(raw_scenarios, list) and raw_scenarios and isinstance(raw_scenarios[0], dict):
                base = raw_scenarios[0].get("assumptions") or {}
            required = [key for key in required_keys if base.get(key) is None]
            if explicit.get("accept_historical_seed") is True:
                required = [
                    key for key in required
                    if key not in {"capex_to_sales", "da_to_sales", "tax_rate"} or seed.get(key) is None
                ]
            if not required and explicit:
                return _model(
                    "scenario_dcf_ev_bridge",
                    "omitted",
                    reason="invalid:scenario_assumptions_rejected_by_valuation_contract",
                )
            if ev_bridge:
                return _model(
                    "scenario_dcf_ev_bridge",
                    "partial",
                    value={"enterprise_value_bridge": ev_bridge.get("enterprise_value")},
                    components={"ev_bridge": ev_bridge},
                    required_inputs=required,
                    reason="input:explicit_scenario_assumptions_required_for_dcf",
                    estimate={"kind": "derived_bridge", "confidence": "high", "is_forecast": False},
                )
            return _model(
                "scenario_dcf_ev_bridge",
                "needs_input",
                required_inputs=required,
                reason="input:explicit_scenario_assumptions_required",
            )
        try:
            valuation = run_valuation_bundle(
                revenue0=revenue,
                ebitda0=_number(((company.get("ma_metrics") or {}).get("ebitda_proxy") or {}).get("value")),
                net_debt=_number(((company.get("ma_metrics") or {}).get("net_debt") or {}).get("value")),
                shares_out=_number(company.get("shares_out")),
                share_basis=company.get("share_basis") or user_inputs.get("share_basis"),
                share_metadata=company.get("share_metadata") or user_inputs.get("share_metadata"),
                scenarios=scenarios,
            )
        except (TypeError, ValueError) as exc:
            return _model(
                "scenario_dcf_ev_bridge",
                "omitted",
                reason=f"invalid:scenario_assumptions:{exc}",
            )
    if valuation.get("status") != "scenario":
        if valuation.get("status") == "blocked_quality":
            reasons = [
                (scenario.get("fcff_dcf") or {}).get("reason")
                for scenario in valuation.get("scenarios") or []
                if (scenario.get("fcff_dcf") or {}).get("reason")
            ]
            detail = reasons[0] if reasons else valuation.get("reason") or "no_successful_fcff_scenario"
            return _model(
                "scenario_dcf_ev_bridge",
                "omitted",
                reason="invalid:scenario_assumptions:" + str(detail),
            )
        return _model("scenario_dcf_ev_bridge", "omitted", reason="missing:supported_scenario_dcf")
    successful_scenarios = [
        scenario
        for scenario in valuation.get("scenarios") or []
        if (scenario.get("fcff_dcf") or {}).get("ok")
    ]
    if not successful_scenarios:
        reasons = [
            (scenario.get("fcff_dcf") or {}).get("reason")
            for scenario in valuation.get("scenarios") or []
            if (scenario.get("fcff_dcf") or {}).get("reason")
        ]
        return _model(
            "scenario_dcf_ev_bridge",
            "omitted",
            reason="invalid:scenario_assumptions:" + (str(reasons[0]) if reasons else "no_successful_fcff_scenario"),
        )
    return _model(
        "scenario_dcf_ev_bridge",
        "computed" if ev_bridge else "partial",
        value={"value_band": valuation.get("value_band"), "enterprise_value_bridge": (ev_bridge or {}).get("enterprise_value")},
        components={"scenarios": deepcopy(successful_scenarios), "ev_bridge": deepcopy(ev_bridge)},
        reason=None if ev_bridge else "missing:market_cap_or_verified_net_debt_for_ev_bridge",
        estimate={
            "kind": "scenario_assumption",
            "formula": "FCFF = EBIT*(1-tax) + D&A - Capex - delta_NWC",
            "assumptions": deepcopy(user_inputs.get("valuation_assumptions") or {}),
            "confidence": "low",
            "is_price_target": False,
        },
    )


def _trading_comps_model(cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    card = cards.get("trading_comps") or {}
    if card.get("value") is None:
        return _model("trading_comps", "omitted", reason="missing:verified_peer_multiples")
    return _model(
        "trading_comps",
        "computed",
        value=deepcopy(card["value"]),
        components={"provenance": deepcopy(card.get("provenance") or {})},
        estimate={"kind": "derived_median", "formula": "median of verified peer observations", "confidence": "high"},
    )


def _sotp_model(
    cards: dict[str, dict[str, Any]],
    user_inputs: dict[str, Any],
    currency_contract: dict[str, Any],
) -> dict[str, Any]:
    segments = (cards.get("segment") or {}).get("value") or []
    if not segments:
        return _model("sotp", "omitted", reason="missing:verified_segment_inputs")
    parts = []
    for segment in segments:
        direct, direct_reason = convert_monetary_input_to_calculation_currency(
            segment.get("enterprise_value"),
            input_currency=segment.get("currency"),
            contract=currency_contract,
        )
        metric, metric_reason = convert_monetary_input_to_calculation_currency(
            segment.get("metric_value"),
            input_currency=segment.get("currency"),
            contract=currency_contract,
        )
        multiple = _number(segment.get("multiple"))
        enterprise_value = direct if direct is not None else (metric * multiple if metric is not None and multiple is not None else None)
        if enterprise_value is None:
            currency_reason = direct_reason or metric_reason
            return _model(
                "sotp",
                "omitted",
                reason=currency_reason or "missing:verified_segment_value_or_metric_and_multiple",
            )
        parts.append({
            "id": segment.get("id"), "name": segment.get("name"),
            "enterprise_value": enterprise_value, "source": segment.get("source"),
            "as_of": segment.get("as_of"),
            "input_currency": segment.get("currency"),
        })
    gross_ev = sum(part["enterprise_value"] for part in parts)
    discount_raw = (user_inputs.get("sotp_assumptions") or {}).get("conglomerate_discount")
    discount = _number(discount_raw)
    if discount is not None and not 0 <= discount < 1:
        return _model("sotp", "omitted", reason="invalid:conglomerate_discount")
    after_discount = gross_ev if discount is None else gross_ev * (1.0 - discount)
    net_debt = _number(cards.get("net_debt", {}).get("value"))
    equity = None if net_debt is None else after_discount - net_debt
    return _model(
        "sotp",
        "computed" if equity is not None else "partial",
        value={"gross_segment_ev": gross_ev, "after_discount_ev": after_discount, "equity_value": equity},
        components={"segments": parts},
        reason=None if equity is not None else "missing:verified_net_debt_for_equity_bridge",
        estimate={
            "kind": "verified_input_calculation",
            "formula": "sum(segment EV) * (1 - explicit discount) - net debt",
            "assumptions": {"conglomerate_discount": discount, "discount_applied": discount is not None},
            "confidence": "medium",
        },
    )


def _computed_models(
    company: dict[str, Any],
    cards: dict[str, dict[str, Any]],
    user_inputs: dict[str, Any],
    currency_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    market_cap, market_meta = _market_cap(company, user_inputs, currency_contract)
    bridge = cards.get("ev_bridge", {}).get("value")
    period = company.get("period") or {}
    selected = period.get("selected")
    period_kind = str(period.get("period_kind") or "")
    annual_or_ttm = (selected in {None, "annual", "ttm"}) and "quarter" not in period_kind
    if annual_or_ttm:
        delever = _delever_model(cards, user_inputs)
        fcf_yield = _fcf_yield_model(cards, market_cap, market_meta)
        reverse_dcf = _reverse_dcf_model(company, user_inputs, market_cap)
        scenario = _scenario_model(company, user_inputs, bridge)
    else:
        reason = "blocked_quality:model_requires_annual_or_ttm_base"
        delever = _model("delever_path", "omitted", reason=reason)
        fcf_yield = _model("fcf_yield_snapshot", "omitted", reason=reason)
        reverse_dcf = _model("reverse_dcf", "omitted", reason=reason)
        scenario = _model("scenario_dcf_ev_bridge", "omitted", reason=reason)
    return {
        "liquidity_coverage": _liquidity_model(cards),
        "delever_path": delever,
        "fcf_yield_snapshot": fcf_yield,
        "reverse_dcf": reverse_dcf,
        "scenario_dcf_ev_bridge": scenario,
        "trading_comps": _trading_comps_model(cards),
        "sotp": _sotp_model(cards, user_inputs, currency_contract),
    }


def build_unified_views(
    company: dict[str, Any],
    *,
    user_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete visible contract from a normalized company result."""
    user_inputs = user_inputs or {}
    financial = is_financial(company.get("entity_policy"))
    source = company.get("source") or ((company.get("corp") or {}).get("source")) or (company.get("entity_policy") or {}).get("source")
    source_currency = company.get("currency")
    for account in (company.get("accounts") or {}).values():
        if source_currency:
            break
        if not isinstance(account, dict):
            continue
        unit = account.get("unit")
        candidate = (unit or {}).get("currency") if isinstance(unit, dict) else account.get("currency")
        if candidate:
            source_currency = str(candidate).upper()
            break
    currency_contract = build_currency_contract(
        source_adapter=source,
        source_currency=source_currency,
        display_currency=user_inputs.get("display_currency"),
        fx_input=user_inputs.get("fx"),
    )
    # Cards and models are calculated only after the filing currency is known.
    # Models retain this calculation currency; only card values are a UI
    # presentation surface that may be converted by an explicit FX contract.
    calculated_cards = _computed_cards(company, user_inputs, currency_contract)
    calculated_models = _computed_models(company, calculated_cards, user_inputs, currency_contract)
    for card in calculated_cards.values():
        if card.get("unit") != "currency":
            continue
        card["source_currency"] = source_currency
        card["display_currency"] = currency_contract.get("display_currency")
        card["value"] = convert_currency_value(card.get("value"), currency_contract)
        for point in card.get("series") or []:
            if isinstance(point, dict):
                point["value"] = convert_currency_value(point.get("value"), currency_contract)
    for model in calculated_models.values():
        model["calculation_currency"] = currency_contract.get("calculation_currency")
        model["presentation_currency"] = currency_contract.get("calculation_currency")
        model["currency_policy"] = "filing_currency_only"

    card_registry: dict[str, dict[str, Any]] = {}
    model_registry: dict[str, dict[str, Any]] = {}
    card_omissions: list[dict[str, str]] = []
    model_omissions: list[dict[str, str]] = []
    requested_cards = dict.fromkeys(card_id for view in VIEW_DEFINITIONS.values() for card_id in view["card_refs"])
    requested_models = dict.fromkeys(model_id for view in VIEW_DEFINITIONS.values() for model_id in view["model_refs"])

    for card_id in requested_cards:
        decision = card_decision(card_id, calculated_cards.get(card_id), financial_entity=financial)
        if decision["visible"]:
            card_registry[card_id] = calculated_cards[card_id]
        else:
            card_omissions.append({"id": card_id, "status": decision["status"], "reason": decision["reason"]})
    for model_id in requested_models:
        decision = model_decision(model_id, calculated_models.get(model_id), financial_entity=financial)
        if decision["visible"]:
            model_registry[model_id] = calculated_models[model_id]
        else:
            model_omissions.append({"id": model_id, "status": decision["status"], "reason": decision["reason"]})

    views = {}
    for view_id in VIEW_ORDER:
        definition = VIEW_DEFINITIONS[view_id]
        views[view_id] = {
            "id": view_id,
            "label_ko": definition["label_ko"],
            "audience": definition["audience"],
            "goal_ko": definition["goal_ko"],
            "card_refs": [card_id for card_id in definition["card_refs"] if card_id in card_registry],
            "model_refs": [model_id for model_id in definition["model_refs"] if model_id in model_registry],
        }

    return {
        "schema": SCHEMA,
        "definitions_version": DEFINITIONS_VERSION,
        "default_view": DEFAULT_VIEW,
        "view_order": list(VIEW_ORDER),
        "card_registry": card_registry,
        "model_registry": model_registry,
        "currency": currency_contract,
        "views": views,
        "policy": {
            "cards_calculated_once": True,
            "views_reference_registry_by_id": True,
            "unavailable_hidden_from_visible_surface": True,
            "audit_retains_omission_status": True,
            "financial_entity_industrial_framework": "omitted",
            "arbitrary_estimates_allowed": False,
        },
        "audit": {
            "source_adapter": source,
            "entity_class": (company.get("entity_policy") or {}).get("entity_class"),
            "financial_entity": financial,
            "card_omissions": card_omissions,
            "model_omissions": model_omissions,
        },
    }


def attach_unified_views(
    company: dict[str, Any],
    *,
    user_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy with ``unified_views`` attached; source adapters share it."""
    output = deepcopy(company)
    output["unified_views"] = build_unified_views(output, user_inputs=user_inputs)
    return output
