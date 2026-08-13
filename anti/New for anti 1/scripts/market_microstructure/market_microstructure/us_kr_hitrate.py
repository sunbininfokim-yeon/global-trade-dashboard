"""Weekly-style hit-rate / recalibration report for US→KR alerts.

Uses return-bucket proxies (no historical option chains):
  downside alert day ≈ driver US close ≤ −2%
  then score next KR overnight open / open30m.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from market_microstructure.kr_open30m_backtest import _bucket_stats, run_open30m_backtest
from market_microstructure.us_kr_discovery import (
    _align_us_to_next_kr,
    _series_close,
    download_daily,
)


def _suggest_thresholds(bt: dict[str, Any]) -> dict[str, Any]:
    """Heuristic threshold suggestions from overnight hit rates."""
    down_hits = []
    up_hits = []
    for d in bt.get("per_driver") or []:
        oo = d.get("open_overnight") or {}
        du = oo.get("us_down") or {}
        uu = oo.get("us_up") or {}
        if du.get("n", 0) >= 10:
            down_hits.append(du.get("frac_neg"))
        if uu.get("n", 0) >= 10:
            up_hits.append(uu.get("frac_pos"))
    return {
        "downside_hit_rate_mean": None
        if not down_hits
        else round(float(np.mean(down_hits)), 4),
        "upside_hit_rate_mean": None if not up_hits else round(float(np.mean(up_hits)), 4),
        "suggest_keep_downside_emphasis": True
        if down_hits and float(np.mean(down_hits)) >= 0.55
        else False,
        "suggest_pc_vol_downside_floor": 1.1,
        "suggest_day_return_stress": 0.02,
        "note_ko": "옵션 레짐 히스토리 없이 수익률 버킷으로 제안. 월간 리뷰용.",
    }


def composite_stress_hitrate(
    *,
    drivers: list[str] | None = None,
    kr_yahoo: str = "000660.KS",
    period: str = "1y",
    stress_thr: float = -0.02,
) -> dict[str, Any]:
    """Hit-rate when ANY of the key drivers is ≤ stress_thr."""
    drivers = list(drivers or ["MU", "SOXL", "SMH", "NVDA"])
    tickers = drivers + [kr_yahoo]
    daily = download_daily(tickers, period=period)
    close = _series_close(daily, kr_yahoo).dropna()
    if isinstance(daily.columns, pd.MultiIndex) and kr_yahoo in daily.columns.get_level_values(0):
        open_ = daily[kr_yahoo]["Open"].dropna()
    else:
        open_ = daily["Open"]
    open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    r_open = ((open_ / close.shift(1)) - 1.0).dropna()

    us_rets = {}
    for u in drivers:
        try:
            us_rets[u] = _series_close(daily, u).dropna().pct_change().dropna()
        except Exception:  # noqa: BLE001
            continue

    # union of US days where min driver return ≤ thr
    frames = []
    for u, ur in us_rets.items():
        a = _align_us_to_next_kr(ur, r_open)
        if a.empty:
            continue
        a = a.copy()
        a["driver"] = u
        frames.append(a)
    if not frames:
        return {"n": 0}
    all_a = pd.concat(frames, ignore_index=True)
    # per us_day take worst driver
    worst = all_a.groupby("us_day", as_index=False).agg(
        r_us=("r_us", "min"), r_kr=("r_kr", "first")
    )
    alert = worst[worst["r_us"] <= stress_thr]
    baseline = _bucket_stats(worst["r_kr"], "all")
    cond = _bucket_stats(alert["r_kr"], "any_driver_down")
    return {
        "drivers": drivers,
        "stress_thr": stress_thr,
        "n_us_days": int(len(worst)),
        "n_alert_days": int(len(alert)),
        "baseline_open": baseline,
        "alert_open": cond,
        "lift_frac_neg": None
        if not baseline.get("n") or not cond.get("n")
        else round(float(cond["frac_neg"]) - float(baseline["frac_neg"]), 4),
    }


def build_hitrate_report(
    *,
    period: str = "1y",
    backtest_000660: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bt = backtest_000660 or run_open30m_backtest(period=period)
    bt_ss = run_open30m_backtest(kr_yahoo="005930.KS", kr_id="005930", period=period)
    composite = composite_stress_hitrate(period=period)
    return {
        "schema_version": "us-kr-hitrate-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "cadence": "weekly_manual",
        "period": period,
        "channel_summary_000660": bt.get("channel_summary"),
        "channel_summary_005930": bt_ss.get("channel_summary"),
        "composite_any_driver_down": composite,
        "recalibration_suggestions": _suggest_thresholds(bt),
        "disclaimer_ko": "프록시 백테스트. 투자 권유 아님. 주간 리포트용.",
    }
