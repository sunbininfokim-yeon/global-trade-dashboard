"""Average maturity and maturity profile of US marketable debt, security by security (keyless).

The argument this answers: a bills share above its historical average is not by itself a rollover
problem -- what sets refinancing risk is the weighted average maturity (WAM) of the whole marketable
debt and when it comes due. Treasury shows both in its quarterly TBAC presentation; this rebuilds them
monthly from the Monthly Statement of the Public Debt.

Source: Fiscal Data mspd_table_3_market (MSPD Table III, marketable securities, from 2001-01). One row per
issue of a security; the security's outstanding amount sits on one of its rows (reopenings carry null).
Summed per class this matches MSPD Table I (2026-10: bills 7.382, bonds 5.563, TIPS 2.157 tn USD).
TIPS are at the outstanding amount the table gives, without the inflation adjustment.

Duration (from 2003-07, where the NY Fed's security-level SOMA history starts): each security's DV01 from
its coupon and maturity, priced off the Treasury par curve at month end (FRED DGS1MO..DGS30, linear between
tenors). Bills and anything inside six months: discount, DV01 = price x time. FRNs reset weekly: a
quarter-year duration. TIPS on the real par curve (FRED DFII5..DFII30; shorter TIPS at the 5-year real
yield), with the table's outstanding amount, which already carries the inflation adjustment; before the
real curve exists (2003) they fall back to the nominal one. Fed holdings (SOMA par by CUSIP, the Wednesday on or before month end) are taken out to get
the duration the public holds. 10-year equivalents divide by the DV01 of a par 10-year note on that day.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import date
from typing import Any

FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/mspd_table_3_market"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
FIELDS = "record_date,security_class1_desc,security_class2_desc,maturity_date,outstanding_amt,interest_rate_pct"
CURVE_IDS = {"DGS1MO": 1 / 12, "DGS3MO": 0.25, "DGS6MO": 0.5, "DGS1": 1, "DGS2": 2, "DGS3": 3, "DGS5": 5, "DGS7": 7,
             "DGS10": 10, "DGS20": 20, "DGS30": 30}
CURVE_REAL_IDS = {"DFII5": 5, "DFII7": 7, "DFII10": 10, "DFII20": 20, "DFII30": 30}
SOMA_DATES = "https://markets.newyorkfed.org/api/soma/asofdates/list.json"
SOMA_ASOF = "https://markets.newyorkfed.org/api/soma/tsy/get/asof/{d}.json"
FD_BB_DETAIL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/buybacks_security_details"
                "?fields=operation_date,coupon_rate_pct,maturity_date,par_amt_accepted&page[size]=10000")


def fetch_buyback_details() -> dict[str, list[tuple[float, str, float]]]:
    """{'YYYY-MM': [(coupon %, maturity date, par accepted bn)]} -- every security Treasury bought back."""
    out: dict[str, list] = defaultdict(list)
    for r in _get(FD_BB_DETAIL).get("data") or []:
        par = _num(r.get("par_amt_accepted"))
        if par and r.get("maturity_date") not in (None, "null"):
            out[r["operation_date"][:7]].append((_num(r.get("coupon_rate_pct")) or 0.0, r["maturity_date"], par / 1e9))
    return dict(out)

CLASS = {"Bills Maturity Value": "bills", "Notes": "notes", "Bonds": "bonds",
         "Inflation-Protected Securities": "tips", "Floating Rate Notes": "frn"}
CLASS_KO = {"bills": "단기채(Bills)", "notes": "중기채(Notes)", "bonds": "장기채(Bonds)", "tips": "물가연동(TIPS)", "frn": "변동금리(FRN)"}


def _get(url: str, timeout: int = 120) -> Any:
    proc = subprocess.run(["curl", "-sS", "-g", "-L", "-m", str(timeout), "-A", UA, url], check=False, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"mspd: curl rc={proc.returncode}")
    return json.loads(proc.stdout.decode("utf-8"))


def fetch_rows(after: str | None = None) -> list[dict[str, Any]]:
    """Every row after `after` (record_date, exclusive), oldest first."""
    flt = f"&filter=record_date:gt:{after}" if after else ""
    out, page = [], 1
    while True:
        doc = _get(f"{FD}?fields={FIELDS}&sort=record_date{flt}&page[size]=10000&page[number]={page}")
        out += doc.get("data") or []
        if page >= int((doc.get("meta") or {}).get("total-pages") or 1):
            return out
        page += 1


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def curve_on(series: dict[str, list[tuple[str, float]]], day: str, ids: dict[str, float] | None = None) -> list[tuple[float, float]]:
    """[(tenor years, yield as a fraction)] -- each tenor's last value on or before `day`, within 10 days."""
    out = []
    for sid, t in (ids or CURVE_IDS).items():
        pts = [v for d, v in series.get(sid, []) if d <= day and d >= _minus_days(day, 10)]
        if pts:
            out.append((t, pts[-1] / 100))
    return sorted(out)


def _minus_days(day: str, n: int) -> str:
    from datetime import timedelta
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()


def _yield(curve: list[tuple[float, float]], t: float) -> float:
    if t <= curve[0][0]:
        return curve[0][1]
    for (a, ya), (b, yb) in zip(curve, curve[1:]):
        if t <= b:
            return ya + (yb - ya) * (t - a) / (b - a)
    return curve[-1][1]


def price_duration(t: float, coupon: float, y: float, kind: str) -> tuple[float, float]:
    """(price per 1 of par, modified duration in years)."""
    if kind == "frn":
        return 1.0, 0.25 / (1 + y * 0.25)
    if kind == "bills" or t <= 0.5:
        return 1 / (1 + y * t), t / (1 + y * t)
    n = max(1, round(t * 2))
    times = [t - (n - 1 - k) * 0.5 for k in range(n)]
    flows = [coupon / 2] * n
    flows[-1] += 1
    pv = [f / (1 + y / 2) ** (2 * s) for f, s in zip(flows, times)]
    price = sum(pv)
    mac = sum(v * s for v, s in zip(pv, times)) / price
    return price, mac / (1 + y / 2)


def soma_dates() -> list[str]:
    return sorted(_get(SOMA_DATES)["soma"]["asOfDates"])


def fetch_soma(asof: str) -> dict[str, float]:
    """{CUSIP: par held, bn USD} on a Wednesday."""
    out: dict[str, float] = defaultdict(float)
    for h in _get(SOMA_ASOF.format(d=asof))["soma"]["holdings"]:
        if h.get("cusip") and _num(h.get("parValue")):
            out[h["cusip"]] += float(h["parValue"]) / 1e9
    return dict(out)


def _dv01_10y(curve: list[tuple[float, float]]) -> float:
    p10, d10 = price_duration(10, _yield(curve, 10), _yield(curve, 10), "notes")
    return p10 * d10 * 0.1                          # $mn per bp for $1bn of a par 10-year


def summarize(rows: list[dict[str, Any]], horizon: int = 10, curve: list[tuple[float, float]] | None = None,
              soma: dict[str, float] | None = None, soma_asof: str | None = None,
              curve_prev: list[tuple[float, float]] | None = None,
              bought: list[tuple[float, str, float]] | None = None,
              real: list[tuple[float, float]] | None = None, real_prev: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    """One month's rows -> WAM (months), amounts by class (bn USD), bills share, maturity profile by calendar year,
    and with a curve (and SOMA) the DV01 of the marketable debt and of the part the public holds."""
    rec = date.fromisoformat(rows[0]["record_date"])
    by = defaultdict(float)
    wall: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum = total = 0.0
    dv = defaultdict(float)
    mv = defaultdict(float)                   # market value (price x par), the base of a duration in years
    dv_pub = 0.0
    pv_tot = pv_pub = 0.0                     # the same holdings on last month's curve (flow decomposition)
    for r in rows:
        cls = CLASS.get(r.get("security_class1_desc"))
        amt = _num(r.get("outstanding_amt"))
        mat = r.get("maturity_date")
        if cls is None or amt is None or not mat or mat == "null":
            continue
        yrs = (date.fromisoformat(mat) - rec).days / 365.25
        if yrs < 0:
            continue
        amt /= 1000.0                               # millions -> billions
        by[cls] += amt
        total += amt
        wsum += amt * yrs
        y = int(mat[:4])
        if y < rec.year + horizon:
            wall[str(y)][cls] += amt
        if curve:
            cv = real if (cls == "tips" and real) else curve
            price, md = price_duration(yrs, (_num(r.get("interest_rate_pct")) or 0) / 100, _yield(cv, yrs), cls)
            d1 = amt * price * md * 0.1            # $bn x years x 1bp -> $mn per bp
            dv[cls] += d1
            mv[cls] += amt * price
            held = min(soma.get(r.get("security_class2_desc") or "", 0.0), amt) if soma is not None else 0.0
            if soma is not None:
                dv_pub += d1 * (amt - held) / amt
            if curve_prev:
                cvp = real_prev if (cls == "tips" and real_prev) else curve_prev
                pp, mp = price_duration(yrs, (_num(r.get("interest_rate_pct")) or 0) / 100, _yield(cvp, yrs), cls)
                d0 = amt * pp * mp * 0.1
                pv_tot += d0
                pv_pub += d0 * (amt - held) / amt
    if not total:
        raise ValueError(f"mspd {rec}: no marketable amounts")
    duration: dict[str, Any] | None = None
    if curve:
        per_bn_10y = _dv01_10y(curve)
        tot = sum(dv.values())
        duration = {"dv01_mn": round(tot, 1), "dv01_by_class_mn": {k: round(v, 1) for k, v in dv.items()},
                    "mv_bn": round(sum(mv.values()), 1), "mv_by_class_bn": {k: round(v, 1) for k, v in mv.items()},
                    "teneq_bn": round(tot / per_bn_10y, 1), "curve_10y_pct": round(_yield(curve, 10) * 100, 3)}
        if soma is not None:
            duration |= {"dv01_public_mn": round(dv_pub, 1), "teneq_public_bn": round(dv_pub / per_bn_10y, 1),
                         "fed_share_pct": round((1 - dv_pub / tot) * 100, 2) if tot else None, "soma_asof": soma_asof}
        duration["dv01_per_bn_10y"] = round(per_bn_10y, 5)
        if curve_prev and soma is not None:
            bb = 0.0
            for cpn, mat, par in bought or []:
                yrs = (date.fromisoformat(mat) - rec).days / 365.25
                if yrs > 0:
                    pp, mp = price_duration(yrs, cpn / 100, _yield(curve_prev, yrs), "notes")
                    bb += par * pp * mp * 0.1
            duration["on_prev_curve"] = {"dv01_mn": round(pv_tot, 1), "dv01_public_mn": round(pv_pub, 1),
                                         "buyback_dv01_mn": round(bb, 2)}
    return {
        "date": rec.isoformat(),
        "wam_months": round(wsum / total * 12, 2),
        "total_bn": round(total, 1),
        "by_class_bn": {k: round(v, 1) for k, v in by.items()},
        "bills_share_pct": round(by["bills"] / total * 100, 2),
        "maturity_wall_bn": {y: {k: round(v, 1) for k, v in d.items()} for y, d in sorted(wall.items())},
        **({"duration": duration} if duration else {}),
    }


def monthly(rows: list[dict[str, Any]], curves: dict[str, list[tuple[str, float]]] | None = None,
            soma_for: Any = None, bought: dict[str, list] | None = None) -> list[dict[str, Any]]:
    """Month summaries. With `curves` (FRED series by id) duration is added; `soma_for(month_end)` returns
    (asof, {cusip: par bn}) or None for months before the SOMA history."""
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["record_date"]].append(r)
    out = []
    keys = sorted(by)
    for k, d in enumerate(keys):
        curve = curve_on(curves, d) if curves else None
        prev = (prev_month_end(d) if k == 0 else keys[k - 1])
        cprev = curve_on(curves, prev) if curves else None
        held = soma_for(d) if (soma_for and curve) else None
        rl = curve_on(curves, d, CURVE_REAL_IDS) if curves else None
        rlp = curve_on(curves, prev, CURVE_REAL_IDS) if curves else None
        out.append(summarize(by[d], curve=curve if curve and len(curve) >= 4 else None,
                             soma=held[1] if held else None, soma_asof=held[0] if held else None,
                             curve_prev=cprev if cprev and len(cprev) >= 4 else None,
                             bought=(bought or {}).get(d[:7]),
                             real=rl if rl and len(rl) >= 3 else None, real_prev=rlp if rlp and len(rlp) >= 3 else None))
    return out


def prev_month_end(d: str) -> str:
    from datetime import timedelta
    return (date.fromisoformat(d[:8] + "01") - timedelta(days=1)).isoformat()


def flows(months: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Monthly change in the DV01 the public holds, split into: Treasury net supply (issuance less maturities,
    ageing) and buybacks -- both on last month's curve --, the Fed (SOMA purchases or runoff, on last month's
    curve), and the curve moving (the same bonds' DV01 on this month's curve against last month's). All four
    are converted to 10-year equivalents with this month's 10-year DV01, so they add up to the total."""
    out = []
    for a, b in zip(months, months[1:]):
        da, db = a.get("duration") or {}, b.get("duration") or {}
        pc = db.get("on_prev_curve")
        if not pc or da.get("dv01_public_mn") is None or not db.get("dv01_per_bn_10y"):
            continue
        per = db["dv01_per_bn_10y"]
        treasury = pc["dv01_mn"] - da["dv01_mn"]
        buyback = -pc["buyback_dv01_mn"]
        fed = -((pc["dv01_mn"] - pc["dv01_public_mn"]) - (da["dv01_mn"] - da["dv01_public_mn"]))
        rates = db["dv01_public_mn"] - pc["dv01_public_mn"]
        total = db["dv01_public_mn"] - da["dv01_public_mn"]
        out.append({"date": b["date"], "total": round(total / per, 1), "treasury_ex_buyback": round((treasury - buyback) / per, 1),
                    "buyback": round(buyback / per, 1), "fed": round(fed / per, 1), "rates": round(rates / per, 1),
                    "dv01_total_mn": round(total, 1)})
    return out


def card(months: list[dict[str, Any]], retrieved_at: str) -> dict[str, Any]:
    """USA card: WAM history, with bills share and the maturity wall as panels."""
    last = months[-1]
    dates = [m["date"] for m in months]
    wam = [m["wam_months"] for m in months]
    year_ago = next((m for m in reversed(months) if m["date"] <= f"{int(last['date'][:4]) - 1}{last['date'][4:]}"), None)
    hist = lambda n: {"dates": dates[-n:], "values": wam[-n:]}  # noqa: E731
    peak = max(months, key=lambda m: m["bills_share_pct"])
    wall = last["maturity_wall_bn"]
    years = list(wall)
    classes = [c for c in ("bills", "notes", "bonds", "tips", "frn") if any(wall[y].get(c) for y in years)]
    d_wam = f", 1년 전 {year_ago['wam_months']:.1f}개월" if year_ago else ""
    note = (f"{last['date'][:7]} 말 시장성 국채 {last['total_bn'] / 1000:.2f}조 달러의 가중평균 잔존만기(WAM)는 "
            f"{last['wam_months']:.1f}개월{d_wam}입니다. 단기채 비중 {last['bills_share_pct']:.1f}%. "
            f"단기채 비중이 역사적 평균(TBAC 권고 15~20%)을 넘어도, 차환 부담을 정하는 것은 전체 부채의 평균만기와 "
            f"만기가 몰린 해입니다. '단기채 비중'·'만기 벽' 탭에서 함께 보세요. 재무부 월간 국가채무 명세(MSPD) 종목별 잔액으로 계산했습니다.")
    out = {
        "id": "ust_debt_wam",
        "category": "liquidity",
        "label_ko": "국채 평균만기(WAM)",
        "unit": "months",
        "format": "num1",
        "value": last["wam_months"],
        "display": f"{last['wam_months']:.1f}개월",
        "display_chip": f"{last['wam_months']:.1f}개월",
        "change_1m_pct": None,
        "change_1y_pct": None,
        "asof": last["date"],
        "observed_at": last["date"],
        "reference_period": last["date"][:7],
        "history": {"5y": hist(60), "10y": hist(120)},
        "source": "fiscaldata:mspd_table_3_market",
        "source_urls": ["https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "monthly",
        "chart_type": "line",
        "retrieved_at": retrieved_at,
        "note_ko": note,
        "panels": [
            {"id": "bills_share", "label": "단기채 비중", "type": "lines", "unit": "%", "compare_ko": "전월",
             "dates": dates, "series": [{"label": "단기채 비중", "values": [m["bills_share_pct"] for m in months]}],
             "note_ko": (f"시장성 국채 중 단기채(1년 이하) 잔액 비중입니다. 2001년 이후 최고 {peak['bills_share_pct']:.1f}%"
                         f"({peak['date'][:7]}), 현재 {last['bills_share_pct']:.1f}%. TBAC는 장기 평균 15~20%를 권고해 왔습니다.")},
            {"id": "maturity_wall", "label": "만기 벽", "type": "stack", "unit": "십억$", "compare_ko": "앞 연도",
             "dates": years,
             "series": [{"label": CLASS_KO[c], "values": [wall[y].get(c, 0.0) for y in years]} for c in classes],
             "note_ko": (f"{last['date'][:7]} 말 잔액 기준, 만기가 돌아오는 해별 금액(십억 달러)입니다. 첫해는 남은 기간만입니다. "
                         f"신규 발행은 들어 있지 않습니다 -- 앞으로 찍을 단기채는 대부분 이 벽의 앞쪽에 다시 쌓입니다.")},
        ],
        "mspd": {"latest": last},
    }
    dur = [m for m in months if (m.get("duration") or {}).get("teneq_public_bn") is not None]
    if dur:
        ld = dur[-1]["duration"]
        tot_dv = sum(ld["dv01_by_class_mn"].values()) or 1
        fl = flows(dur)[-60:]
        yr = next((m for m in reversed(dur) if m["date"] <= f"{int(dur[-1]['date'][:4]) - 1}{dur[-1]['date'][4:]}"), None)
        d_y = (f", 1년 새 {ld['teneq_public_bn'] - yr['duration']['teneq_public_bn']:+,.0f}십억 달러" if yr else "")
        out["panels"] += [
            {"id": "duration", "label": "듀레이션 공급", "type": "lines", "unit": "조$", "compare_ko": "전월",
             "dates": [m["date"] for m in dur],
             "series": [{"label": "시장성 국채 전체", "values": [round(m["duration"]["teneq_bn"] / 1000, 3) for m in dur]},
                        {"label": "민간 보유(연준 제외)", "values": [round(m["duration"]["teneq_public_bn"] / 1000, 3) for m in dur]}],
             "note_ko": (f"재무부가 시장에 넘긴 금리 위험을 10년물 환산액으로 나타냈습니다(조 달러). {dur[-1]['date'][:7]} 말 전체 "
                         f"{ld['teneq_bn'] / 1000:.1f}조, 연준(SOMA) 보유분을 뺀 민간 보유 {ld['teneq_public_bn'] / 1000:.1f}조{d_y}. "
                         f"DV01(금리 1bp당 가치 변화)은 전체 {ld['dv01_mn'] / 1000:.1f}십억 달러, 이 중 연준 몫 {ld['fed_share_pct']:.1f}%. "
                         "종목별 쿠폰·만기를 그달 말 국채 수익률곡선(FRED)으로 계산했고, 물가연동채는 실질금리 곡선(DFII)과 물가 조정된 잔액을 썼습니다.")},
            {"id": "duration_flow", "label": "월별 듀레이션 순공급", "type": "stack", "unit": "십억$", "compare_ko": "전월",
             "dates": [f["date"] for f in fl],
             "series": [{"label": "재무부 순발행(바이백 제외)", "values": [f["treasury_ex_buyback"] for f in fl]},
                        {"label": "바이백", "values": [f["buyback"] for f in fl]},
                        {"label": "연준(매입·만기)", "values": [f["fed"] for f in fl]},
                        {"label": "금리 변화 효과", "values": [f["rates"] for f in fl]}],
             "line": {"label": "민간 보유 변화 합계", "values": [f["total"] for f in fl]},
             "note_ko": ("한 달 동안 민간이 새로 떠안은 듀레이션(10년물 환산, 십억 달러)을 원인별로 나눴습니다. 재무부 순발행·바이백·연준은 "
                         "전월 말 수익률곡선으로 고정해 계산한 물량 효과이고, 나머지는 금리가 움직여 같은 채권의 듀레이션이 바뀐 효과입니다"
                         "(금리가 내리면 늘어남). 바이백은 Fiscal Data 종목별 매입 내역, 연준은 뉴욕연준 SOMA 종목별 보유입니다. 네 부분을 모두 이번 달 10년물 DV01로 "
                         "환산해 합이 맞도록 했기 때문에, 달마다 환산 기준이 바뀌는 '듀레이션 공급' 탭의 월 차이와는 다를 수 있습니다."
                         + (f" {fl[-1]['date'][:7]}: 합계 {fl[-1]['total']:+,.0f} = 순발행 {fl[-1]['treasury_ex_buyback']:+,.0f}, "
                            f"바이백 {fl[-1]['buyback']:+,.0f}, 연준 {fl[-1]['fed']:+,.0f}, 금리 {fl[-1]['rates']:+,.0f}." if fl else ""))},
            {"id": "dv01_mix", "label": "금리 위험 구성", "type": "hbar", "unit": "%", "asof": dur[-1]["date"],
             "rows": sorted([{"label": CLASS_KO[c], "value": round(v / tot_dv * 100, 1),
                              "sub": f"잔액 비중 {dur[-1]['by_class_bn'].get(c, 0) / dur[-1]['total_bn'] * 100:.1f}%"}
                             for c, v in ld["dv01_by_class_mn"].items()], key=lambda r: -r["value"]),
             "note_ko": ("종류별로 전체 DV01(금리 위험)에서 차지하는 비중과, 잔액 비중을 나란히 놓았습니다. 단기채는 잔액은 크지만 "
                         "금리 위험은 거의 없습니다 -- 단기채를 늘리고 장기채 발행을 묶으면 시장에 풀리는 듀레이션은 거의 늘지 않습니다.")},
        ]
    return out


def add_outlook_panels(card: dict[str, Any], months: list[dict[str, Any]], ol: dict[str, Any]) -> None:
    """'전망' panels: the last 12 months as recorded and the projected path from the latest month end."""
    hist = months[-12:]
    path = ol["path"]
    dates = [m["date"][:7] for m in hist] + [p["month"] for p in path]
    pad = [None] * len(path)
    bt = ol.get("backtest")
    btxt = (f" 같은 방법을 {bt['quarter']} 분기 시작({bt['base'][:7]} 말)부터 돌려 실제와 비교하면 단기채 비중 평균 "
            f"{bt['bills_pp_mean']:+.2f}%p, 평균만기 평균 {bt['wam_m_mean_abs']:.2f}개월 차이였습니다"
            f"(연준이 입찰에서 받아 가는 단기채는 넣지 않아 단기채 비중이 낮게 나오는 경향)." if bt else "")
    basis = ("재무부 분기 순차입 추정치(분기 안에서는 균등 배분)에서 이표채 순발행(발행계획 성명의 입찰 규모 표 - MSPD 월별 만기)을 "
             "뺀 나머지를 단기채로 채웠습니다. 표 밖의 달은 직전 분기와 같은 규모로 가정(재무부 안내: '향후 몇 분기 유지')." + btxt)
    head = (f"{path[-1]['month']} 말 전망: 단기채 비중 {path[-1]['bills_share_pct']:.1f}%, 평균만기 {path[-1]['wam_months']:.1f}개월 "
            f"(지금 {hist[-1]['bills_share_pct']:.1f}%, {hist[-1]['wam_months']:.1f}개월). ")

    def two(key: str, label: str) -> list[dict[str, Any]]:
        return [{"label": f"{label} 실적", "values": [m[key] for m in hist] + pad},
                {"label": f"{label} 전망", "values": [None] * (len(hist) - 1) + [hist[-1][key]] + [p[key] for p in path]}]
    card["panels"][1:1] = [
        {"id": "outlook_bills", "label": "단기채 비중 전망", "type": "lines", "unit": "%", "compare_ko": "전월",
         "dates": dates, "series": two("bills_share_pct", "단기채 비중"), "note_ko": head + basis, "path": path, "backtest": bt},
        {"id": "outlook_wam", "label": "평균만기 전망", "type": "lines", "unit": "개월", "compare_ko": "전월",
         "dates": dates, "series": two("wam_months", "평균만기"), "note_ko": head + basis},
    ]


OFR_MMF_TSY = "https://data.financialresearch.gov/v1/series/timeseries?mnemonic=MMF-MMF_T_TOT-M"
LLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin="


def fetch_bill_buyers() -> dict[str, dict[str, float]]:
    """{'YYYY-MM': value bn} for money-market funds' Treasury holdings (OFR MMF monitor, month end) and
    USD stablecoin supply (DefiLlama, last day of each month)."""
    from datetime import datetime, timezone
    mmf = {d[:7]: v / 1e9 for d, v in _get(OFR_MMF_TSY) if v is not None}
    st: dict[str, float] = {}
    for x in _get(LLAMA_STABLES):
        v = ((x.get("totalCirculatingUSD") or {}).get("peggedUSD"))
        if v:
            st[datetime.fromtimestamp(int(x["date"]), timezone.utc).strftime("%Y-%m")] = v / 1e9   # later days overwrite
    return {"mmf": mmf, "stablecoins": st}


def add_buyers_panel(card: dict[str, Any], months: list[dict[str, Any]], buyers: dict[str, dict[str, float]],
                     since: str = "2019-01") -> None:
    ms = [m for m in months if m["date"][:7] >= since]
    keys = [m["date"][:7] for m in ms]
    bills = [round(m["by_class_bn"].get("bills", 0) / 1000, 3) for m in ms]
    mmf = [round(buyers["mmf"][k] / 1000, 3) if k in buyers["mmf"] else None for k in keys]
    st = [round(buyers["stablecoins"][k] / 1000, 3) if k in buyers["stablecoins"] else None for k in keys]
    i = max((k for k, v in enumerate(mmf) if v is not None), default=None)
    share = f"MMF 국채 보유는 단기채 잔액의 {mmf[i] / bills[i] * 100:.0f}%({keys[i]})" if i is not None else ""
    j = max((k for k, v in enumerate(st) if v is not None), default=None)
    sc = f", 달러 스테이블코인 공급 {st[j] * 10000:,.0f}억 달러(단기채 잔액의 {st[j] / bills[j] * 100:.1f}%)" if j is not None else ""
    card["panels"].append({
        "id": "bill_buyers", "label": "단기채 구매자", "type": "lines", "unit": "조$", "compare_ko": "전월",
        "dates": [m["date"] for m in ms],
        "series": [{"label": "단기채 잔액", "values": bills},
                   {"label": "MMF 국채 보유", "values": mmf},
                   {"label": "달러 스테이블코인 공급", "values": st}],
        "note_ko": (f"단기채를 사 줄 구조적 수요입니다. {share}{sc}. MMF 보유(OFR 단기자금 모니터)는 단기채가 대부분이지만 "
                    "이표채도 일부 섞여 있습니다. 스테이블코인은 공급량이며, 준비금의 대부분이 단기채·국채 레포라 단기채 수요의 대리 지표로 씁니다"
                    "(발행사별 준비금 구성은 공시 PDF라 싣지 않았습니다)."),
    })


FD_TGA = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
          "?fields=record_date,account_type,open_today_bal&filter=account_type:eq:Treasury%20General%20Account%20(TGA)%20Closing%20Balance,"
          "record_date:gte:{since}&sort=record_date&page[size]=10000")


def fetch_tga(since: str) -> list[tuple[str, float]]:
    """Daily TGA closing balance, bn USD (Daily Treasury Statement)."""
    return [(r["record_date"], float(r["open_today_bal"]) / 1000) for r in _get(FD_TGA.format(since=since)).get("data") or []
            if _num(r.get("open_today_bal")) is not None]


def add_tga_panel(card: dict[str, Any], tga: list[tuple[str, float]], quarters_cash: dict[str, float]) -> None:
    """TGA daily against Treasury's end-of-quarter cash assumption (refunding estimates), drawn as a step over
    each quarter. quarters_cash: {'YYYY-MM' first month of quarter: assumed end balance bn}."""
    if not tga:
        return
    def q(d: str) -> str:
        return f"{d[:4]}-{((int(d[5:7]) - 1) // 3) * 3 + 1:02d}"
    dates = [d for d, _ in tga]
    vals = [round(v, 1) for _, v in tga]
    assume = [quarters_cash.get(q(d)) for d in dates]
    last_q = q(dates[-1])
    nxt = sorted(k for k in quarters_cash if k > last_q)
    eok = lambda v: (f"{v / 1000:.2f}".rstrip("0").rstrip(".") + "조 달러") if v >= 1000 else f"{v * 10:,.0f}억 달러"  # noqa: E731
    tail = (f" 재무부 가정: 이번 분기말 {eok(quarters_cash[last_q])}" if last_q in quarters_cash else "") + \
           (f", 다음 분기말 {eok(quarters_cash[nxt[0]])}" if nxt else "")
    card["panels"].append({
        "id": "tga", "label": "TGA 현금잔고", "type": "lines", "unit": "십억$", "compare_ko": "전 영업일",
        "dates": dates, "series": [{"label": "TGA 잔고", "values": vals},
                                   {"label": "재무부 분기말 가정", "values": assume}],
        "note_ko": (f"재무부 현금계좌(TGA) 일별 잔고입니다(차트 단위 십억 달러, 일일 국고 명세 DTS). {dates[-1]} {eok(vals[-1])}." + tail +
                    ". TGA가 가정보다 낮으면 그만큼 시장에 돈이 풀린 상태(지준 증가)이고, 분기말에 가정 수준으로 다시 채우려면 단기채를 더 찍어야 합니다. "
                    "가정선은 각 분기 발행계획 추정치의 분기말 현금잔고를 그 분기 전체에 그은 것입니다."),
    })
