"""Evidence-preserving PE / corporate restructuring diagnostics.

Operates on canonical DART/SEC facts; never substitutes cash interest for P&L
interest, finance costs for interest, or broad receivables for trade receivables.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path


def config():
    return json.loads((Path(__file__).resolve().parents[1] / "config/pe_cr_inputs.json").read_text())


def account_specs():
    return {"PECR_" + key: {
        "nature": "balance" if sj == "BS" else "flow", "statement": sj,
        "source_ids": dart, "source_names": [], "sec_concepts": sec,
        "unit_kind": "currency",
    } for key, (sj, dart, sec) in config()["inputs"].items()}


class Unavailable(ValueError):
    pass


def build_pe_cr(canonical, *, selected_period="annual", history=(),
                entity_policy=None, industry="manufacturing"):
    """History contains canonical bundles, including opening BS for averages.

    EBITDA reuses the existing P1 strict disclosure calculator.
    """
    if canonical.get("schema_version") != "canonical-financial-facts/1":
        raise ValueError("unsupported_canonical_schema")
    if selected_period not in {"annual", "Q1", "Q2", "Q3", "Q4"}:
        raise ValueError("invalid_period")
    cfg = config()
    financial = bool((entity_policy or {}).get("is_financial_entity")) or industry == "financial"
    kit = cfg["kits"]["financial" if financial else industry]
    cards = {}
    used = []

    def cell(bundle, key, period):
        s = bundle.get("series", {}).get("PECR_" + key, {})
        return (s.get("annual") if period == "annual" else s.get("quarters", {}).get(period)) or {}

    def read(key, *, opening=False):
        f = cell(canonical, key, selected_period)
        sj = cfg["inputs"][key][0]
        if opening:
            target = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
            choices = []
            for bundle in [canonical, *history]:
                if any(bundle.get(k) != canonical.get(k) for k in ("entity_id", "fs_div", "currency", "source")):
                    continue
                for p in ("annual", "Q1", "Q2", "Q3", "Q4"):
                    candidate = cell(bundle, key, p)
                    if candidate.get("period_end") == target and candidate.get("value") is not None:
                        choices.append(candidate)
            if not choices:
                raise Unavailable("missing:opening_" + key)
            if len({c["value"] for c in choices}) != 1:
                raise Unavailable("conflict:opening_" + key)
            f = choices[0]
        value = f.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise Unavailable(f.get("reason") or "missing:" + key)
        if f.get("availability") != "available" or f.get("quality") not in {"reported", "deterministic_derived"}:
            raise Unavailable("unverified:" + key)
        if (f.get("unit") or {}).get("currency") != canonical.get("currency") or (f.get("unit") or {}).get("scale") != 1 or f.get("fs_div") != canonical.get("fs_div"):
            raise Unavailable("scope_or_currency_mismatch:" + key)
        if not f.get("provenance"):
            raise Unavailable("missing:provenance_" + key)
        if not opening and (f.get("period_end") != end or (sj != "BS" and f.get("period_start") != start)):
            raise Unavailable("period_mismatch:" + key)
        if sj == "BS" and value < 0 and key != "equity":
            raise Unavailable("negative_balance:" + key)
        used.append({"input": key, "opening": opening, **f})
        return value

    # Anchor to the canonical period calendar, never to the latest non-null fact.
    anchors = [cell(canonical, k, selected_period) for k, v in cfg["inputs"].items() if v[0] != "BS"]
    anchor = next((a for a in anchors if a.get("period_start") and a.get("period_end")), {})
    start, end = anchor.get("period_start"), anchor.get("period_end")
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 if start and end else None

    def ratio(a, b):
        if b <= 0:
            raise Unavailable("nonpositive:denominator")
        return a / b

    def avg(key):
        return (read(key, opening=True) + read(key)) / 2

    def emit(key, formula, fn, unit="ratio", note=None):
        used.clear()
        value, reason = None, None
        try:
            if financial:
                raise Unavailable("not_applicable:financial_entity")
            if days is None or days <= 0:
                raise Unavailable("missing:period_bounds")
            value = fn()
            if not math.isfinite(value):
                raise Unavailable("nonfinite:result")
        except Unavailable as exc:
            reason = str(exc)
        cards[key] = {"value": value, "reason": reason, "unit": unit,
                      "definition": formula, "note": note,
                      "period_start": start, "period_end": end,
                      "currency": canonical.get("currency") if unit == "money" else None,
                      "inputs": list(used), "status": "computed" if reason is None else "unavailable"}

    emit("fcf", "CFO - abs(PPE cash purchases) - abs(intangible cash purchases)",
         lambda: read("cfo") - abs(read("capex_ppe")) - abs(read("capex_intangible")), "money",
         "공시 CFO 기준; FCFF·채무상환 가능액과 다름. 이자·세금·운전자본 재차감 금지.")
    emit("fcf_ppe_only", "CFO - abs(PPE cash purchases)",
         lambda: read("cfo") - abs(read("capex_ppe")), "money", "유형자산 투자만 차감; 전체 FCF 대체 금지")
    emit("interest_coverage", "operating_income / abs(P&L interest_expense)",
         lambda: ratio(read("op"), abs(read("interest"))))
    emit("finance_cost_coverage", "operating_income / abs(finance_costs)",
         lambda: ratio(read("op"), abs(read("finance_costs"))), note="금융원가 커버리지; 이자보상배율·한계기업 판정에 사용 금지")
    emit("current_ratio", "current_assets / current_liabilities", lambda: ratio(read("current_assets"), read("current_liabilities")))
    emit("cash_ratio", "cash / current_liabilities", lambda: ratio(read("cash"), read("current_liabilities")))
    emit("current_borrowings", "reported current borrowings including current portion", lambda: read("debt_current_total"), "money", "리스 포함 여부 미확인; 총 1년 만기부채와 다름")
    emit("cash_to_current_borrowings", "cash / reported current borrowings", lambda: ratio(read("cash"), read("debt_current_total")), note="은행 규제 LCR 아님; 리스 포함 총 만기 커버리지 아님")
    emit("capex_to_sales", "(abs(PPE purchases) + abs(intangible purchases)) / revenue", lambda: ratio(abs(read("capex_ppe")) + abs(read("capex_intangible")), read("revenue")))
    emit("receivables_to_sales", "closing trade receivables / period revenue", lambda: ratio(read("receivables"), read("revenue")), note="잔액/기간매출 비율; 기간 길이가 다른 값끼리 비교 금지")
    for key in ("contract_assets", "contract_liabilities"):
        emit(key + "_to_sales", key + " / period revenue", lambda key=key: ratio(read(key), read("revenue")))
    def cycle(key, denominator):
        if not kit["ccc"]:
            raise Unavailable("not_applicable:industry_ccc")
        den = read(denominator)
        return ratio(avg(key), abs(den) if denominator == "cogs" else den) * days
    emit("dso_days", "average trade receivables / revenue * actual period days", lambda: cycle("receivables", "revenue"), "days", "외상매출 대신 총매출 사용")
    emit("dio_days", "average inventory / abs(COGS) * actual period days", lambda: cycle("inventory", "cogs"), "days")
    emit("dpo_days", "average trade payables / abs(COGS) * actual period days", lambda: cycle("payables", "cogs"), "days", "매입액 대신 매출원가 사용한 대용치")
    emit("ccc_days", "DSO + DIO - DPO (COGS proxy)", lambda: cycle("receivables", "revenue") + cycle("inventory", "cogs") - cycle("payables", "cogs"), "days")
    def nwc(opening=False):
        return read("receivables", opening=opening) + read("inventory", opening=opening) - read("payables", opening=opening)
    emit("nwc_change_to_sales", "change in (trade receivables + inventory - trade payables) / revenue", lambda: ratio(nwc() - nwc(True), read("revenue")), note="좁은 영업운전자본 정의; 계약자산·선수금 별도, CFO에서 재차감 금지")
    from .p1_disclosures import compute_strict_ebitda
    ebitda = compute_strict_ebitda(canonical, endpoint=selected_period)
    if ebitda.get("value") is not None:
        p, u = ebitda.get("period") or {}, ebitda.get("unit") or {}
        inputs = ebitda["provenance"]["input_facts"]
        problem = None
        if (p.get("period_start") != start or p.get("period_end") != end
                or p.get("fs_div") != canonical.get("fs_div")
                or u.get("currency") != canonical.get("currency") or u.get("scale") != 1):
            problem = "incompatible:ebitda_period_scope_unit"
        elif any(not f.get("provenance") for f in inputs.values()):
            problem = "missing:ebitda_input_provenance"
        elif any(inputs[k]["value"] < 0 for k in ("PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION")):
            problem = "requires:normalized_positive_da_charges"
        if problem:
            ebitda = {**ebitda, "value": None, "status": "unavailable", "reason": problem}
    if financial:
        ebitda = {"value": None, "reason": "not_applicable:financial_entity", "status": "unavailable"}
    cards["ebitda"] = {
        "value": ebitda.get("value"), "reason": ebitda.get("reason"),
        "status": "computed" if ebitda.get("value") is not None else "unavailable",
        "unit": "money", "currency": canonical.get("currency"),
        "period_start": start, "period_end": end,
        "definition": "operating income + PPE depreciation + intangible amortization",
        "note": "동일 범위의 별도 D&A 공시 입력 필요; 조정 EBITDA가 아님",
        "inputs": [{"input": "strict_ebitda", **ebitda}],
    }
    def fcf_conversion():
        if ebitda.get("value") is None or cards["fcf"]["value"] is None:
            raise Unavailable("missing:strict_ebitda_or_fcf")
        # P1 guards its inputs internally; also align with this period's CFO.
        p = ebitda.get("period") or {}
        if p.get("period_start") != start or p.get("period_end") != end or (ebitda.get("unit") or {}).get("currency") != canonical.get("currency") or p.get("fs_div") != canonical.get("fs_div"):
            raise Unavailable("period_mismatch:ebitda")
        used.extend(cards["fcf"]["inputs"])
        used.append({"input": "ebitda", **ebitda})
        return ratio(cards["fcf"]["value"], ebitda["value"])
    emit("fcf_to_ebitda", "CFO-based FCF / strict EBITDA", fcf_conversion)
    # Explicitly surface blocked decisions instead of silently estimating.
    for key, reason in {"net_debt_to_ebitda": "requires:complete_debt_and_annual_or_ttm_ebitda",
                        "debt_due_within_1y": "requires:complete_current_debt_and_lease_policy",
                        "liquidity_coverage_1y": "requires:debt_due_within_1y_and_unrestricted_cash",
                        "dscr": "requires:cfads_and_contractual_debt_service",
                        "maintenance_capex": "requires:reported_or_explicit_scenario_assumption"}.items():
        cards[key] = {"value": None, "status": "unavailable", "reason": "not_applicable:financial_entity" if financial else reason}
    return {"schema_version": "kfa-pe-cr/1", "industry": "financial" if financial else industry,
            "cards": cards, "focus": kit["focus"], "notes": kit["notes"],
            "visible_cards": [] if financial else [k for k, v in cards.items() if v["value"] is not None],
            "no_price_target": True}
