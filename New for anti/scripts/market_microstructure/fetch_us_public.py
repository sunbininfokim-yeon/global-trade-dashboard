"""US public market fetch — official-first, Yahoo fallback.

Priority:
  1) FINRA consolidated short interest (official)
  2) Cboe delayed options + VIX/VVIX/SKEW CDN
  3) Yahoo/yfinance for spot/premarket (and options if Cboe fails)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from fetch_cboe_public import fetch_cboe_equity_quote, fetch_cboe_options, fetch_vol_indices

UA = {
    "User-Agent": "market-microstructure/1.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

FINRA_SHORT = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def fetch_finra_short(symbol: str, *, lookback_days: int = 400) -> dict[str, Any]:
    """Latest bi-monthly short interest for one symbol (FINRA official API)."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)
    payload = {
        "compareFilters": [
            {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": symbol}
        ],
        "dateRangeFilters": [
            {
                "fieldName": "settlementDate",
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            }
        ],
        "limit": 40,
    }
    r = requests.post(FINRA_SHORT, headers=UA, json=payload, timeout=60)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return {
            "symbol": symbol,
            "quality": "missing",
            "source": "FINRA consolidatedShortInterest",
            "note_ko": "no rows in date range",
        }
    rows = sorted(rows, key=lambda x: x.get("settlementDate") or "", reverse=True)
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    cur = float(latest.get("currentShortPositionQuantity") or 0)
    prev_q = float((prev or {}).get("currentShortPositionQuantity") or latest.get("previousShortPositionQuantity") or 0)
    chg_pct = None
    if prev_q > 0:
        chg_pct = (cur - prev_q) / prev_q * 100.0
    elif latest.get("changePercent") is not None:
        chg_pct = float(latest["changePercent"])
    return {
        "symbol": symbol,
        "settlement_date": latest.get("settlementDate"),
        "short_shares": cur,
        "short_shares_prev": prev_q,
        "short_chg_pct": None if chg_pct is None else round(chg_pct, 3),
        "days_to_cover": latest.get("daysToCoverQuantity"),
        "avg_daily_volume": latest.get("averageDailyVolumeQuantity"),
        "quality": "observed",
        "source": "FINRA consolidatedShortInterest",
        "history_n": len(rows),
    }


def fetch_yahoo_spot_options(symbol: str) -> dict[str, Any]:
    """Spot + nearest-expiry option chain aggregates (Yahoo fallback)."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    info = t.info or {}
    px = info.get("regularMarketPrice") or info.get("currentPrice")
    prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
    pre = info.get("preMarketPrice")
    day_r = None
    if px is not None and prev not in (None, 0):
        day_r = (float(px) - float(prev)) / float(prev)
    gap_pre = None
    if pre is not None and prev not in (None, 0):
        gap_pre = (float(pre) - float(prev)) / float(prev)

    # Yahoo short fields as supplement (FINRA preferred when present)
    y_short = {
        "short_ratio": info.get("shortRatio"),
        "short_percent_of_float": info.get("shortPercentOfFloat"),
        "shares_short": info.get("sharesShort"),
        "shares_short_prior": info.get("sharesShortPriorMonth"),
        "source": "Yahoo info (supplement)",
        "quality": "estimated",
    }

    options_summary: dict[str, Any] = {
        "quality": "missing",
        "source": "Yahoo option_chain",
    }
    try:
        exps = list(t.options or [])
    except Exception:  # noqa: BLE001
        exps = []
    if exps:
        exp0 = exps[0]
        chain = t.option_chain(exp0)
        calls = chain.calls
        puts = chain.puts
        call_vol = float(calls["volume"].fillna(0).sum()) if "volume" in calls else 0.0
        put_vol = float(puts["volume"].fillna(0).sum()) if "volume" in puts else 0.0
        call_oi = float(calls["openInterest"].fillna(0).sum()) if "openInterest" in calls else 0.0
        put_oi = float(puts["openInterest"].fillna(0).sum()) if "openInterest" in puts else 0.0
        pc_vol = None if call_vol <= 0 else put_vol / call_vol
        pc_oi = None if call_oi <= 0 else put_oi / call_oi
        # ATM-ish IV: nearest strike to spot
        atm_iv = None
        if px is not None and "impliedVolatility" in calls.columns and len(calls):
            c2 = calls.copy()
            c2["dist"] = (c2["strike"] - float(px)).abs()
            atm_iv = float(c2.sort_values("dist").iloc[0]["impliedVolatility"])
        options_summary = {
            "nearest_expiry": exp0,
            "n_expiries_listed": len(exps),
            "call_volume": call_vol,
            "put_volume": put_vol,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "put_call_volume": None if pc_vol is None else round(pc_vol, 4),
            "put_call_oi": None if pc_oi is None else round(pc_oi, 4),
            "atm_call_iv": None if atm_iv is None else round(atm_iv, 6),
            "total_volume": call_vol + put_vol,
            "quality": "observed",
            "source": "Yahoo option_chain (delayed; OPRA redistributor)",
            "note_ko": "공식 OPRA 피드 재배포. Cboe EOD 유료 대체 가능 시 교체.",
        }

    return {
        "symbol": symbol,
        "spot": {
            "price": px,
            "prev_close": prev,
            "day_return": None if day_r is None else round(day_r, 6),
            "premarket_price": pre,
            "premarket_gap": None if gap_pre is None else round(gap_pre, 6),
            "premarket_gap_quality": "observed" if gap_pre is not None else "missing",
            "premarket_gap_formula": "(Yahoo premarket price / Yahoo previous close) - 1",
            "quality": "observed" if px is not None else "missing",
            "source": "Yahoo quote",
        },
        "yahoo_short_supplement": y_short,
        "options": options_summary,
    }


def fetch_us_names(symbols: list[str]) -> dict[str, Any]:
    names: list[dict[str, Any]] = []
    errors: list[str] = []
    sources_used: list[str] = []

    try:
        vol_idx = fetch_vol_indices()
        sources_used.append("cboe_vol_indices")
    except Exception as e:  # noqa: BLE001
        vol_idx = {"quality": "missing", "error": str(e), "indices": {}}
        errors.append(f"cboe_vol:{e}")

    for sym in symbols:
        row: dict[str, Any] = {"symbol": sym}
        try:
            row["finra_short"] = fetch_finra_short(sym)
            if "finra_short" not in sources_used:
                sources_used.append("finra_short")
        except Exception as e:  # noqa: BLE001
            row["finra_short"] = {
                "symbol": sym,
                "quality": "missing",
                "source": "FINRA",
                "error": f"{type(e).__name__}: {e}",
            }
            errors.append(f"finra:{sym}:{e}")

        # Spot: Cboe delayed preferred; Yahoo fills premarket + fallback
        cboe_spot: dict[str, Any] | None = None
        try:
            cboe_spot = fetch_cboe_equity_quote(sym)
            if "cboe_spot" not in sources_used:
                sources_used.append("cboe_spot")
        except Exception as e:  # noqa: BLE001
            errors.append(f"cboe_spot:{sym}:{e}")

        y: dict[str, Any] | None = None
        try:
            y = fetch_yahoo_spot_options(sym)
            if "yahoo_spot_options_fallback" not in sources_used:
                sources_used.append("yahoo_spot_options_fallback")
        except Exception as e:  # noqa: BLE001
            errors.append(f"yahoo:{sym}:{e}")

        if cboe_spot and cboe_spot.get("quality") == "observed":
            premarket_price = (
                (y or {}).get("spot", {}).get("premarket_price") if y else None
            )
            cboe_prev_close = cboe_spot.get("prev_close")
            premarket_gap = None
            if premarket_price is not None and cboe_prev_close not in (None, 0):
                premarket_gap = round(
                    (float(premarket_price) - float(cboe_prev_close))
                    / float(cboe_prev_close),
                    6,
                )
            spot = {
                "price": cboe_spot.get("price"),
                "prev_close": cboe_prev_close,
                "day_return": cboe_spot.get("day_return"),
                "premarket_price": premarket_price,
                # Recompute with the displayed Cboe previous close.  Reusing
                # Yahoo's gap while showing Cboe's denominator made the JSON
                # internally inconsistent and could fire a false gap alert.
                "premarket_gap": premarket_gap,
                "premarket_gap_quality": "partial" if premarket_gap is not None else "missing",
                "premarket_gap_formula": "(Yahoo premarket price / Cboe previous close) - 1",
                "quality": "observed",
                "source": "Cboe delayed_quotes (+ Yahoo premarket if any)",
            }
        elif y:
            spot = y["spot"]
        else:
            spot = {"quality": "missing", "source": "cboe+yahoo"}
        row["spot"] = spot
        row["yahoo_short_supplement"] = (y or {}).get("yahoo_short_supplement") or {
            "quality": "missing"
        }

        # Options: Cboe first
        try:
            opt = fetch_cboe_options(sym)
            row["options"] = opt
            if "cboe_options" not in sources_used:
                sources_used.append("cboe_options")
        except Exception as e:  # noqa: BLE001
            errors.append(f"cboe_opt:{sym}:{e}")
            if y and (y.get("options") or {}).get("quality") == "observed":
                row["options"] = y["options"]
            else:
                row["options"] = {
                    "quality": "missing",
                    "source": "Cboe+Yahoo",
                    "error": str(e),
                }

        names.append(row)

    return {
        "schema_version": "us-microstructure-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_priority_used": sources_used or ["finra_short", "yahoo_spot_options_fallback"],
        "vol_indices": vol_idx,
        "names": names,
        "errors": errors,
        "disclaimer_ko": "공개·지연 데이터. 투자 권유 아님. 주체 특정 아님.",
    }
