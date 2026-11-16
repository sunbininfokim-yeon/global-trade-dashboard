"""Company-tagged note facts from the OpenDART original XBRL -> reviewed rows.

`fnlttSinglAcntAll` carries only the face statements. Most large Korean
filers summarise the cash-flow statement ("영업에서 창출된 현금") and tag only
total finance costs on the P&L, so D&A and P&L interest -- the inputs for
strict EBITDA and the interest coverage ratio -- live in the notes. The
original XBRL package (`fnlttXbrl.xml`, one zip per receipt) tags those notes
too, under the filer's own contexts.

This module reads that instance and emits `kfa-pe-cr-reviewed/1` rows for a
small set of keys, under rules that are deterministic and conservative:

* period: exactly the fiscal-year duration;
* scope: the Consolidated member for CFS, Separate for OFS (or, when the
  filer never uses the scope axis at all, contexts without it);
* no other dimension except a short whitelist of *total* members
  (`dart:ReportedAmountMember`, the financial-liabilities/assets category
  totals). Segment, asset-class and by-function breakdowns are never summed;
* one concept at a time in priority order, and every qualifying context of
  that concept must carry the same value -- any disagreement and the key is
  left out rather than picked.

Checked against the hand-reviewed Samsung Electronics FY2025 bundle
(config/pe_cr_reviewed/samsung_00126380_2025_cfs.json): all three rows --
D&A 43,605,740 / amortisation 3,320,852 / interest 605,783 (KRW mn) -- are
reproduced exactly (tests/test_xbrl_notes.py).

The rows are labelled with the XBRL concept and context in `evidence`, so a
reader can tell a machine-extracted row from a hand-reviewed one.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .pe_cr_evidence import BASES

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
SCOPE_AXIS = "ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis"
SCOPE_MEMBER = {"CFS": "ifrs-full:ConsolidatedMember", "OFS": "ifrs-full:SeparateMember"}
TOTAL_MEMBERS = {
    ("ifrs-full:CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis", "dart:ReportedAmountMember"),
    ("ifrs-full:AssetsAndLiabilitiesAxis", "ifrs-full:FinancialLiabilitiesCategoryMember"),
    ("ifrs-full:AssetsAndLiabilitiesAxis", "ifrs-full:FinancialAssetsCategoryMember"),
}

# key -> concepts in priority order (local names; namespace prefix ignored).
# The cash-flow add-back comes first for D&A: it is the amount actually added
# back to profit, which is the scope EBITDA needs, and in the Samsung case it
# equals the by-nature total exactly.
CONCEPTS = {
    "PPE_DEPRECIATION": ("AdjustmentsForDepreciationExpense", "DepreciationExpense"),
    "INTANGIBLE_AMORTIZATION": ("AdjustmentsForAmortisationExpense", "AmortisationExpense",
                                "AmortisationIntangibleAssetsOtherThanGoodwill"),
    "interest": ("InterestExpenseFinanceExpense", "InterestExpense"),
    "interest_income": ("InterestIncomeFinanceIncome",),
}


def instance_from_zip(blob: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.endswith(".xbrl")]
        if len(names) != 1:
            raise ValueError("invalid:xbrl_package_instance_count")
        return z.read(names[0])


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_instance(xml: bytes):
    root = ET.fromstring(xml)
    contexts = {}
    for c in root.iter(XBRLI + "context"):
        period = c.find(XBRLI + "period")
        start = period.findtext(XBRLI + "startDate") if period is not None else None
        end = period.findtext(XBRLI + "endDate") if period is not None else None
        dims = {m.get("dimension"): (m.text or "").strip() for m in c.iter(XBRLDI + "explicitMember")}
        typed = any(True for _ in c.iter(XBRLDI + "typedMember"))
        contexts[c.get("id")] = {"start": start, "end": end, "dims": dims, "typed": typed}
    facts = []
    for el in root:
        ref = el.get("contextRef")
        if ref is None or el.text is None:
            continue
        facts.append({"concept": _local(el.tag), "context": ref, "text": el.text.strip(), "unit": el.get("unitRef")})
    return contexts, facts


def note_bundle(instance: bytes, *, entity_id: str, fs_div: str, fiscal_year_end: str, receipt: str,
                currency: str = "KRW") -> dict | None:
    """Return a kfa-pe-cr-reviewed/1 pack with the keys found, or None."""
    if fs_div not in SCOPE_MEMBER:
        raise ValueError("invalid:fs_div")
    contexts, facts = parse_instance(instance)
    end = date.fromisoformat(fiscal_year_end)
    start = (end.replace(year=end.year - 1) + timedelta(days=1)).isoformat()
    uses_scope_axis = any(SCOPE_AXIS in c["dims"] for c in contexts.values())

    def qualifies(ctx) -> bool:
        if ctx is None or ctx["typed"] or ctx["start"] != start or ctx["end"] != fiscal_year_end:
            return False
        dims = dict(ctx["dims"])
        scope = dims.pop(SCOPE_AXIS, None)
        if uses_scope_axis and scope != SCOPE_MEMBER[fs_div]:
            return False
        return all((axis, member) in TOTAL_MEMBERS for axis, member in dims.items())

    by_concept = {}
    for f in facts:
        ctx = contexts.get(f["context"])
        if qualifies(ctx) and f["unit"] and f["unit"].upper() == currency:
            by_concept.setdefault(f["concept"], []).append(f)

    rows = []
    for key, concepts in CONCEPTS.items():
        for concept in concepts:
            hits = by_concept.get(concept) or []
            try:
                values = {Decimal(h["text"]) for h in hits}
            except InvalidOperation:
                values = set()
            if len(values) != 1:
                continue        # absent, or contexts disagree: never pick one
            value = abs(values.pop())
            if value != value.to_integral_value():
                continue
            rows.append({
                "key": key, "basis": BASES[key], "period_start": start, "period_end": fiscal_year_end,
                "amount": int(value), "scale": 1,
                "evidence": {
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                    "document": "OpenDART 재무제표 원본 XBRL (fnlttXbrl.xml), 회사 태그 주석값 자동 추출",
                    "table": concept,
                    "row": "contexts " + ", ".join(sorted(h["context"] for h in hits)),
                },
            })
            break
    if not rows:
        return None
    return {"schema_version": "kfa-pe-cr-reviewed/1", "source": "DART", "entity_id": entity_id,
            "fs_div": fs_div, "currency": currency, "fiscal_year_end": fiscal_year_end, "rows": rows}


def merge_packs(primary: dict | None, extra: dict | None) -> dict | None:
    """Hand-reviewed rows win; XBRL rows only fill keys the primary lacks."""
    if not primary:
        return extra
    if not extra:
        return primary
    have = {(r["key"], r.get("period_start"), r["period_end"]) for r in primary.get("rows", [])}
    rows = list(primary["rows"]) + [r for r in extra["rows"] if (r["key"], r.get("period_start"), r["period_end"]) not in have]
    return {**primary, "rows": rows}
