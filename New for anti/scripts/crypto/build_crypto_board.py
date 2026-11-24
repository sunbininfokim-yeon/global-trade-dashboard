#!/usr/bin/env python3
"""Daily crypto board for the 시장 미시구조 › 가상자산 tab -> public/data/crypto_board_v1.json.

    python3 build_crypto_board.py            # refresh the recent window, keep the rest
    python3 build_crypto_board.py --backfill # full history (run once, locally)

Free, key-free sources only:

* Prices: Yahoo BTC-USD / ETH-USD (2014-/2017-), falling back to OKX spot candles and then
  CoinGecko when Yahoo throttles the runner. Upbit KRW daily candles (2017-09-) for the won price
  and won turnover.
* 원/달러: Yahoo KRW=X, falling back to open.er-api.com.
* 김치 프리미엄 = Upbit KRW close / (USD close x 원/달러) - 1. Both daily bars close at 00:00 UTC
  (09:00 KST); the FX close is New York's, so a day's premium carries up to a few hours of FX drift.
* Stablecoin supply: DefiLlama (all USD-pegged stablecoins, circulating, daily).
* BTC perpetuals: OKX open interest (USD) and daily volume, and the 8-hourly funding rate averaged
  per day. OKX serves 180 days of open interest and about three months of funding, so the file
  keeps what it has seen and the history grows.
* Upbit whole-market 24h turnover (all KRW pairs), one snapshot per run -- there is no history
  endpoint, so this series starts on the first run.

Every series merges into the existing file; a source that fails leaves its series as it was and
the run exits 1 after writing the rest.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "public" / "data" / "crypto_board_v1.json"
UA = {"User-Agent": "Mozilla/5.0 (crypto-board; public data)"}
ASSETS = {"BTC": {"yahoo": "BTC-USD", "okx": "BTC-USDT", "gecko": "bitcoin", "upbit": "KRW-BTC"},
          "ETH": {"yahoo": "ETH-USD", "okx": "ETH-USDT", "gecko": "ethereum", "upbit": "KRW-ETH"}}


def get(url: str, timeout: int = 40) -> Any:
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001 -- retried, then raised
            last = exc
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url[:90]}: {last}")


def day(ts_ms: float) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Sources -> {date: value}
# --------------------------------------------------------------------------

def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def yahoo_close(symbol: str, rng: str) -> dict[str, float]:
    # range=max silently switches to monthly bars; an explicit window keeps them daily
    now = int(time.time())
    start = 1262304000 if rng == "max" else now - 100 * 86400
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={now}&interval=1d")
    r = d["chart"]["result"][0]
    closes = r["indicators"]["quote"][0]["close"]
    return {day(t * 1000): round(c, 6) for t, c in zip(r["timestamp"], closes)
            if c is not None and day(t * 1000) < today()}


def okx_close(inst: str, backfill: bool) -> dict[str, float]:
    out: dict[str, float] = {}
    after = ""
    for _ in range(40 if backfill else 1):
        rows = get(f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1Dutc&limit=100{after}")["data"]
        for r in rows:
            if r[8] == "1":                        # confirmed (closed) bars only
                out[day(int(r[0]))] = float(r[4])
        if len(rows) < 100:
            break
        after = f"&after={rows[-1][0]}"
    return out


def gecko_close(coin: str) -> dict[str, float]:
    d = get(f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=90&interval=daily")
    return {day(t): round(v, 6) for t, v in d["prices"][:-1]}   # the last point is "now", not a close


def usd_close(a: dict[str, str], backfill: bool) -> tuple[dict[str, float], str]:
    tries: list[tuple[str, Callable[[], dict[str, float]]]] = [
        ("yahoo", lambda: yahoo_close(a["yahoo"], "max" if backfill else "3mo")),
        ("okx", lambda: okx_close(a["okx"], backfill)),
        ("coingecko", lambda: gecko_close(a["gecko"])),
    ]
    errs = []
    for name, fn in tries:
        try:
            got = fn()
            if len(got) > 5:
                return got, name
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{name}: {str(exc)[:80]}")
    raise RuntimeError("; ".join(errs))


def upbit_days(market: str, backfill: bool) -> dict[str, tuple[float, float]]:
    """date -> (KRW close, KRW turnover). Candle dates are UTC days (09:00 KST boundary)."""
    out: dict[str, tuple[float, float]] = {}
    to = ""
    for _ in range(20 if backfill else 1):
        rows = get(f"https://api.upbit.com/v1/candles/days?market={market}&count=200{to}")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for r in rows:
            d = r["candle_date_time_utc"][:10]
            if d < today:                          # today's candle is still open
                out[d] = (float(r["trade_price"]), round(float(r["candle_acc_trade_price"])))
        if len(rows) < 200:
            break
        to = f"&to={rows[-1]['candle_date_time_utc']}"
        time.sleep(0.15)
    return out


def usdkrw(backfill: bool) -> dict[str, float]:
    try:
        got = yahoo_close("KRW=X", "max" if backfill else "3mo")
        if got:
            return got
    except Exception:  # noqa: BLE001
        pass
    d = get("https://open.er-api.com/v6/latest/USD")
    return {day(d["time_last_update_unix"] * 1000): round(d["rates"]["KRW"], 4)}


def stablecoins() -> dict[str, float]:
    rows = get("https://stablecoins.llama.fi/stablecoincharts/all")
    return {day(int(r["date"]) * 1000): round(r["totalCirculatingUSD"]["peggedUSD"] / 1e9, 3)
            for r in rows if (r.get("totalCirculatingUSD") or {}).get("peggedUSD") and day(int(r["date"]) * 1000) < today()}


def okx_oi() -> dict[str, tuple[float, float]]:
    rows = get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy=BTC&period=1D")["data"]
    # [ts, open interest USD, volume USD]; the newest row is today, still moving
    return {day(int(r[0])): (round(float(r[1]) / 1e9, 3), round(float(r[2]) / 1e9, 3)) for r in rows[1:]}


def okx_funding() -> dict[str, float]:
    """Mean of the day's 8-hourly funding rates, in % per 8h."""
    per: dict[str, list[float]] = {}
    after = ""
    for _ in range(4):
        rows = get(f"https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100{after}")["data"]
        for r in rows:
            per.setdefault(day(int(r["fundingTime"])), []).append(float(r["realizedRate"] or r["fundingRate"]) * 100)
        if len(rows) < 100:
            break
        after = f"&after={rows[-1]['fundingTime']}"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {d: round(sum(v) / len(v), 5) for d, v in per.items() if d < today and len(v) >= 3}


def upbit_turnover_now() -> tuple[str, float, int]:
    markets = [m["market"] for m in get("https://api.upbit.com/v1/market/all?isDetails=false") if m["market"].startswith("KRW-")]
    total = 0.0
    for i in range(0, len(markets), 100):
        for t in get("https://api.upbit.com/v1/ticker?markets=" + ",".join(markets[i:i + 100])):
            total += float(t.get("acc_trade_price_24h") or 0)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d"), round(total / 1e12, 3), len(markets)


# --------------------------------------------------------------------------

def merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    out = dict(old or {})
    out.update(new)
    return dict(sorted(out.items()))


def main() -> int:
    backfill = "--backfill" in sys.argv
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    series: dict[str, Any] = doc.get("series") or {}
    sources: dict[str, str] = doc.get("sources") or {}
    failed: list[str] = []

    def step(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- keep the rest, report at the end
            failed.append(f"{name}: {str(exc)[:200]}")

    fx: dict[str, float] = {}

    def do_fx() -> None:
        nonlocal fx
        series["usdkrw"] = merge(series.get("usdkrw"), usdkrw(backfill))
    step("usdkrw", do_fx)

    for sym, a in ASSETS.items():
        def do_usd(sym=sym, a=a) -> None:
            got, src = usd_close(a, backfill)
            series[f"{sym}_usd"] = merge(series.get(f"{sym}_usd"), got)
            sources[f"{sym}_usd"] = src
        step(f"{sym} USD", do_usd)

        def do_krw(sym=sym, a=a) -> None:
            got = upbit_days(a["upbit"], backfill)
            series[f"{sym}_krw"] = merge(series.get(f"{sym}_krw"), {d: v[0] for d, v in got.items()})
            series[f"{sym}_upbit_turnover_tn"] = merge(series.get(f"{sym}_upbit_turnover_tn"),
                                                       {d: round(v[1] / 1e12, 4) for d, v in got.items()})
        step(f"{sym} Upbit", do_krw)

    def do_stable() -> None:
        series["stablecoin_bn"] = merge(series.get("stablecoin_bn"), stablecoins())
    step("stablecoins", do_stable)

    def do_oi() -> None:
        got = okx_oi()
        series["btc_oi_bn"] = merge(series.get("btc_oi_bn"), {d: v[0] for d, v in got.items()})
        series["btc_perp_volume_bn"] = merge(series.get("btc_perp_volume_bn"), {d: v[1] for d, v in got.items()})
    step("OKX open interest", do_oi)

    def do_funding() -> None:
        series["btc_funding_pct"] = merge(series.get("btc_funding_pct"), okx_funding())
    step("OKX funding", do_funding)

    def do_upbit_total() -> None:
        d, tn, n = upbit_turnover_now()
        series["upbit_total_turnover_tn"] = merge(series.get("upbit_total_turnover_tn"), {d: tn})
        doc["upbit_markets"] = n
    step("Upbit turnover", do_upbit_total)

    # 김치 프리미엄: the FX close on or before the day (weekends carry Friday's)
    fxs = sorted((series.get("usdkrw") or {}).items())
    for sym in ASSETS:
        usd, krw = series.get(f"{sym}_usd") or {}, series.get(f"{sym}_krw") or {}
        prem, j, last_fx = {}, 0, None
        for d in sorted(set(usd) & set(krw)):
            while j < len(fxs) and fxs[j][0] <= d:
                last_fx = fxs[j][1]
                j += 1
            if last_fx and usd[d]:
                prem[d] = round((krw[d] / (usd[d] * last_fx) - 1) * 100, 3)
        series[f"{sym}_kimchi_pct"] = prem

    doc.update({
        "schema_version": "crypto_board_v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": sources,
        "series": series,
        "failed": failed,
        "notes_ko": {
            "kimchi": "업비트 원화 종가 / (달러 종가 × 원/달러) − 1. 코인 일봉은 둘 다 09:00 KST 마감, 환율은 뉴욕 종가라 몇 시간 차이가 있습니다.",
            "funding": "OKX BTC 무기한 선물 8시간 펀딩비의 일평균(%). 양수면 롱이 숏에게 지불 = 레버리지 롱 쏠림.",
            "oi": "OKX BTC 선물·무기한 미결제약정(10억 달러). 한 거래소 기준이라 시장 전체가 아니라 방향을 보는 용도입니다.",
            "stable": "달러 연동 스테이블코인 전체 유통량(10억 달러, DefiLlama). 코인 시장으로 들어온 달러 유동성입니다.",
            "upbit": "업비트 원화마켓 전 종목 24시간 거래대금(조원). 과거 이력 API가 없어 수집을 시작한 날부터 쌓입니다.",
        },
    })
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    n = {k: len(v) for k, v in series.items()}
    print(f"crypto board: {n}")
    for k in ("BTC_usd", "BTC_krw", "BTC_kimchi_pct", "stablecoin_bn", "btc_oi_bn", "btc_funding_pct", "upbit_total_turnover_tn"):
        s = series.get(k) or {}
        if s:
            d = max(s)
            print(f"  {k:24s} {d} {s[d]}")
    for f in failed:
        print(f"FAILED {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
