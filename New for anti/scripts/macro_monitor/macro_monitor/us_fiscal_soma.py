"""Two US cards get more to show, from data the pack and free sources already have.

SOMA (`fed_ust_holdings`)
  * 'SOMA + TGA' tab: the Fed's Treasury holdings (H.4.1 TREAST) with the Treasury General Account drawn
    underneath on the same weekly axis (both from public/data/fed_balance_sheet_v1.json, WTREGEN) -- QT drains
    reserves, a TGA rebuild drains them too; seen together they explain the reserve path.
  * right rail 'duration': what the Fed's holdings mean for interest-rate risk in private hands, read off the
    Treasury duration panels wire_ust_maturity.py builds on `ust_debt_wam` (10-year equivalents, monthly):
    total, Fed share, private, and the Fed's monthly contribution to private duration (QT runoff adds to it).

Government interest (`sovereign_interest`)
  * 'GDP 대비' tab: Monthly Treasury Statement interest on the public debt (gross, completed fiscal years) over
    the fiscal year's nominal GDP (BEA via FRED GDP, the four quarters October-September), next to OMB's federal
    interest outlays as % of GDP (FRED FYOIGDA188S) as a cross-check from a second official source.
  * '평균 금리' tab: Treasury's average interest rate on outstanding debt (Fiscal Data avg_interest_rates,
    monthly): all interest-bearing debt, bills, notes, bonds. This is the rate the stock of debt carries now --
    the '원자료·산식' tab of the card is annual interest dollars, not a rate.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

AVG_RATES = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
             "?sort=-record_date&page[size]=10000&fields=record_date,security_desc,avg_interest_rate_amt"
             "&filter=record_date:gte:{since}")
RATE_LINES = [("Total Interest-bearing Debt", "이자부 부채 전체"), ("Treasury Bills", "단기채(Bills)"),
              ("Treasury Notes", "중기채(Notes)"), ("Treasury Bonds", "장기채(Bonds)")]


def _wk(d: str) -> str:
    return f"{d[2:4]}.{int(d[5:7])}.{int(d[8:10])}"


def soma_tga_panel(bs: dict[str, Any], weeks: int = 260) -> dict[str, Any] | None:
    layers = {l["id"]: l for s in bs.get("sides", []) for l in s.get("layers", [])}
    if "treasuries" not in layers or "tga" not in layers:
        return None
    dates = bs["dates"][-weeks:]
    lab = [_wk(d) for d in dates]
    soma = layers["treasuries"]["values"][-weeks:]
    tga = layers["tga"]["values"][-weeks:]
    def chart(pid: str, label: str, vals: list, note: str) -> dict:
        return {"id": pid, "type": "lines", "unit": "십억달러", "dates": lab, "compare_ko": "직전 주",
                "series": [{"label": label, "values": [round(v * 1000, 1) if v is not None else None for v in vals]}], "note_ko": note}
    return {"id": "soma_tga", "label": "SOMA + TGA", "type": "charts", "charts": [
        chart("soma_w", "연준 보유 국채(SOMA)", soma, "연준 H.4.1 보유 국채(TREAST, 물가보상분 포함, 수요일, 십억 달러). 줄면 양적긴축(QT)으로 지준이 빠집니다."),
        chart("tga_w", "재무부 일반계정(TGA)", tga, "재무부가 연준에 둔 현금(WTREGEN, 수요일, 십억 달러). 늘면 그만큼 시장의 지준이 빠집니다 -- QT와 같은 방향."),
    ], "note_ko": f"{dates[0]}~{dates[-1]} 주간. 두 차트는 같은 날짜 축입니다."}


def duration_rail(wam: dict[str, Any] | None) -> dict[str, Any] | None:
    panels = {p["id"]: p for p in (wam or {}).get("panels") or []}
    dur, flow = panels.get("duration"), panels.get("duration_flow")
    if not dur or not dur.get("series"):
        return None
    s = {x["label"]: x["values"] for x in dur["series"]}
    total = s.get("시장성 국채 전체", [None])[-1]
    private = s.get("민간 보유(연준 제외)", [None])[-1]
    if total is None or private is None:
        return None
    fed = total - private
    priv_prev = s["민간 보유(연준 제외)"][-13] if len(s["민간 보유(연준 제외)"]) >= 13 else None
    rows = [{"label": "시장성 국채 전체", "value": f"{total:.1f}조$"},
            {"label": "연준(SOMA) 보유", "value": f"{fed:.1f}조$ · {fed / total * 100:.1f}%"},
            {"label": "민간 보유", "value": f"{private:.1f}조$" + (f" (1년 {private - priv_prev:+.2f})" if priv_prev is not None else "")}]
    bars = []
    if flow and flow.get("series"):
        fs = {x["label"]: x["values"] for x in flow["series"]}
        fedf = fs.get("연준(매입·만기)")
        if fedf:
            d = flow["dates"][-12:]
            bars = [{"date": dd[2:7].replace("-", "."), "value": v} for dd, v in zip(d, fedf[-12:])]
            last = fedf[-1]
            yr = sum(v for v in fedf[-12:] if v is not None)
            rows.append({"label": f"연준 몫 변화 {flow['dates'][-1][:7]}", "value": f"{last:+.1f}십억$"})
            rows.append({"label": "최근 12개월 합계", "value": f"{yr:+.0f}십억$"})
    return {"title": "듀레이션 (10년물 환산)", "asof": dur["dates"][-1], "rows": rows, "bars": bars,
            "note_ko": "연준이 국채를 들고 있으면 그만큼의 금리 위험이 시장에 없습니다. 만기 상환분을 재투자하지 않으면(QT) "
                       "그 듀레이션이 민간으로 넘어가 장기금리에 부담이 됩니다. 막대 = 월별로 연준 때문에 민간이 더 떠안은 "
                       "듀레이션(+면 QT 런오프로 넘어옴). 평균만기 카드의 '듀레이션' 탭과 같은 계산입니다."}


def fetch_avg_rates(since: str = "2010-01-01") -> list[dict[str, Any]]:
    req = urllib.request.Request(AVG_RATES.format(since=since), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("data") or []


def avg_rate_panel(rows: list[dict[str, Any]], months: int = 120) -> dict[str, Any] | None:
    by: dict[str, dict[str, float]] = {}
    for r in rows:
        try:
            by.setdefault(r["security_desc"], {})[r["record_date"]] = float(r["avg_interest_rate_amt"])
        except (KeyError, TypeError, ValueError):
            continue
    if "Total Interest-bearing Debt" not in by:
        return None
    axis = sorted(by["Total Interest-bearing Debt"])[-months:]
    return {"id": "avg_rate", "label": "평균 금리", "type": "lines", "markers": True, "unit": "%", "compare_ko": "직전 달",
            "dates": [f"{d[2:4]}.{int(d[5:7])}" for d in axis],
            "series": [{"label": lab, "values": [by.get(k, {}).get(d) for d in axis]} for k, lab in RATE_LINES],
            "note_ko": "재무부가 지금 들고 있는 빚에 실제로 물고 있는 평균 금리(월말, %). 새로 찍는 국채 금리가 이보다 높으면 "
                       "만기가 돌아올수록 이자비용이 계속 오릅니다. 미 재무부 Fiscal Data 'Average Interest Rates on U.S. Treasury Securities'."}


def interest_gdp_panel(mts: list[dict[str, Any]], gdp: list[tuple[str, float]], omb: list[tuple[str, float]]) -> dict[str, Any] | None:
    """MTS interest (completed fiscal years) / the fiscal year's nominal GDP; OMB net interest % GDP alongside."""
    q = dict(gdp)
    gross: dict[int, float] = {}
    for o in mts:
        fy = int(o["fiscal_year"])
        quarters = [f"{fy - 1}-10-01", f"{fy}-01-01", f"{fy}-04-01", f"{fy}-07-01"]
        if all(d in q for d in quarters):
            gross[fy] = o["interest_tn_usd"] * 1000 / (sum(q[d] for d in quarters) / 4) * 100
    net = {int(d[:4]): v for d, v in omb}
    years = sorted(set(gross) | {y for y in net if y >= min(gross, default=9999)})
    if not years:
        return None
    return {"id": "interest_gdp", "label": "GDP 대비", "type": "lines", "markers": True, "unit": "%", "compare_ko": "직전 회계연도",
            "dates": [f"FY{y}" for y in years],
            "series": [{"label": "국채이자(총, MTS) / GDP", "values": [round(gross[y], 2) if y in gross else None for y in years]},
                       {"label": "연방 이자 지출(OMB) / GDP", "values": [round(net[y], 2) if y in net else None for y in years]}],
            "note_ko": "회계연도(10~9월) 기준. 국채이자 = 월간 재무제표(MTS) '공공부채 이자' 합계 ÷ 그 회계연도 네 분기 명목 GDP(BEA) 평균. "
                       "옆 선은 백악관 예산관리국(OMB)이 집계한 연방 이자 지출의 GDP 비율(FRED FYOIGDA188S, 1년 늦게 나옴)로, 다른 공식 자료로 같은 값을 확인하는 용도입니다."}


# ---------------------------------------------------------------- national debt card

CLASS_KO = {"bills": "단기채(Bills)", "notes": "중기채(Notes)", "bonds": "장기채(Bonds)", "tips": "물가연동채(TIPS)"}


def debt_duration_panel(months: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Modified duration of marketable Treasury debt in years, month-end: DV01 / (market value x 1bp), all debt and
    by class, with the weighted average maturity (years) beside it. DV01 and market value come from
    wire_ust_maturity.py, security by security on that month's yield curve (TIPS on the real curve)."""
    rows = [m for m in months if (m.get("duration") or {}).get("dv01_mn") and (m["duration"].get("mv_bn"))]
    if not rows:
        return None
    dur = lambda dv01_mn, mv_bn: round(dv01_mn / (mv_bn * 1000 * 1e-4), 2) if dv01_mn and mv_bn else None   # noqa: E731
    series = [{"label": "시장성 국채 전체", "values": [dur(m["duration"]["dv01_mn"], m["duration"]["mv_bn"]) for m in rows]},
              {"label": "평균만기(WAM, 년)", "values": [round(m["wam_months"] / 12, 2) if m.get("wam_months") else None for m in rows]}]
    for k, lab in CLASS_KO.items():
        series.append({"label": lab, "values": [dur((m["duration"].get("dv01_by_class_mn") or {}).get(k),
                                                    (m["duration"].get("mv_by_class_bn") or {}).get(k)) for m in rows]})
    last = rows[-1]
    return {"id": "debt_duration", "label": "듀레이션", "type": "lines", "unit": "년", "compare_ko": "직전 달",
            "dates": [m["date"][:7] for m in rows], "series": series,
            "note_ko": f"시장에 나와 있는 국채(시장성)의 수정 듀레이션 = 금리 1bp 변화 때 가치 변화(DV01) ÷ (시가 × 0.01%), 월말, 년. "
                       f"{last['date'][:7]} 전체 {series[0]['values'][-1]}년, 평균만기 {series[1]['values'][-1]}년. 듀레이션이 평균만기보다 짧은 건 "
                       f"이자를 만기 전에 나눠 받기 때문이고, 금리가 오르면 같은 채권의 듀레이션도 짧아집니다. 종목별 쿠폰·만기를 그달 말 "
                       f"수익률곡선(FRED, 물가연동채는 실질금리 곡선)으로 계산(재무부 MSPD 종목 명세). 정부 내 보유(사회보장기금 등 비시장성)는 빠집니다."}


def maturity_wall_copy(wam: dict[str, Any] | None) -> dict[str, Any] | None:
    p = next((x for x in (wam or {}).get("panels") or [] if x.get("id") == "maturity_wall"), None)
    if not p:
        return None
    return {**p, "id": "debt_maturity_wall", "label": "만기별 잔액"}
