"""Evidence-backed CR/PE review checklist. No distress score or recommendation."""
from datetime import date, timedelta
from math import isfinite

from .pe_cr_evidence import reviewed_facts
from .pe_cr_screen_inputs import cash_plan_13w, governance_profile, industry_metrics


SECTIONS = (
    ("profitability", "수익성", ("operating_income", "operating_margin", "ebitda", "ebitda_margin", "cogs_to_sales")),
    ("cash_flow", "현금흐름", ("cfo", "fcf", "operating_nwc", "operating_nwc_change", "ccc_days")),
    ("repayment", "상환능력", ("interest_coverage", "dscr")),
    ("capital_structure", "재무구조", ("net_debt", "net_debt_to_ebitda", "debt_ratio", "capital_erosion_ratio")),
    ("short_term_liquidity", "단기유동성", ("current_ratio", "current_liabilities_share", "debt_due_within_1y", "liquidity_coverage_1y", "financing_principal_due_1y_share")),
    ("industry", "산업경쟁력", ("order_backlog", "new_orders")),
    ("governance", "지배구조", ()),
)


def _numeric(value):
    return type(value) in (int, float) and isfinite(value)


def _annual_period(bundle):
    try:
        start = date.fromisoformat(bundle.get("fiscal_year_start"))
        end = date.fromisoformat(bundle.get("fiscal_year_end"))
    except (TypeError, ValueError):
        return None
    # Accept normal 52/53-week calendars, not stub fiscal periods.
    return (start, end) if 350 <= (end - start).days + 1 <= 380 else None


def _value(bundle, key, start, end, evidence=None):
    fact = ((bundle.get("series") or {}).get("PECR_" + key) or {}).get("annual") or {}
    reason = fact.get("reason") or ""
    if evidence and (not fact or reason.startswith(("missing:dart_fact_", "missing:sec_exact_period_fact_"))):
        fact = evidence.get((key, start, end), fact)
    unit = fact.get("unit") or {}
    if (fact.get("availability") != "available" or fact.get("quality") not in {"reported", "deterministic_derived"}
            or fact.get("nature") != "flow" or fact.get("period_start") != start or fact.get("period_end") != end
            or fact.get("fs_div") != bundle.get("fs_div") or unit.get("kind") != "currency"
            or unit.get("scale") != 1 or unit.get("currency") != bundle.get("currency")
            or not fact.get("provenance") or not _numeric(fact.get("value"))):
        return None, None
    return fact["value"], fact["provenance"]


def _annual_history(canonical, history, end, reviewed_current, reviewed_by_end):
    if not end or not canonical.get("entity_id") or type(canonical.get("fiscal_year")) is not int:
        return []
    cutoff = date.fromisoformat(end)
    fy_end = date.fromisoformat(canonical["fiscal_year_end"])
    latest_year = canonical["fiscal_year"] - int(cutoff < fy_end)
    groups = {}
    for b in (canonical, *history):
        if (not isinstance(b, dict) or b.get("schema_version") != "canonical-financial-facts/1"
                or any(b.get(k) != canonical.get(k) for k in ("entity_id", "source", "fs_div", "currency"))):
            continue
        year, p = b.get("fiscal_year"), _annual_period(b)
        if p and p[1] <= cutoff and type(year) is int and latest_year - 2 <= year <= latest_year:
            groups.setdefault(year, []).append((b, p))
    points = []
    for year in range(latest_year, latest_year - 3, -1):
        observations = []
        for b, (first, last) in groups.get(year, []):
            start, finish = first.isoformat(), last.isoformat()
            verified = reviewed_current if b is canonical else None
            if b is not canonical and finish in reviewed_by_end:
                verified = reviewed_facts(reviewed_by_end[finish], b)
            values = {key: _value(b, key, start, finish, verified) for key in ("op", "cfo", "revenue", "cogs", "interest")}
            op, cfo, sales, cogs, interest = [values[k][0] for k in ("op", "cfo", "revenue", "cogs", "interest")]
            metrics = {"operating_income": op, "cfo": cfo,
                       "cogs_to_sales": abs(cogs) / sales if cogs is not None and sales is not None and sales > 0 else None,
                       "interest_coverage": op / abs(interest) if op is not None and interest not in (None, 0) else None}
            observations.append({"fiscal_year": year, "start": start, "end": finish, "metrics": metrics,
                                 "inputs": {k: {"value": v[0], "provenance": v[1]} for k, v in values.items() if v[1]}, "reason": None})
        signatures = {(o["start"], o["end"], tuple((k, v["value"]) for k, v in o["inputs"].items())) for o in observations}
        if len(signatures) == 1:
            points.append(observations[0])
        else:
            points.append({"fiscal_year": year, "metrics": {}, "start": None, "end": None,
                           "reason": "conflict:duplicate_annual_evidence" if observations else "missing:complete_annual_evidence"})
    return points


def _consecutive(points):
    return all(row.get("start") and row.get("end") for row in points) and all(
        date.fromisoformat(older["end"]) + timedelta(days=1) == date.fromisoformat(newer["start"])
        for newer, older in zip(points, points[1:]))


def _signal(key, section, label, state, reason=None, evidence=None):
    return {"id": key, "section": section, "label_ko": label, "status": state, "reason": reason, "observations": evidence or []}


def _trend(key, section, label, points, metric, size, predicate, financial):
    if financial:
        return _signal(key, section, label, "not_applicable", "not_applicable:financial_entity_industrial_trend")
    rows = points[:size]
    data = [{"fiscal_year": row["fiscal_year"], "period_end": row["end"], "value": row["metrics"].get(metric)} for row in rows]
    values = [row["value"] for row in data]
    if len(rows) != size or not _consecutive(rows) or any(not _numeric(x) for x in values):
        return _signal(key, section, label, "unavailable", "requires:consecutive_comparable_annual_observations", data)
    return _signal(key, section, label, "triggered" if predicate(values) else "not_triggered", evidence=data)


def _current_signal(key, section, label, cards, card_key, predicate):
    card = cards.get(card_key) or {}
    v, reason = card.get("value"), card.get("reason") or "missing:card_" + card_key
    if not _numeric(v):
        return _signal(key, section, label, "not_applicable" if reason.startswith("not_applicable:") else "unavailable", reason)
    return _signal(key, section, label, "triggered" if predicate(v) else "not_triggered",
                   evidence=[{"card_id": card_key, "value": v, "period_end": card.get("period_end")}])


def build_screen(canonical, result, *, history, period, start, end, financial, reviewed_current, inputs=None):
    inputs = inputs if inputs is not None else {}
    if not isinstance(inputs, dict):
        raise ValueError("invalid:screen_inputs")
    annual_reviewed = inputs.get("annual_reviewed_disclosures", {})
    if not isinstance(annual_reviewed, dict):
        raise ValueError("invalid:screen_annual_reviewed_disclosures")
    points = [] if financial else _annual_history(canonical, history, end, reviewed_current, annual_reviewed)
    cash = cash_plan_13w(inputs.get("cash_plan"), canonical)
    industry = industry_metrics(inputs.get("industry"), canonical, start, end)
    governance = governance_profile(inputs.get("governance"), canonical, start, end, period=period,
                                    dart_audit=inputs.get("dart_audit"), dart_ownership=inputs.get("dart_ownership"))
    cards = result["cards"]
    signals = [
        _trend("operating_loss_2y", "profitability", "영업적자 2년 연속", points, "operating_income", 2, lambda v: all(x < 0 for x in v), financial),
        _trend("rising_cost_ratio_3y", "profitability", "3개년 매출원가율 연속 상승", points, "cogs_to_sales", 3, lambda v: v[0] > v[1] > v[2], financial),
        _trend("negative_cfo_2y", "cash_flow", "영업현금 유출 2년 연속", points, "cfo", 2, lambda v: all(x < 0 for x in v), financial),
        _trend("interest_coverage_under_1_3y", "repayment", "이자보상배율 3년 연속 1배 미만", points, "interest_coverage", 3, lambda v: all(x < 1 for x in v), financial),
        _current_signal("dscr_under_1", "repayment", "검증된 실적 DSCR 1배 미만", cards, "dscr", lambda v: v < 1),
        _current_signal("negative_equity", "capital_structure", "총자본 음수", cards, "book_equity", lambda v: v < 0),
        _current_signal("equity_below_issued_capital", "capital_structure", "지배주주 자본이 납입자본 항목보다 작음", cards, "capital_erosion_ratio", lambda v: v > 0),
        _current_signal("cash_below_1y_principal", "short_term_liquidity", "가용현금만으로 1년 원금 미충족", cards, "liquidity_coverage_1y", lambda v: v < 1),
    ]
    if cash["reason"] is not None:
        signals.append(_signal("cash_plan_below_minimum", "short_term_liquidity", "13주 시나리오 최소현금 미달", "unavailable", cash["reason"]))
    else:
        breach = cash["first_week_below_minimum"]
        signals.append(_signal("cash_plan_below_minimum", "short_term_liquidity", "13주 시나리오 최소현금 미달",
                               "triggered" if breach is not None else "not_triggered",
                               evidence=[{"classification": "scenario", "first_week_below_minimum": breach}]))
    prior_industry = {"rows": []}
    if inputs.get("prior_industry") is not None and period == "annual" and _consecutive(points[:2]) and len(points) >= 2 and points[0]["end"] == end:
        prior_industry = industry_metrics(inputs["prior_industry"], canonical, points[1]["start"], points[1]["end"])
    for metric, label in (("capacity_utilization", "가동률 하락"), ("order_backlog", "동일 범위 수주잔고 감소")):
        prior = {(row["scope"], row["unit"]): row for row in prior_industry["rows"] if row["metric"] == metric}
        pairs = [{"current": row, "prior": prior[(row["scope"], row["unit"])]} for row in industry["rows"]
                 if row["metric"] == metric and (row["scope"], row["unit"]) in prior]
        state = ("triggered" if any(p["current"]["value"] < p["prior"]["value"] for p in pairs) else "not_triggered") if pairs else "unavailable"
        signals.append(_signal(metric + "_down", "industry", label, state, None if pairs else "requires:verified_comparable_fy_industry_pairs", pairs))
    audit = governance["audit"] or {}
    modified = audit.get("opinion")
    signals.append(_signal("modified_audit_opinion", "governance", "변형 감사의견 공시",
                           ("not_triggered" if modified == "unmodified" else "triggered") if modified else "unavailable",
                           None if modified else governance["audit_reason"], [audit] if audit else []))
    return {"schema_version": "kfa-cr-pe-screen/1", "period_start": start, "period_end": end,
            "sections": [{"id": key, "label_ko": label, "card_ids": [k for k in keys if k in cards]} for key, label, keys in SECTIONS],
            "lens_order": {"cr": ["short_term_liquidity", "repayment", "cash_flow", "capital_structure", "profitability", "industry", "governance"],
                           "pe": ["profitability", "cash_flow", "industry", "capital_structure", "repayment", "short_term_liquidity", "governance"]},
            "annual_history": points, "signals": signals, "cash_plan_13w": cash, "industry_observations": industry,
            "governance": governance, "references": {"funding": "disclosure_profile", "comparables": "peer_comparison"},
            "no_risk_rating_or_investment_recommendation": True}
