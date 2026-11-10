"""Cash-flow presentation using canonical statement totals, never inferred from detail."""

ACTIVITIES = (
    ("operating", "영업활동", "cfo", (("cash_interest_operating", "영업활동 분류 이자지급"),)),
    ("investing", "투자활동", "cfi", (("capex_ppe", "유형자산 현금 취득"), ("capex_intangible", "무형자산 현금 취득"))),
    ("financing", "재무활동", "cff", (("cash_interest_financing", "재무활동 분류 이자지급"),)),
)


def _filing_versions(fact):
    provenance = fact["provenance"]
    if provenance.get("derivation") == "reported_direct_quarter":
        direct = provenance.get("direct_quarter_source") or {}
        refs = [{**row, "report_code": direct.get("report_code")} for row in direct.get("source_facts", [])]
    elif provenance.get("derivation"):
        refs = provenance.get("source_facts") or []
    else:
        refs = [provenance]
    for ref in refs:
        key = ref.get("source_end") or ref.get("report_code")
        if key and ref.get("filing_id"):
            yield key, ref["filing_id"]


def add_cash_flow_statement(canonical, cards, cell, read, emit, used, period):
    from .pe_cr import Unavailable

    def cash_flow_fact(key):
        fact = cell(canonical, key, period)
        if fact.get("value") is not None and (
                fact.get("source") != canonical.get("source")
                or fact.get("statement") != "CF" or fact.get("nature") != "flow"
                or (fact.get("unit") or {}).get("kind") != "currency"
                or fact.get("period_kind") != ("flow_annual" if period == "annual" else "flow_discrete_quarter")
                or (period != "annual" and fact.get("fiscal_quarter") != period)):
            raise Unavailable("incompatible:cash_flow_statement_or_period")
        return read(key)

    activities = []
    for activity, label, total, details in ACTIVITIES:
        emit(total, "net cash from (used in) " + activity + " activities", lambda key=total: cash_flow_fact(key),
             "money", "공시 현금흐름표 순액. 양수는 순유입, 음수는 순유출.", financial_allowed=True)
        detail_rows = []
        for key, detail_label in details:
            if key.startswith("cash_interest_") and canonical.get("source") != "DART":
                continue
            card_id = "cash_flow_" + key
            emit(card_id, "cash flow detail on source tag sign basis: " + key,
                 lambda key=key: cash_flow_fact(key), "money",
                 "원본 태그의 부호 기준. 지급 항목이 양수로 태깅될 수 있으며, 활동 순액과 다시 합산하지 않음.",
                 financial_allowed=True)
            detail_rows.append({"card_id": card_id, "label_ko": detail_label})
        activities.append({"id": activity, "label_ko": label, "card_id": total, "details": detail_rows})

    def net_activities():
        total_ids = [a["card_id"] for a in activities]
        missing = [key for key in total_ids if cards[key]["value"] is None]
        if missing:
            raise Unavailable("requires:cash_flow_activity_totals:" + ",".join(missing))
        versions = {}
        for key in total_ids:
            used.extend(cards[key]["inputs"])
            for fact in cards[key]["inputs"]:
                for report, filing in _filing_versions(fact):
                    if versions.setdefault(report, filing) != filing:
                        raise Unavailable("conflict:cash_flow_filing_versions")
        return sum(cards[key]["value"] for key in total_ids)

    emit("cash_flow_net_activities", "CFO + CFI + CFF", net_activities, "money",
         "환율효과 제외. FCF 또는 기초·기말 현금 차이와 동일하지 않음.", financial_allowed=True)
    emit("cash_flow_fx_effect", "reported FX effect on cash under the mapped concept",
         lambda: cash_flow_fact("cash_fx"), "money",
         "활동 합계와 분리. SEC 매핑은 제한현금 포함 태그이며, 태그가 없으면 추정하지 않음.", financial_allowed=True)
    return {"schema_version": "kfa-cash-flow-statement/1", "activities": activities,
            "net_activity_card_id": "cash_flow_net_activities", "fx_effect_card_id": "cash_flow_fx_effect",
            "detail_sign_basis": "source_tag", "details_are_exhaustive": False}
