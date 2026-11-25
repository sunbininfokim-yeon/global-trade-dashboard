"""Average maturity and maturity profile of US marketable debt, security by security (keyless).

The argument this answers: a bills share above its historical average is not by itself a rollover
problem -- what sets refinancing risk is the weighted average maturity (WAM) of the whole marketable
debt and when it comes due. Treasury shows both in its quarterly TBAC presentation; this rebuilds them
monthly from the Monthly Statement of the Public Debt.

Source: Fiscal Data mspd_table_3_market (MSPD Table III, marketable securities, from 2001-01). One row per
issue of a security; the security's outstanding amount sits on one of its rows (reopenings carry null).
Summed per class this matches MSPD Table I (2026-10: bills 7.382, bonds 5.563, TIPS 2.157 tn USD).
TIPS are at the outstanding amount the table gives, without the inflation adjustment.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import date
from typing import Any

FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/mspd_table_3_market"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
FIELDS = "record_date,security_class1_desc,security_class2_desc,maturity_date,outstanding_amt"

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


def summarize(rows: list[dict[str, Any]], horizon: int = 10) -> dict[str, Any]:
    """One month's rows -> WAM (months), amounts by class (bn USD), bills share, maturity profile by calendar year."""
    rec = date.fromisoformat(rows[0]["record_date"])
    by = defaultdict(float)
    wall: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum = total = 0.0
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
    if not total:
        raise ValueError(f"mspd {rec}: no marketable amounts")
    return {
        "date": rec.isoformat(),
        "wam_months": round(wsum / total * 12, 2),
        "total_bn": round(total, 1),
        "by_class_bn": {k: round(v, 1) for k, v in by.items()},
        "bills_share_pct": round(by["bills"] / total * 100, 2),
        "maturity_wall_bn": {y: {k: round(v, 1) for k, v in d.items()} for y, d in sorted(wall.items())},
    }


def monthly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["record_date"]].append(r)
    return [summarize(v) for _, v in sorted(by.items())]


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
    return {
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
