"""Tier B: rolling US→KR correlation discovery.

Uses daily US close returns vs next KR session open / open30m returns.
quality=estimated — review before promoting to Tier A.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_US = [
    "MU",
    "NVDA",
    "AMD",
    "AMZN",
    "MSFT",
    "GOOGL",
    "META",
    "TSM",
    "AVGO",
    "ASML",
    "QCOM",
    "INTC",
    "SOXL",
    "SMH",
    "SOXX",
    "KORU",
    "EWY",
    "SPY",
    "QQQ",
]

DEFAULT_KR = {
    "000660.KS": "000660",
    "005930.KS": "005930",
    "^KS11": "KOSPI",
}


def _series_close(df: pd.DataFrame, ticker: str) -> pd.Series:
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance group_by=ticker → (ticker, OHLCV) or (OHLCV, ticker)
        if ticker in df.columns.get_level_values(0):
            sub = df[ticker]
            return sub["Close"] if "Close" in sub.columns else sub.iloc[:, 0]
        if "Close" in df.columns.get_level_values(0):
            return df["Close"][ticker]
    return df["Close"] if "Close" in df.columns else df.iloc[:, 0]


def download_daily(tickers: list[str], *, period: str = "1y") -> pd.DataFrame:
    import yfinance as yf

    return yf.download(
        tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )


def kr_open30m_returns(kr_yahoo: str, *, period: str = "60d") -> pd.Series:
    """(close of first 30m bar − prior daily close) / prior daily close.

    Yahoo KR bars are UTC; session open ≈ 00:00 UTC = 09:00 KST.
    """
    import yfinance as yf

    daily = yf.download(kr_yahoo, period=period, interval="1d", auto_adjust=True, progress=False)
    bars = yf.download(kr_yahoo, period=period, interval="30m", auto_adjust=True, progress=False)
    if daily.empty or bars.empty:
        return pd.Series(dtype=float)

    d_close = daily["Close"].dropna()
    if isinstance(d_close, pd.DataFrame):
        d_close = d_close.iloc[:, 0]
    d_close.index = pd.to_datetime(d_close.index).tz_localize(None).normalize()

    b = bars.copy()
    b.index = pd.to_datetime(b.index)
    if b.index.tz is not None:
        b.index = b.index.tz_convert("UTC")
    # First bar of each UTC calendar day ≈ KRX open block
    b["day"] = b.index.tz_localize(None).normalize() if b.index.tz is None else b.index.tz_convert("UTC").tz_localize(None).normalize()
    first = b.sort_index().groupby("day").head(1)
    c30 = first["Close"]
    if isinstance(c30, pd.DataFrame):
        c30 = c30.iloc[:, 0]
    c30.index = pd.to_datetime(first["day"].values)

    out = {}
    for day, px in c30.items():
        day = pd.Timestamp(day).normalize()
        # prior KR close = previous trading day close
        prev_days = d_close.index[d_close.index < day]
        if len(prev_days) == 0:
            continue
        prev = float(d_close.loc[prev_days[-1]])
        if prev == 0:
            continue
        out[day] = (float(px) - prev) / prev
    return pd.Series(out, dtype=float).sort_index()


def _align_us_to_next_kr(us_r: pd.Series, kr_r: pd.Series) -> pd.DataFrame:
    """Map US session date T → KR return on next KR trading day after T."""
    us_r = us_r.dropna().copy()
    kr_r = kr_r.dropna().copy()
    us_r.index = pd.to_datetime(us_r.index).tz_localize(None).normalize()
    kr_r.index = pd.to_datetime(kr_r.index).tz_localize(None).normalize()
    rows = []
    kr_days = list(kr_r.index)
    for us_day, ur in us_r.items():
        # next KR day strictly after US calendar day
        nxt = [d for d in kr_days if d > us_day]
        if not nxt:
            continue
        kd = nxt[0]
        # skip if gap > 5 calendar days (holiday stretch)
        if (kd - us_day).days > 5:
            continue
        rows.append({"us_day": us_day, "kr_day": kd, "r_us": float(ur), "r_kr": float(kr_r.loc[kd])})
    return pd.DataFrame(rows)


def _corr_pack(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) < 20:
        return {"n": len(df), "corr": None, "quality": "insufficient"}
    x = df["r_us"].to_numpy()
    y = df["r_kr"].to_numpy()
    corr = float(np.corrcoef(x, y)[0, 1])
    down = df[df["r_us"] <= -0.015]
    up = df[df["r_us"] >= 0.015]
    def _c(sub: pd.DataFrame) -> float | None:
        if len(sub) < 10:
            return None
        return float(np.corrcoef(sub["r_us"], sub["r_kr"])[0, 1])

    return {
        "n": int(len(df)),
        "corr": round(corr, 4),
        "corr_us_down": None if _c(down) is None else round(_c(down), 4),  # type: ignore[arg-type]
        "corr_us_up": None if _c(up) is None else round(_c(up), 4),  # type: ignore[arg-type]
        "n_us_down": int(len(down)),
        "n_us_up": int(len(up)),
        "quality": "estimated",
    }


def discover_edges(
    *,
    us_symbols: list[str] | None = None,
    kr_map: dict[str, str] | None = None,
    period: str = "1y",
    min_abs_corr: float = 0.25,
    min_abs_down_corr: float = 0.30,
) -> dict[str, Any]:
    us_symbols = list(us_symbols or DEFAULT_US)
    kr_map = dict(kr_map or DEFAULT_KR)

    all_tickers = us_symbols + list(kr_map.keys())
    daily = download_daily(all_tickers, period=period)

    # daily close returns for US
    us_rets: dict[str, pd.Series] = {}
    for u in us_symbols:
        try:
            s = _series_close(daily, u).dropna().pct_change().dropna()
            us_rets[u] = s
        except Exception:  # noqa: BLE001
            continue

    # KR open (daily Open vs prior Close) + open30m
    edges: list[dict[str, Any]] = []
    kr_stats: dict[str, Any] = {}
    for ky, kid in kr_map.items():
        try:
            close = _series_close(daily, ky).dropna()
            # open from same download
            if isinstance(daily.columns, pd.MultiIndex) and ky in daily.columns.get_level_values(0):
                open_ = daily[ky]["Open"].dropna()
            else:
                open_ = daily["Open"].dropna() if "Open" in daily.columns else close
            open_ = open_.copy()
            open_.index = pd.to_datetime(open_.index).tz_localize(None).normalize()
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            # overnight open return: Open_t / Close_{t-1} - 1
            prev_c = close.shift(1)
            r_open = ((open_ / prev_c) - 1.0).dropna()
            r_30 = kr_open30m_returns(ky, period="60d" if period.endswith("y") else period)
            kr_stats[kid] = {
                "yahoo": ky,
                "n_open": int(len(r_open)),
                "n_open30m": int(len(r_30)),
            }
        except Exception as e:  # noqa: BLE001
            kr_stats[kid] = {"error": str(e)}
            continue

        for u, ur in us_rets.items():
            pack_open = _corr_pack(_align_us_to_next_kr(ur, r_open))
            pack_30 = _corr_pack(_align_us_to_next_kr(ur, r_30)) if len(r_30) else {"n": 0, "corr": None}
            # score: prefer down-day corr then overall
            candidates = [
                abs(pack_open.get("corr_us_down") or 0),
                abs(pack_open.get("corr") or 0),
                abs(pack_30.get("corr_us_down") or 0),
                abs(pack_30.get("corr") or 0),
            ]
            score = max(candidates)
            promote = (
                abs(pack_open.get("corr") or 0) >= min_abs_corr
                or abs(pack_open.get("corr_us_down") or 0) >= min_abs_down_corr
                or abs(pack_30.get("corr") or 0) >= min_abs_corr
                or abs(pack_30.get("corr_us_down") or 0) >= min_abs_down_corr
            )
            if not promote:
                continue
            edges.append(
                {
                    "id": f"disc_{u.lower()}_{kid.lower()}",
                    "us": u,
                    "kr": kid,
                    "edge_type": "discovered_corr",
                    "weight": round(min(0.95, 0.35 + score), 3),
                    "quality": "estimated",
                    "tier": "B",
                    "corr_us_close_kr_open": pack_open,
                    "corr_us_close_kr_open30m": pack_30,
                    "score": round(score, 4),
                    "note_ko": "통계 발견. Tier A 편입 전 리뷰 필요.",
                }
            )

    edges.sort(key=lambda e: e.get("score") or 0, reverse=True)
    return {
        "schema_version": "us-kr-discovered-edges-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "min_abs_corr": min_abs_corr,
        "min_abs_down_corr": min_abs_down_corr,
        "us_universe": us_symbols,
        "kr_universe": list(kr_map.values()),
        "kr_stats": kr_stats,
        "n_edges": len(edges),
        "discovered_edges": edges,
        "disclaimer_ko": "추정 corr. 인과·투자 권유 아님.",
        "source": "yfinance daily + 30m",
    }
