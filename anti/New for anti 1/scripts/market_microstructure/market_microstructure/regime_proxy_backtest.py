"""Historical US regime-proxy → KR open backtest (options history unavailable).

Labels each US session with proxy regimes from returns + VIX, then measures
next KR overnight open / open30m — channels scored separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_microstructure.kr_open30m_backtest import _bucket_stats
from market_microstructure.us_kr_discovery import (
    _align_us_to_next_kr,
    _series_close,
    download_daily,
    kr_open30m_returns,
)


def _proxy_regimes(day_r: float, vix_r: float | None) -> list[str]:
    regs: list[str] = []
    if day_r <= -0.02:
        regs.append("gap_down_stress")
        regs.append("downside_put_bid")  # proxy: down day ≈ put-heavy stress
    if day_r >= 0.02:
        regs.append("upside_call_bid")
    if vix_r is not None and vix_r >= 0.05 and abs(day_r) < 0.015:
        regs.append("vol_long_straddle")
    if vix_r is not None and vix_r <= -0.05 and abs(day_r) < 0.01:
        regs.append("vol_short_strangle")
    if not regs:
        regs.append("quiet")
    return regs


def _channel_for_regimes(regs: list[str]) -> str:
    if "gap_down_stress" in regs or "downside_put_bid" in regs:
        return "downside"
    if "upside_call_bid" in regs:
        return "upside"
    if "vol_long_straddle" in regs:
        return "vol_up"
    if "vol_short_strangle" in regs:
        return "vol_down"
    return "quiet"


def run_regime_proxy_backtest(
    *,
    drivers: list[str] | None = None,
    kr_yahoo: str = "000660.KS",
    kr_id: str = "000660",
    period: str = "1y",
) -> dict[str, Any]:
    drivers = list(drivers or ["MU", "NVDA", "SOXL", "SMH", "AMZN"])
    tickers = drivers + [kr_yahoo, "^VIX"]
    daily = download_daily(tickers, period=period)

    close = _series_close(daily, kr_yahoo).dropna()
    if isinstance(daily.columns, pd.MultiIndex) and kr_yahoo in daily.columns.get_level_values(0):
        open_ = daily[kr_yahoo]["Open"].dropna()
    else:
        open_ = daily["Open"]
    open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    r_open = ((open_ / close.shift(1)) - 1.0).dropna()
    r30 = kr_open30m_returns(kr_yahoo, period="60d")

    try:
        vix = _series_close(daily, "^VIX").dropna().pct_change()
    except Exception:  # noqa: BLE001
        vix = pd.Series(dtype=float)

    by_channel: dict[str, list[float]] = {
        "downside": [],
        "upside": [],
        "vol_up": [],
        "vol_down": [],
        "quiet": [],
    }
    by_channel_30: dict[str, list[float]] = {k: [] for k in by_channel}
    per_driver: list[dict[str, Any]] = []

    for u in drivers:
        try:
            ur = _series_close(daily, u).dropna().pct_change().dropna()
        except Exception as e:  # noqa: BLE001
            per_driver.append({"us": u, "error": str(e)})
            continue
        aligned = _align_us_to_next_kr(ur, r_open)
        a30 = _align_us_to_next_kr(ur, r30) if len(r30) else pd.DataFrame()
        rows = []
        for _, row in aligned.iterrows():
            us_day = pd.Timestamp(row["us_day"]).normalize()
            vr = float(vix.loc[us_day]) if us_day in vix.index else None
            regs = _proxy_regimes(float(row["r_us"]), vr)
            ch = _channel_for_regimes(regs)
            by_channel[ch].append(float(row["r_kr"]))
            rows.append({"channel": ch, "regimes": regs, "r_kr": float(row["r_kr"])})
        if not a30.empty:
            for _, row in a30.iterrows():
                us_day = pd.Timestamp(row["us_day"]).normalize()
                vr = float(vix.loc[us_day]) if us_day in vix.index else None
                ch = _channel_for_regimes(_proxy_regimes(float(row["r_us"]), vr))
                by_channel_30[ch].append(float(row["r_kr"]))
        # per-driver channel stats (overnight)
        ch_stats = {}
        for ch in ("downside", "upside", "vol_up", "vol_down"):
            ch_stats[ch] = _bucket_stats(
                pd.Series([r["r_kr"] for r in rows if r["channel"] == ch]), ch
            )
        per_driver.append(
            {
                "us": u,
                "kr": kr_id,
                "n": len(rows),
                "channels_overnight": ch_stats,
            }
        )

    summary = {}
    for ch, vals in by_channel.items():
        summary[ch] = {
            "overnight": _bucket_stats(pd.Series(vals), ch),
            "open30m": _bucket_stats(pd.Series(by_channel_30.get(ch) or []), ch),
        }

    return {
        "schema_version": "us-kr-regime-proxy-backtest-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kr": kr_id,
        "period": period,
        "proxy_note_ko": (
            "옵션 체인 히스토리 없음 → US 수익률±2% + VIX±5%로 레짐 프록시. "
            "공개 옵션 EOD 히스토리 확보 시 교체."
        ),
        "channel_summary": summary,
        "per_driver": per_driver,
        "disclaimer_ko": "프록시 백테스트. 투자 권유 아님.",
        "source": "yfinance",
    }
