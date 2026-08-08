"""Map daily investor nets onto price bins (public-data proxy).

True tick-level “이 호가에서 누가 샀다” is not free (KRX 분단위 투자자/체결).
This module attributes each day's 개인/외국인/기관 순매수 to that day's OHLC
price zone — the usual public approximation for “어느 가격대에서 누가 샀나”.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

ACTORS = ("retail", "foreign", "institution")
ACTOR_KO = {"retail": "개인", "foreign": "외국인", "institution": "기관"}


def parse_signed_qty(s: Any) -> int | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    t = str(s).strip().replace(",", "").replace("+", "")
    if t in {"", "-", "N/A"}:
        return None
    return int(t)


def parse_close_krw(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(",", "")
    if not t:
        return None
    return float(t)


def fetch_naver_investor_trend(ticker: str, *, page_size: int = 60) -> list[dict[str, Any]]:
    import requests

    url = f"https://m.stock.naver.com/api/stock/{ticker}/trend"
    r = requests.get(
        url,
        params={"pageSize": page_size},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"unexpected trend payload for {ticker}: {type(data)}")
    return data


def fetch_ohlc_panel(ticker: str, start: str) -> pd.DataFrame:
    """Daily OHLC from FinanceDataReader (index=date)."""
    import FinanceDataReader as fdr

    df = fdr.DataReader(ticker, start)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    out.index = pd.to_datetime(out.index).normalize()
    return out[["open", "high", "low", "close", "volume"]].sort_index()


def trend_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    recs = []
    for row in rows:
        biz = str(row.get("bizdate") or "")
        if len(biz) != 8:
            continue
        dt = pd.Timestamp(f"{biz[:4]}-{biz[4:6]}-{biz[6:8]}")
        recs.append(
            {
                "date": dt,
                "close_naver": parse_close_krw(row.get("closePrice")),
                "retail_net_shares": parse_signed_qty(row.get("individualPureBuyQuant")),
                "foreign_net_shares": parse_signed_qty(row.get("foreignerPureBuyQuant")),
                "institution_net_shares": parse_signed_qty(row.get("organPureBuyQuant")),
                "volume": parse_signed_qty(row.get("accumulatedTradingVolume")),
            }
        )
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs).set_index("date").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _bin_edges(prices: np.ndarray, n_bins: int) -> np.ndarray:
    lo = float(np.nanmin(prices))
    hi = float(np.nanmax(prices))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.array([lo, lo + 1.0], dtype=float)
    return np.linspace(lo, hi, n_bins + 1)


def _empty_bins(edges: np.ndarray) -> list[dict[str, Any]]:
    bins = []
    for i in range(len(edges) - 1):
        bins.append(
            {
                "bin": i,
                "price_lo": round(float(edges[i]), 2),
                "price_hi": round(float(edges[i + 1]), 2),
                "price_mid": round(float((edges[i] + edges[i + 1]) / 2), 2),
                "n_days": 0,
                "retail_net_shares": 0,
                "foreign_net_shares": 0,
                "institution_net_shares": 0,
            }
        )
    return bins


def aggregate_by_close_bins(joined: pd.DataFrame, *, n_bins: int = 12) -> list[dict[str, Any]]:
    """Attribute each day's full net to that day's close bin."""
    px = joined["close"].astype(float).to_numpy()
    edges = _bin_edges(px, n_bins)
    bins = _empty_bins(edges)
    idx = np.clip(np.digitize(px, edges[1:-1], right=False), 0, len(bins) - 1)
    for i, (_, row) in enumerate(joined.iterrows()):
        b = bins[int(idx[i])]
        b["n_days"] += 1
        for a in ACTORS:
            key = f"{a}_net_shares"
            v = row.get(key)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                b[key] += int(v)
    return bins


def aggregate_by_range_bins(joined: pd.DataFrame, *, n_bins: int = 12) -> list[dict[str, Any]]:
    """Spread each day's net uniformly across OHLC range bins (volume-profile style)."""
    lo = float(joined["low"].min())
    hi = float(joined["high"].max())
    edges = _bin_edges(np.array([lo, hi], dtype=float), n_bins)
    bins = _empty_bins(edges)
    for _, row in joined.iterrows():
        day_lo = float(row["low"])
        day_hi = float(row["high"])
        if not np.isfinite(day_lo) or not np.isfinite(day_hi) or day_hi < day_lo:
            continue
        # bins overlapping [day_lo, day_hi]
        touched = []
        for i, b in enumerate(bins):
            if b["price_hi"] < day_lo or b["price_lo"] > day_hi:
                continue
            overlap = min(b["price_hi"], day_hi) - max(b["price_lo"], day_lo)
            if overlap > 0:
                touched.append((i, overlap))
        total = sum(w for _, w in touched) or 1.0
        for i, w in touched:
            frac = w / total
            bins[i]["n_days"] += 1
            for a in ACTORS:
                key = f"{a}_net_shares"
                v = row.get(key)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                bins[i][key] += int(round(int(v) * frac))
    return bins


def _top_zone(bins: list[dict[str, Any]], actor: str, *, side: str = "buy") -> dict[str, Any] | None:
    key = f"{actor}_net_shares"
    scored = []
    for b in bins:
        v = int(b.get(key) or 0)
        if side == "buy" and v > 0:
            scored.append((v, b))
        elif side == "sell" and v < 0:
            scored.append((-v, b))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    v, b = scored[0]
    return {
        "actor": actor,
        "actor_ko": ACTOR_KO[actor],
        "side": side,
        "net_shares": int(b[key]),
        "price_lo": b["price_lo"],
        "price_hi": b["price_hi"],
        "price_mid": b["price_mid"],
        "n_days": b["n_days"],
        "label_ko": (
            f"{ACTOR_KO[actor]} 순매수 집중 {int(b['price_lo']):,}–{int(b['price_hi']):,}원"
            if side == "buy"
            else f"{ACTOR_KO[actor]} 순매도 집중 {int(b['price_lo']):,}–{int(b['price_hi']):,}원"
        ),
    }


def build_ticker_levels(
    ticker: str,
    *,
    page_size: int = 60,
    n_bins: int = 12,
    label_ko: str | None = None,
) -> dict[str, Any]:
    trend = fetch_naver_investor_trend(ticker, page_size=page_size)
    inv = trend_to_frame(trend)
    if inv.empty:
        return {
            "ticker": ticker,
            "label_ko": label_ko,
            "quality": "missing",
            "note_ko": "네이버 trend 수급이 비어 있음",
        }

    start = (inv.index.min() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    ohlc = fetch_ohlc_panel(ticker, start)
    # Avoid volume name clash with Naver trend volume.
    ohlc = ohlc.rename(columns={"volume": "volume_fdr"})
    out = inv.join(ohlc, how="inner")
    if "close" not in out.columns or out["close"].isna().all():
        out["close"] = out["close_naver"]
        out["high"] = out["close_naver"]
        out["low"] = out["close_naver"]
        out["open"] = out["close_naver"]
    else:
        out["close"] = out["close"].fillna(out["close_naver"])
        out["high"] = out["high"].fillna(out["close"])
        out["low"] = out["low"].fillna(out["close"])
        out["open"] = out["open"].fillna(out["close"])

    if "volume_fdr" in out.columns:
        out["volume"] = out["volume"].fillna(out["volume_fdr"])

    joined = out.dropna(subset=["close", "retail_net_shares", "foreign_net_shares"])
    if joined.empty:
        return {
            "ticker": ticker,
            "label_ko": label_ko,
            "quality": "missing",
            "note_ko": "OHLC·수급 조인 실패",
        }

    close_bins = aggregate_by_close_bins(joined, n_bins=n_bins)
    range_bins = aggregate_by_range_bins(joined, n_bins=n_bins)

    days = []
    for dt, row in joined.iterrows():
        days.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                "close": float(row["close"]),
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "retail_net_shares": int(row["retail_net_shares"]),
                "foreign_net_shares": int(row["foreign_net_shares"]),
                "institution_net_shares": int(row["institution_net_shares"])
                if pd.notna(row.get("institution_net_shares"))
                else None,
            }
        )

    highlights = {
        "close_bin": {
            a: {
                "buy": _top_zone(close_bins, a, side="buy"),
                "sell": _top_zone(close_bins, a, side="sell"),
            }
            for a in ACTORS
        },
        "range_bin": {
            a: {
                "buy": _top_zone(range_bins, a, side="buy"),
                "sell": _top_zone(range_bins, a, side="sell"),
            }
            for a in ACTORS
        },
    }

    return {
        "ticker": ticker,
        "label_ko": label_ko,
        "as_of": days[-1]["date"] if days else None,
        "n_days": len(days),
        "date_start": days[0]["date"] if days else None,
        "date_end": days[-1]["date"] if days else None,
        "unit": "shares (순매수; 음수=순매도)",
        "quality": "estimated",
        "method_ko": (
            "일별 개인/외국인/기관 순매수(네이버)를 그날 종가·고저 구간 가격 빈에 귀속. "
            "틱/호가 단위 ‘이 가격에서 누가’가 아님."
        ),
        "source": [
            "https://m.stock.naver.com/api/stock/{ticker}/trend?pageSize=",
            "FinanceDataReader OHLC",
        ],
        "days": days,
        "bins_by_close": close_bins,
        "bins_by_range": range_bins,
        "highlights": highlights,
        "disclaimer_ko": "투자 권유 아님. 공개 일별 수급×가격 근사.",
    }


def build_investor_price_levels_report(
    tickers: list[tuple[str, str]] | None = None,
    *,
    page_size: int = 60,
    n_bins: int = 12,
) -> dict[str, Any]:
    tickers = tickers or [("000660", "SK하이닉스"), ("005930", "삼성전자")]
    names: dict[str, Any] = {}
    errors: list[str] = []
    for code, label in tickers:
        try:
            names[code] = build_ticker_levels(
                code, page_size=page_size, n_bins=n_bins, label_ko=label
            )
        except Exception as e:  # noqa: BLE001 — surface per-ticker
            errors.append(f"{code}: {type(e).__name__}: {e}")
            names[code] = {
                "ticker": code,
                "label_ko": label,
                "quality": "missing",
                "error": f"{type(e).__name__}: {e}",
            }

    return {
        "schema_version": "investor-price-levels-v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "n_bins": n_bins,
        "page_size": page_size,
        "tickers": names,
        "ui_hint_ko": (
            "종가 빈(bins_by_close) 또는 고저 분산(bins_by_range) 막대 + "
            "highlights.*.buy.label_ko 를 박스에 표시. quality=estimated."
        ),
        "cannot_do_ko": [
            "체결/호가 단위로 개인·외인·기관을 나눈 진짜 가격대 매집도 (유료)",
            "장중 1분 투자자별 실적 (KRX 유료 상품)",
        ],
        "errors": errors,
        "disclaimer_ko": "투자 권유 아님. 일별 순매수×가격 빈 근사.",
    }


def markdown_investor_price_levels(rep: dict[str, Any]) -> str:
    lines = [
        f"# Investor × price levels — {rep.get('as_of')}",
        "",
        rep.get("disclaimer_ko") or "",
        "",
        "일별 수급을 가격 빈에 귀속한 **추정**. 틱 단위 아님.",
        "",
    ]
    for code, block in (rep.get("tickers") or {}).items():
        lines.append(f"## {block.get('label_ko') or code} (`{code}`)")
        lines.append("")
        if block.get("quality") == "missing":
            lines.append(f"- missing: {block.get('error') or block.get('note_ko')}")
            lines.append("")
            continue
        lines.append(
            f"- 표본 {block.get('n_days')}일 ({block.get('date_start')} → {block.get('date_end')}) "
            f"· quality=`{block.get('quality')}`"
        )
        hi = ((block.get("highlights") or {}).get("close_bin") or {})
        for a in ACTORS:
            buy = (hi.get(a) or {}).get("buy")
            sell = (hi.get(a) or {}).get("sell")
            if buy:
                lines.append(f"- {buy['label_ko']} ({buy['net_shares']:+,}주)")
            if sell:
                lines.append(f"- {sell['label_ko']} ({sell['net_shares']:+,}주)")
        lines.append("")
        lines.append("| 가격대(종가빈) | 개인 | 외국인 | 기관 | n |")
        lines.append("|---------------|-----:|-------:|-----:|--:|")
        for b in block.get("bins_by_close") or []:
            lines.append(
                f"| {int(b['price_lo']):,}–{int(b['price_hi']):,} | "
                f"{b['retail_net_shares']:+,} | {b['foreign_net_shares']:+,} | "
                f"{b['institution_net_shares']:+,} | {b['n_days']} |"
            )
        lines.append("")
    if rep.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for e in rep["errors"]:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines)
