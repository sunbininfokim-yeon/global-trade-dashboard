"""Market quote helpers (Yahoo chart API — no key). For PER/PBR screens."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_UA = "KFA-Engine/1.0 (research; contact: local-dev)"


class QuoteError(RuntimeError):
    pass


def fetch_yahoo_quote(ticker: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Best-effort last price / market cap from Yahoo finance chart endpoint."""
    sym = ticker.strip().upper()
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.request.quote(sym)}?interval=1d&range=5d"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise QuoteError(str(e)) from e

    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        err = ((data.get("chart") or {}).get("error") or {}).get("description")
        raise QuoteError(err or "empty chart result")
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    currency = meta.get("currency")
    return {
        "ticker": sym,
        "price": float(price) if price is not None else None,
        "currency": currency,
        "exchange": meta.get("exchangeName"),
        "asof": meta.get("regularMarketTime"),
        "source": "yahoo_chart",
    }


def market_multiples(
    *,
    price: float | None,
    shares_out: float | None,
    net_income: float | None,
    equity: float | None,
    ebitda: float | None,
    net_debt: float | None,
) -> dict[str, Any]:
    """PER / PBR / EV/EBITDA from price × shares and filing fundamentals."""
    out: dict[str, Any] = {
        "price": price,
        "shares_out": shares_out,
        "market_cap": None,
        "per": None,
        "pbr": None,
        "ev": None,
        "ev_ebitda": None,
        "reasons": {},
    }
    if price is None or shares_out is None:
        out["reasons"]["market_cap"] = "missing:price_or_shares"
        return out
    mcap = float(price) * float(shares_out)
    out["market_cap"] = round(mcap, 2)

    if net_income not in (None, 0):
        out["per"] = round(mcap / float(net_income), 4)
    else:
        out["reasons"]["per"] = "missing:net_income"

    if equity not in (None, 0):
        out["pbr"] = round(mcap / float(equity), 4)
    else:
        out["reasons"]["pbr"] = "missing:equity"

    if net_debt is not None:
        ev = mcap + float(net_debt)  # net cash → EV < mcap
        out["ev"] = round(ev, 2)
        if ebitda not in (None, 0):
            out["ev_ebitda"] = round(ev / float(ebitda), 4)
        else:
            out["reasons"]["ev_ebitda"] = "missing:ebitda"
    else:
        out["reasons"]["ev"] = "missing:net_debt"

    return out
