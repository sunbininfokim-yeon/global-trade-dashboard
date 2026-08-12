"""Fetch HK LETF (Yahoo) + crypto perps (Binance) — venue-separated.

Never merge these into KR cash wag-the-dog without an explicit flag.
HK CSOP products are swap-based (flexible L). Crypto uses OI notional.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"

UA = {"User-Agent": "Mozilla/5.0 market-microstructure/1.0"}


def load_universe() -> dict[str, Any]:
    return json.loads((CONFIG / "letf_universe.json").read_text(encoding="utf-8"))


def _fx_to_usd(amount: float, currency: str, *, usdkrw: float, usdhkd: float = 7.8) -> float:
    c = currency.upper()
    if c in {"USD", "USDT"}:
        return amount
    if c == "HKD":
        return amount / usdhkd
    if c == "KRW":
        return amount / usdkrw
    return amount


def fetch_yahoo_etf(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    t = yf.Ticker(symbol)
    info = t.info or {}
    hist = t.history(period="5d")
    last = None
    if hist is not None and not hist.empty:
        # drop NaN closes
        closes = hist["Close"].dropna()
        vols = hist["Volume"].dropna()
        if len(closes):
            last = {
                "close": float(closes.iloc[-1]),
                "volume": float(vols.iloc[-1]) if len(vols) else None,
                "as_of": str(closes.index[-1].date()),
            }
    aum = info.get("totalAssets")
    ccy = info.get("currency") or "HKD"
    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "aum": float(aum) if aum is not None else None,
        "currency": ccy,
        "nav": info.get("navPrice"),
        "previous_close": info.get("previousClose"),
        "volume": info.get("volume"),
        "average_volume": info.get("averageVolume"),
        "last_bar": last,
        "source": "Yahoo Finance (yfinance)",
        "quality": "observed" if aum is not None else "partial",
    }


def fetch_binance_perp(symbol: str) -> dict[str, Any]:
    base = "https://fapi.binance.com"
    oi = requests.get(f"{base}/fapi/v1/openInterest", params={"symbol": symbol}, timeout=20, headers=UA)
    px = requests.get(f"{base}/fapi/v1/ticker/price", params={"symbol": symbol}, timeout=20, headers=UA)
    t24 = requests.get(f"{base}/fapi/v1/ticker/24hr", params={"symbol": symbol}, timeout=20, headers=UA)
    prem = requests.get(f"{base}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=20, headers=UA)
    for r, label in ((oi, "oi"), (px, "px"), (t24, "24h"), (prem, "prem")):
        if r.status_code != 200:
            raise RuntimeError(f"Binance {label} {symbol} HTTP {r.status_code}: {r.text[:160]}")
    oi_j, px_j, t24_j, prem_j = oi.json(), px.json(), t24.json(), prem.json()
    oiq = float(oi_j["openInterest"])
    price = float(px_j["price"])
    notional = oiq * price
    return {
        "symbol": symbol,
        "price": price,
        "open_interest_contracts": oiq,
        "open_interest_notional_usdt": notional,
        "quote_volume_24h_usdt": float(t24_j.get("quoteVolume") or 0),
        "price_change_pct_24h": float(t24_j.get("priceChangePercent") or 0),
        "mark_price": float(prem_j.get("markPrice") or price),
        "last_funding_rate": float(prem_j.get("lastFundingRate") or 0),
        "source": "Binance USD-M futures public API",
        "quality": "observed",
    }


def build_external_venues(
    *,
    usdkrw: float = 1400.0,
    usdhkd: float = 7.8,
) -> dict[str, Any]:
    uni = load_universe()
    hk_products_cfg = uni.get("venues", {}).get("hk", {}).get("products", [])
    crypto_cfg = uni.get("venues", {}).get("crypto", {}).get("products", [])
    us_cfg = uni.get("venues", {}).get("us", {}).get("products", [])

    hk_out: list[dict[str, Any]] = []
    for p in hk_products_cfg:
        ysym = p.get("yahoo") or p["ticker"]
        try:
            y = fetch_yahoo_etf(ysym)
        except Exception as e:  # noqa: BLE001
            hk_out.append(
                {
                    "ticker": p["ticker"],
                    "underlying": p.get("underlying"),
                    "error": str(e),
                    "quality": "error",
                }
            )
            continue
        aum = y.get("aum")
        aum_usd = None if aum is None else _fx_to_usd(aum, y.get("currency") or "HKD", usdkrw=usdkrw, usdhkd=usdhkd)
        # trading value proxy: volume * close (same currency as price)
        close = (y.get("last_bar") or {}).get("close") or y.get("previous_close")
        vol = y.get("volume")
        tv = None if close is None or vol is None else float(close) * float(vol)
        tv_usd = None if tv is None else _fx_to_usd(tv, y.get("currency") or "HKD", usdkrw=usdkrw, usdhkd=usdhkd)
        L = float(p.get("L", 2))
        hk_out.append(
            {
                "ticker": p["ticker"],
                "name": p.get("name") or y.get("name"),
                "underlying": p.get("underlying"),
                "venue": "hk",
                "L": L,
                "L_flexible": bool(p.get("L_flexible")),
                "structure": p.get("structure", "swap"),
                "direction": p.get("direction"),
                "aum_native": aum,
                "aum_currency": y.get("currency"),
                "aum_usd": aum_usd,
                "notional_exposure_usd": None if aum_usd is None else abs(L) * aum_usd,
                "trading_value_native": tv,
                "trading_value_usd": tv_usd,
                "kr_spot_impact": "indirect_swap",
                "yahoo": y,
                "quality": y.get("quality", "observed"),
                "source": y.get("source"),
            }
        )

    crypto_out: list[dict[str, Any]] = []
    for p in crypto_cfg:
        sym = p["ticker"]
        try:
            b = fetch_binance_perp(sym)
        except Exception as e:  # noqa: BLE001
            crypto_out.append(
                {
                    "ticker": sym,
                    "underlying": p.get("underlying"),
                    "error": str(e),
                    "quality": "error",
                }
            )
            continue
        oi_usd = b["open_interest_notional_usdt"]
        L_max = float(p.get("L_max") or 1)
        und = p.get("underlying")
        is_single = und in {"000660", "005930"}
        crypto_out.append(
            {
                "ticker": sym,
                "name": p.get("name"),
                "underlying": und,
                "venue": "crypto",
                "exchange": p.get("exchange", "binance"),
                "structure": p.get("structure", "tradifi_perp"),
                "bucket": "single_stock_kr" if is_single else "regime_proxy",
                "L_max": L_max,
                "open_interest_notional_usd": oi_usd,
                "notional_exposure_usd": oi_usd,
                "quote_volume_24h_usd": b["quote_volume_24h_usdt"],
                "price": b["price"],
                "last_funding_rate": b["last_funding_rate"],
                "price_change_pct_24h": b["price_change_pct_24h"],
                "kr_spot_impact": "indirect_synthetic",
                "note": p.get("note"),
                "binance": b,
                "quality": "observed",
                "source": b["source"],
            }
        )

    us_out: list[dict[str, Any]] = []
    for p in us_cfg:
        ysym = p.get("yahoo") or p["ticker"]
        try:
            y = fetch_yahoo_etf(ysym)
        except Exception as e:  # noqa: BLE001
            us_out.append({"ticker": p["ticker"], "error": str(e), "quality": "error"})
            continue
        aum = y.get("aum")
        aum_usd = None if aum is None else _fx_to_usd(aum, y.get("currency") or "USD", usdkrw=usdkrw, usdhkd=usdhkd)
        L = float(p.get("L", 3))
        us_out.append(
            {
                "ticker": p["ticker"],
                "name": p.get("name") or y.get("name"),
                "underlying": p.get("underlying"),
                "venue": "us",
                "L": L,
                "structure": p.get("structure", "swap"),
                "aum_usd": aum_usd,
                "notional_exposure_usd": None if aum_usd is None else abs(L) * aum_usd,
                "kr_spot_impact": "regime_proxy",
                "yahoo": y,
                "quality": y.get("quality", "observed"),
                "source": y.get("source"),
            }
        )

    def _sum_exp(rows: list[dict[str, Any]], key: str = "notional_exposure_usd") -> float:
        return float(sum(float(r[key]) for r in rows if r.get(key) is not None))

    by_underlying: dict[str, dict[str, float]] = {}
    for row in hk_out + crypto_out:
        und = row.get("underlying")
        if not und or row.get("notional_exposure_usd") is None:
            continue
        by_underlying.setdefault(und, {"hk_usd": 0.0, "crypto_usd": 0.0})
        if row.get("venue") == "hk":
            by_underlying[und]["hk_usd"] += float(row["notional_exposure_usd"])
        elif row.get("venue") == "crypto":
            by_underlying[und]["crypto_usd"] += float(row["notional_exposure_usd"])

    return {
        "schema_version": "external-venues-v1",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fx": {"usdkrw": usdkrw, "usdhkd": usdhkd},
        "disclaimer_ko": "HK·코인은 국내 현물 호가에 직접 리밸런싱하지 않음(스왑/합성). venue 분리 필수. 투자 권유 아님.",
        "hk": {
            "products": hk_out,
            "notional_exposure_usd_sum": _sum_exp(hk_out),
            "source": "Yahoo Finance",
        },
        "crypto": {
            "products": crypto_out,
            "open_interest_notional_usd_sum": _sum_exp(crypto_out),
            "open_interest_notional_usd_single_stock_kr": float(
                sum(
                    float(r["open_interest_notional_usd"])
                    for r in crypto_out
                    if r.get("bucket") == "single_stock_kr"
                    and r.get("open_interest_notional_usd") is not None
                )
            ),
            "open_interest_notional_usd_regime_proxy": float(
                sum(
                    float(r["open_interest_notional_usd"])
                    for r in crypto_out
                    if r.get("bucket") == "regime_proxy"
                    and r.get("open_interest_notional_usd") is not None
                )
            ),
            "quote_volume_24h_usd_sum": float(
                sum(
                    float(r["quote_volume_24h_usd"])
                    for r in crypto_out
                    if r.get("quote_volume_24h_usd") is not None
                )
            ),
            "source": "Binance fapi",
        },
        "us_proxy": {
            "products": us_out,
            "notional_exposure_usd_sum": _sum_exp(us_out),
            "source": "Yahoo Finance",
        },
        "by_underlying_usd": by_underlying,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / "tests/fixtures/external_venues.json")
    p.add_argument("--usdkrw", type=float, default=1400.0)
    p.add_argument("--usdhkd", type=float, default=7.8)
    args = p.parse_args()
    data = build_external_venues(usdkrw=args.usdkrw, usdhkd=args.usdhkd)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  HK notional USD: {data['hk']['notional_exposure_usd_sum']:,.0f}")
    print(f"  Crypto OI USD:   {data['crypto']['open_interest_notional_usd_sum']:,.0f}")
    print(f"  Crypto 24h vol:  {data['crypto']['quote_volume_24h_usd_sum']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
