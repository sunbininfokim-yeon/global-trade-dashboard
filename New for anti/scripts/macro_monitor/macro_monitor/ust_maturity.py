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
quarter-year duration. TIPS are priced on the nominal curve -- an approximation, their real duration is a
little longer. Fed holdings (SOMA par by CUSIP, the Wednesday on or before month end) are taken out to get
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
SOMA_DATES = "https://markets.newyorkfed.org/api/soma/asofdates/list.json"
SOMA_ASOF = "https://markets.newyorkfed.org/api/soma/tsy/get/asof/{d}.json"

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


def curve_on(series: dict[str, list[tuple[str, float]]], day: str) -> list[tuple[float, float]]:
    """[(tenor years, yield as a fraction)] -- each tenor's last value on or before `day`, within 10 days."""
    out = []
    for sid, t in CURVE_IDS.items():
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


def summarize(rows: list[dict[str, Any]], horizon: int = 10, curve: list[tuple[float, float]] | None = None,
              soma: dict[str, float] | None = None, soma_asof: str | None = None) -> dict[str, Any]:
    """One month's rows -> WAM (months), amounts by class (bn USD), bills share, maturity profile by calendar year,
    and with a curve (and SOMA) the DV01 of the marketable debt and of the part the public holds."""
    rec = date.fromisoformat(rows[0]["record_date"])
    by = defaultdict(float)
    wall: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum = total = 0.0
    dv = defaultdict(float)
    dv_pub = 0.0
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
            price, md = price_duration(yrs, (_num(r.get("interest_rate_pct")) or 0) / 100, _yield(curve, yrs), cls)
            d1 = amt * price * md * 0.1            # $bn x years x 1bp -> $mn per bp
            dv[cls] += d1
            if soma is not None:
                held = min(soma.get(r.get("security_class2_desc") or "", 0.0), amt)
                dv_pub += d1 * (amt - held) / amt
    if not total:
        raise ValueError(f"mspd {rec}: no marketable amounts")
    duration: dict[str, Any] | None = None
    if curve:
        p10, d10 = price_duration(10, _yield(curve, 10), _yield(curve, 10), "notes")
        per_bn_10y = p10 * d10 * 0.1                 # $mn per bp for $1bn of a par 10-year
        tot = sum(dv.values())
        duration = {"dv01_mn": round(tot, 1), "dv01_by_class_mn": {k: round(v, 1) for k, v in dv.items()},
                    "teneq_bn": round(tot / per_bn_10y, 1), "curve_10y_pct": round(_yield(curve, 10) * 100, 3)}
        if soma is not None:
            duration |= {"dv01_public_mn": round(dv_pub, 1), "teneq_public_bn": round(dv_pub / per_bn_10y, 1),
                         "fed_share_pct": round((1 - dv_pub / tot) * 100, 2) if tot else None, "soma_asof": soma_asof}
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
            soma_for: Any = None) -> list[dict[str, Any]]:
    """Month summaries. With `curves` (FRED series by id) duration is added; `soma_for(month_end)` returns
    (asof, {cusip: par bn}) or None for months before the SOMA history."""
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["record_date"]].append(r)
    out = []
    for d, v in sorted(by.items()):
        curve = curve_on(curves, d) if curves else None
        held = soma_for(d) if (soma_for and curve) else None
        out.append(summarize(v, curve=curve if curve and len(curve) >= 4 else None,
                             soma=held[1] if held else None, soma_asof=held[0] if held else None))
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
        flow = [(dur[k]["date"], round(dur[k]["duration"]["teneq_public_bn"] - dur[k - 1]["duration"]["teneq_public_bn"], 1))
                for k in range(1, len(dur))][-60:]
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
                         "종목별 쿠폰·만기를 그달 말 국채 수익률곡선(FRED)으로 계산했고, 물가연동채는 명목 곡선으로 근사했습니다.")},
            {"id": "duration_flow", "label": "월별 듀레이션 순공급", "type": "bars", "unit": "십억$", "compare_ko": "전월",
             "dates": [d for d, _ in flow], "series": [{"label": "민간 보유 10년물 환산 변화", "values": [v for _, v in flow]}],
             "note_ko": ("한 달 동안 민간이 새로 떠안은 듀레이션(10년물 환산, 십억 달러)입니다. 재무부 순발행이 늘리고, 바이백·연준 매입·"
                         "만기 경과가 줄입니다. 금리 수준이 바뀌어도 같은 채권의 듀레이션이 달라지므로 발행량과 정확히 같지는 않습니다.")},
            {"id": "dv01_mix", "label": "금리 위험 구성", "type": "hbar", "unit": "%", "asof": dur[-1]["date"],
             "rows": sorted([{"label": CLASS_KO[c], "value": round(v / tot_dv * 100, 1),
                              "sub": f"잔액 비중 {dur[-1]['by_class_bn'].get(c, 0) / dur[-1]['total_bn'] * 100:.1f}%"}
                             for c, v in ld["dv01_by_class_mn"].items()], key=lambda r: -r["value"]),
             "note_ko": ("종류별로 전체 DV01(금리 위험)에서 차지하는 비중과, 잔액 비중을 나란히 놓았습니다. 단기채는 잔액은 크지만 "
                         "금리 위험은 거의 없습니다 -- 단기채를 늘리고 장기채 발행을 묶으면 시장에 풀리는 듀레이션은 거의 늘지 않습니다.")},
        ]
    return out
