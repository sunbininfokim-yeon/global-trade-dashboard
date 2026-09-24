"""Build prior-actual / prior-forecast / current compare bars for UI."""

from __future__ import annotations

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
