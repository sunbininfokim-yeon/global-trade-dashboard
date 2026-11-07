"""Korean bank credit quality in depth, from the Financial Supervisory Service's FISIS open API.

Every FISIS table is per bank, so each series here is the sum over every domestic bank FISIS lists
(closed ones included: a quarter before a merger counts both), and every ratio is a ratio of sums --
the way the FSS aggregates its own sector figures. Nothing is estimated.

What it produces (config/kr_bank_credit_v1.json, then cards on the KOR macro panel):

* 연체율 by segment (SA040: household, corporate, SME, sole proprietors, total).
* The delinquency flow (SA061): new delinquencies, write-offs, restructurings (대환) and loans that
  became current again (정상화), per quarter. FISIS reports them year-to-date; the quarter is the
  difference. Opening balance + new - write-offs - 대환 - 정상화 = closing balance, exactly, so a
  falling rate can be told apart from write-offs that only cleaned the book.
* Early delinquency: the quarter's new delinquencies over the loan book at the start of the quarter
  (분기 신규연체율), and loans 1 day to 1 month overdue (1일 이상 원금 연체 - 1개월 이상 원리금 연체).
* Asset classification (SA015): 요주의 / 고정 / 회수의문 / 추정손실.
* Loss absorption: loan-loss reserves over NPLs (SA042 / SA015), BIS and CET1 ratios (SA014), and
  (NPLs - reserves) / CET1 capital -- the IMF FSI measure the China panel also shows.
* The latest quarter bank by bank.

Not in the API: NPLs newly classified in a quarter and how they were cleared (write-off, sale,
collateral recovery), and mortgage NPL ratios. kr_npl_release.py reads those from the FSS press-release
PDFs and wire_kr_bank_credit.py adds them as panels on the 부실채권비율 card.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from .free_cards import _fisis, _num

CACHE = Path(__file__).resolve().parent.parent / "config" / "kr_bank_credit_v1.json"

# (list_no, account): every series the cards need, per bank.
STOCK = {
    "SA040": ["A1", "A2", "B1", "B2", "BB1", "BB2", "BBA1", "BBA2", "C1", "C2"],
    "SA015": ["A", "B6", "B1", "B2", "B3", "B4"],
    "SA042": ["A"],
    "SA014": ["B0", "B", "C"],
}
# SA061: five columns per account -- a 신규연체, b 상각, c 대환, d 정상화 등 (year to date), e 연체잔액.
FLOW_1M = {"E": "기업", "E2": "중소기업", "E21": "개인사업자", "F": "가계", "G": "공공·기타", "H": "신용카드"}
FLOW_1D = {"A": "기업", "A2": "중소기업", "A21": "개인사업자", "B": "가계", "C": "공공·기타", "D": "신용카드"}


def _window() -> tuple[str, str]:
    y = date.today().year
    return f"{y - 9}01", f"{y}12"          # FISIS refuses spans over 40 quarters


def _rows(cd: str, list_no: str, account: str) -> list[dict[str, Any]]:
    a, b = _window()
    q = f"financeCd={cd}&listNo={list_no}&accountCd={account}&term=Q&startBaseMm={a}&endBaseMm={b}"
    return _fisis("statisticsInfoSearch", q).get("list") or []


def fetch() -> dict[str, Any]:
    """Every series, summed over banks, plus each bank's latest ratios. Raises when FISIS is down."""
    banks = {b["finance_cd"]: b["finance_nm"] for b in _fisis("companySearch", "partDiv=A").get("list") or []}
    if len(banks) < 15:
        raise RuntimeError(f"FISIS bank list has {len(banks)} entries")
    with ThreadPoolExecutor(max_workers=8) as ex:
        live = [cd for cd, rows in zip(banks, ex.map(lambda cd: _rows(cd, "SA015", "A"), banks)) if rows]
        jobs = [(cd, l, a) for cd in live for l, accs in STOCK.items() for a in accs] + \
               [(cd, "SA061", a) for cd in live for a in [*FLOW_1M, *FLOW_1D]]
        results = list(ex.map(lambda j: _rows(*j), jobs))

    stock: dict[str, dict[str, float]] = {}          # "SA040.A1" -> {yyyymm: sum}
    flow: dict[str, dict[str, float]] = {}           # "SA061.E.a" -> {yyyymm: sum}
    per_bank: dict[str, dict[str, dict[str, float]]] = {}
    for (cd, l, acc), rows in zip(jobs, results):
        for r in rows:
            ym = r["base_month"]
            if l == "SA061":
                for col in "abcde":
                    v = _num(r.get(col))
                    if v is not None:
                        k = f"{l}.{acc}.{col}"
                        flow.setdefault(k, {})[ym] = flow.get(k, {}).get(ym, 0.0) + v
                continue
            v = _num(r.get("a"))
            if v is None:
                continue
            k = f"{l}.{acc}"
            stock.setdefault(k, {})[ym] = stock.get(k, {}).get(ym, 0.0) + v
            per_bank.setdefault(cd, {}).setdefault(k, {})[ym] = v
    if not stock.get("SA040.A1") or not stock.get("SA015.B4"):
        raise RuntimeError("FISIS returned no loan or NPL rows")

    latest = max(stock["SA015.B4"])
    banks_latest = []
    for cd in live:
        s = per_bank.get(cd, {})
        g = lambda k: (s.get(k) or {}).get(latest)  # noqa: E731
        a1, a2, tot, npl, res = g("SA040.A1"), g("SA040.A2"), g("SA015.A"), g("SA015.B4"), g("SA042.A")
        if not tot:
            continue
        banks_latest.append({
            "name": banks[cd].replace("주식회사 ", "").replace(" 주식회사", "").replace("주식회사", ""),
            "delinq": round(a2 / a1 * 100, 3) if a1 and a2 is not None else None,
            "npl": round(npl / tot * 100, 3) if npl is not None else None,
            "coverage": round(res / npl * 100, 1) if res and npl else None,
            "loans_tn": round(tot / 1e12, 1),
        })
    return {"stock": stock, "flow": flow, "banks": banks_latest, "banks_asof": latest}


# --------------------------------------------------------------------------
# Series arithmetic (quarter-end yyyymm keys)
# --------------------------------------------------------------------------

def _q(ym: str) -> str:
    return f"{ym[:4]}-{(int(ym[4:6]) - 1) // 3 * 3 + 1:02d}-01"


def _label(ym: str) -> str:
    return f"{ym[2:4]}.{(int(ym[4:6]) - 1) // 3 + 1}Q"


def _prev(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:6]) - 3
    return f"{y - 1}12" if m <= 0 else f"{y}{m:02d}"


def quarterly(ytd: dict[str, float]) -> dict[str, float]:
    """Year-to-date sums -> the quarter's own amount (March is its own quarter)."""
    out = {}
    for ym, v in ytd.items():
        if ym[4:6] == "03":
            out[ym] = v
        elif _prev(ym) in ytd:
            out[ym] = v - ytd[_prev(ym)]
    return out


def ratio(n: dict[str, float], d: dict[str, float], scale: float = 100.0) -> dict[str, float]:
    return {k: v / d[k] * scale for k, v in n.items() if d.get(k)}


def build(doc: dict[str, Any]) -> dict[str, Any]:
    """Cards (headline series) and their detail panels from the cached sums."""
    st, fl = doc["stock"], doc["flow"]
    S = lambda k: st.get(k) or {}  # noqa: E731
    F = lambda k: fl.get(k) or {}  # noqa: E731
    tn = lambda d: {k: v / 1e12 for k, v in d.items()}  # noqa: E731
    months = sorted(S("SA040.A1"))

    def pts(d: dict[str, float]) -> list[tuple[str, float]]:
        return [(_q(k), v) for k, v in sorted(d.items())]

    def panel_series(keys: list[str], series: list[tuple[str, dict[str, float]]], digits: int = 3):
        return [{"label": lab, "values": [round(d[k], digits) if k in d else None for k in keys]} for lab, d in series]

    last = lambda n: months[-n:]  # noqa: E731

    # 연체율 by segment
    seg = [("가계", ratio(S("SA040.C2"), S("SA040.C1"))), ("기업", ratio(S("SA040.B2"), S("SA040.B1"))),
           ("중소기업", ratio(S("SA040.BB2"), S("SA040.BB1"))), ("개인사업자", ratio(S("SA040.BBA2"), S("SA040.BBA1")))]
    total = ratio(S("SA040.A2"), S("SA040.A1"))

    # Delinquency flow, 1 month+ basis, all segments except card receivables (not in SA040's book)
    segs_1m = ["E", "F", "G"]
    q = {col: {} for col in "abcd"}
    for acc in segs_1m:
        for col in "abcd":
            for k, v in quarterly(F(f"SA061.{acc}.{col}")).items():
                q[col][k] = q[col].get(k, 0.0) + v
    bal = {}
    for acc in segs_1m:
        for k, v in F(f"SA061.{acc}.e").items():
            bal[k] = bal.get(k, 0.0) + v
    fk = [k for k in last(16) if all(k in q[c] for c in "abcd")]

    # Early delinquency: new delinquencies in the quarter / loans at the start of the quarter
    def new_rate(acc: str, den: str) -> dict[str, float]:
        nq, d = quarterly(F(f"SA061.{acc}.a")), S(den)
        return {k: v / d[_prev(k)] * 100 for k, v in nq.items() if d.get(_prev(k))}

    new_total = {}
    for k in months:
        n = sum(quarterly(F(f"SA061.{a}.a")).get(k, 0.0) for a in segs_1m)
        if n and S("SA040.A1").get(_prev(k)):
            new_total[k] = n / S("SA040.A1")[_prev(k)] * 100
    new_seg = [("가계", new_rate("F", "SA040.C1")), ("기업", new_rate("E", "SA040.B1")),
               ("중소기업", new_rate("E2", "SA040.BB1")), ("개인사업자", new_rate("E21", "SA040.BBA1"))]
    early = [(lab, tn({k: F(f"SA061.{a1}.e")[k] - F(f"SA061.{a30}.e")[k]
                       for k in F(f"SA061.{a30}.e") if k in F(f"SA061.{a1}.e")}))
             for lab, a1, a30 in (("가계", "B", "F"), ("기업", "A", "E"), ("중소기업", "A2", "E2"), ("개인사업자", "A21", "E21"))]

    # Classification and loss absorption
    stages = [("요주의", tn(S("SA015.B6"))), ("고정", tn(S("SA015.B1"))), ("회수의문", tn(S("SA015.B2"))), ("추정손실", tn(S("SA015.B3")))]
    coverage = ratio(S("SA042.A"), S("SA015.B4"))
    bis, cet1 = ratio(S("SA014.B"), S("SA014.C")), ratio(S("SA014.B0"), S("SA014.C"))
    net_npl = {k: (v - S("SA042.A")[k]) / S("SA014.B0")[k] * 100 for k, v in S("SA015.B4").items()
               if k in S("SA042.A") and S("SA014.B0").get(k)}

    banks = doc.get("banks") or []
    bank_asof = _label(doc.get("banks_asof") or months[-1])
    bank_panel = lambda key, lab: {  # noqa: E731
        "id": f"banks_{key}", "label": "은행별", "type": "hbar", "unit": "%", "asof": bank_asof,
        "rows": [{"label": b["name"], "value": b[key], "sub": f"대출 {b['loans_tn']:,.0f}조원"}
                 for b in sorted(banks, key=lambda b: -(b[key] or 0)) if b.get(key) is not None],
        "note_ko": f"{bank_asof} 말 은행별 {lab}. 금융감독원 FISIS."}

    k12, k16 = last(12), last(16)
    out = {
        "delinq_all": {
            "points": pts(total),
            "panels": [
                {"id": "segments", "label": "부문별", "type": "bars", "unit": "%", "dates": [_label(k) for k in k12],
                 "series": panel_series(k12, seg), "line": panel_series(k12, [("전체", total)])[0],
                 "note_ko": "국내은행 부문별 연체율(분기말, 1개월 이상 원리금 연체 / 대출잔액). 선은 전체. 금융감독원 FISIS, 은행별 합산. 중소기업은 기업의 일부, 개인사업자는 중소기업의 일부입니다."},
                {"id": "flow", "label": "연체 흐름", "type": "stack", "unit": "조원", "dates": [_label(k) for k in fk],
                 "series": panel_series(fk, [("신규연체", tn(q["a"])), ("상각", tn({k: -v for k, v in q["b"].items()})),
                                             ("정상화 등", tn({k: -v for k, v in q["d"].items()})),
                                             ("대환", tn({k: -v for k, v in q["c"].items()}))], 2),
                 "line": panel_series(fk, [("연체잔액(분기말)", tn(bal))], 2)[0],
                 "note_ko": "분기 중 새로 연체된 금액(+)과 연체에서 빠져나간 금액(−: 상각, 정상화, 대환). 기초 연체잔액 + 신규 − 상각 − 정상화 − 대환 = 기말 연체잔액. "
                            "연체율이 내려간 분기에 상각 막대가 크면 개선이 아니라 장부 정리입니다. 1개월 이상 원리금 연체, 기업·가계·공공(신용카드채권 제외). 금융감독원 FISIS 'SA061 신규연체 및 상각 현황'."},
                bank_panel("delinq", "연체율"),
            ],
        },
        "early_delinq": {
            "label": "신규연체율(분기)", "unit": "%", "format": "pct2",
            "note_ko": "분기 중 새로 1개월 이상 연체된 금액 / 분기 초 대출잔액(%). 연체율(잔액)보다 먼저 움직이는 선행 지표입니다. 금감원 월별 신규연체율의 약 3배 수준(분기 누적). 금융감독원 FISIS, 은행별 합산.",
            "points": pts(new_total),
            "panels": [
                {"id": "new_segments", "label": "부문별", "type": "bars", "unit": "%", "dates": [_label(k) for k in k12],
                 "series": panel_series(k12, new_seg), "line": panel_series(k12, [("전체", new_total)])[0],
                 "note_ko": "부문별 분기 신규연체율(분기 중 신규 연체 / 분기 초 대출잔액). 금융감독원 FISIS. 중소기업은 기업의 일부, 개인사업자는 중소기업의 일부입니다."},
                {"id": "early_balance", "label": "1개월 미만 연체", "type": "bars", "unit": "조원", "dates": [_label(k) for k in k12],
                 "series": panel_series(k12, early, 2),
                 "note_ko": "연체 1일 이상(원금 기준) 잔액 − 1개월 이상(원리금 기준) 잔액 = 막 연체되기 시작한 대출. 이 막대가 커지면 다음 분기 연체율이 오르기 쉽습니다. 두 기준의 정의가 조금 달라(원금 vs 원리금) 근사치입니다. 금융감독원 FISIS. 중소기업은 기업의 일부, 개인사업자는 중소기업의 일부입니다."},
            ],
        },
        "npl_ratio": {
            "points": pts(ratio(S("SA015.B4"), S("SA015.A"))),
            "panels": [
                {"id": "stages", "label": "건전성 단계", "type": "stack", "unit": "조원", "dates": [_label(k) for k in k16],
                 "series": panel_series(k16, stages, 2),
                 "note_ko": "국내은행 여신을 건전성 분류별로 쌓은 잔액(조원). 고정·회수의문·추정손실이 부실채권(고정이하여신)이고, 요주의는 그 직전 단계입니다. 요주의가 두꺼워지면 몇 분기 뒤 부실채권이 늘기 쉽습니다. 금융감독원 FISIS SA015."},
                bank_panel("npl", "부실채권비율"),
            ],
        },
        "loss_absorption": {
            "label": "손실흡수력(충당금/부실채권)", "unit": "%", "format": "pct1",
            "note_ko": "대손충당금 / 고정이하여신(%). 100%면 부실채권 전액이 이미 비용으로 쌓여 있다는 뜻이고, 내려갈수록 앞으로 이익에서 더 떼어 내야 합니다. 금융감독원 FISIS, 은행별 합산.",
            "points": pts(coverage),
            "panels": [
                {"id": "buffer", "label": "부실 vs 충당금", "type": "bars", "unit": "조원", "dates": [_label(k) for k in k12],
                 "series": panel_series(k12, [("부실채권(고정이하)", tn(S("SA015.B4"))), ("대손충당금", tn(S("SA042.A")))], 2),
                 "note_ko": "부실채권 잔액과 쌓아 둔 대손충당금(조원). 충당금 막대가 더 길면 부실이 모두 손실로 확정돼도 추가 비용이 없습니다."},
                {"id": "capital", "label": "자본비율", "type": "lines", "unit": "%", "dates": [_label(k) for k in months],
                 "series": panel_series(months, [("BIS 총자본비율", bis), ("보통주자본비율(CET1)", cet1)], 2),
                 "note_ko": "국내은행 BIS 총자본비율과 보통주자본비율(자기자본 / 위험가중자산, 은행별 합산). 충당금을 넘는 손실은 이 자본이 흡수합니다. 규제 최저: 총자본 10.5%, CET1 7%(완충자본 포함)."},
                {"id": "net_npl", "label": "순부실/자본", "type": "bars", "unit": "%", "dates": [_label(k) for k in k12],
                 "series": panel_series(k12, [("(부실채권 − 충당금) / 보통주자본", net_npl)], 2),
                 "note_ko": "충당금으로 덮이지 않은 부실채권이 보통주자본의 몇 %인지. 음수면 충당금이 부실채권보다 많습니다. IMF 금융건전성지표와 같은 정의라 중국 패널의 같은 지표와 비교할 수 있습니다."},
                bank_panel("coverage", "충당금 적립률"),
            ],
        },
    }
    return out
