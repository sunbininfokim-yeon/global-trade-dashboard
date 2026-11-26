"""US real estate tab: housing, commercial real estate, mortgage rates and credit risk, from series the Federal
Reserve publishes or watches in its Financial Stability Report. All FRED, keyless.

    rates        Freddie Mac 30-year mortgage rate, and its spread over the 10-year Treasury
    residential  Case-Shiller national price growth; price-to-rent (Case-Shiller / CPI rent of primary residence)
    commercial   commercial real estate loans at all commercial banks (Fed H.8, weekly)
    credit risk  delinquency rates on residential and commercial real estate loans (Fed Board, all banks);
                 Senior Loan Officer Survey: net share of banks tightening CRE standards, mortgage demand

Not here because there is no free source: office vacancy (CoStar), CMBS delinquency and spreads (Trepp, ICE),
transaction-based CRE prices (Green Street, RCA).
"""

from __future__ import annotations

from typing import Callable

from . import us_public_series as ups

CATEGORY = {"id": "realestate", "label_ko": "부동산", "label_en": "Real Estate", "order": 7,
            "description_ko": "모기지 금리 · 주택가격 · 가격/임대료 · 은행 CRE 대출 · 연체율 · 대출 기준(SLOOS)"}

ups._FORMATS.setdefault("pct2", lambda v: f"{v:.2f}%")
ups._FORMATS.setdefault("bp0", lambda v: f"{v:,.0f}bp")
ups._FORMATS.setdefault("idx1", lambda v: f"{v:,.1f}")
ups._FORMATS.setdefault("net_pct1", lambda v: f"{v:+.1f}%p")

_u = ups._fred_urls
Spec = ups.Spec

SPECS: dict[str, ups.Spec] = {s.id: s for s in [
    Spec("mortgage_30y", "weekly", "%", "pct2",
         "프레디맥 주간 설문(PMMS) 30년 고정 모기지 평균 금리입니다. 미국 주택 구입 비용을 가장 직접 보여 줍니다.",
         "fred:MORTGAGE30US", _u("MORTGAGE30US"), "weekly", label_ko="30년 모기지 금리", chart_type="line"),
    Spec("mortgage_spread", "weekly", "bp", "bp0",
         "30년 모기지 금리 − 같은 날(없으면 직전 영업일) 국채 10년물 금리. 벌어지면 금리 변동성·MBS 수요 부족으로 "
         "주택 금융이 국채보다 더 조여졌다는 뜻입니다.",
         "fred:MORTGAGE30US,DGS10", _u("MORTGAGE30US", "DGS10"), "weekly", label_ko="모기지 − 10년물 스프레드", chart_type="line"),
    Spec("home_price_yoy", "monthly", "%", "pct1",
         "S&P 코탈리티 케이스-실러 전국 주택가격지수(계절조정 안 됨)의 전년 같은 달 대비 상승률입니다. 발표는 두 달 늦습니다.",
         "fred:CSUSHPINSA", _u("CSUSHPINSA"), "monthly", label_ko="주택가격 (케이스-실러, 전년비)", chart_type="line"),
    Spec("price_to_rent", "monthly", "index", "idx1",
         "케이스-실러 전국 주택가격 ÷ CPI 주거 임대료, 1987년 이후 평균 = 100. 연준 금융안정보고서가 주택 고평가를 보는 방식입니다. "
         "100보다 높을수록 임대료에 비해 집값이 비쌉니다.",
         "fred:CSUSHPINSA,CUSR0000SEHA", _u("CSUSHPINSA", "CUSR0000SEHA"), "monthly", label_ko="주택가격/임대료", chart_type="line"),
    Spec("bank_cre_loans", "weekly", "tn_usd", "tn2usd",
         "연준 H.8: 미국 상업은행 전체의 상업용 부동산 대출 잔액(계절조정, 조 달러, 수요일). 카드를 열면 전년비 증가율 선이 함께 나옵니다. "
         "중소형 은행이 이 대출의 큰 몫을 들고 있어 CRE 가격 하락이 은행 위험으로 번지는 통로입니다.",
         "fred:CREACBW027SBOG", _u("CREACBW027SBOG"), "weekly", label_ko="은행 상업용 부동산 대출", chart_type="line"),
    Spec("delinq_residential", "quarterly", "%", "pct2",
         "연준 이사회: 상업은행 전체의 1~4인 가구 주택담보대출 연체율(30일 이상, 계절조정). 분기 자료로 약 두 달 늦습니다.",
         "fred:DRSFRMACBS", _u("DRSFRMACBS"), "quarterly", label_ko="주택담보대출 연체율", chart_type="line"),
    Spec("delinq_cre", "quarterly", "%", "pct2",
         "연준 이사회: 상업은행 전체의 상업용 부동산 대출(농지 제외) 연체율(30일 이상, 계절조정).",
         "fred:DRCRELEXFACBS", _u("DRCRELEXFACBS"), "quarterly", label_ko="상업용 부동산 대출 연체율", chart_type="line"),
    Spec("sloos_cre", "quarterly", "%", "net_pct1",
         "연준 고위대출담당자 설문(SLOOS): 비농업·비주거용 상업용 부동산(오피스·상가 등) 대출 기준을 강화한 은행 비율 − 완화한 은행 비율. "
         "양수면 조이는 중, 크게 오르면 CRE 자금줄이 마른다는 신호입니다.",
         "fred:SUBLPDRCSN", _u("SUBLPDRCSN"), "quarterly", label_ko="CRE 대출 기준 강화 (SLOOS)", chart_type="line"),
    Spec("sloos_mortgage_demand", "quarterly", "%", "net_pct1",
         "연준 고위대출담당자 설문(SLOOS): 적격(GSE) 주택담보대출 수요가 늘었다는 은행 비율 − 줄었다는 비율. 음수면 수요 위축입니다.",
         "fred:SUBLPDHMDENQ", _u("SUBLPDHMDENQ"), "quarterly", label_ko="주택담보대출 수요 (SLOOS)", chart_type="line"),
]}

YOY_LINE_IDS = frozenset({"bank_cre_loans"})


def spread_on_dates(a: ups.Points, b: ups.Points, scale_by: float = 100.0) -> ups.Points:
    """a - b on a's dates, b taken on the same day or the latest day before it (weekly vs daily series)."""
    out, j = [], 0
    bs = sorted(b)
    for d, v in sorted(a):
        while j + 1 < len(bs) and bs[j + 1][0] <= d:
            j += 1
        if bs and bs[j][0] <= d:
            out.append((d, (v - bs[j][1]) * scale_by))
    return out


def ratio_index(a: ups.Points, b: ups.Points, base_from: str = "1987-01-01") -> ups.Points:
    """a / b on common dates, rescaled so the average since base_from is 100."""
    bd = dict(b)
    r = [(d, v / bd[d]) for d, v in a if d in bd and bd[d] and d >= base_from]
    if not r:
        return []
    avg = sum(v for _, v in r) / len(r)
    return [(d, v / avg * 100) for d, v in r]


def series_for(spec_id: str, fred: Callable[[str], ups.Points]) -> ups.Points:
    if spec_id == "mortgage_30y":
        return fred("MORTGAGE30US")
    if spec_id == "mortgage_spread":
        return spread_on_dates(fred("MORTGAGE30US"), fred("DGS10"))
    if spec_id == "home_price_yoy":
        return ups.pct_change(fred("CSUSHPINSA"), 12)
    if spec_id == "price_to_rent":
        return ratio_index(fred("CSUSHPINSA"), fred("CUSR0000SEHA"))
    if spec_id == "bank_cre_loans":
        return ups.scale(fred("CREACBW027SBOG"), 1e-3)          # $ billion -> $ trillion
    if spec_id == "delinq_residential":
        return fred("DRSFRMACBS")
    if spec_id == "delinq_cre":
        return fred("DRCRELEXFACBS")
    if spec_id == "sloos_cre":
        return fred("SUBLPDRCSN")
    if spec_id == "sloos_mortgage_demand":
        return fred("SUBLPDHMDENQ")
    raise KeyError(spec_id)


def _q(d: str) -> str:
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def extra_note(spec_id: str, points: ups.Points) -> str:
    """Reference levels computed from the full history (the card's chart shows ten years at most), so no
    note carries a remembered number."""
    if not points:
        return ""
    last = points[-1][1]
    if spec_id == "price_to_rent":
        top = max(points, key=lambda x: x[1])
        pre = [x for x in points if x[0] < "2010-01-01"]
        pk = max(pre, key=lambda x: x[1]) if pre else None
        out = f" 1987년 이후 최고 {top[1]:.1f}({top[0][:7]})"
        if pk and pk[0] != top[0]:
            out += f", 주택 거품 고점 {pk[1]:.1f}({pk[0][:7]})"
        return out + f", 지금 {last:.1f}."
    if spec_id == "mortgage_spread":
        v = sorted(x[1] for x in points)
        return (f" {points[0][0][:4]}년 이후 중앙값 {v[len(v) // 2]:.0f}bp, 10~90% 범위 {v[len(v) // 10]:.0f}~{v[len(v) * 9 // 10]:.0f}bp"
                f" — 지금 {last:.0f}bp.")
    if spec_id in ("delinq_cre", "delinq_residential"):
        top = max(points, key=lambda x: x[1])
        since = [x for x in points if x[0] >= "2008-01-01"]
        out = f" {points[0][0][:4]}년 이후 최고 {top[1]:.2f}%({_q(top[0])})"
        if since and max(since, key=lambda x: x[1])[0] != top[0]:
            t2 = max(since, key=lambda x: x[1])
            out += f", 금융위기 이후 최고 {t2[1]:.2f}%({_q(t2[0])})"
        return out + f", 지금 {last:.2f}%."
    if spec_id == "sloos_cre":
        top = max(points, key=lambda x: x[1])
        return f" {points[0][0][:4]}년 이후 최고 {top[1]:+.1f}({_q(top[0])}), 지금 {last:+.1f}."
    return ""


def ensure_tab(pack: dict, usa: dict) -> bool:
    """The tab exists in the pack's tab list and in the US country's categories, in that order."""
    changed = False
    tabs = pack.setdefault("ui", {}).setdefault("category_tabs", [])
    if not any(t.get("id") == CATEGORY["id"] for t in tabs):
        tabs.append(dict(CATEGORY))
        tabs.sort(key=lambda t: t.get("order", 99))
        changed = True
    act = usa.setdefault("active_categories", [])
    if CATEGORY["id"] not in act:
        act.append(CATEGORY["id"])
        changed = True
    return changed


def apply(pack: dict, patches: dict[str, dict]) -> list[str]:
    """Create missing cards (in SPECS order), write the patches, resync chips. Returns changed ids."""
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    changed = ["(tab)"] if ensure_tab(pack, usa) else []
    for sid in SPECS:
        if sid in patches:
            if ups.ensure_card(usa, sid, CATEGORY["id"], SPECS[sid]):
                changed.append(f"+{sid}")
    by_id = {i["id"]: i for i in usa["indicators"]}
    for sid, p in patches.items():
        if sid in YOY_LINE_IDS:
            p["yoy_line"] = True
        if ups.apply_patch(by_id[sid], p):
            changed.append(sid)
    ups.sync_chips(usa, by_id, set(patches))
    ups.refresh_status_summary(usa)
    return changed
