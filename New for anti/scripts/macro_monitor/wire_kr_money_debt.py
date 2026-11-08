#!/usr/bin/env python3
"""Korea: money supply as a whole (M1 -> M2 -> Lf -> L) against US M2, and the government's debt next
to the public institutions' debt.

    python3 wire_kr_money_debt.py

1. 통화량 구성 (on KOR m2_yoy): ECOS month-end, seasonally adjusted -- M1 161Y003, M2 161Y007,
   Lf 171Y001, L 172Y001 -- stacked as M1 | M2-M1 | Lf-M2 | L-Lf, so each band is what the next wider
   aggregate adds and the top is L. 미국 대비: Korean M2 (161Y005, monthly average, SA) against US M2
   (FRED M2SL, monthly average, SA) -- the same definition window on both sides -- as YoY and as
   cumulative growth since 2019-12. Growth rates, not levels: won and dollars do not share a scale.

2. 국가부채 (KOR sovereign_debt): 국가채무 D1 (central + local government, 조원) and D1/GDP from
   e-나라지표 1106, annual since 1997, replacing the IMF series (in US dollars) as the headline; the IMF
   general-government figure stays in the card's 원자료 tab. Beside it, 공공기관 부채 (e-나라지표 1100,
   ALIO: 공기업·준정부기관·기타공공기관 합계). The two are shown side by side, not stacked: public
   institutions lend to and borrow from the government, so their sum would double-count. The official
   consolidated totals (D2 general government, D3 public sector) are published once a year by the
   finance ministry without a machine-readable series; the card says so instead of inventing one.

ECOS needs ECOS_API_KEY (already used by the Korea pipeline); the rest is keyless.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ecos  # noqa: E402
from macro_monitor import jp_public_series as jps  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
Points = list[tuple[str, float]]

ENARA = "https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?stts_cd={stts}&idx_cd={idx}&freq=Y&period={a}:{b}"
ENARA_PAGE = "https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd={idx}"


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------

def ecos_tn(stat: str, item: str) -> Points:
    pts, _ = ecos.series(stat, "M", (item,))
    return [(ups.month_end(d), v * 1e-3) for d, v in pts]                    # 십억원 -> 조원


def money_stack(m1: Points, m2: Points, lf: Points, l_: Points, since: str = "2015-01-01") -> dict:
    a, b, c, d = (dict(x) for x in (m1, m2, lf, l_))
    dates = sorted(k for k in a if k >= since and k in b and k in c and k in d)
    if not dates:
        raise ValueError("no month with all four aggregates")
    r = lambda v: round(v, 2)  # noqa: E731
    layers = [
        {"id": "m1", "label_ko": "M1 (협의통화)", "color": "#38bdf8",
         "note_ko": "현금통화 + 요구불예금 + 수시입출식 저축성예금. 바로 쓸 수 있는 돈.", "values": [r(a[k]) for k in dates]},
        {"id": "m2_add", "label_ko": "M2 − M1", "color": "#a78bfa",
         "note_ko": "만기 2년 미만 정기예적금·시장형상품·MMF 등 M2가 M1에 더하는 부분.", "values": [r(b[k] - a[k]) for k in dates]},
        {"id": "lf_add", "label_ko": "Lf − M2", "color": "#f59e0b",
         "note_ko": "만기 2년 이상 예금·보험계약준비금 등 금융기관 유동성(Lf)이 M2에 더하는 부분.", "values": [r(c[k] - b[k]) for k in dates]},
        {"id": "l_add", "label_ko": "L − Lf", "color": "#f472b6",
         "note_ko": "국채·지방채·회사채·기업어음 등 광의유동성(L)이 Lf에 더하는 부분.", "values": [r(d[k] - c[k]) for k in dates]},
    ]
    return {
        "asof": dates[-1], "dates": dates, "unit": "tn_krw", "unit_suffix": "조원", "frequency": "monthly",
        "data_status": "live",
        "source": "한국은행 ECOS 161Y003(M1)·161Y007(M2)·171Y001(Lf)·172Y001(L), 말잔·계절조정",
        "total": {"label_ko": "L (광의유동성)", "values": [r(d[k]) for k in dates]},
        "sides": [{"id": "aggregates", "label_ko": "통화량 구성", "tab_ko": "통화량 구성",
                   "note_ko": "아래부터 M1, M2, Lf, L이 차례로 더하는 부분. 맨 위가 L.", "layers": layers}],
        "stack_note_ko": ("각 밴드는 한 단계 넓은 통화지표가 그 아래 지표에 더하는 몫이라, 밴드를 아래부터 쌓은 높이가 "
                          "차례로 M1·M2·Lf·L입니다. 말잔·계절조정 계열."),
    }


def yoy(points: Points) -> Points:
    return [(d, round(v, 2)) for d, v in ups.pct_change(points, 12)]


def cumulative(points: Points, base: str) -> Points:
    return [(d, round(v, 2)) for d, v in ups.vs_base(points, base)]


def benchmark(kr_m2: Points, us_m2: Points, base: str = "2019-12-01", since: str = "2015-01-01") -> dict:
    """KR vs US M2 growth, aligned by month."""
    kr = {d[:7]: v for d, v in kr_m2}
    us = {d[:7]: v for d, v in us_m2}
    months = sorted(set(kr) & set(us))
    kr_pts = [(m + "-01", kr[m]) for m in months]
    us_pts = [(m + "-01", us[m]) for m in months]
    out = {}
    for mode, fn, label in (("yoy", yoy, "전년비 증가율"), ("cum", lambda p: cumulative(p, base), f"{base[:7]} 이후 누적 증가율")):
        k, u = dict(fn(kr_pts)), dict(fn(us_pts))
        ms = [d for d in sorted(k) if d in u and d >= since]
        out[mode] = {"label_ko": label, "dates": [ups.month_end(d) for d in ms],
                     "kr": [k[d] for d in ms], "us": [u[d] for d in ms],
                     "gap": [round(k[d] - u[d], 2) for d in ms]}
    last = out["cum"]
    return {
        "label_ko": "한국 M2 vs 미국 M2", "unit": "%", "base": base[:7], "modes": out,
        "series_ko": {"kr": "한국 M2", "us": "미국 M2 (벤치마크)"},
        "source": "한국은행 ECOS 161Y005(M2 평잔·계절조정), FRED M2SL(미국 M2, 월평균·계절조정)",
        "note_ko": (f"두 나라 M2를 각자 통화로 잰 증가율로 비교합니다(원과 달러는 같은 축에 놓을 수 없어 수준이 아닌 "
                    f"증가율). {last['dates'][-1][:7]} 기준 {base[:7]} 이후 누적: 한국 {last['kr'][-1]:+.1f}%, 미국 "
                    f"{last['us'][-1]:+.1f}% -- 차이 {last['gap'][-1]:+.1f}%p. 같은 기간 원화 M2가 달러 M2보다 이만큼 더 "
                    "(음수면 덜) 늘었다는 뜻입니다. 양국 모두 월평균·계절조정 계열."),
    }


# --------------------------------------------------------------------------
# Debt
# --------------------------------------------------------------------------

def parse_enara(text: str) -> tuple[list[int], list[tuple[list[str], list[float | None]]]]:
    """e-나라지표 table iframe: (years, [(row labels, values)])."""
    rows = []
    for row in re.findall(r"<tr.*?</tr>", text, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<t[hd][^>]*>.*?</t[hd]>", row, re.S)]
        cells = [c for c in cells if c != ""]
        if cells:
            rows.append(cells)
    head = next((r for r in rows if len(r) >= 3 and all(re.fullmatch(r"\d{4}", c) for c in r)), None)
    if not head:
        raise ValueError("e-나라지표: no year header")
    years = [int(c) for c in head]
    out = []
    for r in rows:
        if r is head:
            continue
        vals = r[-len(years):]
        labels = r[:-len(years)]
        try:
            nums = [None if v in ("-", "") else float(v.replace(",", "")) for v in vals]
        except ValueError:
            continue
        if labels:
            out.append((labels, nums))
    return years, out


def enara(stts: str, idx: str, first: int, last: int) -> tuple[list[int], list[tuple[list[str], list[float | None]]]]:
    return parse_enara(jps._get(ENARA.format(stts=stts, idx=idx, a=first, b=last), timeout=60).decode("utf-8", errors="replace"))


def pick(rows, *want: str) -> list[float | None]:
    for labels, vals in rows:
        if list(labels[:len(want)]) == list(want):
            return vals
    raise ValueError(f"e-나라지표: no row {want}")


def debt_breakdown(rows, col: int) -> list[dict]:
    """The three rows right after '부채 | 합계' (the same labels also appear under 자산 and 부채비율)."""
    i = next(k for k, (labels, _) in enumerate(rows) if labels[:2] == ["부채", "합계"])
    out = []
    for labels, vals in rows[i + 1:i + 4]:
        out.append({"label_ko": labels[-1], "value": vals[col]})
    if [r["label_ko"] for r in out] != ["공기업", "준정부기관", "기타공공기관"]:
        raise ValueError(f"e-나라지표 1100: unexpected rows under 부채 {[r['label_ko'] for r in out]}")
    return out


def debt_card(old: dict, now: str, last_year: int) -> dict:
    years, rows = enara("110601", "1106", 1997, last_year)
    d1, ratio = pick(rows, "국가채무(1+2)"), pick(rows, "(GDP대비, %)")
    pyears, prows = enara("110002", "1100", 2010, last_year)
    pub = pick(prows, "부채", "합계")
    d1_pts = [(f"{y}-12-31", v) for y, v in zip(years, d1) if v is not None]
    ratio_pts = [(f"{y}-12-31", v) for y, v in zip(years, ratio) if v is not None]
    y, v = d1_pts[-1]
    prev = d1_pts[-2][1] if len(d1_pts) > 1 else None
    pub_by = {yy: vv for yy, vv in zip(pyears, pub) if vv is not None}
    both = [yy for yy in years if yy in pub_by and dict(zip(years, d1)).get(yy) is not None]
    card = dict(old)
    card.update({
        "label_ko": "국가부채", "unit": "tn_krw", "format": "tn1",
        "value": v, "display": f"{v:,.1f}조", "display_chip": f"{v:,.1f}조",
        "change_1y_pct": round((v / prev - 1) * 100, 2) if prev else None, "change_1m_pct": None,
        "asof": y, "observed_at": y, "reference_period": y[:4],
        "history": ups.history_block(d1_pts, "annual"),
        "source": "e-나라지표 1106(국가채무, 기획예산처)", "source_urls": [ENARA_PAGE.format(idx="1106"), ENARA_PAGE.format(idx="1100")],
        "quality": "live", "data_status": "live", "refresh_tier": "annual", "series_frequency": "annual",
        "chart_type": "fiscal_dual_line", "retrieved_at": now,
        "note_ko": (f"국가채무(D1: 중앙정부 + 지방정부 순채무, 결산 기준)입니다. {y[:4]}년 {v:,.1f}조원, GDP 대비 "
                    f"{ratio_pts[-1][1]:.1f}%. 카드를 열면 공공기관 부채(공기업·준정부기관·기타공공기관)를 나란히 볼 수 있습니다. "
                    "다른 나라와 비교하는 IMF 일반정부 부채(달러)는 '원자료·산식' 탭에 그대로 있습니다."),
    })
    card.pop("snapshot_asof", None)
    fc = dict(card.get("fiscal_compare") or {})
    fc.update({"primary_label_ko": "국가채무(D1)", "primary_unit": "조원", "secondary_label_ko": "국가채무/GDP",
               "secondary_unit": "%", "secondary_history": ups.history_block(ratio_pts, "annual")})
    fc.pop("actuals_only", None)
    card["fiscal_compare"] = fc
    card["debt_groups"] = {
        "label_ko": "정부 vs 공공기관 부채", "unit_suffix": "조원",
        "years": [str(yy) for yy in both],
        "series": [
            {"id": "d1", "label_ko": "국가채무(D1, 중앙+지방정부)", "color": "#38bdf8",
             "values": [dict(zip(years, d1))[yy] for yy in both]},
            {"id": "public_inst", "label_ko": "공공기관 부채(공기업·준정부·기타)", "color": "#f59e0b",
             "values": [pub_by[yy] for yy in both]},
        ],
        "breakdown": {"label_ko": f"{both[-1]}년 공공기관 부채 구성",
                      "rows": debt_breakdown(prows, pyears.index(both[-1]))} if both else None,
        "note_ko": ("두 부채는 나란히 비교할 뿐 더하지 않습니다. 공공기관이 정부에 빌려주거나 정부 채권을 들고 있는 몫이 "
                    "겹쳐 단순 합계는 이중 계산이 됩니다. 이를 걸러 낸 공식 합계는 기획재정부가 매년 12월 한 번 발표하는 "
                    "일반정부 부채(D2: D1 + 비영리 공공기관)와 공공부문 부채(D3: D2 + 비금융 공기업)인데, 기계로 읽을 수 있는 "
                    "시계열로는 공개되지 않아 여기 싣지 않았습니다."),
        "source": "e-나라지표 1106(국가채무), 1100(공공기관 재무정보, ALIO)",
    }
    return card


# --------------------------------------------------------------------------

def main() -> int:
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    kor = next(c for c in pack["countries"] if c["iso3"] == "KOR")
    by_id = {i["id"]: i for i in kor["indicators"]}
    now, failures = ups.now_iso(), []

    try:
        stack = money_stack(ecos_tn("161Y003", "BBKS00"), ecos_tn("161Y007", "BBGS00"),
                            ecos_tn("171Y001", "LES0000"), ecos_tn("172Y001", "XS00000"))
        kr_m2 = ecos.series("161Y005", "M", ("BBHS00",))[0]
        bench = benchmark(kr_m2, ups.fetch_fred("M2SL"))
        card = by_id["m2_yoy"]
        card["balance_sheet"] = stack
        card["benchmark"] = bench
        lay = stack["sides"][0]["layers"]
        print(f"KOR money {stack['asof']}: " + ", ".join(f"{l['label_ko']} {l['values'][-1]}" for l in lay)
              + f" | L {stack['total']['values'][-1]}조")
        print("  " + bench["note_ko"])
    except Exception as exc:  # noqa: BLE001
        failures.append(f"money: {str(exc)[:200]}")

    try:
        # The current year's column is the budget (예산), not an outturn: settled accounts (결산) for a year
        # come out the following April, so the last settled year is last year from May, else the year before.
        year = int(now[:4]) - (1 if int(now[5:7]) >= 5 else 2)
        card = debt_card(by_id["sovereign_debt"], now, year)
        kor["indicators"] = [card if i["id"] == "sovereign_debt" else i for i in kor["indicators"]]
        ups.sync_chips(kor, {"sovereign_debt": card}, {"sovereign_debt"})
        g = card["debt_groups"]
        print(f"KOR debt {card['asof']}: {card['display']} | " + "; ".join(
            f"{s['label_ko']} {s['values'][-1]}" for s in g["series"]))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"debt: {str(exc)[:200]}")

    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
