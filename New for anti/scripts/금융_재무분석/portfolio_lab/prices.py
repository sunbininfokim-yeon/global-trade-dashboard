"""Fetch / cache daily prices — Yahoo primary, Stooq fallback (no yfinance)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_CHART_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_DOWNLOAD = "https://query1.finance.yahoo.com/v7/finance/download/{symbol}"
STOOQ_DAILY = "https://stooq.com/q/d/l/?s={symbol}&i=d"
UA = "Mozilla/5.0 (compatible; portfolio-lab/0.1; +local)"


class PriceProvider(Protocol):
    name: str

    def fetch_daily(self, symbol: str, *, years: float = 5.0) -> pd.Series:
        """Return adjusted/close daily series indexed by date (naive midnight)."""


def _cache_path(cache_dir: Path, yahoo_symbol: str) -> Path:
    safe = yahoo_symbol.replace("=", "_").replace("/", "_")
    return cache_dir / f"{safe}.csv"


def _meta_path(cache_dir: Path, yahoo_symbol: str) -> Path:
    return _cache_path(cache_dir, yahoo_symbol).with_suffix(".meta.json")


def _http_get(url: str, *, accept: str, pause: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    if pause > 0:
        time.sleep(pause)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _series_from_yahoo_payload(payload: dict, symbol: str) -> pd.Series:
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo empty result for {symbol}: {payload.get('chart', {}).get('error')}")
    block = result[0]
    ts = block.get("timestamp") or []
    quote = ((block.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    adj = ((block.get("indicators") or {}).get("adjclose") or [{}])
    adj_closes = (adj[0].get("adjclose") if adj else None) or closes
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize()
    s = pd.Series(adj_closes, index=idx, name=symbol, dtype="float64")
    s = s[~s.index.duplicated(keep="last")].dropna().sort_index()
    if s.empty:
        raise RuntimeError(f"Yahoo no closes for {symbol}")
    return s


def fetch_yahoo_daily(
    symbol: str,
    *,
    years: float = 5.0,
    session_pause: float = 0.25,
    chart_base: str = YAHOO_CHART,
) -> pd.Series:
    period2 = int(time.time())
    period1 = int(period2 - years * 365.25 * 24 * 3600)
    url = (
        chart_base.format(symbol=urllib.parse.quote(symbol, safe=""))
        + f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    raw = _http_get(url, accept="application/json", pause=session_pause)
    payload = json.loads(raw.decode("utf-8"))
    return _series_from_yahoo_payload(payload, symbol)


def fetch_yahoo_download_daily(
    symbol: str,
    *,
    years: float = 5.0,
    session_pause: float = 0.25,
) -> pd.Series:
    """Yahoo historical CSV download endpoint (chart API cousin)."""
    from io import StringIO

    period2 = int(time.time())
    period1 = int(period2 - years * 365.25 * 24 * 3600)
    q = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = YAHOO_DOWNLOAD.format(symbol=urllib.parse.quote(symbol, safe="")) + f"?{q}"
    raw = _http_get(url, accept="text/csv,*/*", pause=session_pause)
    text = raw.decode("utf-8", errors="replace").strip()
    if not text or text.lstrip().startswith("<!") or text.lstrip().startswith("{"):
        raise RuntimeError(f"Yahoo download empty/non-CSV for {symbol}")
    df = pd.read_csv(StringIO(text))
    if df.empty or "Date" not in df.columns:
        raise RuntimeError(f"Yahoo download unexpected columns for {symbol}: {list(df.columns)}")
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    if close_col not in df.columns:
        raise RuntimeError(f"Yahoo download no close for {symbol}")
    idx = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    closes = pd.to_numeric(df[close_col], errors="coerce")
    s = pd.Series(closes.values, index=pd.DatetimeIndex(idx), name=symbol, dtype="float64")
    s = s[~s.index.duplicated(keep="last")].dropna().sort_index()
    if s.empty:
        raise RuntimeError(f"Yahoo download no closes for {symbol}")
    return s


def yahoo_to_stooq_symbol(yahoo_symbol: str) -> str | None:
    """
    Map Yahoo chart symbols to Stooq daily CSV symbols.

    Examples
    --------
    AAPL        → aapl.us
    BRK-B       → brk-b.us
    005930.KS   → 005930.ks  (best-effort; Stooq KR coverage is sparse)
    1482.T      → 1482.jp
    USDKRW=X    → usdkrw
    """
    sym = (yahoo_symbol or "").strip()
    if not sym:
        return None
    upper = sym.upper()

    # FX: USDKRW=X → usdkrw
    if upper.endswith("=X"):
        base = upper[:-2].replace("^", "").lower()
        if len(base) >= 6:
            return base
        return None

    # Indices / futures / crypto-ish — skip Stooq unless obvious
    if upper.startswith("^") or "=" in upper or upper.endswith("-USD"):
        return None

    if "." in sym:
        code, exch = sym.rsplit(".", 1)
        exch_l = exch.lower()
        code_l = code.lower()
        # Korea: Stooq uses .ks / .kq when listed; try same suffix
        if exch_l in ("ks", "kq"):
            return f"{code_l}.{exch_l}"
        if exch_l in ("t", "jp"):
            return f"{code_l}.jp"
        if exch_l in ("l", "lon"):
            return f"{code_l}.uk"
        if exch_l in ("de", "f", "pa", "as", "br", "hk", "ss", "sz", "to", "ax", "sa"):
            # best-effort: lowercase Yahoo-style; Stooq may or may not list it
            return f"{code_l}.{exch_l}"
        # Unknown exchange suffix — still try lowercase as-is
        return f"{code_l}.{exch_l}"

    # Plain equity/ETF ticker → US listing on Stooq
    return f"{sym.lower()}.us"


def fetch_stooq_daily(
    yahoo_symbol: str,
    *,
    years: float = 5.0,
    session_pause: float = 0.25,
) -> pd.Series:
    stooq_sym = yahoo_to_stooq_symbol(yahoo_symbol)
    if not stooq_sym:
        raise RuntimeError(f"Stooq: no symbol mapping for {yahoo_symbol}")
    url = STOOQ_DAILY.format(symbol=urllib.parse.quote(stooq_sym, safe="."))
    raw = _http_get(url, accept="text/csv,*/*", pause=session_pause)
    text = raw.decode("utf-8", errors="replace").strip()
    low = text[:500].lower()
    if not text:
        raise RuntimeError(f"Stooq empty body for {stooq_sym}")
    if low.startswith("<!") or "requires javascript" in low or "<html" in low:
        raise RuntimeError(
            f"Stooq blocked/bot-challenge for {stooq_sym} (HTML challenge page; try later or another network)"
        )
    # Stooq returns "No data" plain text on miss
    first_line = text.splitlines()[0].lower() if text else ""
    if "no data" in text.lower() and "date" not in first_line:
        raise RuntimeError(f"Stooq no data for {stooq_sym}")
    from io import StringIO

    df = pd.read_csv(StringIO(text))
    if df.empty or "Date" not in df.columns:
        # some locales / responses use lowercase
        cols = {c.lower(): c for c in df.columns}
        if "date" not in cols:
            raise RuntimeError(f"Stooq unexpected columns for {stooq_sym}: {list(df.columns)}")
        date_col = cols["date"]
        close_col = cols.get("close") or cols.get("adjusted close")
        if close_col is None:
            raise RuntimeError(f"Stooq no close column for {stooq_sym}")
    else:
        date_col = "Date"
        close_col = "Close" if "Close" in df.columns else None
        if close_col is None:
            raise RuntimeError(f"Stooq no Close for {stooq_sym}")

    idx = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    closes = pd.to_numeric(df[close_col], errors="coerce")
    s = pd.Series(closes.values, index=pd.DatetimeIndex(idx), name=yahoo_symbol, dtype="float64")
    s = s[~s.index.duplicated(keep="last")].dropna().sort_index()
    if years and years > 0 and not s.empty:
        cutoff = s.index.max() - pd.Timedelta(days=int(years * 365.25))
        s = s.loc[s.index >= cutoff]
    if s.empty:
        raise RuntimeError(f"Stooq no closes for {stooq_sym}")
    return s


def _attach_source(s: pd.Series, source: str) -> pd.Series:
    out = s.copy()
    out.attrs["source"] = source
    return out


def _try_yahoo(symbol: str, *, years: float, pause: float) -> pd.Series:
    try:
        return _attach_source(fetch_yahoo_daily(symbol, years=years, session_pause=pause), "yahoo")
    except Exception as first:  # noqa: BLE001
        # Alternate host (query2) — same chart shape
        try:
            return _attach_source(
                fetch_yahoo_daily(
                    symbol,
                    years=years,
                    session_pause=pause,
                    chart_base=YAHOO_CHART_ALT,
                ),
                "yahoo_alt",
            )
        except Exception:  # noqa: BLE001
            pass
        # Shorter window retry on primary host
        if years > 2.0:
            try:
                return _attach_source(
                    fetch_yahoo_daily(symbol, years=2.0, session_pause=pause),
                    "yahoo_retry",
                )
            except Exception:  # noqa: BLE001
                pass
        # CSV download endpoint (still Yahoo family)
        try:
            return _attach_source(
                fetch_yahoo_download_daily(symbol, years=years, session_pause=pause),
                "yahoo_download",
            )
        except Exception:  # noqa: BLE001
            pass
        raise first


def _try_stooq(symbol: str, *, years: float, pause: float) -> pd.Series:
    return _attach_source(fetch_stooq_daily(symbol, years=years, session_pause=pause), "stooq")


# Ordered providers: Yahoo bundle (chart → alt host → short period → CSV), then Stooq.
PROVIDERS: list[tuple[str, Callable[..., pd.Series]]] = [
    ("yahoo", _try_yahoo),
    ("stooq", _try_stooq),
]


def fetch_daily(
    symbol: str,
    *,
    years: float = 5.0,
    session_pause: float = 0.25,
    providers: list[tuple[str, Callable[..., pd.Series]]] | None = None,
) -> pd.Series:
    """Try providers in order; return first non-empty series (attrs.source set)."""
    chain = providers or PROVIDERS
    errors: list[str] = []
    for name, fn in chain:
        try:
            s = fn(symbol, years=years, pause=session_pause)
            if s is None or s.empty:
                errors.append(f"{name}: empty")
                continue
            if "source" not in s.attrs:
                s = _attach_source(s, name)
            return s
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    raise RuntimeError(f"all price providers failed for {symbol}: {'; '.join(errors)}")


def _write_cache(path: Path, meta_path: Path, s: pd.Series, source: str) -> None:
    pd.DataFrame({"date": s.index, "close": s.values}).to_csv(path, index=False)
    meta_path.write_text(
        json.dumps(
            {
                "source": source,
                "symbol": s.name,
                "n": int(len(s)),
                "start": str(s.index.min().date()) if len(s) else None,
                "end": str(s.index.max().date()) if len(s) else None,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_cache(path: Path, meta_path: Path, yahoo_symbol: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"])
    s = pd.Series(df["close"].values, index=pd.DatetimeIndex(df["date"]), name=yahoo_symbol)
    s = s.dropna().sort_index()
    source = "yahoo"  # legacy caches predate sidecar meta
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            source = str(meta.get("source") or "yahoo")
        except (OSError, json.JSONDecodeError):
            pass
    return _attach_source(s, source)


def load_price_series(
    yahoo_symbol: str,
    cache_dir: Path,
    *,
    years: float = 5.0,
    cache_only: bool = False,
    max_age_hours: float = 20.0,
) -> pd.Series:
    """
    Load daily closes for a Yahoo-style symbol.

    Tries cache (fresh), else providers in order (yahoo → stooq).
    Successful network fetches are cached with a ``.meta.json`` sidecar
    recording ``source``. Series.attrs["source"] always set.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, yahoo_symbol)
    meta_path = _meta_path(cache_dir, yahoo_symbol)

    if path.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600.0
        if cache_only or age_h <= max_age_hours:
            return _read_cache(path, meta_path, yahoo_symbol)

    if cache_only:
        raise FileNotFoundError(f"cache miss for {yahoo_symbol}: {path}")

    try:
        s = fetch_daily(yahoo_symbol, years=years)
    except Exception as e:
        # Stale cache is better than hard fail when network/providers blow up
        if path.exists():
            return _read_cache(path, meta_path, yahoo_symbol)
        if isinstance(e, urllib.error.HTTPError):
            raise RuntimeError(f"price HTTP {e.code} for {yahoo_symbol}") from e
        raise

    source = str(s.attrs.get("source") or "yahoo")
    _write_cache(path, meta_path, s, source)
    return s


def synthetic_flat(index: pd.DatetimeIndex, name: str = "FLAT") -> pd.Series:
    return _attach_source(pd.Series(1.0, index=index, name=name, dtype="float64"), "synthetic")
