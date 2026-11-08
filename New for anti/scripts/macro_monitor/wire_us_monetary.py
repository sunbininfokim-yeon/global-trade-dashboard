#!/usr/bin/env python3
"""US monetary-policy cards that need more than one series:

  * fedwatch          -- the policy path implied by fed funds futures, meeting by meeting (macro_monitor/fed_path.py).
                         Replaces the demo FedWatch card; CME's own numbers are licensed, the futures are not.
  * real_policy_rate  -- effective fed funds rate (monthly) minus core PCE inflation (YoY).
  * sovereign_debt    -- for the USA only: Treasury's daily Debt to the Penny instead of the IMF's annual
                         general-government figure (the IMF series stays under '원자료·산식'), with debt/GDP.

    python3 wire_us_monetary.py

Keyless (FRED through us_public_series.fetch_fred, Yahoo through the dashboard Worker, Fiscal Data).
A card whose source cannot be read keeps what the pack has; exit status 1 names it.
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import fed_path as fp  # noqa: E402
from macro_monitor import ust_auctions as ua  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
CALENDAR = ROOT / "config" / "fomc_calendar_v1.json"
DTTP = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
        "?sort=-record_date&page%5Bsize%5D=3000&fields=record_date,tot_pub_debt_out_amt")
KEEP = ("news", "news_query", "news_tags")


def _keep(old: dict | None, card: dict) -> dict:
    for k in KEEP:
        if old and old.get(k) is not None and k not in card:
            card[k] = old[k]
    return card


def weekly_last(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """The last observation of each ISO week -- ten years of a daily series in ~520 points."""
    by: dict[tuple[int, int], tuple[str, float]] = {}
    for d, v in sorted(points):
        y, w, _ = date.fromisoformat(d).isocalendar()
        by[(y, w)] = (d, v)
    return [by[k] for k in sorted(by)]


# --------------------------------------------------------------------------
# Rate path
# --------------------------------------------------------------------------

def rate_path_card(now: str, today: str) -> dict:
    meetings = [m["decision_date"] for m in json.loads(CALENDAR.read_text(encoding="utf-8"))["meetings"]]
    effr_pts = ups.fetch_fred("EFFR")
    effr = effr_pts[-1][1]
    cur = today[:7]
    months = [fp.add_months(cur, i) for i in range(0, 14)]
    rates, closes, last_day, far = {}, {}, "", []
    for ym in months:
        try:
            pts = fp.fetch_contract(ym)
        except Exception as exc:  # noqa: BLE001 -- the path simply stops at the last contract read
            print(f"  {fp.symbol(ym)}: {exc}")
            break
        if not pts:
            break
        closes[ym] = pts[-1][1]
        rates[ym] = round(100 - pts[-1][1], 4)
        last_day = max(last_day, pts[-1][0])
        far = pts
    rows = fp.path(rates, meetings, today, effr)
    if not rows:
        raise ValueError("no meeting within the contracts read")
    start = rates[cur] if cur in rates and not any(m[:7] == cur and m > today for m in meetings) else effr
    lower = math.floor(effr / fp.STEP + 1e-9) * fp.STEP
    fp.enrich(rows, start, lower)
    chip, full = fp.headline(rows)
    end = rows[-1]
    far_ym = max(rates)
    hist = [(d, round(100 - c, 4)) for d, c in far]
    nxt = rows[0]
    word = {"+0": "동결", "+25": "25bp 인상", "-25": "25bp 인하", "+50": "50bp 인상", "-50": "50bp 인하"}
    outcomes = [{"label_ko": word.get(k, f"{k}bp"), "bp_change": int(k), "prob": round(v * 100, 1)}
                for k, v in sorted(nxt["move_odds"].items(), key=lambda kv: int(kv[0]))]
    note = (f"연방기금 선물(CBOT 30일물) 가격으로 계산한 회의별 금리 경로입니다. {full}. "
            f"{end['date'][:7].replace('-', '년 ')}월 회의 뒤 내재 금리 {end['post']:.2f}% "
            f"(지금 실효금리 {effr:.2f}% 대비 {end['cum_bp']:+.0f}bp). CME FedWatch와 같은 산식이지만 그 수치는 "
            f"유료라 직접 계산했고, 여러 회의에 걸친 확률은 누적 변화폭을 인접한 25bp 두 칸에 나눈 단순화입니다.")
    return {
        "id": "fedwatch",
        "category": "rates",
        "label_ko": "금리 경로 (선물 내재)",
        "unit": "%",
        "format": "pct2",
        "value": end["post"],
        "display": f"{chip} · {end['post']:.2f}%",
        "display_chip": chip,
        "change_1m_pct": None,
        "change_1y_pct": None,
        "asof": last_day,
        "observed_at": last_day,
        "reference_period": nxt["date"],
        "history": ups.history_block(hist, "weekly"),
        "history_note_ko": f"차트는 {far_ym[:4]}년 {int(far_ym[5:7])}월물 선물의 내재 금리(100 − 가격) 추이입니다.",
        "source": "cbot:ZQ via yahoo",
        "source_urls": ["https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.html"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "daily",
        "chart_type": "line",
        "retrieved_at": now,
        "note_ko": note,
        "outcomes": outcomes,
        "rate_path": {
            "as_of": last_day,
            "effr": effr,
            "start_rate": round(start, 4),
            "target_lower": lower,
            "meetings": rows,
            "contracts": [{"month": ym, "symbol": fp.symbol(ym), "price": closes[ym], "rate": rates[ym]} for ym in rates],
            "method_ko": ("월물 가격 = 100 − 그 달 평균 실효금리. 회의가 있는 달은 (결정일까지 일수×회의 전 금리 + 나머지×회의 후 "
                          "금리) ÷ 그 달 일수로 풀고, 다음 달에 회의가 없으면 다음 달 월물로 회의 후 금리를 잡습니다. "
                          "기대 변화폭을 인접한 25bp 두 칸에 나눠 확률로 읽습니다."),
        },
        "news_query": "fed funds futures FOMC rate path odds",
        "news_tags": ["fedwatch", "fomc", "fed"],
    }


# --------------------------------------------------------------------------
# Real policy rate
# --------------------------------------------------------------------------

def real_rate_card(usa: dict, now: str) -> dict:
    ff = {d[:7]: v for d, v in ups.fetch_fred("FEDFUNDS")}
    core = next(i for i in usa["indicators"] if i["id"] == "core_pce_yoy")
    h = ((core.get("modes") or {}).get("yoy") or core).get("history", {}).get("10y", {})
    pce = {d[:7]: v for d, v in zip(h.get("dates", []), h.get("values", [])) if v is not None}
    pts = [(f"{m}-01", round(ff[m] - pce[m], 4)) for m in sorted(ff) if m in pce]
    if not pts:
        raise ValueError("no month with both EFFR and core PCE")
    last_m, v = pts[-1][0][:7], pts[-1][1]
    asof = ups.month_end(pts[-1][0]) if hasattr(ups, "month_end") else pts[-1][0]
    return {
        "id": "real_policy_rate",
        "category": "rates",
        "label_ko": "실질 정책금리",
        "unit": "%",
        "format": "pct2",
        "value": v,
        "display": f"{v:.2f}%",
        "display_chip": f"{v:.2f}%",
        "change_1m_pct": None,
        "change_1y_pct": None,
        "asof": asof,
        "observed_at": asof,
        "reference_period": last_m,
        "history": ups.history_block(pts, "monthly"),
        "source": "fred:FEDFUNDS − BEA core PCE",
        "source_urls": ["https://fred.stlouisfed.org/series/FEDFUNDS", "https://www.bea.gov/data/personal-consumption-expenditures-price-index-excluding-food-and-energy"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "monthly",
        "chart_type": "line",
        "retrieved_at": now,
        "note_ko": (f"월평균 실효 연방기금금리 {ff[last_m]:.2f}%에서 근원 PCE 전년비 {pce[last_m]:.2f}%를 뺀 값입니다"
                    f"({last_m}). 양수가 클수록 물가를 감안해도 금리가 높아 긴축적입니다. 연준이 보는 중립금리(실질 0.5~1% 안팎) "
                    "추정과 견주어 읽습니다."),
        "thresholds": [{"kind": "threshold", "value": 0, "label_ko": "실질 0%"}],
        "news_query": "real fed funds rate restrictive neutral rate",
        "news_tags": ["fed", "fomc"],
    }


# --------------------------------------------------------------------------
# Debt to the Penny
# --------------------------------------------------------------------------

def fetch_dttp() -> list[tuple[str, float]]:
    req = urllib.request.Request(DTTP, headers={"User-Agent": fp.USER_AGENT, "Accept": "application/json"})
    out = []
    url = DTTP
    for page in range(1, 4):                                   # 3 pages x 3,000 days = ~36 years
        req = urllib.request.Request(f"{url}&page%5Bnumber%5D={page}", headers={"User-Agent": fp.USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.loads(r.read().decode("utf-8"))
        rows = doc.get("data") or []
        out += [(x["record_date"], float(x["tot_pub_debt_out_amt"]) / 1e12) for x in rows if x.get("tot_pub_debt_out_amt")]
        if len(rows) < 3000:
            break
    return sorted(out)


def debt_card(old: dict, now: str) -> dict:
    daily = fetch_dttp()
    gdp = ups.fetch_fred("GDP")                                 # nominal, $bn SAAR, quarterly
    weekly = weekly_last([p for p in daily if p[0] >= "2014-01-01"])

    def gdp_at(d: str) -> float | None:
        # the quarter the date falls in (FRED dates a quarter by its first day)
        prior = [v for q, v in gdp if q <= d]
        return prior[-1] if prior else None

    ratio = [(d, round(v * 1000 / g * 100, 2)) for d, v in weekly for g in [gdp_at(d)] if g]
    d, v = daily[-1]
    year_ago = [x for x in daily if x[0] <= f"{int(d[:4]) - 1}{d[4:]}"]
    yoy = (v / year_ago[-1][1] - 1) * 100 if year_ago else None
    card = dict(old)
    card.update({
        "label_ko": "국가부채",
        "value": round(v, 4),
        "display": f"{v:.2f}T",
        "display_chip": f"{v:.2f}T",
        "change_1y_pct": round(yoy, 2) if yoy is not None else None,
        "asof": d,
        "observed_at": d,
        "reference_period": d,
        "history": ups.history_block([(x, round(y, 4)) for x, y in weekly], "weekly"),
        "source": "fiscaldata:debt_to_penny",
        "source_urls": ["https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"],
        "quality": "live",
        "data_status": "live",
        "refresh_tier": "daily",
        "series_frequency": "daily",
        "retrieved_at": now,
        "note_ko": (f"미 재무부 'Debt to the Penny'의 연방정부 총부채(시장성·비시장성, 정부 내 보유 포함)입니다. 매 영업일 "
                    f"갱신됩니다. {d} 기준 {v:.2f}조 달러, 1년 전보다 {yoy:+.1f}%. 국가부채/GDP는 그 날짜가 속한 분기의 "
                    "명목 GDP(연율)로 나눈 값입니다(2020년 2분기의 튀어 오름은 GDP 급감 때문). 다른 나라와 비교하는 IMF 일반정부 부채(연간)는 '원자료·산식' 탭에 "
                    "그대로 있습니다." if yoy is not None else "미 재무부 Debt to the Penny 연방정부 총부채입니다."),
    })
    card.pop("snapshot_asof", None)
    fc = dict(card.get("fiscal_compare") or {})
    fc.update({"primary_label_ko": "국가부채(연방, 일간)", "primary_unit": "조 달러",
               "secondary_label_ko": "국가부채/GDP", "secondary_unit": "%",
               "secondary_history": ups.history_block(ratio, "weekly")})
    fc.pop("actuals_only", None)
    card["fiscal_compare"] = fc
    return card


def main() -> int:
    now, today = ups.now_iso(), fp.today_iso()
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    old = {i["id"]: i for i in usa["indicators"]}
    failures = []
    for name, build in (("fedwatch", lambda: rate_path_card(now, today)),
                        ("real_policy_rate", lambda: real_rate_card(usa, now)),
                        ("sovereign_debt", lambda: debt_card(old["sovereign_debt"], now))):
        try:
            card = _keep(old.get(name), build())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {exc}")
            continue
        card.pop("hidden", None)
        prev = old.get(name)
        if prev and {**prev, "retrieved_at": None} == {**card, "retrieved_at": None}:
            card["retrieved_at"] = prev.get("retrieved_at")
        ua.upsert(usa, card)
        print(f"{name}: {card['display']}  ({card.get('reference_period') or card.get('asof')})")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
