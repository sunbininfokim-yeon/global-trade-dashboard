"""업권별 금융회사 지표: 은행·보험·증권·카드/캐피탈.

Two layers, kept apart on purpose:

1. **Computed** from the face statements (fnlttSinglAcntAll, exact ids):
   bank      순이자이익, 순수수료이익, NII ÷ 평균총자산 (NIM 대용), 비용효율(CIR),
             대손비용률(신용손실충당금 전입 ÷ 평균 대출채권), 대출 ÷ 예수부채, 대출 성장률
   insurer   보험수익, 보험서비스결과와 마진, 투자손익 비중
             (CSM 잔액은 아님: XBRL 은 상품군별로만 태그되고 총계가 없으며 본문 표 양식도
             회사마다 달라, 확인되지 않은 합계를 만들지 않는다)
   card/cap  영업수익 대비 대손비용, 총자산 대비 대손비용, 레버리지(총자산 ÷ 자본)
   all       ROA, ROE (지배주주 순이익 ÷ 평균 자본)
   These are proxies where noted (NIM uses total assets, not interest-earning
   assets) and say so.

2. **Reported** ratios lifted from the periodic report's own tables (고정이하
   여신비율, 대손충당금적립률, 연체율, 명목순이자마진, 손해율·합산비율). A holding
   company's report repeats these tables for every subsidiary, often a foreign
   one, so a candidate is rejected when its unit is a foreign currency or the
   value is outside a sane range, and a table labelled 연결 wins over others.
   Every value carries the caption of the table it came from.
"""
from __future__ import annotations

import re

from .regulatory_capital import number as cell_number
from .regulatory_capital import report_tables

FACE = {
    "assets": ("BS", ["ifrs-full_Assets"]),
    "equity": ("BS", ["ifrs-full_Equity"]),
    "parent_equity": ("BS", ["ifrs-full_EquityAttributableToOwnersOfParent"]),
    "loans": ("BS", ["dart_LoansAtAmortisedCost", "ifrs-full_LoansAndAdvancesToCustomers", "ifrs-full_LoansAndReceivables"]),
    "deposits": ("BS", ["ifrs-full_DepositsFromCustomers"]),
    "net_income": ("IS", ["ifrs-full_ProfitLoss"]),
    "parent_income": ("IS", ["ifrs-full_ProfitLossAttributableToOwnersOfParent"]),
    "nii": ("IS", ["ifrs-full_InterestRevenueExpense"]),
    "interest_income": ("IS", ["ifrs-full_RevenueFromInterest"]),
    "interest_expense": ("IS", ["ifrs-full_InterestExpense"]),
    "net_fee": ("IS", ["ifrs-full_FeeAndCommissionIncomeExpense"]),
    "fee_income": ("IS", ["ifrs-full_FeeAndCommissionIncome"]),
    "fee_expense": ("IS", ["ifrs-full_FeeAndCommissionExpense"]),
    "credit_loss": ("IS", ["ifrs-full_ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9",
                           "ifrs-full_AdditionalAllowanceRecognisedInProfitOrLossAllowanceAccountForCreditLossesOfFinancialAssets",
                           "ifrs-full_ImpairmentLossOnFinancialAssets"]),
    "sga": ("IS", ["ifrs-full_SellingGeneralAndAdministrativeExpense", "ifrs-full_GeneralAndAdministrativeExpense"]),
    "op": ("IS", ["ifrs-full_ProfitLossFromOperatingActivities", "dart_OperatingIncomeLoss"]),
    "revenue": ("IS", ["ifrs-full_Revenue"]),
    "insurance_revenue": ("IS", ["ifrs-full_InsuranceRevenue"]),
    "insurance_expense": ("IS", ["ifrs-full_InsuranceServiceExpensesFromInsuranceContractsIssued"]),
    "insurance_result": ("IS", ["ifrs-full_InsuranceServiceResult", "dart_InsuranceRevenueExpense"]),
    "investment_result": ("IS", ["dart_InvestmentIncomeExpenses", "ifrs-full_NetFinancialResult"]),
}
PPOP_NAMES = ("신용손실충당금반영전영업이익", "충당금적립전이익", "충당금적립전영업이익")


def _num(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def face_values(rows: list) -> dict:
    """{key: (current, prior)} from one FY fnlttSinglAcntAll response."""
    out = {}
    for key, (sj, ids) in FACE.items():
        sjs = ("IS", "CIS") if sj == "IS" else (sj,)
        row = next((r for s in sjs for aid in ids for r in rows if r.get("sj_div") == s and r.get("account_id") == aid), None)
        if row:
            out[key] = (_num(row.get("thstrm_amount")), _num(row.get("frmtrm_amount")))
    for r in rows:
        if r.get("sj_div") in ("IS", "CIS") and re.sub(r"\s", "", r.get("account_nm") or "") in PPOP_NAMES:
            out["ppop"] = (_num(r.get("thstrm_amount")), _num(r.get("frmtrm_amount")))
            break
    return out


def _avg(pair):
    return (pair[0] + pair[1]) / 2 if pair and None not in pair else (pair[0] if pair else None)


def _m(value, basis, **extra):
    return {"value": value, "basis": basis, **{k: v for k, v in extra.items() if v is not None}} if value is not None \
        else {"value": None, "basis": basis, "reason": "missing:input"}


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def computed(rows: list, kind: str) -> dict:
    v = face_values(rows)
    cur = lambda k: (v.get(k) or (None, None))[0]  # noqa: E731
    out = {}
    ni = cur("parent_income") if cur("parent_income") is not None else cur("net_income")
    eq = v.get("parent_equity") or v.get("equity")
    out["roe"] = _m(_div(ni, _avg(eq)), "지배주주 순이익 ÷ 평균 지배주주 자본")
    out["roa"] = _m(_div(cur("net_income"), _avg(v.get("assets"))), "당기순이익 ÷ 평균 총자산")
    out["leverage"] = _m(_div(cur("assets"), cur("equity")), "총자산 ÷ 자본총계 (배)")
    if kind == "basel":
        nii = cur("nii")
        if nii is None and cur("interest_income") is not None and cur("interest_expense") is not None:
            nii = cur("interest_income") - cur("interest_expense")
        fee = cur("net_fee")
        if fee is None and cur("fee_income") is not None and cur("fee_expense") is not None:
            fee = cur("fee_income") - cur("fee_expense")
        ppop, sga, loss = cur("ppop"), cur("sga"), cur("credit_loss")
        if ppop is None and cur("op") is not None and loss is not None:
            ppop = cur("op") + abs(loss)          # 신한: no 충당금 적립 전 이익 row
        out["net_interest_income"] = _m(nii, "순이자손익", unit="money")
        out["net_fee_income"] = _m(fee, "순수수료손익", unit="money")
        out["nii_to_assets"] = _m(_div(nii, _avg(v.get("assets"))),
                                  "순이자손익 ÷ 평균 총자산 (NIM 대용 — 이자수익자산이 아닌 총자산 기준이라 공시 NIM보다 낮음)")
        out["cost_income"] = _m(_div(sga, sga + ppop) if sga is not None and ppop is not None else None,
                                "일반관리비 ÷ (일반관리비 + 충당금 적립 전 이익)")
        out["credit_cost"] = _m(_div(abs(loss) if loss is not None else None, _avg(v.get("loans"))),
                                "신용손실충당금 전입액 ÷ 평균 대출채권")
        out["loans_to_deposits"] = _m(_div(cur("loans"), cur("deposits")),
                                      "연결 대출채권 ÷ 예수부채 (규제 예대율과 산식 다름)")
        loans = v.get("loans")
        out["loan_growth"] = _m(_div(loans[0], loans[1]) - 1 if loans and None not in loans and loans[1] else None,
                                "대출채권 전년말 대비 증가율")
    elif kind == "kics":
        rev, res = cur("insurance_revenue"), cur("insurance_result")
        if res is None and rev is not None and cur("insurance_expense") is not None:
            res = rev - cur("insurance_expense")
        out["insurance_revenue"] = _m(rev, "보험수익", unit="money")
        out["insurance_result"] = _m(res, "보험서비스결과 (보험손익)", unit="money")
        out["insurance_margin"] = _m(_div(res, rev), "보험서비스결과 ÷ 보험수익")
        inv = cur("investment_result")
        out["investment_result"] = _m(inv, "투자손익", unit="money")
        both = (res or 0) + (inv or 0) if res is not None and inv is not None else None
        out["insurance_share_of_profit"] = _m(_div(res, both) if both and both > 0 else None,
                                              "보험손익 ÷ (보험손익 + 투자손익)")
    elif kind == "credit_finance":
        loss, rev = cur("credit_loss"), cur("revenue")
        out["operating_revenue"] = _m(rev, "영업수익", unit="money")
        out["credit_cost_to_revenue"] = _m(_div(abs(loss) if loss is not None else None, rev), "신용손실충당금 전입 ÷ 영업수익")
        out["credit_cost_to_assets"] = _m(_div(abs(loss) if loss is not None else None, _avg(v.get("assets"))),
                                          "신용손실충당금 전입 ÷ 평균 총자산")
        out["funding_cost"] = _m(_div(cur("interest_expense"), _avg(v.get("assets"))), "이자비용 ÷ 평균 총자산 (조달비용 대용)")
    elif kind == "ncr":
        out["net_fee_income"] = _m(cur("net_fee") if cur("net_fee") is not None else (
            cur("fee_income") - cur("fee_expense") if None not in (cur("fee_income"), cur("fee_expense")) else None),
            "순수수료손익", unit="money")
    return out


# ---------------------------------------------------------------- reported tables

REPORTED = {
    "basel": {
        "npl_ratio": (r"고정이하\s*여신\s*비율", (0, 0.10), "고정이하여신비율"),
        "coverage_ratio": (r"대손충당금\s*적립률|NPL\s*커버리지", (0.3, 5.0), "대손충당금적립률(NPL 커버리지)"),
        "delinquency": (r"연체율", (0, 0.10), "연체율"),
        "nim_reported": (r"순이자\s*마진|\bNIM\b", (0.003, 0.06), "순이자마진(NIM, 공시)"),
    },
    "credit_finance": {
        "delinquency": (r"연체율", (0, 0.20), "연체율"),
        "npl_ratio": (r"고정이하\s*(?:채권|여신)\s*비율", (0, 0.20), "고정이하채권비율"),
        "coverage_ratio": (r"대손충당금\s*적립률", (0.3, 10.0), "대손충당금적립률"),
    },
    "kics": {
        "loss_ratio": (r"^손해율", (0.3, 1.5), "손해율"),
        "combined_ratio": (r"합산\s*비율", (0.6, 1.5), "합산비율"),
    },
}
FOREIGN_UNIT = re.compile(r"VND|USD|달러|위안|CNY|엔|JPY|루피|IDR|EUR|유로|파운드|GBP|HKD|SGD|MXN")


def _caption(before: str) -> str:
    """The table's own heading: text after the last '(3) …', '1) …', '가. …' marker,
    with any half tag cut off at the 600-character window."""
    text = re.sub(r"\s+", " ", before).strip()
    text = re.sub(r'^[^<>]*?">', "", text)
    marks = list(re.finditer(r"(\(\d+\)|\b\d\)|[가-하]\.|※|\b\d\.)\s", text))
    if marks:
        text = text[marks[-1].start():] if marks[-1].group(1) == "※" else text[marks[max(0, len(marks) - 2)].start():]
    return text[-110:].strip()


def _pct(cell: str):
    v = cell_number(cell)
    return v / 100 if v is not None else None


def reported_ratios(doc: str, kind: str) -> dict:
    defs = REPORTED.get(kind) or {}
    if not defs:
        return {}
    out = {}
    # Holding companies alternate "[지배회사에 관한 사항] … [주요 종속회사에 관한
    # 사항] [KB국민은행] …" in every section. A table belongs to a subsidiary
    # when the nearest marker before it is the subsidiary one; a group-level
    # table always wins.
    markers = sorted([(m.start(), False) for m in re.finditer(r"지배회사에\s*관한\s*사항", doc)]
                     + [(m.start(), True) for m in re.finditer(r"주요\s*종속회사에\s*관한\s*사항", doc)])
    for t in report_tables(doc):
        before = t["before"][-200:]
        last = [sub for pos, sub in markers if pos < t["start"]]
        subsidiary = bool(last and last[-1]) and "연결" not in before
        units = re.findall(r"단위\s*[:：]([^)]*)", before)
        if units and FOREIGN_UNIT.search(units[-1]):
            continue
        header = t["rows"][0] if t["rows"] else []
        consolidated = "연결" in before
        for row in t["rows"][1:]:
            for key, (rx, (lo, hi), label) in defs.items():
                cells = [c for c in row if c.strip()]
                idx = next((i for i, c in enumerate(cells[:2]) if re.search(rx, c)), None)
                if idx is None:
                    continue
                vals = [_pct(c) for c in cells[idx + 1:]]
                vals = [x for x in vals if x is not None]
                if not vals or not (lo <= vals[0] <= hi):
                    continue
                prev = out.get(key)
                rank = (consolidated, not subsidiary)
                if prev and (prev["consolidated"], not prev["subsidiary"]) >= rank:
                    continue
                periods = [c for c in header[1:] if re.search(r"\d{2,4}", c)][:len(vals)]
                out[key] = {"value": vals[0], "label": label, "series": list(zip(periods, vals)) if periods else None,
                            "source": _caption(before), "consolidated": consolidated,
                            "subsidiary": subsidiary}
    return out


def financial_kpis(fy_rows: list, *, kind: str | None, doc: str | None = None, receipt: str | None = None,
                   period_end: str | None = None) -> dict | None:
    if not kind:
        return None
    out = {"kind": kind, "computed": computed(fy_rows, kind), "reported": {}, "reported_receipt": receipt,
           "reported_period_end": period_end}
    if doc:
        out["reported"] = reported_ratios(doc, kind)
    return out
