"""Common note items from the FY XBRL: R&D and its capitalised share, share-based
compensation, inventory write-downs and provisions by class.

These sit in the notes, not on the face statements, and filers tag them with
a mix of IFRS and DART-extension concepts (경상연구개발비 is
`dart:OrdinaryDevelopmentExpenseSellingGeneralAdministrativeExpenses…` at
삼성전자 and SK하이닉스, `ifrs-full:ResearchAndDevelopmentExpense` at NAVER).
Concepts are matched by name prefix in priority order; only contexts with no
dimension besides scope and `dart:ReportedAmountMember` count, except where a
specific class member is asked for (capitalised development, provision
classes). Values that disagree across contexts are left out.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .xbrl_notes import SCOPE_AXIS, SCOPE_MEMBER, parse_instance

REPORTED = ("ifrs-full:CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis",
            "dart:ReportedAmountMember")
INTANGIBLE_CLASS = "ifrs-full:ClassesOfIntangibleAssetsAndGoodwillAxis"
PROVISION_CLASS = "ifrs-full:ClassesOfProvisionsAxis"

FLOWS = {
    "rd_expensed": ("ResearchAndDevelopmentExpense", "OrdinaryDevelopmentExpense", "ExpenditureOnResearchAndDevelopment"),
    "sbc": ("ExpenseFromSharebasedPaymentTransactionsWithEmployees", "ExpenseFromSharebasedPaymentTransactions",
            "AdjustmentsForSharebasedPayments"),
    "inventory_writedown": ("InventoryWritedown", "WriteDownsOfInventories"),
    "inventory_writedown_reversal": ("ReversalOfInventoryWritedown",),
}
PROVISION_LABEL = {
    "WarrantyProvisionMember": "판매보증", "LegalProceedingsProvisionMember": "소송",
    "OnerousContractsProvisionMember": "손실부담계약(공사손실 등)", "RestructuringProvisionMember": "구조조정",
    "ProvisionForDecommissioningRestorationAndRehabilitationCostsMember": "복구",
    "MiscellaneousOtherProvisionsMember": "기타",
}


def note_items(instance: bytes, *, fs_div: str, fiscal_year_end: str, labels: dict | None = None,
               revenue: float | None = None) -> dict:
    labels = labels or {}
    contexts, facts = parse_instance(instance)
    end = date.fromisoformat(fiscal_year_end)
    start = (end.replace(year=end.year - 1) + timedelta(days=1)).isoformat()
    uses_scope = any(SCOPE_AXIS in c["dims"] for c in contexts.values())

    def dims_of(ctx):
        dims = dict(ctx["dims"])
        scope = dims.pop(SCOPE_AXIS, None)
        if uses_scope and scope != SCOPE_MEMBER[fs_div]:
            return None
        if dims.get(REPORTED[0]) == REPORTED[1]:
            dims.pop(REPORTED[0])
        return dims

    cells = {}
    for f in facts:
        ctx = contexts.get(f["context"])
        if not ctx or ctx["typed"] or not (f["unit"] or "").upper() == "KRW":
            continue
        dims = dims_of(ctx)
        if dims is None:
            continue
        if ctx["start"] == start and ctx["end"] == fiscal_year_end:
            when = "flow"
        elif ctx["instant"] == fiscal_year_end:
            when = "balance"
        else:
            continue
        try:
            v = float(f["text"])
        except ValueError:
            continue
        cells.setdefault((f["concept"], when, tuple(sorted(dims.items()))), set()).add(v)

    def pick(prefixes, when, dims=()):
        for prefix in prefixes:
            hits = {k: v for k, v in cells.items() if k[0].startswith(prefix) and k[1] == when and k[2] == tuple(sorted(dims))}
            for (concept, _, _), vals in sorted(hits.items()):
                if len(vals) == 1:
                    return abs(next(iter(vals))), concept
        return None, None

    out = {"fiscal_year_end": fiscal_year_end}
    for key, prefixes in FLOWS.items():
        v, concept = pick(prefixes, "flow")
        out[key] = {"value": v, "concept": concept} if v is not None else {"value": None}
    capdev = next((m for (_, _, d) in cells for a, m in d if a == INTANGIBLE_CLASS and "CapitalisedDevelopment" in m), None)
    cap, cap_concept = (pick(("AdditionsOtherThanThroughBusinessCombinationsIntangibleAssets",), "flow",
                             ((INTANGIBLE_CLASS, capdev),)) if capdev else (None, None))
    if cap is None:
        cap, cap_concept = pick(("DevelopmentCostCapitalized", "CapitalisedDevelopmentExpenditure"), "flow")
    out["rd_capitalised"] = {"value": cap, "concept": cap_concept} if cap is not None else {"value": None}
    exp = out["rd_expensed"]["value"]
    if exp is not None and cap is not None and exp + cap > 0:
        out["capitalisation_ratio"] = {"value": cap / (exp + cap), "basis": "개발비 자산화 ÷ (비용 처리 연구개발비 + 자산화)"}
    if revenue:
        total = (exp or 0) + (cap or 0)
        if exp is not None:
            out["rd_to_sales"] = {"value": total / revenue, "basis": "(연구개발비 + 자산화 개발비) ÷ 매출"}
        if out["sbc"]["value"] is not None:
            out["sbc_to_sales"] = {"value": out["sbc"]["value"] / revenue, "basis": "주식보상비용 ÷ 매출"}

    total, _ = pick(("OtherProvisions", "Provisions"), "balance")
    classes = []
    for (concept, when, dims), vals in cells.items():
        if when != "balance" or not concept.startswith("OtherProvisions") or len(dims) != 1 or dims[0][0] != PROVISION_CLASS:
            continue
        if len(vals) != 1:
            continue
        member = dims[0][1].split(":")[-1]
        label = PROVISION_LABEL.get(member) or re.sub(r"\s*\[(구성요소|member)\]\s*$", "", labels.get(member, "")) or member
        classes.append({"member": member, "label": label, "value": abs(next(iter(vals)))})
    classes.sort(key=lambda c: -c["value"])
    if classes or total is not None:
        out["provisions"] = {"total": total, "classes": classes,
                             "classes_sum": sum(c["value"] for c in classes) if classes else None}
    return out
