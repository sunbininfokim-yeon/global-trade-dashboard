"""Segment, product and regional breakdowns from the OpenDART original XBRL.

IFRS 8 notes (영업부문 정보) and the revenue disaggregation note (IFRS 15
수익의 구분) are tagged with dimensional contexts: a SegmentsAxis /
ProductsAndServicesAxis / GeographicalAreasAxis member per row. Member names
are the filer's own (entity00126380:DsDivisionMemberOf...), so the Korean
caption comes from the package's label linkbase (lab-ko.xml).

Filers differ in how they tag the same table:

* 삼성전자: SegmentsAxis member + SegmentConsolidationItemsAxis =
  OperatingSegmentsMember, a total row under OperatingSegmentsMember alone,
  and the inter-segment elimination under MaterialReconcilingItemsMember;
* 한화오션: the segment members sit directly on SegmentConsolidationItemsAxis;
* SK하이닉스: only revenue by product (DRAM / NAND) on SegmentsAxis, no
  segment operating profit;
* NAVER: ProductsAndServicesAxis, with separate-basis members tagged under
  the consolidated scope ("...Seperate...").

So every breakdown is checked: its parts (plus the reported reconciling
items) must add up to the consolidated revenue on the face income statement,
or to the table's own total row, within 1.5 %. A breakdown that does not is
kept but flagged `reconciles: false`; nothing is rescaled or forced.

Rules shared with xbrl_notes: exact fiscal-year duration, scope member for
the basis, KRW only, and contexts that disagree on a value drop that value.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .xbrl_notes import SCOPE_AXIS, SCOPE_MEMBER, parse_instance

AXES = {
    "ifrs-full:SegmentsAxis": "segment",
    "ifrs-full:ProductsAndServicesAxis": "product",
    "ifrs-full:GeographicalAreasAxis": "geography",
}
CONSOL_AXIS = "ifrs-full:SegmentConsolidationItemsAxis"
CONSOL_TOTAL = "ifrs-full:OperatingSegmentsMember"
RECONCILING = {"ifrs-full:EliminationOfIntersegmentAmountsMember", "ifrs-full:MaterialReconcilingItemsMember",
               "ifrs-full:UnallocatedAmountsMember", "ifrs-full:CorporateMember"}
REVENUE = ("Revenue", "RevenueFromContractsWithCustomers")
OPERATING = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
KIND_LABEL = {"segment": "사업부문", "product": "제품·서비스", "geography": "지역"}
TOLERANCE = 0.015


def labels_from_zip(blob: bytes, lang: str = "ko") -> dict:
    """member local name -> standard label, from the package's label linkbase."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.endswith(f"lab-{lang}.xml")]
        if not names:
            return {}
        text = z.read(names[0]).decode("utf-8", "ignore")
    out = {}
    for m in re.finditer(r"<link:label\b([^>]*)>([^<]*)</link:label>", text):
        attrs, body = m.group(1), m.group(2).strip()
        role = re.search(r'xlink:role="[^"]*/(\w+)"', attrs)
        name = re.search(r'xlink:label="Label_label_(?:[A-Za-z0-9-]+_)?(\w+?)_' + lang + '"', attrs)
        if not name or not body or (role and role.group(1) != "label"):
            continue
        out.setdefault(name.group(1), body)
    return out


def _clean_label(text: str | None, member: str) -> str:
    if text:
        return re.sub(r"\s*\[(구성요소|member|Member)\]\s*$", "", text).strip()
    local = member.split(":")[-1]
    local = re.split(r"MemberOf|Member$", local)[0]
    return re.sub(r"(?<!^)([A-Z])", r" \1", local)


def _family(member: str) -> str:
    """The note table a member belongs to (…MemberOfDisclosureOfOperatingSegmentsTableOfMember).
    Matching on the table name, not the whole suffix, keeps a typo'd member
    (NAVER 'EnterpriseMembrOf…') with its siblings."""
    local = member.split(":")[-1]
    m = re.search(r"(Disclosure\w*?Table)", local, re.I)
    if m:
        return m.group(1).lower()
    return local.split("MemberOf", 1)[1] if "MemberOf" in local else "_standard"


def _is_adjustment(member: str, label: str | None) -> bool:
    return bool(re.search(r"Elimination|Reconcil|Unallocated", member.split(":")[-1])) or bool(
        re.search(r"제거|조정|내부거래|연결조정", label or ""))


def _separate_basis(member: str, label: str | None) -> bool:
    return bool(re.search(r"Sep[ae]rate", member.split(":")[-1])) or "별도" in (label or "")


def segment_breakdowns(instance: bytes, *, fs_div: str, fiscal_year_end: str, labels: dict | None = None,
                       face_revenue: float | None = None, currency: str = "KRW") -> dict:
    labels = labels or {}
    contexts, facts = parse_instance(instance)
    end = date.fromisoformat(fiscal_year_end)
    prior_end = end.replace(year=end.year - 1)
    periods = {
        ((end.replace(year=end.year - 1) + timedelta(days=1)).isoformat(), end.isoformat()): "cur",
        ((prior_end.replace(year=prior_end.year - 1) + timedelta(days=1)).isoformat(), prior_end.isoformat()): "prior",
    }
    uses_scope = any(SCOPE_AXIS in c["dims"] for c in contexts.values())

    def classify(ctx):
        """-> (kind, member) for a breakdown row, ('total', None), ('reconciling', member) or None."""
        dims = dict(ctx["dims"])
        scope = dims.pop(SCOPE_AXIS, None)
        if uses_scope and scope != SCOPE_MEMBER[fs_div]:
            return None
        consol = dims.pop(CONSOL_AXIS, None)
        axes = [a for a in dims if a in AXES]
        if len(dims) > 1 or (dims and not axes):
            return None
        if axes:
            if consol not in (None, CONSOL_TOTAL):
                return None
            return AXES[axes[0]], dims[axes[0]]
        if consol is None:
            return None
        if consol == CONSOL_TOTAL:
            return "total", None
        if consol in RECONCILING:
            return "reconciling", consol
        return "segment_consol", consol   # 한화오션: segment members on the consolidation axis

    cells = {}      # (kind, member, measure, period) -> {values}
    for f in facts:
        if not (f["unit"] and f["unit"].upper() == currency):
            continue
        measure = "revenue" if f["concept"] in REVENUE else "op" if f["concept"] in OPERATING else None
        if not measure:
            continue
        ctx = contexts.get(f["context"])
        if ctx is None or ctx["typed"]:
            continue
        period = periods.get((ctx["start"], ctx["end"]))
        if not period:
            continue
        hit = classify(ctx)
        if not hit:
            continue
        try:
            value = Decimal(f["text"])
        except InvalidOperation:
            continue
        rank = (REVENUE if measure == "revenue" else OPERATING).index(f["concept"])
        cells.setdefault((hit[0], hit[1], measure, period), {}).setdefault(rank, set()).add(value)

    def value(kind, member, measure, period):
        by_rank = cells.get((kind, member, measure, period)) or {}
        for rank in sorted(by_rank):
            vals = by_rank[rank]
            if len(vals) == 1:
                return float(next(iter(vals)))
            return None           # contexts disagree: leave it out
        return None

    totals = {m: value("total", None, m, "cur") for m in ("revenue", "op")}
    reconciling = {}
    for (kind, member, measure, period) in cells:
        if kind == "reconciling" and period == "cur":
            v = value(kind, member, measure, period)
            if v is not None:
                reconciling.setdefault(measure, {})[member.split(":")[-1]] = v

    families = {}
    for (kind, member, _measure, _period) in cells:
        if kind in ("total", "reconciling"):
            continue
        label = labels.get(member.split(":")[-1])
        if fs_div == "CFS" and _separate_basis(member, label):
            continue
        fam = "consolidation_axis" if kind == "segment_consol" else _family(member)
        families.setdefault(("segment" if kind == "segment_consol" else kind, fam), set()).add((kind, member))
    # Standard members (AllOtherSegmentsMember, CountryOfDomicileMember ...) join
    # the largest filer-specific family of the same kind.
    for (kind, fam), members in list(families.items()):
        if fam != "_standard":
            continue
        peers = [k for k in families if k[0] == kind and k[1] != "_standard"]
        if peers:
            target = max(peers, key=lambda k: len(families[k]))
            families[target] |= members
            del families[(kind, fam)]

    out = []
    for (kind, fam), members in families.items():
        rows, adjustments = [], []
        for ckind, member in members:
            local = member.split(":")[-1]
            row = {"member": local, "label": _clean_label(labels.get(local), member),
                   "revenue": value(ckind, member, "revenue", "cur"), "revenue_prior": value(ckind, member, "revenue", "prior"),
                   "op": value(ckind, member, "op", "cur"), "op_prior": value(ckind, member, "op", "prior")}
            if row["revenue"] is None and row["op"] is None:
                continue
            (adjustments if _is_adjustment(member, row["label"]) else rows).append(row)
        if len(rows) < 2:
            continue
        rev = [r["revenue"] for r in rows if r["revenue"] is not None]
        parts = sum(rev) if len(rev) == len(rows) else None
        adjust = sum(a["revenue"] for a in adjustments if a["revenue"] is not None)
        if kind == "segment":
            adjust += sum((reconciling.get("revenue") or {}).values())
        checks = []
        if parts is not None and totals["revenue"] and kind == "segment":
            checks.append(("segment_total", totals["revenue"], parts))
        if parts is not None and face_revenue:
            checks.append(("income_statement", face_revenue, parts + adjust))
        ok = next((name for name, target, got in checks if target and abs(got - target) <= TOLERANCE * abs(target)), None)
        # LX인터내셔널: segment revenue is already external (net of inter-segment
        # sales) yet an elimination member is tagged too. Accept parts = income
        # statement only when it is exact to 0.2 %, so an incomplete table that
        # happens to land near the total (한화오션 without 플랜트) cannot pass.
        if ok is None and parts is not None and face_revenue and adjust and abs(parts - face_revenue) <= 0.002 * abs(face_revenue):
            ok = "income_statement_external"
        rows.sort(key=lambda r: -(r["revenue"] if r["revenue"] is not None else float("-inf")))
        base = parts or face_revenue
        for r in rows:
            if r["revenue"] is not None and base:
                r["share"] = r["revenue"] / base
            if r["revenue"] and r["op"] is not None:
                r["margin"] = r["op"] / r["revenue"]
            if r["revenue"] is not None and r["revenue_prior"]:
                r["revenue_yoy"] = r["revenue"] / r["revenue_prior"] - 1
            if r["op"] is not None and r["op_prior"] and r["op_prior"] > 0:
                r["op_yoy"] = r["op"] / r["op_prior"] - 1
        out.append({
            "kind": kind, "label": KIND_LABEL[kind], "table": fam, "rows": rows,
            "has_operating_income": any(r["op"] is not None for r in rows),
            "sum_revenue": parts, "total_revenue_reported": totals["revenue"],
            "reconciling_items": ({**(reconciling.get("revenue") or {}), **{a["label"]: a["revenue"] for a in adjustments}}
                                  if kind == "segment" else {a["label"]: a["revenue"] for a in adjustments}) or None,
            "face_revenue": face_revenue, "reconciles": ok is not None, "reconciled_against": ok,
        })
    order = {"segment": 0, "product": 1, "geography": 2}
    out.sort(key=lambda b: (order[b["kind"]], not b["reconciles"], -len(b["rows"])))
    return {"fiscal_year_end": fiscal_year_end, "fs_div": fs_div, "breakdowns": out,
            "source": "OpenDART 재무제표 원본 XBRL (fnlttXbrl.xml) 영업부문·수익 구분 주석"}
