"""KR open30m conditional backtest vs US return stress proxies.

Without historical option chains, use US close return buckets (and VIX Δ)
as regime proxies. Scores channels separately (no mixing).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from market_microstructure.us_kr_discovery import (
    _align_us_to_next_kr,
    _series_close,
    download_daily,
    kr_open30m_returns,
)


def _pct(series: pd.Series, q: float) -> float | None:
    s = series.dropna()
    if len(s) < 5:
        return None
    return float(np.quantile(s.to_numpy(), q))


def _bucket_stats(r: pd.Series, label: str) -> dict[str, Any]:
    s = r.dropna()
    if len(s) == 0:
        return {"label": label, "n": 0}
    arr = s.to_numpy()
    return {
        "label": label,
        "n": int(len(s)),
        "mean": round(float(arr.mean()), 6),
        "median": round(float(np.median(arr)), 6),
        "p10": round(_pct(s, 0.10) or 0.0, 6),
        "p90": round(_pct(s, 0.90) or 0.0, 6),
        "frac_neg": round(float((arr < 0).mean()), 4),
        "frac_pos": round(float((arr > 0).mean()), 4),
    }


def run_open30m_backtest(
    *,
    us_drivers: list[str] | None = None,
    kr_yahoo: str = "000660.KS",
    kr_id: str = "000660",
    period: str = "1y",
    down_thr: float = -0.02,
    up_thr: float = 0.02,
) -> dict[str, Any]:
    """Condition KR open30m on prior US session stress for listed drivers."""
    us_drivers = list(us_drivers or ["MU", "NVDA", "SOXL", "SMH", "AMZN"])
    tickers = us_drivers + [kr_yahoo, "^VIX"]
    daily = download_daily(tickers, period=period)

    r30 = kr_open30m_returns(kr_yahoo, period="60d")
    # also overnight open as longer history backup
    close = _series_close(daily, kr_yahoo).dropna()
    if isinstance(daily.columns, pd.MultiIndex) and kr_yahoo in daily.columns.get_level_values(0):
        open_ = daily[kr_yahoo]["Open"].dropna()
    else:
        open_ = daily["Open"]
    open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    r_open = ((open_ / close.shift(1)) - 1.0).dropna()

    try:
        vix = _series_close(daily, "^VIX").dropna().pct_change().dropna()
    except Exception:  # noqa: BLE001
        vix = pd.Series(dtype=float)

    channels: dict[str, Any] = {}
    per_driver: list[dict[str, Any]] = []

    for u in us_drivers:
        try:
            ur = _series_close(daily, u).dropna().pct_change().dropna()
        except Exception as e:  # noqa: BLE001
            per_driver.append({"us": u, "error": str(e)})
            continue

        aligned_30 = _align_us_to_next_kr(ur, r30)
        aligned_open = _align_us_to_next_kr(ur, r_open)

        def _cond(df: pd.DataFrame, mask) -> pd.Series:
            if df.empty:
                return pd.Series(dtype=float)
            return df.loc[mask, "r_kr"]

        down_m = aligned_30["r_us"] <= down_thr if not aligned_30.empty else pd.Series(dtype=bool)
        up_m = aligned_30["r_us"] >= up_thr if not aligned_30.empty else pd.Series(dtype=bool)
        quiet_m = aligned_30["r_us"].abs() < 0.01 if not aligned_30.empty else pd.Series(dtype=bool)

        row = {
            "us": u,
            "kr": kr_id,
            "open30m": {
                "baseline": _bucket_stats(aligned_30["r_kr"] if not aligned_30.empty else pd.Series(dtype=float), "all"),
                "us_down": _bucket_stats(_cond(aligned_30, down_m), "us_down"),
                "us_up": _bucket_stats(_cond(aligned_30, up_m), "us_up"),
                "us_quiet": _bucket_stats(_cond(aligned_30, quiet_m), "us_quiet"),
                "n_aligned": int(len(aligned_30)),
            },
            "open_overnight": {
                "baseline": _bucket_stats(aligned_open["r_kr"] if not aligned_open.empty else pd.Series(dtype=float), "all"),
                "us_down": _bucket_stats(
                    _cond(aligned_open, aligned_open["r_us"] <= down_thr) if not aligned_open.empty else pd.Series(dtype=float),
                    "us_down",
                ),
                "us_up": _bucket_stats(
                    _cond(aligned_open, aligned_open["r_us"] >= up_thr) if not aligned_open.empty else pd.Series(dtype=float),
                    "us_up",
                ),
                "n_aligned": int(len(aligned_open)),
            },
            "proxy_note_ko": "옵션 레짐 대신 US 종가 수익률 버킷(±2%).",
        }
        per_driver.append(row)

        # accumulate channel hit-rates using overnight (longer n) for headline
        for ch, key in (("downside", "us_down"), ("upside", "us_up")):
            st = row["open_overnight"][key]
            channels.setdefault(ch, {"samples": [], "drivers": []})
            if st.get("n", 0) >= 5:
                channels[ch]["samples"].append(st)
                channels[ch]["drivers"].append(u)

    # vol_up proxy: VIX up day
    vol_block: dict[str, Any] = {"quality": "missing"}
    if len(vix) and len(r_open):
        a = _align_us_to_next_kr(vix, r_open)
        if not a.empty:
            vol_up = a[a["r_us"] >= 0.05]
            vol_block = {
                "proxy": "VIX_day_return>=5%",
                "open_overnight": {
                    "baseline": _bucket_stats(a["r_kr"], "all"),
                    "vix_up": _bucket_stats(vol_up["r_kr"], "vix_up"),
                },
                "quality": "estimated",
            }

    def _summarize(ch: str) -> dict[str, Any]:
        samples = channels.get(ch, {}).get("samples") or []
        if not samples:
            return {"level": "n/a", "n": 0}
        # mean of means / frac_neg
        means = [s["mean"] for s in samples if s.get("mean") is not None]
        fracs = [s["frac_neg"] if ch == "downside" else s.get("frac_pos", 0) for s in samples]
        return {
            "n_driver_buckets": len(samples),
            "drivers": channels[ch]["drivers"],
            "mean_of_means": round(float(np.mean(means)), 6) if means else None,
            "hit_rate_mean": round(float(np.mean(fracs)), 4) if fracs else None,
            "note_ko": "하방=익일 KR open R<0 비율 평균; 상방=R>0 비율 평균",
        }

    return {
        "schema_version": "us-kr-open30m-backtest-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kr": kr_id,
        "kr_yahoo": kr_yahoo,
        "period": period,
        "down_thr": down_thr,
        "up_thr": up_thr,
        "channel_summary": {
            "downside": _summarize("downside"),
            "upside": _summarize("upside"),
            "vol_up": vol_block,
        },
        "per_driver": per_driver,
        "open30m_note_ko": "Yahoo 30분봉은 ~60일로 짧음. 장기는 overnight open으로 보완.",
        "disclaimer_ko": "백테스트 추정. 투자 권유 아님.",
        "source": "yfinance",
    }
