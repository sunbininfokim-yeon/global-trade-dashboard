"""Build prior-actual / prior-forecast / current compare bars for UI."""

from __future__ import annotations

import calendar
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def _parse_announce(s: Optional[str]) -> datetime:
    if not s:
        return datetime.min
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return datetime.min


def _su_estimates(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    su = event.get("sources_uses") or {}
    return [r for r in (su.get("rows") or []) if r.get("row_kind") == "estimate"]


def _su_actuals(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    su = event.get("sources_uses") or {}
    return [r for r in (su.get("rows") or []) if r.get("row_kind") == "actual"]


def build_net_borrowing_compare(
    event: Dict[str, Any],
    *,
    prior_event: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Three-way compare for QRA click drawer (선빈 요청):

    1. prior_actual   — 직전 분기 실적 순발행
    2. prior_forecast — 같은 당기 구간에 대한 *이전* 공시 예측
    3. current        — 이번 공시의 당기(또는 근기) 예측

    Values = privately-held net marketable borrowing, $B.
    """
    est = event.get("estimates") or {}
    quarters = est.get("quarters") or []
    estimates = [q for q in quarters if q.get("kind") == "estimate"]
    actuals = [q for q in quarters if q.get("kind") == "actual"]

    current_q = estimates[0] if estimates else None
    prior_act = actuals[0] if actuals else None

    # Prior forecast for *same* period as current: earlier announce in S&U, else prior event
    prior_fc: Optional[Dict[str, Any]] = None
    if current_q:
        cur_period = current_q.get("period") or ""
        # Normalize July–September vs Jul - Sep
        cur_key = _period_key(cur_period)
        su_est = _su_estimates(event)
        same = []
        for r in su_est:
            if _period_key(r.get("period") or "") == cur_key:
                same.append(r)
        # sort by announcement date string; earlier = prior forecast
        if len(same) >= 2:
            same_sorted = sorted(same, key=lambda r: _parse_announce(r.get("announcement_date")))
            earliest, latest_su = same_sorted[0], same_sorted[-1]
            prior_fc = {
                "period": earliest.get("period"),
                "net_borrowing_bn": earliest.get("marketable_borrowing_bn"),
                "end_cash_balance_bn": earliest.get("end_cash_balance_bn"),
                "announcement_date": earliest.get("announcement_date"),
                "kind": "estimate",
            }
            if current_q.get("net_borrowing_bn") is None:
                current_q = {
                    **current_q,
                    "net_borrowing_bn": latest_su.get("marketable_borrowing_bn"),
                    "end_cash_balance_bn": latest_su.get("end_cash_balance_bn"),
                }
        elif len(same) == 1 and prior_event:
            # look in prior event estimates for same period
            for q in (prior_event.get("estimates") or {}).get("quarters") or []:
                if q.get("kind") == "estimate" and _period_key(q.get("period") or "") == cur_key:
                    prior_fc = q
                    break
            if prior_fc is None:
                for r in _su_estimates(prior_event):
                    if _period_key(r.get("period") or "") == cur_key:
                        prior_fc = {
                            "period": r.get("period"),
                            "net_borrowing_bn": r.get("marketable_borrowing_bn"),
                            "end_cash_balance_bn": r.get("end_cash_balance_bn"),
                            "announcement_date": r.get("announcement_date"),
                            "kind": "estimate",
                        }
                        break

    # Fallback prior_forecast from vs_prior on current
    if prior_fc is None and current_q and current_q.get("vs_prior_bn") is not None:
        prior_fc = {
            "period": current_q.get("period"),
            "net_borrowing_bn": float(current_q["net_borrowing_bn"]) - float(current_q["vs_prior_bn"]),
            "end_cash_balance_bn": None,
            "announcement_date": None,
            "kind": "estimate_implied",
            "note_ko": "당기 공시 vs_prior로부터 역산",
        }

    # If prior actual missing, try S&U
    if prior_act is None:
        acts = _su_actuals(event)
        if acts:
            a = acts[-1]
            prior_act = {
                "period": a.get("period"),
                "net_borrowing_bn": a.get("marketable_borrowing_bn"),
                "end_cash_balance_bn": a.get("end_cash_balance_bn"),
                "kind": "actual",
            }

    series: List[Dict[str, Any]] = []
    if prior_act and prior_act.get("net_borrowing_bn") is not None:
        series.append(
            {
                "id": "prior_actual",
                "label_ko": "전분기 실적",
                "period": prior_act.get("period"),
                "value": float(prior_act["net_borrowing_bn"]),
                "end_cash_bn": prior_act.get("end_cash_balance_bn"),
                "kind": "actual",
            }
        )
    if prior_fc and prior_fc.get("net_borrowing_bn") is not None:
        series.append(
            {
                "id": "prior_forecast",
                "label_ko": "직전 공시 예측",
                "period": prior_fc.get("period"),
                "value": float(prior_fc["net_borrowing_bn"]),
                "end_cash_bn": prior_fc.get("end_cash_balance_bn"),
                "announcement_date": prior_fc.get("announcement_date"),
                "kind": prior_fc.get("kind") or "estimate",
            }
        )
    if current_q and current_q.get("net_borrowing_bn") is not None:
        series.append(
            {
                "id": "current",
                "label_ko": "당기 공시",
                "period": current_q.get("period"),
                "value": float(current_q["net_borrowing_bn"]),
                "end_cash_bn": current_q.get("end_cash_balance_bn"),
                "vs_prior_bn": current_q.get("vs_prior_bn"),
                "announcement_date": _latest_announcement(event, current_q.get("period") or ""),
                "kind": "estimate",
            }
        )
    if current_q and len(estimates) >= 2:
        next_q = estimates[1]
        next_period = next_q.get("period") or ""
        if (
            next_q.get("net_borrowing_bn") is not None
            and _period_key(next_period) != _period_key(current_q.get("period") or "")
        ):
            series.append(
                {
                    "id": "next_estimate",
                    "label_ko": "다음 분기 예상",
                    "period": next_period,
                    "value": float(next_q["net_borrowing_bn"]),
                    "end_cash_bn": next_q.get("end_cash_balance_bn"),
                    "vs_prior_bn": next_q.get("vs_prior_bn"),
                    "announcement_date": _latest_announcement(event, next_period),
                    "kind": "estimate",
                }
            )

    return {
        "metric": "privately_held_net_marketable_bn",
        "unit": "bn_usd",
        "chart_type": "bar",
        "title_ko": "순발행 비교 (전분실적 · 직전예측 · 당기공시 · 다음분기)",
        "series": series,
        "table": [
            {
                "label_ko": s["label_ko"],
                "period": s.get("period"),
                "net_borrowing_bn": s["value"],
                "end_cash_bn": s.get("end_cash_bn"),
                "announcement_date": s.get("announcement_date"),
            }
            for s in series
        ],
        "note_ko": (
            "같은 발표에서 당기 공시와 다음 분기 예상을 나눴다. "
            "직전 공시 예측은 그 전 발표가 같은 분기에 적어 둔 값이다."
        ),
    }


def _latest_announcement(event: Dict[str, Any], period: str) -> Optional[str]:
    """Latest Sources & Uses date for this quarter. Same announcement can cover two quarters."""
    key = _period_key(period)
    dated = [
        r for r in _su_estimates(event)
        if _period_key(r.get("period") or "") == key and r.get("announcement_date")
    ]
    if not dated:
        return None
    return max(dated, key=lambda r: _parse_announce(r.get("announcement_date"))).get("announcement_date")


def _period_key(period: str) -> str:
    p = period.lower().replace("–", "-").replace("—", "-")
    p = p.replace("january", "jan").replace("february", "feb").replace("march", "mar")
    p = p.replace("april", "apr").replace("june", "jun").replace("july", "jul")
    p = p.replace("september", "sep").replace("october", "oct").replace("november", "nov").replace("december", "dec")
    p = "".join(ch for ch in p if ch.isalnum() or ch in "-")
    # Jul-Sep2026 / jan-mar2025
    return p.replace(" ", "")


def build_quarter_history(events: List[Dict[str, Any]], *, limit: int = 16) -> List[Dict[str, Any]]:
    """Chronological net-borrowing points from each event's primary estimate (for spark/line)."""
    pts = []
    for e in sorted(events, key=lambda x: (x.get("year") or 0, x.get("quarter") or 0)):
        est = (e.get("estimates") or {}).get("quarters") or []
        cur = next((q for q in est if q.get("kind") == "estimate"), None)
        if not cur:
            continue
        pts.append(
            {
                "event_id": e.get("id"),
                "period": cur.get("period"),
                "net_borrowing_bn": cur.get("net_borrowing_bn"),
                "end_cash_bn": cur.get("end_cash_balance_bn"),
            }
        )
    return pts[-limit:]


_PERIOD_END = re.compile(r"[\u2013\u2014-]\s*([A-Za-z]+)\s+(\d{4})\s*$")


def _period_end_date(period: Optional[str]) -> Optional[str]:
    """'October\u2013December 2022' -> '2022-12-31' (None when the period does not read that way)."""
    m = _PERIOD_END.search((period or "").strip())
    if not m:
        return None
    try:
        month = datetime.strptime(m.group(1)[:3], "%b").month
    except ValueError:
        return None
    year = int(m.group(2))
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def apply_real_history(ind: Dict[str, Any], rows: Optional[List[Dict[str, Any]]]) -> bool:
    """Give the QRA indicator's trend tab the real quarterly series.

    The pack builder seeds every indicator with a synthetic monthly walk around
    its base value; for qra_issuance that base was the sum of the fixture
    maturity bars (~1,410), so the trend tab drew 60 identical bars under a
    "live" badge while the headline said 739. The real series is the net
    borrowing Treasury announced for each quarter (history_net_borrowing),
    which is an announced estimate made at each refunding, not an outturn.

    Rows without a readable period end or a number are skipped, never filled.
    With no usable rows the trend is emptied rather than left synthetic.
    Returns True when a real series was written.
    """
    pts = []
    for r in rows or []:
        end = _period_end_date(r.get("period"))
        val = r.get("net_borrowing_bn")
        if end is None or not isinstance(val, (int, float)):
            continue
        pts.append((end, round(float(val), 1)))
    pts.sort()
    if not pts:
        ind["history"] = {}
        ind.pop("history_note_ko", None)
        return False
    series = {"dates": [d for d, _ in pts], "values": [v for _, v in pts]}
    ind["history"] = {"5y": series, "10y": series}  # the record starts in 2022; both windows hold all of it
    ind["history_note_ko"] = (
        f"분기별 순발행입니다 ({pts[0][0][:7]}~{pts[-1][0][:7]}, {len(pts)}개 분기, 분기말 날짜에 표시). "
        "각 분기 값은 재무부가 그 분기 재융자 발표 때 낸 예상치이고 실제 집행액이 아닙니다."
    )
    return True


def split_summary_ko(compare: Dict[str, Any], bill: Optional[str] = None, coupon: Optional[str] = None) -> Optional[str]:
    """One-line note for an announcement that covers this quarter and the next.

    Built from the compare block and the stances parsed out of that same
    release -- never a fixed string: the refresh script used to hardcode
    "T-bill 스탠스=maintain · 쿠폰 스탠스=change_bias" from the August 2026
    release, which would have been stamped onto every later announcement.
    """
    by_id = {s.get("id"): s for s in compare.get("series") or []}
    cur, nxt = by_id.get("current"), by_id.get("next_estimate")
    if not cur or not nxt:
        return None

    def money(series: Dict[str, Any]) -> str:
        text = f"순발행 {series['value']:.0f}B"
        if series.get("end_cash_bn") is not None:
            text += f", 기말현금 {float(series['end_cash_bn']):.0f}B"
        return text

    parts = [
        f"{cur.get('announcement_date') or '최근'} 발표. 당기 {cur.get('period')} {money(cur)}.",
        f"다음 분기 {nxt.get('period')} 예상 {money(nxt)}.",
    ]
    stances = [f"{label}={value}" for label, value in (("T-bill 스탠스", bill), ("쿠폰 스탠스", coupon)) if value]
    if stances:
        parts.append(" · ".join(stances))
    return " ".join(parts)
