"""Korean non-bank credit quality from FISIS: savings banks, card companies, capital/lease firms.

Same method as kr_bank_credit.py: FISIS tables are per company, so every series is the sum over all
companies FISIS lists in the sector (closed ones included for the quarters they existed) and every
ratio is a ratio of sums. Non-banks lend to weaker borrowers than banks, so their delinquency moves
first and further -- the sector comparison panel puts the four side by side.

* 저축은행 (FISIS partDiv E): 연체율 (SE019 C1/C2), 고정이하 / 고정 / 회수의문 / 추정손실 and
  loan-loss reserves (SE008), BIS ratio per bank (SE018).
* 신용카드사 (C) and 캐피탈 = 리스 (K) + 할부금융 (T): receivables 1 month+ overdue over managed
  receivables (X117 A5 / A), by how long they are overdue (1-3 / 3-6 / 6 months+), NPLs (X008 A4).

Not here: 상호금융 (농협·신협·수협·산림조합 단위조합). FISIS lists them one cooperative at a time
(over 2,000) and has no delinquency table for them, only 고정이하 -- too many calls for a daily job.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from .free_cards import _fisis, _num

CACHE = Path(__file__).resolve().parent.parent / "config" / "kr_nonbank_credit_v1.json"

# sector -> (partDiv list, {list_no: [accounts]}, probe (list_no, account))
SECTORS: dict[str, tuple[tuple[str, ...], dict[str, list[str]], tuple[str, str]]] = {
    "sb": (("E",), {"SE019": ["C1", "C2"], "SE008": ["A1", "A21", "A22", "A23", "A3", "A6"], "SE018": ["A"]}, ("SE019", "C2")),
    "card": (("C",), {"X117": ["A", "A1", "A2", "A3", "A4", "A5"], "X008": ["A", "A4", "C"]}, ("X117", "A")),
    "cap": (("K", "T"), {"X117": ["A", "A1", "A2", "A3", "A4", "A5"], "X008": ["A", "A4", "C"]}, ("X117", "A")),
}


def _window() -> tuple[str, str]:
    y = date.today().year
    return f"{y - 9}01", f"{y}12"


def _list_no(list_no: str, part: str) -> str:
    return list_no.replace("X", "S" + part) if list_no.startswith("X") else list_no


def _rows(cd: str, list_no: str, account: str) -> list[dict[str, Any]]:
    a, b = _window()
    q = f"financeCd={cd}&listNo={list_no}&accountCd={account}&term=Q&startBaseMm={a}&endBaseMm={b}"
    try:
        return _fisis("statisticsInfoSearch", q).get("list") or []
    except RuntimeError as exc:
        if " 013 " in f" {exc} " or "검색된 데이터가 없습니다" in str(exc):
            return []
        raise


def _clean(name: str) -> str:
    for s in ("주식회사 ", " 주식회사", "주식회사", "㈜", "(주)"):
        name = name.replace(s, "")
    return name.strip()


def fetch() -> dict[str, Any]:
    """Every sector's sums and each company's latest figures. Raises when FISIS is down."""
    out: dict[str, Any] = {"stock": {}, "firms": {}, "asof": {}}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sec, (parts, tables, (plist, pacc)) in SECTORS.items():
            firms: dict[str, tuple[str, str]] = {}            # cd -> (name, partDiv)
            for part in parts:
                for c in _fisis("companySearch", f"partDiv={part}").get("list") or []:
                    firms[c["finance_cd"]] = (c["finance_nm"], part)
            if not firms:
                raise RuntimeError(f"FISIS lists no companies for {sec}")
            probe = list(ex.map(lambda cd: _rows(cd, _list_no(plist, firms[cd][1]), pacc), firms))
            live = [cd for cd, rows in zip(firms, probe) if rows]
            jobs = [(cd, l, a) for cd in live for l, accs in tables.items() for a in accs if (l, a) != (plist, pacc)]
            results = list(ex.map(lambda j: _rows(j[0], _list_no(j[1], firms[j[0]][1]), j[2]), jobs))
            jobs = [(cd, plist, pacc) for cd in live] + jobs
            results = [r for cd, r in zip(firms, probe) if r] + results

            stock: dict[str, dict[str, float]] = {}
            per: dict[str, dict[str, dict[str, float]]] = {}
            for (cd, l, acc), rows in zip(jobs, results):
                for r in rows:
                    v = _num(r.get("a"))
                    if v is None:
                        continue
                    k, ym = f"{l}.{acc}", r["base_month"]
                    stock.setdefault(k, {})[ym] = stock.get(k, {}).get(ym, 0.0) + v
                    per.setdefault(cd, {}).setdefault(k, {})[ym] = v
            if not stock:
                raise RuntimeError(f"FISIS returned no rows for {sec}")
            den = f"{plist}.{pacc}"
            latest = max(stock[den])
            rows_out = []
            for cd in live:
                s = per.get(cd, {})
                g = lambda k: (s.get(k) or {}).get(latest)  # noqa: E731
                if sec == "sb":
                    tot, dl = g("SE019.C2"), g("SE019.C1")
                    rows_out.append({"name": _clean(firms[cd][0]), "loans_tn": round(tot / 1e12, 2) if tot else None,
                                     "delinq": round(dl / tot * 100, 2) if tot and dl is not None else None,
                                     "npl": round(g("SE008.A3") / g("SE008.A1") * 100, 2) if g("SE008.A1") and g("SE008.A3") is not None else None,
                                     "bis": g("SE018.A")})
                else:
                    tot, dl = g("X117.A"), g("X117.A5")
                    rows_out.append({"name": _clean(firms[cd][0]), "loans_tn": round(tot / 1e12, 2) if tot else None,
                                     "delinq": round(dl / tot * 100, 2) if tot and dl is not None else None,
                                     "npl": round(g("X008.A4") / g("X008.A") * 100, 2) if g("X008.A") and g("X008.A4") is not None else None})
            out["stock"][sec] = stock
            out["firms"][sec] = [r for r in rows_out if r["loans_tn"]]
            out["asof"][sec] = latest
    return out


# --------------------------------------------------------------------------
# Cards and panels
# --------------------------------------------------------------------------

def _q(ym: str) -> str:
    return f"{ym[:4]}-{(int(ym[4:6]) - 1) // 3 * 3 + 1:02d}-01"


def _label(ym: str) -> str:
    return f"{ym[2:4]}.{(int(ym[4:6]) - 1) // 3 + 1}Q"


def ratio(n: dict[str, float], d: dict[str, float]) -> dict[str, float]:
    return {k: v / d[k] * 100 for k, v in n.items() if d.get(k)}


NAMES = {"sb": "저축은행", "card": "카드사", "cap": "캐피탈"}


def build(doc: dict[str, Any], bank_delinq: dict[str, float] | None = None) -> dict[str, Any]:
    st = doc["stock"]
    S = lambda sec, k: (st.get(sec) or {}).get(k) or {}  # noqa: E731
    tn = lambda d: {k: v / 1e12 for k, v in d.items()}  # noqa: E731
    rate = {
        "sb": ratio(S("sb", "SE019.C1"), S("sb", "SE019.C2")),
        "card": ratio(S("card", "X117.A5"), S("card", "X117.A")),
        "cap": ratio(S("cap", "X117.A5"), S("cap", "X117.A")),
    }

    def series(keys, pairs, digits=2):
        return [{"label": lab, "values": [round(d[k], digits) if k in d else None for k in keys]} for lab, d in pairs]

    all_q = sorted(set().union(*[set(r) for r in rate.values()]))
    k12 = all_q[-12:]
    compare = {
        "id": "sector_compare", "label": "업권 비교", "type": "bars", "unit": "%", "dates": [_label(k) for k in k12],
        "series": series(k12, ([("은행", bank_delinq)] if bank_delinq else []) +
                         [("저축은행", rate["sb"]), ("카드사", rate["card"]), ("캐피탈", rate["cap"])]),
        "note_ko": "업권별 연체율(%, 분기말). 은행·저축은행은 1개월 이상 연체 대출 / 대출잔액, 카드사·캐피탈은 1개월 이상 연체 채권 / 관리자산 기준 총채권입니다. "
                   "정의가 조금씩 달라 수준보다 방향을 비교하는 용도입니다. 금융감독원 FISIS, 회사별 합산.",
    }

    def firm_panel(sec: str, lab: str) -> dict[str, Any]:
        firms = sorted(doc["firms"].get(sec) or [], key=lambda f: -(f["loans_tn"] or 0))[:20]
        asof = _label(doc["asof"][sec])

        def sub(f):
            s = f"{'대출' if sec == 'sb' else '채권'} {f['loans_tn']:,.1f}조"
            if f.get("npl") is not None:
                s += f" · 부실 {f['npl']:.1f}%"
            if f.get("bis") is not None:
                s += f" · BIS {f['bis']:.1f}%"
            return s
        return {"id": f"firms_{sec}", "label": lab, "type": "hbar", "unit": "%", "asof": asof,
                "rows": [{"label": f["name"], "value": f["delinq"], "sub": sub(f)}
                         for f in sorted(firms, key=lambda f: -(f["delinq"] or 0)) if f.get("delinq") is not None],
                "note_ko": f"{asof} 말, {'대출' if sec == 'sb' else '채권'} 규모 상위 20개사의 연체율(높은 순). 금융감독원 FISIS."}

    def aging(sec: str) -> dict[str, Any]:
        keys = [k for k in sorted(S(sec, "X117.A5"))][-12:]
        return {"id": f"aging_{sec}", "label": "연체 기간별", "type": "stack", "unit": "조원", "dates": [_label(k) for k in keys],
                "series": series(keys, [("1~3개월", tn(S(sec, "X117.A2"))), ("3~6개월", tn(S(sec, "X117.A3"))),
                                        ("6개월 이상", tn(S(sec, "X117.A4")))]),
                "line": series(keys, [("1개월 미만(예비 연체)", tn(S(sec, "X117.A1")))])[0],
                "note_ko": "1개월 이상 연체 채권을 연체 기간별로 쌓은 잔액(조원). 선은 1개월 미만 연체로, 다음 분기 연체율의 예고편입니다. "
                           "1~3개월 막대가 커지면 새 연체가 늘고 있고, 6개월 이상이 커지면 회수 못 한 채 쌓이고 있다는 뜻입니다. 금융감독원 FISIS."}

    def quality(sec: str) -> dict[str, Any]:
        keys = sorted(S(sec, "X008.A4"))[-12:]
        return {"id": f"npl_{sec}", "label": "부실 vs 충당금", "type": "bars", "unit": "조원", "dates": [_label(k) for k in keys],
                "series": series(keys, [("고정이하채권", tn(S(sec, "X008.A4"))), ("대손충당금", tn(S(sec, "X008.C")))]),
                "note_ko": "고정이하로 분류된 채권과 쌓아 둔 대손충당금(조원). 금융감독원 FISIS."}

    sb_keys = sorted(S("sb", "SE008.A3"))[-12:]
    sb_npl = ratio(S("sb", "SE008.A3"), S("sb", "SE008.A1"))
    sb_cov = ratio(S("sb", "SE008.A6"), S("sb", "SE008.A3"))
    out = {
        "sb_delinq": {
            "label": "저축은행 연체율", "unit": "%", "format": "pct2",
            "note_ko": "저축은행 연체금액 / 총여신(%, 분기말). 은행에서 밀려난 차주와 부동산PF 비중이 커서 은행보다 먼저, 크게 움직입니다. 눌러서 업권 비교·건전성 단계·저축은행별을 볼 수 있습니다. 금융감독원 FISIS, 저축은행별 합산.",
            "points": [(_q(k), v) for k, v in sorted(rate["sb"].items())],
            "panels": [
                compare,
                {"id": "sb_stages", "label": "건전성 단계", "type": "stack", "unit": "조원", "dates": [_label(k) for k in sb_keys],
                 "series": series(sb_keys, [("고정", tn(S("sb", "SE008.A21"))), ("회수의문", tn(S("sb", "SE008.A22"))),
                                            ("추정손실", tn(S("sb", "SE008.A23")))]),
                 "note_ko": "저축은행 고정이하여신을 단계별로 쌓은 잔액(조원). 추정손실은 사실상 못 받는 돈입니다. 금융감독원 FISIS SE008."},
                {"id": "sb_buffer", "label": "부실 vs 충당금", "type": "bars", "unit": "%", "dates": [_label(k) for k in sb_keys],
                 "series": series(sb_keys, [("고정이하여신비율", sb_npl), ("충당금/고정이하", sb_cov)], 1),
                 "note_ko": "고정이하여신비율과 대손충당금 적립률(충당금 / 고정이하여신, %). 적립률이 100% 아래면 부실이 손실로 확정될 때 추가 비용이 생깁니다. 금융감독원 FISIS SE008."},
                firm_panel("sb", "저축은행별"),
            ],
        },
        "card_delinq": {
            "label": "카드사 연체율", "unit": "%", "format": "pct2",
            "note_ko": "전업 카드사 8곳의 1개월 이상 연체채권 / 총채권(관리자산 기준, %, 분기말). 현금서비스·카드론을 쓰는 다중채무자의 상환 여력을 보여 줍니다. 대환대출은 빠진 기준이라, 대환대출을 넣은 금감원 보도자료 수치보다 0.3%p 안팎 낮습니다. 금융감독원 FISIS, 회사별 합산.",
            "points": [(_q(k), v) for k, v in sorted(rate["card"].items())],
            "panels": [compare, aging("card"), quality("card"), firm_panel("card", "카드사별")],
        },
        "capital_delinq": {
            "label": "캐피탈 연체율", "unit": "%", "format": "pct2",
            "note_ko": "리스·할부금융사(캐피탈)의 1개월 이상 연체채권 / 총채권(관리자산 기준, %, 분기말). 자동차 할부·기업 대출·부동산PF가 섞여 있습니다. 금융감독원 FISIS, 회사별 합산.",
            "points": [(_q(k), v) for k, v in sorted(rate["cap"].items())],
            "panels": [compare, aging("cap"), quality("cap"), firm_panel("cap", "캐피탈별")],
        },
    }
    for c in out.values():
        for p in c["panels"]:
            if p.get("line") is None:
                p.pop("line", None)
    return out
