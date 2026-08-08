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


def _empty_bins(edges: np.ndarray, *, value_unit: str = "shares") -> list[dict[str, Any]]:
    bins = []
    for i in range(len(edges) - 1):
        row: dict[str, Any] = {
            "bin": i,
            "price_lo": round(float(edges[i]), 2),
            "price_hi": round(float(edges[i + 1]), 2),
            "price_mid": round(float((edges[i] + edges[i + 1]) / 2), 2),
            "n_days": 0,
            "retail_net_shares": 0,
            "foreign_net_shares": 0,
            "institution_net_shares": 0,
            "retail_net_krw": 0,
            "foreign_net_krw": 0,
            "institution_net_krw": 0,
            "value_unit": value_unit,
        }
        bins.append(row)
    return bins


def aggregate_by_close_bins(joined: pd.DataFrame, *, n_bins: int = 12) -> list[dict[str, Any]]:
    """Attribute each day's full net to that day's close bin (shares + KRW≈shares×close)."""
    px = joined["close"].astype(float).to_numpy()
    edges = _bin_edges(px, n_bins)
    bins = _empty_bins(edges)
    idx = np.clip(np.digitize(px, edges[1:-1], right=False), 0, len(bins) - 1)
    for i, (_, row) in enumerate(joined.iterrows()):
        b = bins[int(idx[i])]
        b["n_days"] += 1
        close = float(row["close"])
        for a in ACTORS:
            key = f"{a}_net_shares"
            v = row.get(key)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                iv = int(v)
                b[key] += iv
                b[f"{a}_net_krw"] += int(round(iv * close))
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
        close = float(row["close"])
        if not np.isfinite(day_lo) or not np.isfinite(day_hi) or day_hi < day_lo:
            continue
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
                iv = int(round(int(v) * frac))
                bins[i][key] += iv
                bins[i][f"{a}_net_krw"] += int(round(iv * close))
    return bins


def _top_zone(
    bins: list[dict[str, Any]],
    actor: str,
    *,
    side: str = "buy",
    metric: str = "shares",
    unit_label: str = "원",
) -> dict[str, Any] | None:
    key = f"{actor}_net_shares" if metric == "shares" else f"{actor}_net_krw"
    # index market flows use eok stored in *_net_krw field with value_unit=eok — handled separately
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
    _, b = scored[0]
    lo, hi = b["price_lo"], b["price_hi"]
    net = int(b[key])
    if metric == "shares":
        qty = f"{net:+,}주"
        label_range = f"{int(lo):,}–{int(hi):,}{unit_label}"
    else:
        qty = f"{net:+,}원"
        label_range = f"{int(lo):,}–{int(hi):,}{unit_label}"
    return {
        "actor": actor,
        "actor_ko": ACTOR_KO[actor],
        "side": side,
        "metric": metric,
        "net_shares": int(b.get(f"{actor}_net_shares") or 0),
        "net_krw": int(b.get(f"{actor}_net_krw") or 0),
        "net": net,
        "price_lo": lo,
        "price_hi": hi,
        "price_mid": b["price_mid"],
        "n_days": b["n_days"],
        "label_ko": (
            f"{ACTOR_KO[actor]} 순매수 집중 {label_range} ({qty})"
            if side == "buy"
            else f"{ACTOR_KO[actor]} 순매도 집중 {label_range} ({qty})"
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
        close = float(row["close"])
        retail = int(row["retail_net_shares"])
        foreign = int(row["foreign_net_shares"])
        inst = (
            int(row["institution_net_shares"])
            if pd.notna(row.get("institution_net_shares"))
            else None
        )
        days.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                "close": close,
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "retail_net_shares": retail,
                "foreign_net_shares": foreign,
                "institution_net_shares": inst,
                "retail_net_krw": int(round(retail * close)),
                "foreign_net_krw": int(round(foreign * close)),
                "institution_net_krw": None if inst is None else int(round(inst * close)),
            }
        )

    highlights = {
        "close_bin": {
            a: {
                "buy": _top_zone(close_bins, a, side="buy", metric="shares"),
                "sell": _top_zone(close_bins, a, side="sell", metric="shares"),
                "buy_krw": _top_zone(close_bins, a, side="buy", metric="krw"),
                "sell_krw": _top_zone(close_bins, a, side="sell", metric="krw"),
            }
            for a in ACTORS
        },
        "range_bin": {
            a: {
                "buy": _top_zone(range_bins, a, side="buy", metric="shares"),
                "sell": _top_zone(range_bins, a, side="sell", metric="shares"),
            }
            for a in ACTORS
        },
    }

    latest = days[-1] if days else None
    return {
        "ticker": ticker,
        "label_ko": label_ko,
        "as_of": latest["date"] if latest else None,
        "n_days": len(days),
        "date_start": days[0]["date"] if days else None,
        "date_end": days[-1]["date"] if days else None,
        "unit": "shares + KRW(≈ shares × that-day close)",
        "quality": "estimated",
        "method_ko": (
            "인포맥스/증권사 ‘가격대별 주체 순매수 분포’와 같은 공개 근사: "
            "일별 개인/외국인/기관 순매수(네이버)를 그날 종가 빈에 귀속. "
            "틱/호가 단위가 아님. KRW=주수×당일종가."
        ),
        "source": [
            "https://m.stock.naver.com/api/stock/{ticker}/trend?pageSize=",
            "FinanceDataReader OHLC",
        ],
        "latest_close_row": latest,
        "days": days,
        "bins_by_close": close_bins,
        "bins_by_range": range_bins,
        "highlights": highlights,
        "disclaimer_ko": "투자 권유 아님. 공개 일별 수급×가격 근사.",
    }


def default_kospi_universe(*, top_n: int = 10) -> list[tuple[str, str]]:
    """KOSPI ordinary shares by Marcap (skip 우선주). Live listing."""
    import FinanceDataReader as fdr

    kospi = fdr.StockListing("KOSPI")
    if kospi is None or kospi.empty:
        return [("000660", "SK하이닉스"), ("005930", "삼성전자")]
    df = kospi.dropna(subset=["Marcap", "Code", "Name"]).copy()
    names = df["Name"].astype(str)
    df = df[~names.str.endswith("우") & ~names.str.contains("우선", na=False)]
    df = df.sort_values("Marcap", ascending=False).head(int(top_n))
    out: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        out.append((str(row["Code"]).zfill(6), str(row["Name"])))
    return out or [("000660", "SK하이닉스"), ("005930", "삼성전자")]


def high_vol_kospi_universe(
    *,
    top_n: int = 10,
    pool: int = 40,
    lookback_days: int = 40,
) -> list[tuple[str, str]]:
    """Liquid KOSPI commons ranked by realized vol (Infomax-style focus set)."""
    import FinanceDataReader as fdr

    kospi = fdr.StockListing("KOSPI")
    if kospi is None or kospi.empty:
        return default_kospi_universe(top_n=top_n)
    df = kospi.dropna(subset=["Marcap", "Code", "Name"]).copy()
    names = df["Name"].astype(str)
    df = df[~names.str.endswith("우") & ~names.str.contains("우선", na=False)]
    df = df.sort_values("Marcap", ascending=False).head(int(pool))
    start = (pd.Timestamp.now().normalize() - pd.Timedelta(days=lookback_days + 20)).strftime(
        "%Y-%m-%d"
    )
    scored: list[tuple[float, str, str]] = []
    for _, row in df.iterrows():
        code = str(row["Code"]).zfill(6)
        name = str(row["Name"])
        try:
            px = fdr.DataReader(code, start)
            if px is None or px.empty or "Close" not in px.columns:
                continue
            r = px["Close"].astype(float).pct_change().dropna()
            if len(r) < 15:
                continue
            vol = float(r.tail(lookback_days).std(ddof=1) * np.sqrt(252))
            if not np.isfinite(vol):
                continue
            scored.append((vol, code, name))
        except Exception:  # noqa: BLE001
            continue
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [(c, n) for _, c, n in scored[:top_n]]
    return out or default_kospi_universe(top_n=top_n)


def _parse_naver_flow_date(raw: str) -> pd.Timestamp | None:
    # '26.08.07' or '2026.08.07'
    t = str(raw).strip()
    m = None
    if len(t) >= 8 and t[2] == ".":
        yy, mm, dd = t.split(".")[:3]
        year = 2000 + int(yy) if len(yy) == 2 else int(yy)
        m = pd.Timestamp(year=year, month=int(mm), day=int(dd))
    return m


def fetch_kospi_market_investor_history(*, max_days: int = 60) -> pd.DataFrame:
    """KOSPI cash market 개인/외국인/기관계 순매수 (억원)."""
    import requests
    from datetime import timedelta
    from io import StringIO

    UA = {"User-Agent": "Mozilla/5.0"}
    seen: set[str] = set()
    recs: list[dict[str, Any]] = []
    for i in range(0, max_days + 40):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={d}&page=1"
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            r.encoding = "euc-kr"
            tables = pd.read_html(StringIO(r.text))
        except Exception:  # noqa: BLE001
            continue
        if not tables:
            continue
        df = tables[0].copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                "|".join([str(x) for x in tup if str(x) != "nan"]) for tup in df.columns.values
            ]
        date_col = df.columns[0]
        for _, row in df.iterrows():
            raw = str(row[date_col])
            if raw in seen or not raw or not raw[0].isdigit():
                continue
            dt = _parse_naver_flow_date(raw)
            if dt is None:
                continue
            seen.add(raw)

            def _num(col_substr: str) -> float | None:
                cols = [c for c in df.columns if col_substr in str(c)]
                if not cols:
                    return None
                v = row.get(cols[0])
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return None
                try:
                    return float(str(v).replace(",", ""))
                except ValueError:
                    return None

            retail = _num("개인")
            foreign = _num("외국인")
            inst = _num("기관계")
            if retail is None and foreign is None:
                continue
            recs.append(
                {
                    "date": dt,
                    "retail_net_eok": retail,
                    "foreign_net_eok": foreign,
                    "institution_net_eok": inst,
                }
            )
        if len(seen) >= max_days:
            break
    if not recs:
        return pd.DataFrame()
    out = pd.DataFrame(recs).drop_duplicates("date").set_index("date").sort_index()
    return out.tail(max_days)


def build_kospi_index_levels(*, max_days: int = 60, step: float = 250.0) -> dict[str, Any]:
    """Infomax-style: KOSPI close level × market investor nets (억원)."""
    import FinanceDataReader as fdr

    flows = fetch_kospi_market_investor_history(max_days=max_days)
    if flows.empty:
        return {"quality": "missing", "note_ko": "코스피 시장 수급 히스토리 없음"}

    start = (flows.index.min() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    idx = fdr.DataReader("KS11", start)
    if idx is None or idx.empty:
        return {"quality": "missing", "note_ko": "KS11 지수 없음"}
    close = idx.rename(columns={"Close": "close", "High": "high", "Low": "low", "Open": "open"})
    close.index = pd.to_datetime(close.index).normalize()
    joined = flows.join(close[["open", "high", "low", "close"]], how="inner")
    if joined.empty:
        return {"quality": "missing", "note_ko": "지수·수급 조인 실패"}

    # Psychological step bins (e.g. 250pt): floor to step
    lo = float(np.floor(joined["close"].min() / step) * step)
    hi = float(np.ceil(joined["close"].max() / step) * step)
    if hi <= lo:
        hi = lo + step
    edges = np.arange(lo, hi + step * 0.5, step, dtype=float)
    bins = []
    for i in range(len(edges) - 1):
        bins.append(
            {
                "bin": i,
                "price_lo": float(edges[i]),
                "price_hi": float(edges[i + 1]),
                "price_mid": float((edges[i] + edges[i + 1]) / 2),
                "n_days": 0,
                "retail_net_shares": 0,  # unused; keep schema
                "foreign_net_shares": 0,
                "institution_net_shares": 0,
                "retail_net_krw": 0,  # store 억원 here for index
                "foreign_net_krw": 0,
                "institution_net_krw": 0,
                "value_unit": "eok",
            }
        )
    px = joined["close"].astype(float).to_numpy()
    idx_bin = np.clip(np.digitize(px, edges[1:-1], right=False), 0, len(bins) - 1)
    days = []
    for i, (dt, row) in enumerate(joined.iterrows()):
        b = bins[int(idx_bin[i])]
        b["n_days"] += 1
        for a, col in (
            ("retail", "retail_net_eok"),
            ("foreign", "foreign_net_eok"),
            ("institution", "institution_net_eok"),
        ):
            v = row.get(col)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            b[f"{a}_net_krw"] += int(round(float(v)))
        days.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "retail_net_eok": float(row["retail_net_eok"])
                if pd.notna(row.get("retail_net_eok"))
                else None,
                "foreign_net_eok": float(row["foreign_net_eok"])
                if pd.notna(row.get("foreign_net_eok"))
                else None,
                "institution_net_eok": float(row["institution_net_eok"])
                if pd.notna(row.get("institution_net_eok"))
                else None,
            }
        )

    def _top_eok(actor: str, side: str) -> dict[str, Any] | None:
        key = f"{actor}_net_krw"
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
        _, b = scored[0]
        net = int(b[key])
        return {
            "actor": actor,
            "actor_ko": ACTOR_KO[actor],
            "side": side,
            "net_eok": net,
            "price_lo": b["price_lo"],
            "price_hi": b["price_hi"],
            "n_days": b["n_days"],
            "label_ko": (
                f"코스피 {int(b['price_lo']):,}–{int(b['price_hi']):,}에서 "
                f"{ACTOR_KO[actor]} 순매수 {net:+,}억원"
                if side == "buy"
                else f"코스피 {int(b['price_lo']):,}–{int(b['price_hi']):,}에서 "
                f"{ACTOR_KO[actor]} 순매도 {net:+,}억원"
            ),
        }

    highlights = {
        a: {"buy": _top_eok(a, "buy"), "sell": _top_eok(a, "sell")} for a in ACTORS
    }
    # Infomax-like one-liner
    retail_buy = highlights["retail"]["buy"]
    foreign_sell = highlights["foreign"]["sell"]
    headline = None
    if retail_buy and foreign_sell and retail_buy["price_lo"] == foreign_sell["price_lo"]:
        headline = (
            f"코스피 {int(retail_buy['price_lo']):,} 이상 구간에서 개인 사고 외국인 팔았다 "
            f"(개인 {retail_buy['net_eok']:+,}억 / 외인 {foreign_sell['net_eok']:+,}억, 추정)"
        )
    elif retail_buy:
        headline = retail_buy["label_ko"] + " (추정)"

    return {
        "schema": "kospi-index-investor-levels-v1",
        "quality": "estimated",
        "unit": "억원 (시장 전체 순매수)",
        "step": step,
        "method_ko": (
            "연합인포맥스(메리츠) 스타일: 코스피 종가 레벨(심리적 구간)별 "
            "개인·외인·기관 순매수 분포. 공개 일별 집계 귀속."
        ),
        "source": [
            "https://finance.naver.com/sise/investorDealTrendDay.naver",
            "FinanceDataReader KS11",
            "ref: https://news.einfomax.co.kr/news/articleView.html?idxno=4427169",
        ],
        "n_days": len(days),
        "date_start": days[0]["date"] if days else None,
        "date_end": days[-1]["date"] if days else None,
        "latest": days[-1] if days else None,
        "headline_ko": headline,
        "days": days,
        "bins_by_close": bins,
        "highlights": highlights,
    }


def close_day_table(tickers: dict[str, Any]) -> list[dict[str, Any]]:
    """그날 종가 기준 개인/외인/기관 순매수 표 (주·원)."""
    rows = []
    for code, block in tickers.items():
        latest = block.get("latest_close_row")
        if not latest:
            continue
        rows.append(
            {
                "ticker": code,
                "label_ko": block.get("label_ko"),
                "date": latest.get("date"),
                "close": latest.get("close"),
                "retail_net_shares": latest.get("retail_net_shares"),
                "foreign_net_shares": latest.get("foreign_net_shares"),
                "institution_net_shares": latest.get("institution_net_shares"),
                "retail_net_krw": latest.get("retail_net_krw"),
                "foreign_net_krw": latest.get("foreign_net_krw"),
                "institution_net_krw": latest.get("institution_net_krw"),
            }
        )
    rows.sort(key=lambda r: abs(r.get("retail_net_krw") or 0), reverse=True)
    return rows


def build_investor_price_levels_report(
    tickers: list[tuple[str, str]] | None = None,
    *,
    page_size: int = 60,
    n_bins: int = 12,
    kospi_top_n: int | None = 10,
    universe_mode: str = "high_vol",
) -> dict[str, Any]:
    if tickers is None:
        if universe_mode == "marcap":
            tickers = default_kospi_universe(top_n=kospi_top_n or 10)
            uni_name = "kospi_top_marcap_common"
        else:
            tickers = high_vol_kospi_universe(top_n=kospi_top_n or 10)
            uni_name = "kospi_high_vol_liquid"
    else:
        uni_name = (
            "kospi_high_vol_liquid"
            if universe_mode == "high_vol"
            else "kospi_top_marcap_common"
            if universe_mode == "marcap"
            else "custom"
        )

    names: dict[str, Any] = {}
    errors: list[str] = []
    for code, label in tickers:
        try:
            names[code] = build_ticker_levels(
                code, page_size=page_size, n_bins=n_bins, label_ko=label
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"{code}: {type(e).__name__}: {e}")
            names[code] = {
                "ticker": code,
                "label_ko": label,
                "quality": "missing",
                "error": f"{type(e).__name__}: {e}",
            }

    try:
        index_levels = build_kospi_index_levels(max_days=max(page_size, 40))
    except Exception as e:  # noqa: BLE001
        index_levels = {"quality": "missing", "error": f"{type(e).__name__}: {e}"}
        errors.append(f"KS11: {type(e).__name__}: {e}")

    day_table = close_day_table(names)

    return {
        "schema_version": "investor-price-levels-v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "market": "KOSPI",
        "universe": uni_name,
        "universe_mode": universe_mode if tickers else universe_mode,
        "universe_n": len(tickers),
        "n_bins": n_bins,
        "page_size": page_size,
        "infomax_style_ko": (
            "코스피 지수 레벨별 주체 순매수 + 고변동 개별주 종가 빈 분포 + "
            "당일 종가 기준 순매수 표 (주/원)."
        ),
        "kospi_index_levels": index_levels,
        "close_day_table": day_table,
        "tickers": names,
        "ui_hint_ko": (
            "1) kospi_index_levels.headline_ko / bins_by_close (억원) — 인포맥스형\n"
            "2) close_day_table — 고변동주 당일 종가×개인·외인·기관\n"
            "3) tickers.*.bins_by_close — 개별 가격대 분포 (estimated)"
        ),
        "cannot_do_ko": [
            "체결/호가 단위로 개인·외인·기관을 나눈 진짜 가격대 매집도 (유료)",
            "장중 1분 투자자별 실적 (KRX 유료 상품)",
        ],
        "errors": errors,
        "disclaimer_ko": "투자 권유 아님. 공개 일별 수급×종가 레벨 근사 (인포맥스형).",
    }


def markdown_investor_price_levels(rep: dict[str, Any]) -> str:
    lines = [
        f"# Investor × price levels (KOSPI) — {rep.get('as_of')}",
        "",
        rep.get("disclaimer_ko") or "",
        "",
        f"Universe: `{rep.get('universe')}` n={rep.get('universe_n')} · "
        f"mode=`{rep.get('universe_mode')}`",
        "",
    ]
    idx = rep.get("kospi_index_levels") or {}
    if idx.get("quality") != "missing":
        lines.append("## 코스피 지수 레벨 (인포맥스형)")
        lines.append("")
        if idx.get("headline_ko"):
            lines.append(f"**{idx['headline_ko']}**")
            lines.append("")
        lines.append(
            f"- 표본 {idx.get('n_days')}일 · step={idx.get('step')}pt · unit=억원"
        )
        hi = idx.get("highlights") or {}
        for a in ACTORS:
            buy = (hi.get(a) or {}).get("buy")
            sell = (hi.get(a) or {}).get("sell")
            if buy:
                lines.append(f"- {buy['label_ko']}")
            if sell:
                lines.append(f"- {sell['label_ko']}")
        lines.append("")
        lines.append("| 코스피 레벨 | 개인(억) | 외국인(억) | 기관(억) | n |")
        lines.append("|------------|--------:|----------:|--------:|--:|")
        for b in idx.get("bins_by_close") or []:
            lines.append(
                f"| {int(b['price_lo']):,}–{int(b['price_hi']):,} | "
                f"{b['retail_net_krw']:+,} | {b['foreign_net_krw']:+,} | "
                f"{b['institution_net_krw']:+,} | {b['n_days']} |"
            )
        lines.append("")

    lines.append("## 당일 종가 기준 표 (고변동 개별주)")
    lines.append("")
    lines.append("| 종목 | 종가 | 개인(주) | 외인(주) | 기관(주) | 개인(원) | 외인(원) |")
    lines.append("|------|-----:|--------:|--------:|--------:|--------:|--------:|")
    for r in rep.get("close_day_table") or []:
        lines.append(
            f"| {r.get('label_ko')} ({r.get('ticker')}) | {int(r.get('close') or 0):,} | "
            f"{(r.get('retail_net_shares') or 0):+,} | {(r.get('foreign_net_shares') or 0):+,} | "
            f"{(r.get('institution_net_shares') or 0):+,} | "
            f"{(r.get('retail_net_krw') or 0):+,} | {(r.get('foreign_net_krw') or 0):+,} |"
        )
    lines.append("")

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
                lines.append(f"- {buy['label_ko']}")
            if sell:
                lines.append(f"- {sell['label_ko']}")
        lines.append("")
        lines.append("| 가격대(종가빈) | 개인(주) | 외국인(주) | 기관(주) | 개인(원) | n |")
        lines.append("|---------------|--------:|----------:|--------:|--------:|--:|")
        for b in block.get("bins_by_close") or []:
            lines.append(
                f"| {int(b['price_lo']):,}–{int(b['price_hi']):,} | "
                f"{b['retail_net_shares']:+,} | {b['foreign_net_shares']:+,} | "
                f"{b['institution_net_shares']:+,} | {b['retail_net_krw']:+,} | {b['n_days']} |"
            )
        lines.append("")
    if rep.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for e in rep["errors"]:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines)
