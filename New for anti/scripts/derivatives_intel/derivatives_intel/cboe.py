"""CBOE delayed options chain — the free replacement for a paid tick feed.

``https://cdn.cboe.com/api/global/delayed_quotes/options/<TICKER>.json``

No key, no account, no rate-limit headaches. One request returns the entire
listed chain for an underlying — every strike and expiry with volume, open
interest, bid/ask, IV and full greeks, plus the underlying's spot and IV30.

**What this can and cannot tell you.** It is a *snapshot of positioning*, not a
tape. Sweep detection — one buyer lifting several venues inside a few hundred
milliseconds — is simply not reconstructable from it, and neither is a reliable
per-print aggressor. Those need OPRA tick data with the NBBO attached, which is
the thing that costs money. So this module deliberately does not invent a
BUY/SELL label. What it does give, honestly, is the signal the free tools
actually run on: **volume against open interest**, which is how you spot new
positioning being put on today rather than inventory that was already there.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional

import requests

from .models import ChainQuote, ChainSnapshot
from .osi import parse_osi

log = logging.getLogger(__name__)

CHAIN_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"

# Index products live under an underscore prefix on this endpoint.
INDEX_PREFIX = {"SPX", "VIX", "NDX", "RUT", "XSP", "DJX"}


def chain_url(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym in INDEX_PREFIX:
        sym = f"_{sym}"
    return CHAIN_URL.format(symbol=sym)


def fetch_chain(
    session: requests.Session,
    symbol: str,
    timeout: int = 45,
) -> Optional[ChainSnapshot]:
    """Fetch and decode one underlying's full option chain.

    Returns None on any failure — a dead ticker must not take the build down.
    """
    url = chain_url(symbol)
    try:
        resp = session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("CBOE chain %s failed: %s", symbol, exc)
        return None
    if resp.status_code != 200:
        log.info("CBOE chain %s -> HTTP %s", symbol, resp.status_code)
        return None
    try:
        payload = resp.json()
    except ValueError:
        log.warning("CBOE chain %s returned non-JSON", symbol)
        return None

    return parse_chain(payload, symbol)


def parse_chain(payload: dict, symbol: str) -> Optional[ChainSnapshot]:
    data = payload.get("data") or {}
    raw_options = data.get("options") or []
    if not raw_options:
        return None

    quotes: list[ChainQuote] = []
    for raw in raw_options:
        quote = _parse_quote(raw)
        if quote is not None:
            quotes.append(quote)

    if not quotes:
        return None

    return ChainSnapshot(
        symbol=symbol.upper(),
        as_of=_parse_ts(payload.get("timestamp")),
        spot=_as_float(data.get("current_price")) or 0.0,
        iv30=_as_float(data.get("iv30")),
        underlying_volume=_as_float(data.get("volume")),
        price_change_pct=_as_float(data.get("price_change_percent")),
        quotes=quotes,
    )


def _parse_quote(raw: dict) -> Optional[ChainQuote]:
    contract = parse_osi(raw.get("option") or "")
    if contract is None:
        return None

    return ChainQuote(
        contract=contract,
        bid=_as_float(raw.get("bid")) or 0.0,
        ask=_as_float(raw.get("ask")) or 0.0,
        last=_as_float(raw.get("last_trade_price")) or 0.0,
        volume=int(_as_float(raw.get("volume")) or 0),
        open_interest=int(_as_float(raw.get("open_interest")) or 0),
        iv=_as_float(raw.get("iv")),
        delta=_as_float(raw.get("delta")),
        gamma=_as_float(raw.get("gamma")),
        vega=_as_float(raw.get("vega")),
        theta=_as_float(raw.get("theta")),
        theo=_as_float(raw.get("theo")),
        last_trade_time=_parse_ts(raw.get("last_trade_time")),
    )


def fetch_chains(
    session: requests.Session,
    symbols: Iterable[str],
) -> tuple[dict[str, ChainSnapshot], list[str]]:
    """Fetch several chains; returns the successes and the failed tickers."""
    chains: dict[str, ChainSnapshot] = {}
    failed: list[str] = []
    for symbol in symbols:
        snap = fetch_chain(session, symbol)
        if snap is None:
            failed.append(symbol.upper())
        else:
            chains[symbol.upper()] = snap
            log.info(
                "CBOE %s: %d contracts, spot %.2f, as of %s",
                symbol.upper(), len(snap.quotes), snap.spot, snap.as_of,
            )
    return chains, failed


def _parse_ts(value: object) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


def _as_float(value: object) -> Optional[float]:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # drop NaN
