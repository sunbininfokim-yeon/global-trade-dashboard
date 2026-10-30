"""Fetch HK LETF + crypto perps (Binance) — venue-separated.

Never merge these into KR cash wag-the-dog without an explicit flag.
HK CSOP products are swap-based (flexible L). Crypto uses OI notional.

HK numbers come from the overseas board (``build_overseas_letf.py``), not from
Yahoo. This file used to fetch 7709/7747/7347 itself, which produced a second,
weaker set of figures for the same three funds: leverage pinned at the config's
``L`` (2) after CSOP moved to a flexible daily target on 2026-08-03, HKD
converted at a constant 7.8, and Yahoo ``totalAssets`` carried as if it were a
dated observation. The board refuses all three -- it leaves leverage and AUM
null until the issuer publishes them with a date -- so a notional built on them
here read as measured while resting on assumptions the collector had already
rejected. What survives the change is the ratio that needs none of them:
covered trading value over the same day's Korean cash turnover, the same
denominator the domestic single-stock rows use.
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


OVERSEAS_BOARD = ROOT / "../../public/data/overseas_letf_board_v1.json"


def _hk_tv_ratio_by_underlying(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per Korean underlying: the HK funds' turnover against KR cash turnover.

    Summed across funds on the same underlying because they share one
    denominator -- the board only fills this ratio for `kr_single_stock`, so an
    ADR or basket product never lands here. Only the newest observed day is
    summed: anchoring to whichever row the config happened to list first let a
    stale fund set `as_of` and exclude the current ones, publishing an old
    ratio as today's. Funds last seen on an earlier day are named in
    `excluded_other_date` rather than folded in silently.
    """
    usable = [r for r in rows if r.get("underlying") and r.get("tv_over_kr_cash_tv") is not None]
    newest: dict[str, str] = {}
    for r in usable:
        und, day = r["underlying"], r.get("observed_on") or ""
        if day > newest.get(und, ""):
            newest[und] = day

    out: dict[str, dict[str, Any]] = {}
    for r in usable:
        und = r["underlying"]
        bucket = out.setdefault(und, {"as_of": newest[und], "ratio": 0.0,
                                      "tickers": [], "excluded_other_date": []})
        if (r.get("observed_on") or "") != bucket["as_of"]:
            bucket["excluded_other_date"].append(
                {"ticker": r.get("ticker"), "date": r.get("observed_on")})
            continue
        bucket["ratio"] += float(r["tv_over_kr_cash_tv"])
        bucket["tickers"].append(r.get("ticker"))
    return out


def load_overseas_board(path: Path | None = None) -> dict[str, Any] | None:
    """The overseas board, or None when the daily collector has not run yet."""
    path = path or OVERSEAS_BOARD
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def hk_products_from_board(board: dict[str, Any] | None, cfg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Board rows for the configured HK tickers, in the config's order.

    `cfg` still decides which funds belong to this venue and carries the Korean
    underlying each one maps to; everything measured comes from the board. A
    fund the board has not observed yet keeps its identity and reports missing
    values rather than dropping out of the venue.
    """
    by_ticker: dict[str, dict[str, Any]] = {}
    for prod in (board or {}).get("products") or []:
        for listing in prod.get("listings") or []:
            if listing.get("venue") == "hk":
                by_ticker[str(listing.get("ticker"))] = prod

    out: list[dict[str, Any]] = []
    for p in cfg:
        ticker = p["ticker"]
        prod = by_ticker.get(ticker)
        latest = (prod or {}).get("latest") or {}
        aum_usd = latest.get("aum_usd")
        # Only the board's observed target counts. `leverage_ceiling` is a cap,
        # and multiplying AUM by a cap gives an upper bound, not an exposure.
        leverage = latest.get("leverage")
        notional = (
            None if aum_usd is None or leverage is None else abs(float(leverage)) * float(aum_usd)
        )
        # The board nulls `trading_value_usd` unless every trading currency
        # reported and fills `covered_trading_value_usd` with the subtotal of
        # the ones that did. Prefer the complete figure and carry the flag, so
        # a day when only 7747 of 7747/9747 reports is not published as the
        # fund's turnover without saying so.
        coverage_complete = bool(latest.get("coverage_complete"))
        tv_complete = latest.get("trading_value_usd")
        tv = (
            tv_complete
            if coverage_complete and tv_complete is not None
            else latest.get("covered_trading_value_usd")
        )
        # `latest` is what carries measurements. A product the board lists but
        # has never observed is not an observation, so quality keys on that
        # rather than on the product row merely existing.
        if not prod:
            quality, missing = "missing", "overseas_board_has_no_row_for_this_ticker"
        elif not latest:
            quality, missing = "missing", "overseas_board_product_has_no_observed_day"
        else:
            quality, missing = "observed", None
        out.append(
            {
                "ticker": ticker,
                "name": (prod or {}).get("name") or p.get("name"),
                "underlying": p.get("underlying"),
                "venue": "hk",
                "L": leverage,
                "L_ceiling": (prod or {}).get("leverage_ceiling") or p.get("L"),
                "L_flexible": bool(p.get("L_flexible")),
                "structure": (prod or {}).get("structure") or p.get("structure", "swap"),
                "direction": latest.get("direction") or p.get("direction"),
                "aum_usd": aum_usd,
                "aum_as_of": latest.get("aum_as_of"),
                "notional_exposure_usd": notional,
                "trading_value_usd": tv,
                "trading_value_coverage_complete": coverage_complete,
                "valued_listing_count": latest.get("valued_listing_count"),
                "expected_listing_count": latest.get("expected_listing_count"),
                # Needs no AUM, no target and no constant FX: the fund's own
                # turnover against the same day's Korean cash turnover. This is
                # the figure the domestic rows can actually be read next to.
                "tv_over_kr_cash_tv": latest.get("etf_to_kr_cash_tv_ratio"),
                # The board's trading day. It normally trails the KRX snapshot
                # by a session, so consumers must carry it rather than assume
                # the snapshot's own as_of.
                "observed_on": latest.get("date"),
                "stale": bool((prod or {}).get("stale")),
                "data_age_calendar_days": (prod or {}).get("data_age_calendar_days"),
                "kr_spot_impact": "indirect_swap",
                "quality": quality,
                "source": "overseas_letf_board_v1 (issuer + Yahoo listings)",
                "missing_reason": missing,
            }
        )
    return out


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

    hk_out = hk_products_from_board(load_overseas_board(), hk_products_cfg)

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
                "direction": p.get("direction")
                or ("inverse" if L < 0 else "long"),
                "structure": p.get("structure", "swap"),
                "aum_usd": aum_usd,
                "notional_exposure_usd": None if aum_usd is None else abs(L) * aum_usd,
                "kr_spot_impact": "regime_proxy_and_dealer_hedge",
                "yahoo": y,
                "quality": y.get("quality", "observed"),
                "source": y.get("source"),
                "channel_ko": (
                    "레버·인버스 ETF + 옵션 레짐. "
                    "스왑 상대·글로벌 데스크 헷지가 한국 링크로 번질 수 있음 (spillover)."
                ),
            }
        )

    def _sum_exp_strict(rows: list[dict[str, Any]], key: str = "notional_exposure_usd") -> float | None:
        """Sum, or None when nothing was observed.

        A venue whose every row is missing must not total 0.0: that reads as
        "no leverage here" when it means "not observed". Partial coverage still
        sums, and the per-row `quality`/`missing_reason` say what is absent.
        """
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return float(sum(vals)) if vals else None

    def _dir_split(rows: list[dict[str, Any]]) -> dict[str, float]:
        long_n = inv_n = 0.0
        for r in rows:
            n = r.get("notional_exposure_usd")
            if n is None:
                continue
            L = float(r.get("L") or 0)
            d = r.get("direction") or ("inverse" if L < 0 else "long")
            if d in ("inverse", "gobus_inverse_2x", "inverse_2x") or L < 0:
                inv_n += float(n)
            else:
                long_n += float(n)
        return {
            "long_notional_usd": round(long_n, 2),
            "inverse_notional_usd": round(inv_n, 2),
        }

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
        # usdhkd no longer converts anything: HK figures arrive from the board
        # already in USD, at the dated rate the collector used. Kept only so the
        # CLI flag and older snapshots stay readable.
        "fx": {"usdkrw": usdkrw, "usdhkd": usdhkd, "usdhkd_applies_to": []},
        "disclaimer_ko": (
            "HK·US 레버/인버스=스왑 합성, 코인=퍼프 OI. "
            "국내 cash LETF 회전율 식에 합산 금지. "
            "다만 헷지 데스크→KR 현물/선물 간접 압력(spillover)은 Distortion·Spillover 탭에서 반드시 표시. "
            "투자 권유 아님."
        ),
        "hedge_channel_ko": (
            "홍콩/미국 레버 펀드·옵션 레짐 변화 → 스왑 상대(한국·글로벌 기관) 헷지 요청 → "
            "국내 현물·선물·국내 LETF에 압력이 붙을 수 있음 (유튜브 wag-the-dog reverse 계열)."
        ),
        "hk": {
            "products": hk_out,
            # None (not 0.0) while CSOP publishes no dated AUM and no daily
            # target: the exposure is unobserved, not absent.
            "notional_exposure_usd_sum": _sum_exp_strict(hk_out),
            "direction_split": _dir_split(hk_out),
            # Observed and denominated like the domestic single-stock rows, so
            # this is what the 수급 불균형 table can put beside them.
            "tv_over_kr_cash_tv_by_underlying": _hk_tv_ratio_by_underlying(hk_out),
            "source": "overseas_letf_board_v1 (build_overseas_letf.py)",
            "note_ko": (
                "AUM·배율은 운용사가 기준일과 함께 공개한 값만 사용한다. "
                "CSOP는 2026-08-03부터 가변 목표라 목표 미공개 구간에서는 노셔널이 비어 있다. "
                "거래대금 비율은 그 세 가지 가정 없이 관측된다."
            ),
        },
        "crypto": {
            "products": crypto_out,
            "open_interest_notional_usd_sum": _sum_exp_strict(
                crypto_out, "open_interest_notional_usd"
            ),
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
            # Strict, like HK: a total Yahoo failure must not total 0.0 and
            # read as "no US levered ETFs", and the UI's 미관측 branch is
            # unreachable for this slot while a zero is published instead.
            "notional_exposure_usd_sum": _sum_exp_strict(us_out),
            "direction_split": _dir_split(us_out),
            "source": "Yahoo Finance",
            "note_ko": "SOXL/SOXS·KORU·TQQQ/SQQQ 등. 옵션 보드(us_regime)와 함께 Global Spillover에서 읽음.",
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
    hk_sum = data["hk"]["notional_exposure_usd_sum"]
    print(f"  HK notional USD: {'unobserved (no dated AUM / target)' if hk_sum is None else format(hk_sum, ',.0f')}")
    print(f"  Crypto OI USD:   {data['crypto']['open_interest_notional_usd_sum']:,.0f}")
    print(f"  Crypto 24h vol:  {data['crypto']['quote_volume_24h_usd_sum']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
