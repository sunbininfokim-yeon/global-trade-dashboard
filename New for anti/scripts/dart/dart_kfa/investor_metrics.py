"""Investor / PE screening metrics from OpenDART statements and report tables.

Complements the PE/CR engine (pe_cr.py) with the multi-year and shareholder
views it does not produce. Pure functions: callers pass saved OpenDART
responses, nothing is fetched here.

Three groups:

1. Statement ratios over up to five fiscal years (each FY 사업보고서 carries
   당기/전기/전전기, so the FY, FY-1 and FY-2 reports cover FY-4..FY; the
   newest report wins for any year two reports both show):
   growth (YoY, 3-year CAGR), ROIC, DuPont ROE, accruals, receivable and
   inventory growth against sales, Altman Z'' and Piotroski F.
2. Shareholder returns and dilution: 배당에 관한 사항 (alotMatter),
   자기주식 취득 및 처분 현황 (tesstkAcqsDspsSttus), cash-flow dividends and
   buy-backs, and the 미상환 전환사채 / 신주인수권부사채 / 전환형 조건부자본증권
   tables of the latest periodic report (outstanding after conversion,
   redemption and price resets -- unlike the issue decisions, which overstate).
3. EV bridge items PE adds on top of net debt: net defined-benefit liability,
   provisions, lease liabilities the face balance sheet leaves untagged (from
   the XBRL notes), and equity-method investments as a deduction; plus the
   fixed-charge coverage (EBITDA - capex) / (interest paid + lease principal).

Rules: an input that is not reported stays None and the metric carries a
`reason`; nothing is estimated. Financial companies (banks, insurers,
brokers, card/capital) get growth on profit and EPS, shareholder returns and
dilution only -- sales, working capital, Z-scores and EV do not apply.
Market-priced variants (Altman's original Z with market cap, PEG, dividend
and shareholder yield, adjusted EV multiples) are left to the reader that
has the day's price: this module returns their inputs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .regulatory_capital import number as cell_number
from .regulatory_capital import report_tables, unit_scale

CONFIG = Path(__file__).resolve().parent.parent / "config" / "pe_cr_inputs.json"
SCHEMA = "kfa_investor_metrics/1"

# Keys the engine already maps (exact ids, statement-qualified) ...
ENGINE_KEYS = ("revenue", "op", "pretax_income", "parent_income", "total_income", "cogs", "cfo",
               "capex_ppe", "capex_intangible", "cash_interest_operating", "cash_interest_financing",
               "cash", "receivables", "inventory", "current_assets", "current_liabilities", "assets",
               "equity", "parent_equity", "issued_capital", "liabilities",
               "borrowings_short", "borrowings_current_portion", "bonds_current", "borrowings_long",
               "bonds_noncurrent", "lease_current", "lease_noncurrent", "debt_current_total",
               "cf_depreciation", "cf_amortisation", "cf_dep_amort_total")
# ... and the ones only this module needs: (statement, ids, names). Names are
# a fallback for cash-flow and provision lines whose ids vary by filer.
EXTRA = {
    "eps": ("IS", ["ifrs-full_BasicEarningsLossPerShare"], []),
    "gross_profit": ("IS", ["ifrs-full_GrossProfit"], []),
    "income_tax": ("IS", ["ifrs-full_IncomeTaxExpenseContinuingOperations", "ifrs-full_IncomeTaxExpense"], []),
    "retained_earnings": ("BS", ["ifrs-full_RetainedEarnings"], []),
    "share_premium": ("BS", ["ifrs-full_SharePremium"], []),
    "noncurrent_liabilities": ("BS", ["ifrs-full_NoncurrentLiabilities"], []),
    "short_term_deposits": ("BS", ["ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents",
                                   "dart_ShortTermDepositsNotClassifiedAsCashEquivalents"], ["단기금융상품"]),
    "db_liability": ("BS", ["ifrs-full_NoncurrentRecognisedLiabilitiesDefinedBenefitPlan",
                            "ifrs-full_NetDefinedBenefitLiability", "ifrs-full_DefinedBenefitLiabilityNoncurrent"],
                     ["순확정급여부채", "확정급여부채", "퇴직급여부채"]),
    "db_asset": ("BS", ["ifrs-full_NoncurrentRecognisedAssetsDefinedBenefitPlan", "ifrs-full_NetDefinedBenefitAsset"],
                 ["순확정급여자산", "확정급여자산"]),
    "provisions_current": ("BS", ["ifrs-full_CurrentProvisions", "ifrs-full_OtherShorttermProvisions"],
                           ["유동충당부채", "단기충당부채"]),
    "provisions_noncurrent": ("BS", ["ifrs-full_NoncurrentProvisions", "ifrs-full_OtherLongtermProvisions"],
                              ["비유동충당부채", "장기충당부채"]),
    "equity_method": ("BS", ["ifrs-full_InvestmentAccountedForUsingEquityMethod",
                             "ifrs-full_InvestmentsInAssociatesAccountedForUsingEquityMethod",
                             "ifrs-full_InvestmentsInJointVenturesAccountedForUsingEquityMethod"],
                      ["관계기업 및 공동기업 투자", "관계기업및공동기업투자", "관계기업투자", "지분법적용투자주식"]),
    "dividends_paid": ("CF", ["ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
                              "ifrs-full_DividendsPaidClassifiedAsOperatingActivities", "ifrs-full_DividendsPaid"],
                       ["배당금의 지급", "배당금지급", "배당금의지급"]),
    "buyback": ("CF", ["dart_AcquisitionOfTreasuryShares", "ifrs-full_PaymentsToAcquireOrRedeemEntitysShares"],
                ["자기주식의 취득", "자기주식의취득", "자기주식 취득"]),
    "equity_method_income": ("IS", ["ifrs-full_ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"],
                             ["지분법이익", "지분법손익", "관계기업투자손익", "관계기업 및 공동기업 투자손익"]),
    "impairment": ("IS", ["ifrs-full_ImpairmentLossRecognisedInProfitOrLoss", "dart_ImpairmentLossOfTangibleAssets"],
                   ["손상차손", "유형자산손상차손"]),
    "da_total_sec": ("CF", ["ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense"], ["감가상각비", "감가상각비와 상각비"]),
    "lease_repayment": ("CF", ["ifrs-full_PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities",
                               "dart_RepaymentsOfLeaseLiabilities", "dart_RepaymentOfLeaseLiabilities"],
                        ["리스부채의 상환", "리스부채의상환", "리스부채 상환", "리스부채의 감소"]),
}
NOT_MONEY = {"eps"}
FIELDS = ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")


def _spec() -> dict:
    inputs = json.loads(CONFIG.read_text())["inputs"]
    spec = {k: (inputs[k][0], inputs[k][1], []) for k in ENGINE_KEYS if k in inputs}
    spec.update(EXTRA)
    return spec


def _num(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s or s in {"-", "–", "—"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        x = float(s.strip("()"))
    except ValueError:
        return None
    return -x if neg else x


def _norm(name: str) -> str:
    return re.sub(r"[\s()·.]", "", name or "")


def _pick(rows, sj, ids, names):
    sjs = ("IS", "CIS") if sj == "IS" else (sj,)
    for s in sjs:
        for aid in ids:
            for r in rows:
                if r.get("sj_div") == s and r.get("account_id") == aid:
                    return r, f"id:{aid}"
    wanted = {_norm(n) for n in names}
    for s in sjs:
        for r in rows:
            if r.get("sj_div") == s and _norm(r.get("account_nm")) in wanted:
                return r, f"name:{r.get('account_nm')}"
    return None, None


def annual_series(fy_reports: dict) -> dict:
    """{fiscal_year: fnlttSinglAcntAll FY rows} -> {"years": [...], "values": {year: {key: v}}, "source": {...}}.

    Year Y's report gives Y (당기), Y-1 (전기), Y-2 (전전기). The newest
    report that shows a year wins, so restated comparatives replace the
    originally filed figures."""
    spec = _spec()
    values, source = {}, {}
    for year in sorted(fy_reports, reverse=True):
        rows = fy_reports[year] or []
        for key, (sj, ids, names) in spec.items():
            row, how = _pick(rows, sj, ids, names)
            if not row:
                continue
            for back, field in enumerate(FIELDS):
                v = _num(row.get(field))
                y = year - back
                if v is None or key in values.get(y, {}):
                    continue
                values.setdefault(y, {})[key] = v
                source.setdefault(y, {})[key] = {"report_year": year, "field": field, "match": how,
                                                "receipt": row.get("rcept_no")}
    years = sorted(values)
    return {"years": years, "values": values, "source": source}


# --------------------------------------------------------------------------- helpers


def _m(value=None, reason=None, **extra):
    out = {"value": value, "reason": None if value is not None else (reason or "missing:input")}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def _avg(a, b):
    return (a + b) / 2 if a is not None and b is not None else None


def _sum(*vals):
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _get(values, year, key):
    return (values.get(year) or {}).get(key)


def _net_income(v, year):
    return _get(v, year, "total_income")


def _parent_income(v, year):
    p = _get(v, year, "parent_income")
    return p if p is not None else _get(v, year, "total_income")


def _capex(v, year):
    return _sum(_get(v, year, "capex_ppe"), _get(v, year, "capex_intangible"))


def _gross_profit(v, year):
    gp = _get(v, year, "gross_profit")
    if gp is not None:
        return gp
    rev, cogs = _get(v, year, "revenue"), _get(v, year, "cogs")
    return rev - cogs if rev is not None and cogs is not None else None


def _debt(v, year):
    """Reported interest-bearing debt incl. leases (the engine's reported basis)."""
    current = _get(v, year, "debt_current_total")
    if current is None:
        current = _sum(*(_get(v, year, k) for k in ("borrowings_short", "borrowings_current_portion", "bonds_current")))
    return _sum(current, *(_get(v, year, k) for k in ("borrowings_long", "bonds_noncurrent", "lease_current", "lease_noncurrent")))


# --------------------------------------------------------------------------- group 1


GROWTH_KEYS = {"revenue": "매출액", "op": "영업이익", "parent_income": "지배주주 순이익", "eps": "EPS"}


def growth(series: dict, fy: int, *, financial: bool) -> dict:
    v = series["values"]
    out = {}
    for key, label in GROWTH_KEYS.items():
        if financial and key in ("revenue", "op"):
            out[key] = {"label": label, "yoy": _m(reason="not_applicable:financial"),
                        "cagr_3y": _m(reason="not_applicable:financial")}
            continue
        get = (lambda y: _parent_income(v, y)) if key == "parent_income" else (lambda y, k=key: _get(v, y, k))
        cur, prev, base3 = get(fy), get(fy - 1), get(fy - 3)
        if None in (cur, prev):
            yoy = _m(reason="missing:input")
        elif prev <= 0:
            yoy = _m(reason="turnaround" if cur > 0 else "not_meaningful:base_nonpositive", current=cur, prior=prev)
        else:
            yoy = _m(cur / prev - 1, current=cur, prior=prev)
        if None in (cur, base3):
            cagr = _m(reason=f"missing:FY{fy - 3}")
        elif cur <= 0 or base3 <= 0:
            cagr = _m(reason="not_meaningful:nonpositive_endpoint", current=cur, base=base3)
        else:
            cagr = _m((cur / base3) ** (1 / 3) - 1, current=cur, base=base3, base_year=fy - 3)
        out[key] = {"label": label, "yoy": yoy, "cagr_3y": cagr,
                    "history": {str(y): get(y) for y in series["years"] if get(y) is not None}}
    return out


# 법인세 최고세율 24% + 지방소득세 2.4% (2023~2025 사업연도). Used only when
# the company's own effective rate is not meaningful (loss, tax credit year).
STATUTORY_TOP_RATE = 0.264


def tax_rate(v, fy):
    """Effective rate of the year if 0..50 %, else the 3-year pooled rate if it is."""
    def rate(tax, pre):
        if tax is None or pre is None or pre <= 0:
            return None
        r = tax / pre
        return r if 0 <= r <= 0.5 else None
    r = rate(_get(v, fy, "income_tax"), _get(v, fy, "pretax_income"))
    if r is not None:
        return r, "effective"
    taxes = [_get(v, y, "income_tax") for y in (fy, fy - 1, fy - 2)]
    pres = [_get(v, y, "pretax_income") for y in (fy, fy - 1, fy - 2)]
    if None in taxes or None in pres:
        return None, None
    r = rate(sum(taxes), sum(pres))
    return (r, "effective_3y_pooled") if r is not None else (None, None)


def returns(series: dict, fy: int, *, financial: bool) -> dict:
    v = series["values"]
    if financial:
        na = _m(reason="not_applicable:financial")
        return {"roic": na, "roic_pretax": na, "dupont": na}
    op = _get(v, fy, "op")
    t, t_basis = tax_rate(v, fy)

    def invested(y):
        eq, debt = _get(v, y, "equity"), _debt(v, y)
        cash = _sum(_get(v, y, "cash"), _get(v, y, "short_term_deposits"))
        if eq is None or debt is None or cash is None:
            return None
        return eq + debt - cash
    ic_end, ic_begin = invested(fy), invested(fy - 1)
    ic = _avg(ic_end, ic_begin)
    if t is None and op is not None:
        t, t_basis = STATUTORY_TOP_RATE, "statutory_top_rate_assumed"
    pretax = (_m(op / ic, operating_income=op, invested_capital=ic, basis="영업이익 ÷ 평균 투하자본 (세전)")
              if op is not None and ic and ic > 0 else _m(reason="missing:input"))
    if op is None:
        roic = _m(reason="missing:operating_income")
    elif ic is None:
        roic = _m(reason="missing:invested_capital")
    elif ic <= 0:
        roic = _m(reason="not_meaningful:net_cash_exceeds_capital", invested_capital=ic)
    else:
        nopat = op * (1 - t)
        roic = _m(nopat / ic, nopat=nopat, tax_rate=t, tax_basis=t_basis, invested_capital=ic,
                  invested_capital_end=ic_end, invested_capital_begin=ic_begin,
                  basis="NOPAT = 영업이익 × (1 − 유효세율); 투하자본 = 자본총계 + 차입금·사채·리스 − 현금·단기금융상품, 기초·기말 평균")
    ni, rev = _net_income(v, fy), _get(v, fy, "revenue")
    ta = _avg(_get(v, fy, "assets"), _get(v, fy - 1, "assets"))
    eq = _avg(_get(v, fy, "equity"), _get(v, fy - 1, "equity"))
    if None in (ni, rev, ta, eq) or not rev or not ta or not eq:
        dupont = _m(reason="missing:input")
    else:
        margin, turnover, multiplier = ni / rev, rev / ta, ta / eq
        dupont = _m(margin * turnover * multiplier, net_margin=margin, asset_turnover=turnover,
                    equity_multiplier=multiplier,
                    basis="ROE = 순이익률 × 총자산회전율 × 자기자본승수 (연결 당기순이익·자본총계, 기초·기말 평균)")
    return {"roic": roic, "roic_pretax": pretax, "dupont": dupont}


def quality(series: dict, fy: int, *, financial: bool) -> dict:
    if financial:
        # A lender's operating cash flow moves with loans and deposits, so
        # accruals and CFO/net income say nothing about earnings quality.
        na = _m(reason="not_applicable:financial")
        return {k: na for k in ("accruals_ratio", "cfo_to_net_income", "receivables_vs_sales", "inventory_vs_sales")}
    v = series["values"]
    ni, cfo = _net_income(v, fy), _get(v, fy, "cfo")
    ta = _avg(_get(v, fy, "assets"), _get(v, fy - 1, "assets"))
    out = {}
    if None in (ni, cfo, ta) or not ta:
        out["accruals_ratio"] = _m(reason="missing:input")
    else:
        out["accruals_ratio"] = _m((ni - cfo) / ta, net_income=ni, cfo=cfo, avg_assets=ta,
                                   basis="(당기순이익 − 영업현금흐름) ÷ 평균 총자산")
    out["cfo_to_net_income"] = (_m(cfo / ni, cfo=cfo, net_income=ni) if ni and ni > 0 and cfo is not None
                                else _m(reason="not_meaningful:net_loss" if ni is not None and ni <= 0 else "missing:input"))
    rev_g = _div(_get(v, fy, "revenue"), _get(v, fy - 1, "revenue"))
    for key, item in (("receivables_vs_sales", "receivables"), ("inventory_vs_sales", "inventory")):
        g = _div(_get(v, fy, item), _get(v, fy - 1, item))
        if g is None or rev_g is None:
            out[key] = _m(reason="missing:input")
        else:
            out[key] = _m((g - 1) - (rev_g - 1), item_growth=g - 1, sales_growth=rev_g - 1,
                          basis="잔액 증가율 − 매출 증가율 (%p). +10%p 이상이면 확인 대상")
    return out


def altman(series: dict, fy: int, *, financial: bool) -> dict:
    """Z'' (Altman 1995, non-manufacturer/emerging-market, book equity) for each
    year, plus the FY inputs for the original market-value Z."""
    if financial:
        return {"z_double_prime": _m(reason="not_applicable:financial"), "z_inputs": None}
    v = series["values"]
    hist = {}
    for y in series["years"]:
        ta, ca, cl = _get(v, y, "assets"), _get(v, y, "current_assets"), _get(v, y, "current_liabilities")
        re_, ebit, eq, tl = _get(v, y, "retained_earnings"), _get(v, y, "op"), _get(v, y, "equity"), _get(v, y, "liabilities")
        if None in (ta, ca, cl, re_, ebit, eq, tl) or not ta or not tl:
            continue
        x1, x2, x3, x4 = (ca - cl) / ta, re_ / ta, ebit / ta, eq / tl
        z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        hist[str(y)] = {"z": z, "x1": x1, "x2": x2, "x3": x3, "x4": x4,
                        "zone": "safe" if z > 2.6 else ("grey" if z >= 1.1 else "distress")}
    cur = hist.get(str(fy))
    zpp = (_m(cur["z"], zone=cur["zone"], components={k: cur[k] for k in ("x1", "x2", "x3", "x4")}, history=hist,
              basis="Z'' = 6.56·운전자본/총자산 + 3.26·이익잉여금/총자산 + 6.72·영업이익/총자산 + 1.05·자본총계/부채총계; "
                    ">2.6 안전, 1.1~2.6 회색, <1.1 부실")
           if cur else _m(reason="missing:input"))
    inputs = None
    if cur:
        ta, rev = _get(v, fy, "assets"), _get(v, fy, "revenue")
        inputs = {"x1": cur["x1"], "x2": cur["x2"], "x3": cur["x3"],
                  "x5": rev / ta if rev is not None else None, "total_liabilities": _get(v, fy, "liabilities"),
                  "basis": "Z = 1.2·x1 + 1.4·x2 + 3.3·x3 + 0.6·시가총액/부채총계 + 1.0·매출/총자산; >2.99 안전, 1.81~2.99 회색, <1.81 부실"}
    return {"z_double_prime": zpp, "z_inputs": inputs}


def piotroski(series: dict, fy: int, *, financial: bool) -> dict:
    if financial:
        return _m(reason="not_applicable:financial")
    v = series["values"]
    g = lambda y, k: _get(v, y, k)  # noqa: E731
    ni, ni1, cfo = _net_income(v, fy), _net_income(v, fy - 1), g(fy, "cfo")
    ta, ta1, ta2 = g(fy, "assets"), g(fy - 1, "assets"), g(fy - 2, "assets")
    roa, roa1 = _div(ni, ta1), _div(ni1, ta2)

    def lev(y):
        return _div(g(y, "noncurrent_liabilities"), _avg(g(y, "assets"), g(y - 1, "assets")))

    def cr(y):
        return _div(g(y, "current_assets"), g(y, "current_liabilities"))

    def gm(y):
        return _div(_gross_profit(v, y), g(y, "revenue"))

    def turn(y):
        return _div(g(y, "revenue"), g(y - 1, "assets"))

    def paid_in(y):
        return _sum(g(y, "issued_capital"), g(y, "share_premium")) if g(y, "issued_capital") is not None else None

    def test(name, label, a, b=None, op=">"):
        if a is None or (op != "pos" and b is None):
            return {"key": name, "label": label, "pass": None}
        ok = a > 0 if op == "pos" else (a > b if op == ">" else (a < b if op == "<" else a <= b))
        return {"key": name, "label": label, "pass": bool(ok), "value": a, "compare": b}

    tests = [
        test("roa_positive", "ROA > 0 (순이익 ÷ 기초 총자산)", roa, op="pos"),
        test("cfo_positive", "영업현금흐름 > 0", cfo, op="pos"),
        test("roa_up", "ROA 개선", roa, roa1),
        test("accrual", "영업현금흐름/기초자산 > ROA", _div(cfo, ta1), roa),
        test("leverage_down", "비유동부채/평균자산 감소", lev(fy), lev(fy - 1), "<"),
        test("current_ratio_up", "유동비율 개선", cr(fy), cr(fy - 1)),
        test("no_issuance", "신주 발행 없음 (자본금+주식발행초과금 불변·감소)", paid_in(fy), paid_in(fy - 1), "<="),
        test("gross_margin_up", "매출총이익률 개선", gm(fy), gm(fy - 1)),
        test("asset_turnover_up", "총자산회전율 개선 (매출 ÷ 기초 총자산)", turn(fy), turn(fy - 1)),
    ]
    scored = [t for t in tests if t["pass"] is not None]
    if len(scored) < 7:
        return _m(reason=f"missing:input:{len(scored)}/9_tests", tests=tests)
    return _m(sum(1 for t in scored if t["pass"]), out_of=len(scored), tests=tests,
              basis="Piotroski F (0~9). 8~9 강함, 0~2 약함. 레버리지는 비유동부채 대용")


# --------------------------------------------------------------------------- group 2


def dividends_from_alot(rows: list, fy: int) -> dict | None:
    """alotMatter rows -> per-year DPS, payout and totals (당기/전기/전전기)."""
    if not rows:
        return None
    by = {}
    for r in rows:
        se, kind = (r.get("se") or "").replace(" ", ""), (r.get("stock_knd") or "-").strip()
        by[(se, kind)] = r

    def series(se, kind="-", scale=1.0):
        r = by.get((se, kind))
        if not r:
            return {}
        out = {}
        for back, f in enumerate(("thstrm", "frmtrm", "lwfr")):
            x = _num(r.get(f))
            if x is not None:
                out[str(fy - back)] = x * scale
        return out
    payout = series("(연결)현금배당성향(%)") or series("현금배당성향(%)") or series("(별도)현금배당성향(%)")
    out = {
        "dps_common": series("주당현금배당금(원)", "보통주"),
        "dps_preferred": series("주당현금배당금(원)", "우선주"),
        "cash_dividends_total": series("현금배당금총액(백만원)", scale=1e6),
        "payout_ratio": {k: x / 100 for k, x in payout.items()},
        "dividend_yield_reported": {k: x / 100 for k, x in series("현금배당수익률(%)", "보통주").items()},
        "stock_dividend_total": series("주식배당금총액(백만원)", scale=1e6),
        "source": "OpenDART alotMatter (사업보고서 배당에 관한 사항)",
    }
    # The section was filed but every cell is "-": no cash dividend for these years.
    out["none_paid"] = not any(out[k] for k in ("dps_common", "cash_dividends_total", "payout_ratio"))
    return out


def treasury_from_tesstk(rows: list) -> dict | None:
    """tesstkAcqsDspsSttus '총계' rows -> common/preferred treasury movements."""
    out = {}
    for r in rows or []:
        if (r.get("acqs_mth1") or "").strip() != "총계":
            continue
        kind = "common" if "보통" in (r.get("stock_knd") or "") else "preferred"
        out[kind] = {k: _num(r.get(f)) or 0 for k, f in (("begin", "bsis_qy"), ("acquired", "change_qy_acqs"),
                                                          ("disposed", "change_qy_dsps"), ("cancelled", "change_qy_incnr"),
                                                          ("end", "trmend_qy"))}
    return out or None


def shareholder_returns(series: dict, fy: int, *, dividends: dict | None, treasury: dict | None,
                        issued_common: float | None) -> dict:
    v = series["values"]
    div_cf, buy_cf, ni = _get(v, fy, "dividends_paid"), _get(v, fy, "buyback"), _parent_income(v, fy)
    declared = ((dividends or {}).get("cash_dividends_total") or {}).get(str(fy))
    if declared is None and dividends is not None and (dividends.get("none_paid") or dividends.get("dps_common")):
        declared = 0.0          # filed the dividend section, no cash dividend for FY
    out = {"dividends": dividends, "treasury": treasury,
           "dividends_paid_cf": div_cf, "buyback_cf": buy_cf, "dividends_declared": declared}
    # The consolidated cash-flow line includes dividends subsidiaries pay to
    # their minority holders (두산에너빌리티 -> 두산밥캣), so the company's own
    # declared total for the year comes first.
    div = declared if declared is not None else div_cf
    if div is None and buy_cf is None:
        out["total_payout_ratio"] = _m(reason="missing:dividends_and_buyback")
    elif ni is None or ni <= 0:
        out["total_payout_ratio"] = _m(reason="not_meaningful:net_loss")
    else:
        total = abs(div or 0) + abs(buy_cf or 0)
        out["total_payout_ratio"] = _m(total / ni, returned=total, dividends=abs(div or 0), buyback=abs(buy_cf or 0),
                                       net_income_parent=ni, dividend_basis="declared" if declared is not None else "cash_flow",
                                       basis="(당해 결산 현금배당 총액 + 현금흐름표 자기주식 취득) ÷ 지배주주 순이익. "
                                             "자기주식 취득은 연결 기준이라 종속회사 취득분이 섞일 수 있음")
    t = (treasury or {}).get("common")
    if t and issued_common:
        out["treasury_ratio"] = _m(t["end"] / issued_common, shares=t["end"], issued=issued_common)
        out["cancelled_ratio"] = _m(t["cancelled"] / issued_common, shares=t["cancelled"])
    return out


DILUTION_HEADINGS = {
    "convertible_bond": re.compile(r"미상환\s*전환사채\s*(?:발행)?\s*현황"),
    "bond_with_warrant": re.compile(r"미상환\s*신주인수권부\s*사채\s*등?\s*(?:발행)?\s*현황"),
    "contingent_convertible": re.compile(r"미상환\s*전환형\s*조건부\s*자본증권\s*(?:발행)?\s*현황"),
}
NONE_DECLARED = re.compile(
    r"미상환\s*전환\s*사채[^<>]{0,160}?(?:발행하지\s*않|해당\s*사항\s*(?:이\s*)?없)"
    r"|전환\s*사채\s*등\s*(?:의\s*)?발행\s*현황\s*[-–:：]?\s*(?:\(\s*기준일[^)]{0,30}\)\s*)?해당\s*사항\s*(?:이\s*)?없")
NONE_TEXT = re.compile(r"해당\s*사항\s*(?:이\s*)?없|해당\s*없음|발행\s*(?:한\s*)?(?:내역|사항)\s*(?:이\s*)?없")


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def dilution_from_report(doc: str, *, receipt: str, period_end: str) -> dict:
    """Outstanding convertibles from a periodic report body.

    Takes the first table after each heading (the period-end table; a later
    '보고서 제출일 현재' table, when present, is kept as `after_period`). In
    the 합계 row -- or in each issue row when there is no total -- the last
    two numbers are 미상환 권면총액 and 전환(행사)가능주식수."""
    tables = list(report_tables(doc))
    out = {"receipt": receipt, "period_end": period_end, "instruments": {}}
    heads = []
    for kind, rx in DILUTION_HEADINGS.items():
        m = rx.search(doc)
        if m:
            heads.append((m.start(), kind))
    heads.sort()
    if not heads:
        # Q1/Q3 reports of large filers may omit 자본금 변동사항 altogether
        # ("분기보고서에 기재하지 않습니다"); a mention elsewhere (a subsidiary's
        # CB in the notes) is not the company's own. Undetermined -> the caller
        # tries the next older report.
        text = _plain(doc)
        if NONE_DECLARED.search(text):
            out.update(status="none_declared", potential_shares=0,
                       note="보고서 자본금 변동사항에 '전환사채 등 발행 없음' 명시")
        elif _capital_section_filled(text):
            out.update(status="not_in_capital_section", potential_shares=0,
                       note="자본금 변동사항이 기재돼 있으나 미상환 전환사채 등 항목이 없음 (있으면 기재 의무)")
        else:
            out.update(status="undetermined", potential_shares=None)
        return out
    for i, (pos, kind) in enumerate(heads):
        stop = heads[i + 1][0] if i + 1 < len(heads) else pos + 60000
        after = [t for t in tables if pos < t["start"] < stop]
        between = _plain(doc[pos:after[0]["start"]] if after else doc[pos:min(stop, pos + 3000)])
        if not after or (NONE_TEXT.search(between) and len(between) < 400):
            out["instruments"][kind] = {"outstanding": 0, "shares": 0, "status": "none_reported"}
            continue
        parsed = []
        for t in after[:4]:
            p = _dilution_table(t, doc)
            if p:
                parsed.append(p)
        if not parsed:
            out["instruments"][kind] = {"status": "table_not_parsed"}
            continue
        first = parsed[0]
        item = {**first, "status": "reported"}
        later = [p for p in parsed[1:] if p.get("as_of") and p["as_of"] != first.get("as_of")]
        if later:
            item["after_period"] = later[0]
        out["instruments"][kind] = item
    parsed = [x for x in out["instruments"].values() if x.get("status") in ("reported", "none_reported")]
    unparsed = len(parsed) != len(out["instruments"])
    out["status"] = "partial" if unparsed else "reported"
    out["potential_shares"] = sum(x["shares"] for x in parsed) if parsed else None
    return out


CAPITAL_SECTION = re.compile(r"자본금\s*변동\s*사항(.{0,8000}?)주식의\s*총수\s*등")


def _capital_section_filled(text: str) -> bool:
    """True when some 자본금 변동사항 section has real content -- not the table
    of contents (dashes) nor a '분기보고서에 기재하지 않습니다' placeholder."""
    for m in CAPITAL_SECTION.finditer(text):
        body = m.group(1)
        if re.search(r"기재\s*하지|기재를\s*생략|생략합니다", body):
            continue
        if len(re.sub(r"[-\s\d.]", "", body)) >= 40:
            return True
    return False


def _dilution_table(t, doc):
    rows = t["rows"]
    text = " ".join(" ".join(r) for r in rows) + " " + t["before"]
    if "권면" not in text and "미상환" not in text:
        return None
    scale = unit_scale(t["before"] + " " + " ".join(rows[0] if rows else []))
    total = [r for r in rows if r and re.sub(r"\s", "", r[0]) in ("합계", "합 계", "계", "총계")]
    data = total or [r for r in rows[1:] if sum(1 for c in r if cell_number(c) is not None) >= 4]
    if not data:
        return None
    face = shares = 0
    for r in data:
        nums = [cell_number(c) for c in r if cell_number(c) is not None]
        if len(nums) < 2:
            continue
        face += nums[-2]
        shares += nums[-1]
    as_of = re.search(r"기준일\s*[:：]?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", t["before"])
    return {"outstanding": face * (scale or 1), "shares": shares, "scale": scale,
            "as_of": f"{as_of.group(1)}-{int(as_of.group(2)):02d}-{int(as_of.group(3)):02d}" if as_of else None,
            "rows": len(data), "from_total_row": bool(total)}


# --------------------------------------------------------------------------- group 3


def lease_from_instance(contexts: dict, facts: list, *, fs_div: str, instant: str) -> tuple[int | None, str | None]:
    """Carrying lease liabilities at `instant` from the XBRL notes: the
    LeaseLiabilities total, else current + non-current. Maturity-band and
    related-party members are not totals and are ignored; any disagreement
    between qualifying contexts drops the value. When only the undiscounted
    maturity total is tagged (삼성전자 FY2025), that is returned and labelled:
    it overstates the carrying amount by the discount."""
    from .xbrl_notes import SCOPE_AXIS, SCOPE_MEMBER, TOTAL_MEMBERS
    uses_scope = any(SCOPE_AXIS in c["dims"] for c in contexts.values())

    def ok(ctx):
        if ctx is None or ctx["typed"] or ctx["instant"] != instant:
            return False
        dims = dict(ctx["dims"])
        scope = dims.pop(SCOPE_AXIS, None)
        if uses_scope and scope != SCOPE_MEMBER[fs_div]:
            return False
        # Category members (amortised cost / outside IFRS 7 ...) are not
        # totals: NAVER tags 0 under one and the whole balance under another.
        return all((a, m) in TOTAL_MEMBERS for a, m in dims.items())

    def value(concept):
        vals = {f["text"] for f in facts if f["concept"] == concept and ok(contexts.get(f["context"]))}
        nums = set()
        for x in vals:
            try:
                nums.add(round(float(x)))
            except ValueError:
                return None
        # Filers sometimes tag the same line once in won and once rounded to 백만원 x 10^6.
        if len({round(n, -6) for n in nums}) == 1 and nums:
            return max(nums)
        return None
    total = value("LeaseLiabilities")
    if total is not None:
        return total, "carrying"
    cur, non = value("CurrentLeaseLiabilities"), value("NoncurrentLeaseLiabilities")
    if cur is not None and non is not None:
        return cur + non, "carrying"
    gross = value("GrossLeaseLiabilities")
    return (gross, "undiscounted") if gross is not None else (None, None)


def ev_bridge(series: dict, fy: int, *, financial: bool, lease_in_net_debt: bool, xbrl_lease: int | None,
              xbrl_lease_basis: str | None,
              ebitda: float | None, ebitda_card: str | None) -> dict:
    if financial:
        return {"reason": "not_applicable:financial"}
    v = series["values"]
    g = lambda k: _get(v, fy, k)  # noqa: E731
    items = []
    db = (g("db_liability") or 0) - (g("db_asset") or 0) if (g("db_liability") is not None or g("db_asset") is not None) else None
    if db is not None:
        items.append({"key": "net_pension", "label": "순확정급여부채 (확정급여채무 − 사외적립자산)", "value": db,
                      "sign": 1 if db > 0 else 0, "core": db > 0,
                      "note": None if db > 0 else "적립 초과(순자산) — EV에서 빼지 않음"})
    if not lease_in_net_debt:
        if xbrl_lease is not None and xbrl_lease_basis == "carrying":
            items.append({"key": "lease_untagged", "label": "리스부채 (재무상태표 미표시분, XBRL 주석)", "value": xbrl_lease,
                          "sign": 1, "core": True})
        elif xbrl_lease is not None:
            items.append({"key": "lease_untagged", "label": "리스부채 (할인 전 계약 현금흐름, XBRL 주석)", "value": xbrl_lease,
                          "sign": 1, "core": True,
                          "note": "장부금액 태그 없음 — 할인 전 금액이라 장부가보다 큼(상한)"})
        else:
            items.append({"key": "lease_untagged", "label": "리스부채", "value": None, "sign": 1, "core": True,
                          "note": "재무상태표·XBRL 모두 태그 없음 — 순차입금에 리스 미포함 가능"})
    prov = _sum(g("provisions_current"), g("provisions_noncurrent"))
    if prov is not None:
        items.append({"key": "provisions", "label": "충당부채 (유동+비유동)", "value": prov, "sign": 1, "core": False,
                      "note": "판매보증 등 영업성 충당부채 포함 — 보수적 EV에만 가산"})
    em = g("equity_method")
    if em is not None:
        items.append({"key": "equity_method", "label": "관계기업·공동기업 투자 (비영업자산)", "value": em, "sign": -1, "core": True})
    core = sum(i["value"] * i["sign"] for i in items if i["core"] and i["value"] is not None)
    conservative = core + sum(i["value"] * i["sign"] for i in items if not i["core"] and i["value"] is not None)
    capex = _capex(v, fy)
    interest = _sum(g("cash_interest_operating"), g("cash_interest_financing"))
    lease_pay = g("lease_repayment")
    if ebitda is None or capex is None or interest is None:
        fccr = _m(reason="missing:ebitda_capex_or_interest_paid")
    else:
        charges = abs(interest) + abs(lease_pay or 0)
        fccr = (_m((ebitda - abs(capex)) / charges, ebitda=ebitda, ebitda_card=ebitda_card, capex=abs(capex),
                   interest_paid=abs(interest), lease_principal_paid=abs(lease_pay) if lease_pay is not None else None,
                   lease_missing=lease_pay is None,
                   basis="(EBITDA − 설비투자) ÷ (이자 지급액 + 리스부채 상환액), 현금흐름표 기준")
                if charges else _m(reason="not_meaningful:no_fixed_charges"))
    return {"period_end": f"{fy}-12-31", "items": items, "adjustment_core": core,
            "adjustment_conservative": conservative, "lease_in_net_debt": lease_in_net_debt,
            "fixed_charge_coverage": fccr,
            "basis": "조정 EV = EV + 순확정급여부채 + 미표시 리스부채 − 관계기업투자; 보수적 EV는 충당부채까지 가산"}


# --------------------------------------------------------------------------- industry kits


def _da(v, y):
    total = _get(v, y, "cf_dep_amort_total")
    if total is None:
        total = _get(v, y, "da_total_sec")
    if total is None:
        parts = [_get(v, y, "cf_depreciation"), _get(v, y, "cf_amortisation")]
        total = _sum(*parts) if parts[0] is not None else None
    return abs(total) if total is not None else None


def _days(balance_now, balance_before, flow):
    avg = _avg(balance_now, balance_before) if balance_before is not None else balance_now
    return avg / flow * 365 if avg is not None and flow else None


def industry_metrics(series: dict, fy: int, kit: str | None) -> dict | None:
    """The few ratios a kit is read by, over the years available.

    trading_house    매출총이익률, 영업이익률, 지분법이익 ÷ 세전이익, 매출채권·재고 일수
    mining_smelting  감가·감모상각 ÷ 매출, 설비투자 ÷ 감가상각(재투자율), EBITDA 마진, 손상차손
    """
    if kit not in ("trading_house", "mining_smelting"):
        return None
    v = series["values"]
    years = [y for y in series["years"] if y <= fy][-5:]
    hist = {}
    for y in years:
        rev, op = _get(v, y, "revenue"), _get(v, y, "op")
        row = {}
        if kit == "trading_house":
            gp = _gross_profit(v, y)
            pre, em = _get(v, y, "pretax_income"), _get(v, y, "equity_method_income")
            row["gross_margin"] = _div(gp, rev)
            row["op_margin"] = _div(op, rev)
            row["equity_method_share"] = _div(em, pre) if pre and pre > 0 else None
            row["dso"] = _days(_get(v, y, "receivables"), _get(v, y - 1, "receivables"), rev)
            cogs = _get(v, y, "cogs")
            if cogs is None and rev is not None and _gross_profit(v, y) is not None:
                cogs = rev - _gross_profit(v, y)
            row["dio"] = _days(_get(v, y, "inventory"), _get(v, y - 1, "inventory"), cogs)
        else:
            da, capex = _da(v, y), _capex(v, y)
            row["da_to_sales"] = _div(da, rev)
            row["capex_to_da"] = _div(abs(capex) if capex is not None else None, da)
            row["ebitda_margin"] = _div(op + da, rev) if op is not None and da is not None else None
            imp = _get(v, y, "impairment")
            row["impairment"] = abs(imp) if imp is not None else None
            row["impairment_to_assets"] = _div(abs(imp) if imp is not None else None, _get(v, y, "assets"))
        if any(x is not None for x in row.values()):
            hist[str(y)] = row
    if not hist:
        return None
    labels = {
        "trading_house": {"gross_margin": "매출총이익률", "op_margin": "영업이익률", "equity_method_share": "지분법이익 ÷ 세전이익",
                          "dso": "매출채권 회전일수", "dio": "재고 회전일수"},
        "mining_smelting": {"da_to_sales": "감가·감모상각 ÷ 매출", "capex_to_da": "설비투자 ÷ 감가상각 (재투자율)",
                            "ebitda_margin": "EBITDA 마진", "impairment": "손상차손", "impairment_to_assets": "손상차손 ÷ 총자산"},
    }[kit]
    return {"kit": kit, "labels": labels, "history": hist}


# --------------------------------------------------------------------------- entry


def investor_metrics(fy_reports: dict, *, fiscal_year: int, financial: bool, dividends_rows=None,
                     treasury_rows=None, dilution=None, issued_common=None, lease_in_net_debt=True,
                     xbrl_lease=None, xbrl_lease_basis=None, ebitda=None, ebitda_card=None,
                     balance_overrides=None, kit=None) -> dict:
    series = annual_series(fy_reports)
    # Note balances (trade receivables / payables split out of a face-statement
    # "trade and other" total) fill a year only where the face row is missing.
    for year, vals in (balance_overrides or {}).items():
        for key, value in vals.items():
            if value is not None and key not in series["values"].setdefault(year, {}):
                series["values"][year][key] = value
                series["source"].setdefault(year, {})[key] = {"match": "xbrl_note"}
    fy = fiscal_year
    out = {
        "schema": SCHEMA, "fiscal_year": fy, "years": series["years"], "financial": financial,
        "growth": growth(series, fy, financial=financial),
        "returns": returns(series, fy, financial=financial),
        "quality": quality(series, fy, financial=financial),
        "distress": {**altman(series, fy, financial=financial), "piotroski": piotroski(series, fy, financial=financial)},
        "shareholder": shareholder_returns(series, fy, dividends=dividends_from_alot(dividends_rows or [], fy),
                                           treasury=treasury_from_tesstk(treasury_rows or []), issued_common=issued_common),
        "dilution": dilution,
        "industry": industry_metrics(series, fy, kit),
        "ev_bridge": ev_bridge(series, fy, financial=financial, lease_in_net_debt=lease_in_net_debt,
                               xbrl_lease=xbrl_lease, xbrl_lease_basis=xbrl_lease_basis, ebitda=ebitda,
                               ebitda_card=ebitda_card),
    }
    if dilution and dilution.get("potential_shares") is not None and issued_common:
        dilution["potential_ratio"] = dilution["potential_shares"] / issued_common
        dilution["issued_common"] = issued_common
    return out
