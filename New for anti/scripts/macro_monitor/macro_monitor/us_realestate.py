"""US real estate tab: housing, commercial real estate, mortgage rates and credit risk, from series the Federal
Reserve publishes or watches in its Financial Stability Report. All FRED, keyless.

    rates        Freddie Mac 30-year mortgage rate, and its spread over the 10-year Treasury
    residential  Case-Shiller national price growth; price-to-rent (Case-Shiller / CPI rent of primary residence)
    commercial   commercial real estate loans at all commercial banks (Fed H.8, weekly)
    credit risk  Senior Loan Officer Survey: net share of banks tightening CRE standards, mortgage demand
                 (delinquency and charge-off rates by loan type live on one card, see credit_merge.py)
    industrial   one card for industrial real estate and capex: data centre, factory, power and office
                 construction (Census, monthly), core capital goods orders (monthly), information processing
                 equipment and structures investment (BEA, quarterly), drawn together as coloured lines
    growth tab   semiconductor production (Fed G.17) and manufacturing capacity utilisation

Not here because there is no free source: office vacancy (CoStar), CMBS delinquency and spreads (Trepp, ICE),
transaction-based CRE prices (Green Street, RCA).
"""

from __future__ import annotations

import io
import math
import re
import subprocess
from typing import Callable

from . import us_public_series as ups

CATEGORY = {"id": "realestate", "label_ko": "부동산", "label_en": "Real Estate", "order": 7,
            "description_ko": "모기지 금리 · 주택가격 · 가격/임대료 · 은행 CRE 대출 · 대출 기준(SLOOS) · 산업용 부동산·설비투자"}

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
    Spec("sloos_cre", "quarterly", "%", "net_pct1",
         "연준 고위대출담당자 설문(SLOOS): 비농업·비주거용 상업용 부동산(오피스·상가 등) 대출 기준을 강화한 은행 비율 − 완화한 은행 비율. "
         "양수면 조이는 중, 크게 오르면 CRE 자금줄이 마른다는 신호입니다.",
         "fred:SUBLPDRCSN", _u("SUBLPDRCSN"), "quarterly", label_ko="CRE 대출 기준 강화 (SLOOS)", chart_type="line"),
    Spec("sloos_mortgage_demand", "quarterly", "%", "net_pct1",
         "연준 고위대출담당자 설문(SLOOS): 적격(GSE) 주택담보대출 수요가 늘었다는 은행 비율 − 줄었다는 비율. 음수면 수요 위축입니다.",
         "fred:SUBLPDHMDENQ", _u("SUBLPDHMDENQ"), "quarterly", label_ko="주택담보대출 수요 (SLOOS)", chart_type="line"),
    Spec("industrial_capex", "monthly", "bn_usd", "bn1usd",
         "숫자와 기본 차트는 데이터센터 건설 지출(민간, 계절조정 연율, 십억 달러)입니다. 카드를 열면 산업용 부동산·설비투자 7개를 색을 달리한 "
         "선으로 함께 봅니다: 데이터센터·제조업 공장·전력·오피스(데이터센터 제외) 건설 지출(센서스, 월), 핵심 자본재 주문(항공기·국방 제외, 월), "
         "정보처리 장비 투자·구조물 투자(BEA, 분기 — 분기 가운데 달에 점). 점 하나가 발표 하나입니다.",
         "census:C30,fred:NEWORDER,Y034RC1Q027SBEA,B009RC1Q027SBEA",
         ("https://www.census.gov/construction/c30/data/index.html", *_u("NEWORDER", "Y034RC1Q027SBEA", "B009RC1Q027SBEA")),
         "monthly", label_ko="산업용 부동산·설비투자", chart_type="line"),
    Spec("ip_semis", "monthly", "index", "idx1",
         "연준 산업생산(G.17): 반도체·기타 전자부품 생산지수(2017=100, 계절조정). AI·데이터센터 수요가 국내 생산으로 이어지는지 봅니다.",
         "fred:IPG3344S", _u("IPG3344S"), "monthly", label_ko="반도체·전자부품 생산", chart_type="line"),
    Spec("cu_manufacturing", "monthly", "%", "pct1",
         "연준 산업생산(G.17): 제조업 가동률(계절조정, %). 높을수록 설비가 빠듯해 증설 투자가 필요해집니다.",
         "fred:MCUMFN", _u("MCUMFN"), "monthly", label_ko="제조업 가동률", chart_type="line"),
]}

YOY_LINE_IDS = frozenset({"bank_cre_loans"})
# Cards that belong to another tab; everything else goes to the real estate tab.
CATEGORY_OF = {"ip_semis": "growth", "cu_manufacturing": "growth"}
# Cards this module made earlier and no longer makes (merged into credit_merge's delinquency card).
RETIRED = ("delinq_residential", "delinq_cre")

CENSUS_PRIVATE_SA = "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
# (label, source, column or FRED id, cadence, scale to $ billion)
CAPEX = [
    ("데이터센터 건설", "census", "Data center", "monthly", 1e-3),
    ("제조업 공장 건설", "census", "Manufacturing", "monthly", 1e-3),
    ("전력 시설 건설", "census", "Power (inc. Gas and Oil)", "monthly", 1e-3),
    ("오피스 건설(데이터센터 제외)", "census", "General", "monthly", 1e-3),
    ("핵심 자본재 주문", "fred", "NEWORDER", "monthly", 1e-3),
    ("정보처리 장비 투자(분기)", "fred", "Y034RC1Q027SBEA", "quarterly", 1.0),
    ("구조물 투자(분기)", "fred", "B009RC1Q027SBEA", "quarterly", 1.0),
]


def fetch_census_private() -> dict[str, ups.Points]:
    """Census 'Value of Private Construction Put in Place', seasonally adjusted annual rate ($ million), every
    column of the time-series workbook by its header. Keyless; curl (the site refuses Python's default client)."""
    proc = subprocess.run(["curl", "-sS", "-L", "-m", "90", "-A", "Mozilla/5.0", CENSUS_PRIVATE_SA], capture_output=True, check=False)
    if proc.returncode != 0 or len(proc.stdout) < 10000:
        raise RuntimeError(f"census privsatime: curl rc={proc.returncode}, {len(proc.stdout)} bytes")
    return parse_census_private(proc.stdout)


def parse_census_private(data: bytes) -> dict[str, ups.Points]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rows[:15]) if r and str(r[0] or "").strip() == "Date")
    head = [re.sub(r"\s+", " ", str(c or "")).strip() for c in rows[hi]]
    out: dict[str, list] = {}
    for r in rows[hi + 1:]:
        m = re.match(r"([A-Za-z]{3})-(\d{2})", str((r or [None])[0] or "").strip())
        if not m:
            continue
        yy = int(m.group(2))
        d = f"{1900 + yy if yy >= 50 else 2000 + yy}-{MON[m.group(1).lower()]:02d}-01"     # the file starts in 1993
        for j, h in enumerate(head[1:], 1):
            v = r[j] if j < len(r) else None
            if h and isinstance(v, (int, float)):
                out.setdefault(h, []).append((d, float(v)))
    return {k: sorted(v) for k, v in out.items()}


def _ym(d: str) -> str:
    return f"{d[2:4]}.{int(d[5:7])}"


def _mid_quarter(d: str) -> str:
    """BEA stamps a quarter with its first month; its point goes in the middle month."""
    return f"{d[:5]}{int(d[5:7]) + 1:02d}-01"


def capex_panels(raw: dict[str, ups.Points], months: int = 60) -> list[dict]:
    """Three panels over the same monthly axis (the last `months` months): an index of every series (first
    point in the window = 100) so seven different-sized lines share one chart, the dollar amounts of the four
    construction lines (same unit: annual rate), and the year-on-year growth of all seven."""
    prepared = []
    for label, _, _, cadence, k in CAPEX:
        pts = [(d, v * k) for d, v in raw.get(label, [])]
        yoy = ups.pct_change(pts, 12 if cadence == "monthly" else 4)
        if cadence == "quarterly":
            pts = [(_mid_quarter(d), v) for d, v in pts]
            yoy = [(_mid_quarter(d), v) for d, v in yoy]
        prepared.append((label, cadence, dict(pts), dict(yoy)))
    last = max(max(p[2]) for p in prepared if p[2] and p[1] == "monthly")
    axis = []
    y, m = int(last[:4]), int(last[5:7])
    for _ in range(months):
        axis.append(f"{y}-{m:02d}-01")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    axis.reverse()
    dates = [_ym(d) for d in axis]

    def col(d: dict) -> list:
        return [round(d[a], 3) if a in d and math.isfinite(d[a]) else None for a in axis]

    idx_series, amt_series, yoy_series = [], [], []
    for label, cadence, lv, yy in prepared:
        vals = col(lv)
        base = next((v for v in vals if v), None)
        idx_series.append({"label": label, "values": [round(v / base * 100, 2) if v is not None and base else None for v in vals]})
        if label.endswith("건설") or label.startswith("오피스"):
            amt_series.append({"label": label, "values": vals})
        yoy_series.append({"label": label, "values": [round(v, 2) if v is not None else None for v in col(yy)]})
    common = {"type": "lines", "markers": True, "dates": dates, "compare_ko": "직전 발표"}
    return [
        {**common, "id": "capex_index", "series": idx_series, "label": "7개 지수 비교", "unit": "", "log": True,
         "note_ko": f"각 선의 {dates[0]} 값을 100으로 놓은 지수, 세로축은 로그(같은 배율이면 같은 높이)입니다. 크기가 다른 7개를 한 차트에서 비교하려는 것으로, 금액은 '건설 지출' 탭과 카드 설명을 보세요. "
                    "분기 자료(정보처리 장비·구조물)는 분기 가운데 달에 점을 찍었습니다."},
        {**common, "id": "capex_construction", "series": amt_series, "label": "건설 지출 (금액)", "unit": "십억달러",
         "note_ko": "민간 건설 지출, 계절조정 연율(십억 달러). 센서스 'Value of Construction Put in Place'."},
        {**common, "id": "capex_yoy", "series": yoy_series, "label": "전년비", "unit": "%",
         "note_ko": "월 자료는 12개월 전, 분기 자료는 4분기 전 대비 증가율(%)."},
    ]


def capex_raw(fred: Callable[[str], ups.Points], census: Callable[[], dict[str, ups.Points]]) -> dict[str, ups.Points]:
    out = {}
    for label, src, key, _, _ in CAPEX:
        out[label] = census()[key] if src == "census" else fred(key)
    return out


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


def series_for(spec_id: str, fred: Callable[[str], ups.Points],
               census: Callable[[], dict[str, ups.Points]] | None = None) -> ups.Points:
    if spec_id == "industrial_capex":
        if census is None:
            raise ValueError("industrial_capex needs the Census reader")
        return ups.scale(census()["Data center"], 1e-3)       # $ million -> $ billion
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
    if spec_id == "ip_semis":
        return fred("IPG3344S")
    if spec_id == "cu_manufacturing":
        return fred("MCUMFN")
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
    for old in RETIRED:
        if ups.remove_indicator(usa, old):
            changed.append(f"-{old}")
    for sid in SPECS:
        if sid in patches:
            if ups.ensure_card(usa, sid, CATEGORY_OF.get(sid, CATEGORY["id"]), SPECS[sid]):
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
