#!/usr/bin/env python3
"""Build public/data/equity_heatmap_v1.json -- per-constituent daily moves for
the macro monitor's index treemap (box size = market cap, colour = move).

Three free, key-less sources, each used only for what it is reliable at:

- Membership + market cap
  * Nasdaq-100: api.nasdaq.com list-type/nasdaq100 (the official member list).
  * S&P 500: datasets/s-and-p-500-companies constituents.csv (GICS sector),
    market cap from api.nasdaq.com's all-stock screener.
- Price moves: Yahoo v8 spark, 20 symbols per call, three months of daily
  closes: 1-day, 1-week (5 sessions back) and 1-month (21 sessions back).
  Nasdaq's screener lags a full session at some hours (checked 2026-11-04:
  it still showed AAPL's 11-02 close while the list-type feed and Yahoo had
  11-03), so moves never come from it -- otherwise the S&P map would be a day
  behind the Nasdaq-100 map for the same stock.

Market cap here is total company value, which is what the box is sized by.
The indices themselves are float-adjusted (S&P) or modified-cap (NDX), so
the box shares approximate rather than equal official index weights.

Dual share classes (GOOG/GOOGL, FOX/FOXA, NWS/NWSA) both report the whole
company's market cap; keeping both would draw Alphabet twice as big as it
is. The Class C/B line is dropped when its partner is in the same index.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "equity_heatmap_v1.json"
UA = {"User-Agent": "Mozilla/5.0 (equity-heatmap builder)", "Accept": "application/json,text/csv,*/*"}

NDX_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true"
SPX_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark?symbols={syms}&range=3mo&interval=1d"

DUP_CLASS = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}

GICS_KO = {
    "Information Technology": "정보기술", "Communication Services": "커뮤니케이션",
    "Consumer Discretionary": "경기소비재", "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어", "Financials": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Materials": "소재", "Utilities": "유틸리티", "Real Estate": "부동산",
}
# Nasdaq's own sector names, for Nasdaq-100 members that are not in the
# S&P 500 (ASML, ARM, PDD, ...) and so have no GICS row to borrow.
NASDAQ_SECTOR_KO = {
    "Technology": "정보기술", "Telecommunications": "커뮤니케이션",
    "Consumer Discretionary": "경기소비재", "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어", "Finance": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Basic Materials": "소재", "Utilities": "유틸리티", "Real Estate": "부동산",
}


def get(url: str, *, raw: bool = False, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                body = r.read()
            return body.decode("utf-8") if raw else json.loads(body)
        except Exception as exc:  # noqa: BLE001 -- retried, then re-raised
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def num(s) -> float | None:
    if s in (None, "", "NA"):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def norm(sym: str) -> str:
    """One spelling for a ticker across sources: BRK.B / BRK/B / BRK-B -> BRK.B."""
    return sym.strip().upper().replace("/", ".").replace("-", ".")


def short_name(name: str) -> str:
    for tail in (" Common Stock", " Class A", " Class B", " Class C", " Ordinary Shares",
                 " American Depositary Shares", " Capital Stock"):
        name = name.split(tail)[0]
    return name.strip().rstrip(",")


def spark(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 20):
        chunk = symbols[i:i + 20]
        ysyms = ",".join(s.replace(".", "-") for s in chunk)
        data = get(SPARK_URL.format(syms=ysyms))
        for s in chunk:
            row = data.get(s.replace(".", "-")) or {}
            ts, closes = row.get("timestamp") or [], row.get("close") or []
            pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
            if len(pts) >= 2:
                out[s] = {
                    "dates": [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t, _ in pts],
                    "close": [c for _, c in pts],
                }
        time.sleep(0.4)
    return out


def drop_dup_classes(syms: set[str]) -> set[str]:
    return {s for s in syms if not (s in DUP_CLASS and DUP_CLASS[s] in syms)}


def build_rows(members: dict[str, dict], prices: dict[str, dict], as_of: str) -> tuple[list[dict], list[str]]:
    rows, missing = [], []
    for sym in sorted(drop_dup_classes(set(members))):
        m, p = members[sym], prices.get(sym)
        if not p or not m.get("mc") or p["dates"][-1] != as_of:
            missing.append(sym)
            continue
        c = p["close"]
        rows.append({
            "s": sym, "n": m["n"], "sec": m["sec"], "mc": round(m["mc"] / 1e9, 2),
            "px": round(c[-1], 2),
            "d1": round((c[-1] / c[-2] - 1) * 100, 2),
            "w1": round((c[-1] / c[-6] - 1) * 100, 2) if len(c) >= 6 else None,
            "m1": round((c[-1] / c[-22] - 1) * 100, 2) if len(c) >= 22 else None,
        })
    return rows, missing


def main() -> int:
    screener = (get(SCREENER_URL).get("data") or {}).get("rows") or []
    scr = {norm(r["symbol"]): r for r in screener}

    gics = {norm(r["Symbol"]): r for r in csv.DictReader(io.StringIO(get(SPX_CSV_URL, raw=True)))}
    if len(gics) < 490:
        print(f"refusing: S&P constituent list has only {len(gics)} rows")
        return 1

    ndx_rows = (((get(NDX_URL).get("data") or {}).get("data")) or {}).get("rows") or []
    if len(ndx_rows) < 95:
        print(f"refusing: Nasdaq-100 list has only {len(ndx_rows)} rows")
        return 1

    def sector(sym: str) -> str:
        if sym in gics:
            return GICS_KO.get(gics[sym]["GICS Sector"], "기타")
        return NASDAQ_SECTOR_KO.get((scr.get(sym) or {}).get("sector") or "", "기타")

    ndx_members = {
        norm(r["symbol"]): {"n": short_name(r["companyName"]), "sec": sector(norm(r["symbol"])),
                            "mc": num(r.get("marketCap"))}
        for r in ndx_rows
    }
    spx_members = {
        sym: {"n": g["Security"], "sec": sector(sym), "mc": num((scr.get(sym) or {}).get("marketCap"))}
        for sym, g in gics.items()
    }

    prices = spark(sorted(set(ndx_members) | set(spx_members)))
    # The session everyone agrees on: the most common last date, so one
    # stale or halted ticker can't drag the whole map back a day.
    lasts = [p["dates"][-1] for p in prices.values()]
    as_of = max(set(lasts), key=lasts.count)

    out = {"schema": "equity_heatmap_v1", "as_of": as_of,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "note_ko": "박스 크기는 시가총액, 색은 전일 종가 대비 등락입니다. 지수의 실제 편입 비중(유동주식·수정시총)과는 조금 다를 수 있습니다.",
           "sources": {"membership": ["api.nasdaq.com nasdaq100", "datasets/s-and-p-500-companies"],
                       "market_cap": "api.nasdaq.com", "prices": "Yahoo Finance spark"},
           "indices": {}}
    for key, label, members in (("ndx", "나스닥100", ndx_members), ("spx", "S&P 500", spx_members)):
        rows, missing = build_rows(members, prices, as_of)
        if len(rows) < 0.9 * len(drop_dup_classes(set(members))):
            print(f"refusing: {key} only {len(rows)} usable rows; missing {missing[:20]}")
            return 1
        out["indices"][key] = {"label_ko": label, "n": len(rows), "missing": missing, "rows": rows}
        print(f"{key}: {len(rows)} rows, {len(missing)} missing {missing[:10]}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT} as_of {as_of}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
