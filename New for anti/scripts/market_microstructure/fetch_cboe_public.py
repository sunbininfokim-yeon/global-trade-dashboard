"""Cboe public delayed quotes + index history (official CDN).

Free delayed equity/index options and VIX/VVIX/SKEW CSVs.
Does not replace OPRA vendor feeds; quality=observed delayed.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

UA = "market-microstructure/1.0 (research; +https://github.com/)"

OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")

CDN = "https://cdn.cboe.com/api/global"
INDEX_CSV = {
    "VIX": f"{CDN}/us_indices/daily_prices/VIX_History.csv",
    "VVIX": f"{CDN}/us_indices/daily_prices/VVIX_History.csv",
    "SKEW": f"{CDN}/us_indices/daily_prices/SKEW_History.csv",
}


def _get(url: str, *, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _get_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    import json

    return json.loads(_get(url, timeout=timeout).decode("utf-8"))


def fetch_index_history_tail(symbol: str, *, n: int = 5) -> list[dict[str, Any]]:
    """Last n rows from Cboe daily index CSV (VIX/VVIX/SKEW)."""
    url = INDEX_CSV.get(symbol.upper())
    if not url:
        raise ValueError(f"unsupported index {symbol}")
    text = _get(url, timeout=60).decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    out: list[dict[str, Any]] = []
    for row in rows[-n:]:
        date = row.get("DATE") or row.get("Date")
        close = row.get("CLOSE") or row.get(symbol.upper()) or row.get("VVIX") or row.get("SKEW")
        try:
            close_f = float(close) if close not in (None, "") else None
        except ValueError:
            close_f = None
        out.append({"date": date, "close": close_f})
    return out


def fetch_vol_indices() -> dict[str, Any]:
    """Snapshot of VIX/VVIX/SKEW from Cboe public history + delayed VIX quote."""
    indices: dict[str, Any] = {}
    errors: list[str] = []
    for name in ("VIX", "VVIX", "SKEW"):
        try:
            hist = fetch_index_history_tail(name, n=3)
            last = hist[-1] if hist else {}
            prev = hist[-2] if len(hist) >= 2 else {}
            chg = None
            if last.get("close") is not None and prev.get("close") not in (None, 0):
                chg = (float(last["close"]) - float(prev["close"])) / float(prev["close"])
            indices[name] = {
                "as_of": last.get("date"),
                "close": last.get("close"),
                "prev_close": prev.get("close"),
                "day_return": None if chg is None else round(chg, 6),
                "source": f"Cboe {name}_History.csv",
                "quality": "observed",
            }
        except Exception as e:  # noqa: BLE001
            indices[name] = {"quality": "missing", "error": f"{type(e).__name__}: {e}"}
            errors.append(f"{name}:{e}")

    try:
        q = _get_json(f"{CDN}/delayed_quotes/quotes/_VIX.json", timeout=30)
        data = q.get("data") or {}
        indices["VIX_quote"] = {
            "price": data.get("current_price"),
            "change_pct": data.get("price_change_percent"),
            "timestamp": q.get("timestamp"),
            "source": "Cboe delayed_quotes/_VIX",
            "quality": "observed",
        }
    except Exception as e:  # noqa: BLE001
        errors.append(f"VIX_quote:{e}")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "indices": indices,
        "errors": errors,
        "source": "cboe_cdn",
    }


def fetch_cboe_equity_quote(symbol: str) -> dict[str, Any]:
    q = _get_json(f"{CDN}/delayed_quotes/quotes/{symbol.upper()}.json", timeout=30)
    data = q.get("data") or {}
    px = data.get("current_price")
    prev = data.get("prev_day_close")
    day_r = None
    if px is not None and prev not in (None, 0):
        day_r = (float(px) - float(prev)) / float(prev)
    # Cboe sometimes sets prev_day_close == close after hours; use price_change_percent
    if day_r is None and data.get("price_change_percent") is not None:
        day_r = float(data["price_change_percent"]) / 100.0
    return {
        "symbol": symbol.upper(),
        "price": px,
        "prev_close": prev,
        "day_return": None if day_r is None else round(day_r, 6),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "volume": data.get("volume"),
        "timestamp": q.get("timestamp"),
        "quality": "observed" if px is not None else "missing",
        "source": "Cboe delayed_quotes",
    }


def _aggregate_chain(options: list[dict[str, Any]], spot: float | None) -> dict[str, Any]:
    call_vol = put_vol = call_oi = put_oi = 0.0
    nearest_exp: str | None = None
    atm_iv: float | None = None
    best_dist: float | None = None
    expiries: set[str] = set()

    for o in options:
        raw = str(o.get("option") or "")
        m = OCC_RE.match(raw)
        if not m:
            continue
        _root, yymmdd, side, _strike8 = m.groups()
        exp = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
        expiries.add(exp)
        if nearest_exp is None or exp < nearest_exp:
            nearest_exp = exp
        vol = float(o.get("volume") or 0)
        oi = float(o.get("open_interest") or 0)
        if side == "C":
            call_vol += vol
            call_oi += oi
        else:
            put_vol += vol
            put_oi += oi
        if spot is not None and side == "C":
            try:
                strike = int(_strike8) / 1000.0
            except ValueError:
                continue
            iv = o.get("iv")
            try:
                iv_f = float(iv) if iv not in (None, "") else None
            except (TypeError, ValueError):
                iv_f = None
            if iv_f is None or iv_f <= 0:
                continue
            dist = abs(strike - float(spot))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                atm_iv = iv_f

    pc_vol = None if call_vol <= 0 else put_vol / call_vol
    pc_oi = None if call_oi <= 0 else put_oi / call_oi
    return {
        "nearest_expiry": nearest_exp,
        "n_expiries_listed": len(expiries),
        "call_volume": call_vol,
        "put_volume": put_vol,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "put_call_volume": None if pc_vol is None else round(pc_vol, 4),
        "put_call_oi": None if pc_oi is None else round(pc_oi, 4),
        "atm_call_iv": None if atm_iv is None else round(atm_iv, 6),
        "total_volume": call_vol + put_vol,
        "n_contracts": len(options),
        "quality": "observed",
        "source": "Cboe delayed_quotes/options (CDN)",
        "note_ko": "지연 공개 체인. Open-Close/고객분류 아님.",
    }


def fetch_cboe_options(symbol: str) -> dict[str, Any]:
    """Full delayed option chain aggregate for one underlier."""
    payload = _get_json(f"{CDN}/delayed_quotes/options/{symbol.upper()}.json", timeout=90)
    options = (payload.get("data") or {}).get("options") or []
    spot = None
    try:
        spot = fetch_cboe_equity_quote(symbol).get("price")
    except Exception:  # noqa: BLE001
        pass
    summary = _aggregate_chain(options, spot)
    summary["timestamp"] = payload.get("timestamp")
    return summary
