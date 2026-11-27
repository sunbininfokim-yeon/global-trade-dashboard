"""1년 내 만기 차입금, 만기 구간표, 넓힌 CCC·순차입금, PF 우발채무 만기.

The PE/CR engine's strict `debt_due_within_1y` and `net_debt` need a
hand-reviewed principal schedule, which no filer has, so those cards are empty
everywhere; its reported-basis net debt needs standard account ids, which a
quarter of filers do not use (삼성전자 tags 단기차입금 as "표준계정코드 미사용").
This module fills the gap on a labelled reported basis:

* **short-term debt by type** from the balance sheet: 단기차입금, 유동성장기차입금,
  유동성사채, 기업어음·단기사채, 유동리스부채 -- ids first, then account names;
  only interest-bearing lines. 매입채무·미지급금·선수금 are 유동부채 but not debt.
* **maturity ladder** from the XBRL 유동성위험 note (MaturityAxis members on
  borrowing / bond / lease / financial-liability concepts). These are
  undiscounted contractual cash flows incl. interest -- labelled so.
* **CCC on the combined receivables** (매출채권및기타채권) when the trade-only
  line is not on the face statement; labelled 기타채권 포함.
* **net debt with name-matched borrowings** for filers whose borrowing lines
  carry no standard id.
* **contingent-debt (PF 보증) maturities** where the contingent-liability note
  tags the guaranteed borrowings by maturity (현대건설).
"""
from __future__ import annotations

import re

from .investor_metrics import _num, _pick

# (key, label, ids, names) -- interest-bearing current lines only
SHORT_TERM = [
    ("borrowings_short", "단기차입금", ["ifrs-full_ShorttermBorrowings"], ["단기차입금"]),
    ("current_portion", "유동성장기차입금", ["ifrs-full_CurrentPortionOfLongtermBorrowings"],
     ["유동성장기차입금", "유동성장기부채", "유동성 장기차입금"]),
    ("bonds_current", "유동성사채", ["ifrs-full_CurrentPortionOfNoncurrentBondsIssued", "ifrs-full_CurrentPortionOfBondsIssued"],
     ["유동성사채", "유동성 사채"]),
    ("cp", "기업어음·단기사채", ["dart_ShortTermBonds", "ifrs-full_CommercialPapersIssued"], ["단기사채", "기업어음"]),
    ("lease_current", "유동리스부채", ["ifrs-full_CurrentLeaseLiabilities"], ["유동리스부채", "유동 리스부채", "리스부채(유동)"]),
]
COMBINED_CURRENT = (["ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
                    ["단기차입금 및 유동성장기부채", "단기차입금및유동성장기부채", "단기차입부채"])
LONG_TERM = [
    ("borrowings_long", ["ifrs-full_LongtermBorrowings", "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived"], ["장기차입금"]),
    ("bonds_noncurrent", ["ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "ifrs-full_BondsIssued"], ["사채", "비유동성사채", "회사채"]),
    ("lease_noncurrent", ["ifrs-full_NoncurrentLeaseLiabilities"], ["비유동리스부채", "리스부채"]),
]
CASH = (["ifrs-full_CashAndCashEquivalents"], ["현금및현금성자산"])
DEPOSITS = (["ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", "dart_ShortTermDepositsNotClassifiedAsCashEquivalents"],
            ["단기금융상품"])


def _row(rows, ids, names, field="thstrm_amount"):
    row, how = _pick(rows or [], "BS", ids, names)
    return (_num(row.get(field)) if row else None), (how, row.get("account_nm") if row else None)


def short_term_debt(rows: list, field: str = "thstrm_amount") -> dict | None:
    """Interest-bearing debt due within a year, by type, from one balance sheet."""
    parts = []
    for key, label, ids, names in SHORT_TERM:
        v, (how, nm) = _row(rows, ids, names, field)
        if v:
            parts.append({"key": key, "label": label, "value": v, "account": nm, "match": how})
    if not any(p["key"] in ("borrowings_short", "current_portion", "bonds_current") for p in parts):
        v, (how, nm) = _row(rows, *COMBINED_CURRENT, field)
        if v:
            parts.insert(0, {"key": "combined", "label": "단기차입금(유동성 포함)", "value": v, "account": nm, "match": how})
    if not parts:
        return None
    total = sum(p["value"] for p in parts)
    return {"total": total, "parts": parts}


def total_debt(rows: list, field: str = "thstrm_amount") -> tuple[float | None, list]:
    st = short_term_debt(rows, field)
    parts = list((st or {}).get("parts") or [])
    for key, ids, names in LONG_TERM:
        v, (how, nm) = _row(rows, ids, names, field)
        if v and any(p["value"] == v and p["account"] == nm for p in parts):
            continue      # the same row already counted (one 리스부채 line for both)
        if v:
            parts.append({"key": key, "label": {"borrowings_long": "장기차입금", "bonds_noncurrent": "사채",
                                                "lease_noncurrent": "비유동리스부채"}[key], "value": v, "account": nm, "match": how})
    if not parts:
        return None, []
    return sum(p["value"] for p in parts), parts


def refinancing(rows: list, ebitda: float | None) -> dict | None:
    st = short_term_debt(rows)
    if not st:
        return None
    cash, _ = _row(rows, *CASH)
    dep, _ = _row(rows, *DEPOSITS)
    liquid = (cash or 0) + (dep or 0) if cash is not None else None
    gross, _ = total_debt(rows)
    out = {**st,
           "cash": cash, "short_term_deposits": dep,
           "cover_by_cash": liquid / st["total"] if liquid is not None and st["total"] else None,
           "to_ebitda": st["total"] / ebitda if ebitda and ebitda > 0 else None,
           "share_of_debt": st["total"] / gross if gross else None,
           "basis": "재무상태표 이자부 유동부채(단기차입금·유동성장기차입금·유동성사채·CP·유동리스). 매입채무·미지급금 등 영업부채 제외"}
    return out


def net_debt_wide(rows: list) -> dict | None:
    """Gross debt (ids, then names) − cash; for filers the engine's id-only map misses."""
    gross, parts = total_debt(rows)
    cash, _ = _row(rows, *CASH)
    if gross is None or cash is None:
        return None
    return {"value": gross - cash, "gross": gross, "cash": cash, "parts": parts,
            "basis": "차입금·사채·리스(계정 id, 없으면 계정명) − 현금및현금성자산"}


# --------------------------------------------------------------------------- CCC

RECEIVABLES = (["ifrs-full_CurrentTradeReceivables", "dart_ShortTermTradeReceivable", "ifrs-full_TradeAndOtherCurrentReceivables"],
               ["매출채권", "매출채권및기타채권", "매출채권 및 기타채권", "매출채권및기타유동채권", "매출채권 및 기타유동채권"])
PAYABLES = (["ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", "dart_ShortTermTradePayables", "ifrs-full_TradePayables",
             "ifrs-full_TradeAndOtherCurrentPayables"],
            ["매입채무", "매입채무및기타채무", "매입채무 및 기타채무", "매입채무및기타유동채무"])
INVENTORY = (["ifrs-full_Inventories"], ["재고자산"])


def ccc_wide(rows: list) -> dict | None:
    """CCC from one FY report (당기·전기 balances, 당기 flows), combined lines allowed."""
    def flow(ids, names):
        for sj in ("IS", "CIS"):
            row, _ = _pick(rows, sj, ids, names)
            if row:
                return _num(row.get("thstrm_amount"))
        return None
    rev = flow(["ifrs-full_Revenue"], ["매출액", "영업수익", "수익(매출액)"])
    cogs = flow(["ifrs-full_CostOfSales"], ["매출원가"])
    if not rev or not cogs:
        return None

    def avg(spec):
        cur, (how, nm) = _row(rows, *spec)
        pri, _ = _row(rows, *spec, field="frmtrm_amount")
        if cur is None:
            return None, nm
        return ((cur + pri) / 2 if pri is not None else cur), nm
    ar, ar_nm = avg(RECEIVABLES)
    inv, _ = avg(INVENTORY)
    ap, ap_nm = avg(PAYABLES)
    if ar is None or ap is None:
        return None
    dso, dio, dpo = ar / rev * 365, (inv or 0) / cogs * 365, ap / cogs * 365
    combined = any("기타" in (n or "") for n in (ar_nm, ap_nm))
    return {"value": dso + dio - dpo, "dso": dso, "dio": dio, "dpo": dpo,
            "receivables_account": ar_nm, "payables_account": ap_nm, "includes_other": combined,
            "basis": "매출채권 회전일수 + 재고 회전일수 − 매입채무 회전일수 (기초·기말 평균, 매출·매출원가)"
                     + (" — 기타채권·채무 포함 계정" if combined else "")}


# --------------------------------------------------------------------------- maturity ladders (XBRL)

BUCKETS = [  # (bucket, regex on the maturity member, lower-cased)
    ("~3개월", r"notlaterthanthreemonths|lessthan3months|within3months"),
    ("3~6개월", r"laterthanthreemonthsandnotlaterthansixmonths"),
    ("6~12개월", r"laterthansixmonthsandnotlaterthanoneyear"),
    ("1년 이내", r"notlaterthanoneyear|lessthanoneyear|lessthan1year|within1year"),
    ("1~2년", r"laterthanoneyearandnotlaterthantwoyears"),
    ("2~5년", r"laterthantwoyearsandnotlaterthan(three|four|five)years|laterthan(three|four)yearsandnotlaterthan(four|five)years"),
    ("1~5년", r"laterthanoneyearandnotlaterthanfiveyears|notlessthan1yearsandlessthan5years"),
    ("2년 초과", r"laterthantwoyears(member|of)"),
    ("5년 초과", r"laterthanfiveyears|morethan5years|over5years"),
]
CLASSES = [  # (class, label, concept regex)
    ("borrowings", "차입금", r"^(Bank)?Borrowings(UndiscountedCashFlows)?$|^BorrowingsUndiscounted|^LoansPayableUndiscounted"),
    ("bonds", "사채", r"^Bonds?(Issued)?UndiscountedCashFlows|^BondsIssued$"),
    ("lease", "리스부채", r"^(Gross)?LeaseLiabilities$"),
    ("financial_liabilities", "금융부채 전체", r"^(NonDerivative)?FinancialLiabilitiesUndiscountedCashFlow"),
]
CONTINGENT = r"Contingent|Guarantee|Suretyship|PaymentGuarantee"


def _bucket(member: str) -> str | None:
    m = member.lower()
    for name, rx in BUCKETS:
        if re.search(rx, m):
            return name
    return None


def maturity_ladders(contexts: dict, facts: list, *, fs_div: str, instant: str) -> dict:
    """Contractual maturity buckets by instrument class, and contingent (guaranteed)
    borrowings by maturity, at the fiscal year end."""
    from .xbrl_notes import SCOPE_AXIS, SCOPE_MEMBER
    uses_scope = any(SCOPE_AXIS in c["dims"] for c in contexts.values())
    cells = {}
    for f in facts:
        ctx = contexts.get(f["context"])
        if not ctx or ctx["typed"] or ctx["instant"] != instant or (f["unit"] or "").upper() != "KRW":
            continue
        dims = dict(ctx["dims"])
        scope = dims.pop(SCOPE_AXIS, None)
        if uses_scope and scope != SCOPE_MEMBER[fs_div]:
            continue
        mat = [(a, m) for a, m in dims.items() if "Maturity" in a]
        if len(mat) != 1 or len(dims) != 1:
            continue
        bucket = _bucket(mat[0][1].split(":")[-1])
        if not bucket:
            continue
        concept = f["concept"]
        if re.search(CONTINGENT, concept):
            cls = "contingent"
        else:
            cls = next((c for c, _, rx in CLASSES if re.search(rx, concept)), None)
        if not cls:
            continue
        try:
            v = float(f["text"])
        except ValueError:
            continue
        cells.setdefault((cls, concept, bucket), set()).add(v)
    out = {}
    for cls, label, _ in CLASSES + [("contingent", "보증·우발 차입(PF 등)", "")]:
        best = {}
        concepts = {c for (k, c, _) in cells if k == cls}
        for concept in sorted(concepts):
            row = {b: next(iter(v)) for (k, c, b), v in cells.items() if k == cls and c == concept and len(v) == 1}
            if len(row) > len(best.get("buckets", {})):
                best = {"concept": concept, "buckets": row}
        if best:
            order = [b for b, _ in BUCKETS]
            buckets = sorted(best["buckets"].items(), key=lambda kv: order.index(kv[0]))
            within = sum(v for b, v in buckets if b in ("~3개월", "3~6개월", "6~12개월", "1년 이내"))
            out[cls] = {"label": label, "concept": best["concept"], "buckets": [{"bucket": b, "value": v} for b, v in buckets],
                        "within_1y": within or None}
    if out:
        out["basis"] = "XBRL 유동성위험 주석의 계약상 만기 구간(할인 전, 이자 포함). 보증 차입은 우발부채 주석의 피보증 차입 만기."
        out["period_end"] = instant
    return out


def flag_partial(ladders: dict, *, borrowings_bs: float | None, lease_bs: float | None) -> dict:
    """A ladder that covers under half of the balance-sheet amount is one subsidiary's
    table (삼성전자: 0.07조 of bank borrowings vs 18.75조 on the face) -- keep it
    but mark it partial so nobody reads it as the company's schedule."""
    for cls, bs in (("borrowings", borrowings_bs), ("lease", lease_bs)):
        lad = ladders.get(cls)
        if lad and bs:
            total = sum(b["value"] for b in lad["buckets"])
            lad["coverage"] = total / bs
            lad["partial"] = total < 0.5 * bs
    return ladders
