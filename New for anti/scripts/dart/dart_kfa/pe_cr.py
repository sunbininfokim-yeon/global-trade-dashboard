"""Evidence-preserving PE / corporate restructuring diagnostics.

Operates on canonical DART/SEC facts; never substitutes cash interest for P&L
interest, finance costs for interest, or broad receivables for trade receivables.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

from .entity_policy import is_financial, classify_entity
from .pe_cr_evidence import BALANCES, reviewed_facts
from .pe_cr_industry import resolve_industry


def config():
    return json.loads((Path(__file__).resolve().parents[1] / "config/pe_cr_inputs.json").read_text())


def account_specs():
    return {"PECR_" + key: {
        "nature": "balance" if sj == "BS" else "flow", "statement": sj,
        "source_statements": ["IS", "CIS"] if sj == "IS" else [sj],
        "source_ids": dart, "source_names": [], "sec_concepts": sec,
        "unit_kind": "currency",
    } for key, (sj, dart, sec) in config()["inputs"].items()}


class Unavailable(ValueError):
    pass


def build_pe_cr(canonical, *, selected_period="annual", history=(),
                entity_policy=None, industry=None, corp=None, reviewed_disclosures=None):
    """History contains canonical bundles, including opening BS for averages.

    EBITDA reuses the existing P1 strict disclosure calculator.
    """
    if canonical.get("schema_version") != "canonical-financial-facts/1":
        raise ValueError("unsupported_canonical_schema")
    if selected_period not in {"annual", "Q1", "Q2", "Q3", "Q4"}:
        raise ValueError("invalid_period")
    history = tuple(history)
    cfg = config()
    industry, selection_basis, ksic = resolve_industry(cfg["kits"], canonical=canonical, corp=corp, requested=industry)
    identity_policy = classify_entity({"corp_code": canonical.get("entity_id"), "source": canonical.get("source")})
    financial = is_financial(entity_policy or {}) or is_financial(identity_policy) or industry == "financial"
    if financial and industry != "financial":
        industry, selection_basis = "financial", "financial_entity_policy"
    kit = cfg["kits"][industry]
    ccc_policy = kit["ccc_policy"]
    ccc_allowed = ccc_policy in {"primary", "secondary"}
    trade_receivables_allowed = kit.get("trade_receivables", industry != "shipping")
    cards = {}
    used = []
    evidence = reviewed_facts(reviewed_disclosures, canonical) if not financial else {}

    def reviewed(key):
        return evidence.get((key, None if key in BALANCES else start, end))

    def read_reviewed(key):
        fact = reviewed(key)
        if not fact:
            raise Unavailable("missing:reviewed_" + key)
        used.append({"input": key, **fact})
        return fact["value"]

    def cell(bundle, key, period):
        s = bundle.get("series", {}).get("PECR_" + key, {})
        return (s.get("annual") if period == "annual" else s.get("quarters", {}).get(period)) or {}

    def no_mapped_row(fact):
        return not fact or (fact.get("reason") or "").startswith(("missing:dart_fact_", "missing:sec_exact_period_fact_"))

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
                    if candidate.get("period_end") == target:
                        if any(x in (candidate.get("reason") or "") for x in ("conflict", "incompatible", "mismatch")):
                            raise Unavailable("conflict:opening_" + key)
                        if candidate.get("value") is not None:
                            choices.append(candidate)
            if not choices:
                approved = evidence.get((key, None, target)) if key in {"receivables", "payables"} else None
                if approved is None:
                    raise Unavailable("missing:opening_" + key)
                choices.append(approved)
            if len({c["value"] for c in choices}) != 1:
                raise Unavailable("conflict:opening_" + key)
            f = choices[0]
        elif key in {"receivables", "payables"} and no_mapped_row(f) and reviewed(key):
            f = reviewed(key)
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

    def read_or_reviewed(key):
        if no_mapped_row(cell(canonical, key, selected_period)) and reviewed(key):
            return read_reviewed(key)
        return read(key)

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
            value, reason = None, str(exc)
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
         lambda: ratio(read("op"), abs(read_or_reviewed("interest"))))
    emit("finance_cost_coverage", "operating_income / abs(finance_costs)",
         lambda: ratio(read("op"), abs(read("finance_costs"))), note="금융원가 커버리지; 이자보상배율·한계기업 판정에 사용 금지")
    emit("current_ratio", "current_assets / current_liabilities", lambda: ratio(read("current_assets"), read("current_liabilities")))
    emit("cash_ratio", "cash / current_liabilities", lambda: ratio(read("cash"), read("current_liabilities")))
    emit("current_borrowings", "reported current borrowings including current portion", lambda: read("debt_current_total"), "money", "리스 포함 여부 미확인; 총 1년 만기부채와 다름")
    emit("cash_to_current_borrowings", "cash / reported current borrowings", lambda: ratio(read("cash"), read("debt_current_total")), note="은행 규제 LCR 아님; 리스 포함 총 만기 커버리지 아님")
    emit("capex_to_sales", "(abs(PPE purchases) + abs(intangible purchases)) / revenue", lambda: ratio(abs(read("capex_ppe")) + abs(read("capex_intangible")), read("revenue")))
    def require_trade_receivables():
        if not trade_receivables_allowed:
            raise Unavailable("not_applicable:unconfirmed_trade_receivables_scope")

    def closing_receivables_ratio():
        require_trade_receivables()
        return ratio(read("receivables"), read("revenue"))

    emit("receivables_to_sales", "closing trade receivables / period revenue", closing_receivables_ratio, note="잔액/기간매출 비율; 기간 길이가 다른 값끼리 비교 금지")
    for key in ("contract_assets", "contract_liabilities"):
        emit(key + "_to_sales", key + " / period revenue", lambda key=key: ratio(read(key), read("revenue")))
    def require_inventory_cycle():
        if not ccc_allowed:
            raise Unavailable("requires:confirmed_industry_ccc_scope" if ccc_policy == "unconfirmed" else "not_applicable:industry_ccc")

    def cycle(key, denominator):
        if key == "receivables":
            require_trade_receivables()
        else:
            require_inventory_cycle()
        den = read(denominator)
        return ratio(avg(key), abs(den) if denominator == "cogs" else den) * days
    emit("dso_days", "average trade receivables / revenue * actual period days", lambda: cycle("receivables", "revenue"), "days", "외상매출 대신 총매출 사용")
    emit("dio_days", "average inventory / abs(COGS) * actual period days", lambda: cycle("inventory", "cogs"), "days")
    emit("dpo_days", "average trade payables / abs(COGS) * actual period days", lambda: cycle("payables", "cogs"), "days", "매입액 대신 매출원가 사용한 대용치")
    def ccc(dpo):
        require_inventory_cycle()
        return cycle("receivables", "revenue") + cycle("inventory", "cogs") - dpo()

    emit("ccc_days", "DSO + DIO - DPO (COGS proxy)", lambda: ccc(lambda: cycle("payables", "cogs")), "days")
    def nwc(opening=False):
        require_inventory_cycle()
        return read("receivables", opening=opening) + read("inventory", opening=opening) - read("payables", opening=opening)
    emit("nwc_change_to_sales", "change in (trade receivables + inventory - trade payables) / revenue", lambda: ratio(nwc() - nwc(True), read("revenue")), note="좁은 영업운전자본 정의; 계약자산·선수금 별도, CFO에서 재차감 금지")
    from .p1_disclosures import compute_strict_ebitda
    ebitda_canonical = canonical
    op_fact = cell(canonical, "op", selected_period)
    if op_fact.get("availability") == "available" and not financial:
        series = dict(canonical.get("series") or {})
        for key in ("OPERATING_INCOME", "PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION"):
            old = series.get(key) or {}
            target = old.get("annual") if selected_period == "annual" else (old.get("quarters") or {}).get(selected_period)
            if target and target.get("availability") == "available":
                continue
            if target and any(x in (target.get("reason") or "") for x in ("conflict", "incompatible", "mismatch")):
                continue
            source = op_fact if key == "OPERATING_INCOME" else reviewed(key)
            if source:
                if key == "OPERATING_INCOME":
                    fact = {**source, "account_id": key}
                else:
                    fact = {**source, **{k: op_fact.get(k) for k in ("fiscal_year", "fiscal_quarter", "period_kind")}}
                if selected_period == "annual":
                    series[key] = {**old, "annual": fact}
                else:
                    series[key] = {**old, "quarters": {**(old.get("quarters") or {}), selected_period: fact}}
        ebitda_canonical = {**canonical, "series": series}
    ebitda = compute_strict_ebitda(ebitda_canonical, endpoint=selected_period)
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
        elif op_fact.get("availability") == "available" and inputs["OPERATING_INCOME"]["value"] != op_fact["value"]:
            problem = "conflict:ebitda_operating_income"
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

    def annual_leverage():
        if selected_period != "annual":
            raise Unavailable("requires:annual_ebitda_no_quarter_annualization")
        if ebitda.get("value") is None:
            raise Unavailable("missing:strict_annual_ebitda")
        debt = read_reviewed("financing_debt") - read_reviewed("unrestricted_cash")
        used.append({"input": "ebitda", **ebitda})
        return ratio(debt, ebitda["value"])

    emit("net_debt_to_ebitda", "(financing debt including leases - unrestricted cash) / annual EBITDA", annual_leverage)
    emit("debt_due_within_1y", "complete financing and lease principal due within 12 months", lambda: read_reviewed("principal_due_1y"), "money",
         "약정 원금만 포함; 유동부채·리스장부잔액·원리금 만기표 합계와 다름")
    emit("liquidity_coverage_1y", "unrestricted cash / complete principal due within 12 months",
         lambda: ratio(read_reviewed("unrestricted_cash"), read_reviewed("principal_due_1y")), note="원금 기준, 이자·신용한도 제외; 규제 LCR 아님")
    emit("dscr", "historical CFADS / (financing principal paid + cash interest paid)",
         lambda: ratio(read_reviewed("cfads"), read_reviewed("principal_paid") + read_reviewed("interest_paid")),
         note="동일 기간 실적 DSCR; 계약상 정의·미래 시나리오와 다름")
    emit("maintenance_capex", "explicitly disclosed cash maintenance capex", lambda: read_reviewed("maintenance_capex"), "money",
         "공시에서 별도로 확인된 유지보수 현금투자; 전체 CapEx나 D&A로 대체하지 않음")

    if industry in {"shipbuilding", "machinery"}:
        emit("order_backlog", "reported outstanding firm customer orders at period end", lambda: read_reviewed("order_backlog"), "money",
             "확정 수주잔고; 옵션·미확정 계약·계약부채 또는 향후 인식할 매출과 동일시하지 않음")
        emit("new_orders", "reported firm customer orders signed within selected period", lambda: read_reviewed("new_orders"), "money")
        emit("net_contract_position_to_sales", "(current contract assets - current contract liabilities) / period revenue",
             lambda: ratio(read("contract_assets") - read("contract_liabilities"), read("revenue")),
             note="유동 계정만 사용한 분석용 차이; 재무제표상 상계를 뜻하지 않음")
    if industry == "machinery":
        def inventory_share(key, other):
            amount, total = read_reviewed(key), read("inventory")
            note_total = read_reviewed("inventory_note_total")
            if note_total != total:
                raise Unavailable("incompatible:inventory_note_total_does_not_match_balance_sheet")
            if amount > total or (reviewed(other) and amount + read_reviewed(other) > total):
                raise Unavailable("incompatible:inventory_note_components_exceed_total")
            return ratio(amount, total)

        emit("wip_to_inventory", "net work in process / closing net inventories",
             lambda: inventory_share("wip_inventory", "raw_material_inventory"))
        emit("raw_materials_to_inventory", "net raw materials / closing net inventories",
             lambda: inventory_share("raw_material_inventory", "wip_inventory"))
    if industry == "retail_wholesale":
        def dpo_on_purchases():
            return ratio(avg("payables"), read_reviewed("merchandise_purchases")) * days

        emit("inventory_turns_period", "abs(COGS) / average inventory", lambda: ratio(abs(read("cogs")), avg("inventory")),
             note="선택 기간의 회전 횟수; 분기값을 연환산하지 않음")
        emit("inventory_less_trade_payables", "closing inventory - closing trade payables",
             lambda: read("inventory") - read("payables"), "money", "상품·재고에 묶인 순자금의 부분 지표; 전체 운전자본이 아님")
        emit("dpo_days_on_purchases", "average trade payables / same-scope disclosed merchandise purchases * days", dpo_on_purchases, "days",
             "공시 매입액 기준; 매출원가·공급업체 지급현금·재고 증감으로 대체하지 않음")
        emit("ccc_days_on_purchases", "DSO + DIO - DPO based on disclosed purchases", lambda: ccc(dpo_on_purchases), "days")
    if industry == "it_services":
        emit("rd_expense_to_sales", "abs(P&L research and development expense) / revenue",
             lambda: ratio(abs(read_or_reviewed("rd_expense")), read("revenue")), note="손익 비용 처리분; 자산화된 개발비 또는 전체 R&D 지출 아님")
        emit("capitalized_development_to_sales", "internally generated development additions / revenue",
             lambda: ratio(read_reviewed("capitalized_development"), read("revenue")), note="자산화 증가액; 무형자산 현금취득·외부인수와 구분")

    return {"schema_version": "kfa-pe-cr/1", "industry": industry,
            "industry_profile": {"label_ko": kit["label_ko"], "selection_basis": selection_basis, "ksic": ksic,
                                 "ccc_policy": ccc_policy, "disclosure_inputs": kit.get("note_inputs", [])},
            "cards": cards, "focus": kit["focus"], "notes": kit["notes"],
            "visible_cards": [] if financial else [k for k, v in cards.items() if v["value"] is not None],
            "no_price_target": True}
