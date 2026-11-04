#!/usr/bin/env python3
"""Build public/data/equity_heatmap_v1.json -- per-constituent moves for the
macro monitor's index treemaps (US, Korea, Japan, Taiwan).

Free, key-less sources, each used only for what it is reliable at:

Membership (+ size)
  * Nasdaq-100: api.nasdaq.com list-type/nasdaq100; market cap from the same.
  * S&P 500: datasets/s-and-p-500-companies constituents.csv (GICS sector),
    market cap from api.nasdaq.com's all-stock screener.
  * KOSPI / KOSDAQ: m.stock.naver.com market-value ranking, top 200 / 100
    common stocks -- KOSPI has ~800 names and the long tail would be a field
    of one-pixel boxes, so the map is labelled "시총 상위 N", not "전 종목".
  * Nikkei 225: Nikkei's own weight file (nikkei_stock_average_weight_jp.csv,
    Shift-JIS) -- codes, sector, and the official weight. The Nikkei is
    price-weighted, so its boxes are sized by that weight, not market cap:
    Fast Retailing is ~10% of the index while being a fraction of Toyota's
    value, and a cap-sized map would misstate what moves the index.
  * TAIEX: TWSE open data company list (t187ap03_L), ranked by Yahoo market
    cap, top 150.
  Market cap for KR/JP/TW and the Korean sector come from Yahoo's v7 quote /
  quoteSummary, which need a session crumb (fetched once per run). Korean
  sectors are cached in config/equity_sector_cache_v1.json since they almost
  never change -- only symbols missing from the cache are looked up.

Price moves, every market: Yahoo v8 spark, 20 symbols per call, three months
of daily closes -> 1-day, 1-week (5 sessions) and 1-month (21 sessions).
Nasdaq's screener lags a full session at some hours (checked 2026-11-04: it
still showed AAPL's 11-02 close while Yahoo had 11-03), so moves never come
from it.

Dual share classes (GOOG/GOOGL, FOX/FOXA, NWS/NWSA) both report the whole
company's market cap; the Class C/B line is dropped when its partner is in
the same index so Alphabet isn't drawn twice its size.

Each market is built independently: if Naver or Nikkei is down, that index
keeps yesterday's block (flagged stale) and the rest still refresh.
"""
from __future__ import annotations

import csv
import http.cookiejar
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "public" / "data" / "equity_heatmap_v1.json"
SECTOR_CACHE = Path(__file__).resolve().parent / "config" / "equity_sector_cache_v1.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

NDX_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true"
SPX_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
NAVER_URL = "https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100"
NIKKEI_CSV_URL = "https://indexes.nikkei.co.jp/nkave/archives/file/nikkei_stock_average_weight_jp.csv"
TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark?symbols={syms}&range=3mo&interval=1d"

DUP_CLASS = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}

GICS_KO = {
    "Information Technology": "정보기술", "Communication Services": "커뮤니케이션",
    "Consumer Discretionary": "경기소비재", "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어", "Financials": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Materials": "소재", "Utilities": "유틸리티", "Real Estate": "부동산",
}
NASDAQ_SECTOR_KO = {
    "Technology": "정보기술", "Telecommunications": "커뮤니케이션",
    "Consumer Discretionary": "경기소비재", "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어", "Finance": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Basic Materials": "소재", "Utilities": "유틸리티", "Real Estate": "부동산",
}
# Yahoo/Morningstar sector names (Korean constituents).
YAHOO_SECTOR_KO = {
    "Technology": "정보기술", "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재",
    "Healthcare": "헬스케어", "Financial Services": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Basic Materials": "소재", "Utilities": "유틸리티", "Real Estate": "부동산",
}
# Nikkei's six-way セクター grouping, as published in its weight file.
NIKKEI_SECTOR_KO = {
    "技術": "기술", "金融": "금융", "消費": "소비", "素材": "소재",
    "資本財・その他": "자본재·기타", "運輸・公共": "운수·공공",
}
# TWSE 產業別 codes.
TWSE_INDUSTRY_KO = {
    "01": "시멘트", "02": "식품", "03": "플라스틱", "04": "섬유", "05": "전기기계", "06": "전선·케이블",
    "08": "유리·세라믹", "09": "제지", "10": "철강", "11": "고무", "12": "자동차", "14": "건설",
    "15": "해운", "16": "관광·외식", "17": "금융·보험", "18": "유통", "19": "종합", "20": "기타",
    "21": "화학", "22": "바이오·의료", "23": "에너지", "24": "반도체", "25": "컴퓨터·주변기기",
    "26": "광전자", "27": "통신·네트워크", "28": "전자부품", "29": "전자유통", "30": "IT서비스",
    "31": "기타전자", "32": "문화·콘텐츠", "33": "농업기술", "34": "전자상거래", "35": "친환경",
    "36": "디지털·클라우드", "37": "스포츠·레저", "38": "생활용품", "91": "예탁증서",
}

_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))
_OPENER.addheaders = [("User-Agent", UA), ("Accept", "application/json,text/csv,*/*")]
_CRUMB: str | None = None


def get(url: str, *, raw: bool = False, binary: bool = False, tries: int = 4):
    last = None
    for i in range(tries):
        try:
            with _OPENER.open(url, timeout=40) as r:
                body = r.read()
            if binary:
                return body
            return body.decode("utf-8") if raw else json.loads(body)
        except Exception as exc:  # noqa: BLE001 -- retried, then re-raised
            last = exc
            # Yahoo answers bursts with 429 for a minute or so; a short
            # retry just extends the block.
            time.sleep((30 if getattr(exc, "code", None) == 429 else 2) * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def crumb() -> str:
    global _CRUMB
    if _CRUMB is None:
        try:
            _OPENER.open("https://fc.yahoo.com", timeout=15)
        except Exception:  # noqa: BLE001 -- 404 is expected; it only sets the cookie
            pass
        _CRUMB = get("https://query1.finance.yahoo.com/v1/test/getcrumb", raw=True).strip()
    return _CRUMB


def yahoo_quotes(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 100):
        chunk = ",".join(symbols[i:i + 100])
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(chunk)}&crumb={urllib.parse.quote(crumb())}"
        for q in (get(url).get("quoteResponse") or {}).get("result") or []:
            out[q["symbol"]] = q
        time.sleep(0.4)
    return out


def yahoo_sector(sym: str) -> str | None:
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(sym)}?modules=assetProfile&crumb={urllib.parse.quote(crumb())}"
    try:
        res = (get(url, tries=2).get("quoteSummary") or {}).get("result") or []
        return ((res[0] if res else {}).get("assetProfile") or {}).get("sector")
    except RuntimeError:
        return None


def num(s) -> float | None:
    if s in (None, "", "NA", "N/A"):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def norm(sym: str) -> str:
    """One spelling for a US ticker across sources: BRK.B / BRK/B / BRK-B -> BRK.B."""
    return sym.strip().upper().replace("/", ".").replace("-", ".")


def short_name(name: str) -> str:
    for tail in (" Common Stock", " Class A", " Class B", " Class C", " Ordinary Shares",
                 " American Depositary Shares", " Capital Stock"):
        name = name.split(tail)[0]
    return name.strip().rstrip(",")


def spark(ysyms: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ysyms), 20):
        chunk = ysyms[i:i + 20]
        try:
            data = get(SPARK_URL.format(syms=urllib.parse.quote(",".join(chunk))))
        except RuntimeError as exc:
            print(f"  spark chunk failed ({chunk[0]}..): {exc}")
            continue
        for s in chunk:
            row = data.get(s) or {}
            ts, closes = row.get("timestamp") or [], row.get("close") or []
            pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
            if len(pts) >= 2:
                gmt = (row.get("meta") or {}).get("gmtoffset") or 0
                out[s] = {
                    # Exchange-local date: an Asian session stamped in UTC
                    # lands on the previous calendar day otherwise.
                    "dates": [datetime.fromtimestamp(t + gmt, timezone.utc).date().isoformat() for t, _ in pts],
                    "close": [c for _, c in pts],
                }
        time.sleep(1.0)
    return out


def finish_index(members: dict[str, dict], prices: dict[str, dict], *, size_key: str = "mc") -> dict:
    """members: sym -> {n, sec, y (yahoo symbol), mc?, w?, l?}."""
    lasts = [prices[m["y"]]["dates"][-1] for m in members.values() if m["y"] in prices]
    if not lasts:
        raise RuntimeError("no prices at all")
    as_of = max(set(lasts), key=lasts.count)
    rows, missing = [], []
    for sym in sorted(members):
        m, p = members[sym], prices.get(members[sym]["y"])
        if not p or not m.get(size_key) or p["dates"][-1] != as_of:
            missing.append(sym)
            continue
        c = p["close"]
        row = {
            "s": sym, "n": m["n"], "sec": m["sec"],
            "px": round(c[-1], 2),
            "d1": round((c[-1] / c[-2] - 1) * 100, 2),
            "w1": round((c[-1] / c[-6] - 1) * 100, 2) if len(c) >= 6 else None,
            "m1": round((c[-1] / c[-22] - 1) * 100, 2) if len(c) >= 22 else None,
        }
        if m.get("mc"):
            row["mc"] = round(m["mc"] / 1e9, 2)   # billions, local currency
        if m.get("w"):
            row["w"] = round(m["w"], 4)
        if m.get("l"):
            row["l"] = m["l"]
        rows.append(row)
    if len(rows) < 0.85 * len(members):
        raise RuntimeError(f"only {len(rows)}/{len(members)} usable rows; missing {missing[:15]}")
    return {"as_of": as_of, "n": len(rows), "missing": missing, "rows": rows}


# ---------------------------------------------------------------- markets

def build_us() -> dict[str, dict]:
    screener = (get(SCREENER_URL).get("data") or {}).get("rows") or []
    scr = {norm(r["symbol"]): r for r in screener}
    gics = {norm(r["Symbol"]): r for r in csv.DictReader(io.StringIO(get(SPX_CSV_URL, raw=True)))}
    if len(gics) < 490:
        raise RuntimeError(f"S&P constituent list has only {len(gics)} rows")
    ndx_rows = (((get(NDX_URL).get("data") or {}).get("data")) or {}).get("rows") or []
    if len(ndx_rows) < 95:
        raise RuntimeError(f"Nasdaq-100 list has only {len(ndx_rows)} rows")

    def sector(sym: str) -> str:
        if sym in gics:
            return GICS_KO.get(gics[sym]["GICS Sector"], "기타")
        return NASDAQ_SECTOR_KO.get((scr.get(sym) or {}).get("sector") or "", "기타")

    def dedupe(d: dict) -> dict:
        return {s: v for s, v in d.items() if not (s in DUP_CLASS and DUP_CLASS[s] in d)}

    ndx = dedupe({norm(r["symbol"]): {"n": short_name(r["companyName"]), "sec": sector(norm(r["symbol"])),
                                      "mc": num(r.get("marketCap")), "y": norm(r["symbol"]).replace(".", "-")}
                  for r in ndx_rows})
    spx = dedupe({sym: {"n": g["Security"], "sec": sector(sym), "mc": num((scr.get(sym) or {}).get("marketCap")),
                        "y": sym.replace(".", "-")} for sym, g in gics.items()})
    prices = spark(sorted({m["y"] for m in (*ndx.values(), *spx.values())}))
    return {
        "ndx": {"label_ko": "나스닥100", "ccy": "USD", "size_by": "mc", **finish_index(ndx, prices)},
        "spx": {"label_ko": "S&P 500", "ccy": "USD", "size_by": "mc", **finish_index(spx, prices)},
    }


def build_kr() -> dict[str, dict]:
    cache = json.loads(SECTOR_CACHE.read_text(encoding="utf-8")) if SECTOR_CACHE.exists() else {}

    def top(mkt: str, n: int, suffix: str) -> dict[str, dict]:
        stocks, page = [], 1
        while len(stocks) < n and page <= 5:
            batch = get(NAVER_URL.format(mkt=mkt, page=page)).get("stocks") or []
            if not batch:
                break
            stocks += [s for s in batch if s.get("stockEndType") == "stock"]
            page += 1
        if len(stocks) < n * 0.9:
            raise RuntimeError(f"Naver {mkt} ranking returned {len(stocks)} stocks")
        return {s["itemCode"]: {"n": s["stockName"], "l": s["stockName"], "y": s["itemCode"] + suffix,
                                "mc": (num(s.get("marketValue")) or 0) * 1e8}   # 억원 -> KRW
                for s in stocks[:n]}

    kospi, kosdaq = top("KOSPI", 200, ".KS"), top("KOSDAQ", 100, ".KQ")
    allm = {**kospi, **kosdaq}
    todo = [m["y"] for m in allm.values() if m["y"] not in cache]
    for i, y in enumerate(todo):
        sec = yahoo_sector(y)
        if sec:
            cache[y] = sec
        time.sleep(0.25)
        if i % 50 == 49:
            print(f"  sector lookups {i + 1}/{len(todo)}")
    if todo:
        SECTOR_CACHE.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for m in allm.values():
        m["sec"] = YAHOO_SECTOR_KO.get(cache.get(m["y"]) or "", "기타")
    prices = spark(sorted(m["y"] for m in allm.values()))
    return {
        "kospi": {"label_ko": "코스피 시총 상위 200", "ccy": "KRW", "size_by": "mc", **finish_index(kospi, prices)},
        "kosdaq": {"label_ko": "코스닥 시총 상위 100", "ccy": "KRW", "size_by": "mc", **finish_index(kosdaq, prices)},
    }


def build_jp() -> dict[str, dict]:
    text = get(NIKKEI_CSV_URL, binary=True).decode("shift_jis", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) < 220:
        raise RuntimeError(f"Nikkei weight file has {len(rows)} rows")
    members = {}
    for r in rows:
        code = (r.get("コード") or "").strip()
        if not code:
            continue
        sec = (r.get("セクター") or "").strip()
        members[code] = {"n": (r.get("社名") or "").strip(), "l": (r.get("社名") or "").strip(),
                         "sec": NIKKEI_SECTOR_KO.get(sec, sec or "기타"),
                         "w": num(r.get("ウエート")), "y": f"{code}.T"}
    quotes = yahoo_quotes([m["y"] for m in members.values()])
    for m in members.values():
        m["mc"] = (quotes.get(m["y"]) or {}).get("marketCap")
    prices = spark(sorted(m["y"] for m in members.values()))
    weight_date = (rows[0].get("日付") or "").strip().replace("/", "-")
    return {"nikkei": {"label_ko": "닛케이225", "ccy": "JPY", "size_by": "w", "weight_as_of": weight_date,
                       **finish_index(members, prices, size_key="w")}}


def build_tw() -> dict[str, dict]:
    listed = get(TWSE_LIST_URL)
    if len(listed) < 900:
        raise RuntimeError(f"TWSE company list has {len(listed)} rows")
    info = {r["公司代號"].strip(): r for r in listed if r.get("公司代號", "").strip().isdigit()}
    quotes = yahoo_quotes([f"{c}.TW" for c in info])
    ranked = sorted(((q.get("marketCap") or 0, s) for s, q in quotes.items()), reverse=True)[:150]
    members = {}
    for mc, ysym in ranked:
        code = ysym.split(".")[0]
        r = info[code]
        name = r.get("公司簡稱", "").strip() or code
        members[code] = {"n": name, "l": name, "mc": mc, "y": ysym,
                         "sec": TWSE_INDUSTRY_KO.get(r.get("產業別", "").strip(), "기타")}
    prices = spark(sorted(m["y"] for m in members.values()))
    return {"taiex": {"label_ko": "대만 가권 시총 상위 150", "ccy": "TWD", "size_by": "mc", **finish_index(members, prices)}}


def main() -> int:
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    indices: dict[str, dict] = {}
    errors = {}
    for name, fn, keys in (("us", build_us, ("ndx", "spx")), ("kr", build_kr, ("kospi", "kosdaq")),
                           ("jp", build_jp, ("nikkei",)), ("tw", build_tw, ("taiex",))):
        try:
            got = fn()
            indices.update(got)
            for k, v in got.items():
                print(f"{k}: {v['n']} rows as_of {v['as_of']}, missing {len(v['missing'])} {v['missing'][:8]}")
        except Exception as exc:  # noqa: BLE001 -- isolate markets from each other
            errors[name] = str(exc)[:300]
            print(f"{name} FAILED: {exc}")
            for k in keys:
                if k in (prev.get("indices") or {}):
                    old = prev["indices"][k]
                    indices[k] = {**old, "as_of": old.get("as_of") or prev.get("as_of"), "stale": True}
    if not indices:
        print("refusing: every market failed")
        return 1

    out = {"schema": "equity_heatmap_v1",
           "as_of": (indices.get("spx") or next(iter(indices.values())))["as_of"],
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "note_ko": "색은 전일 종가 대비 등락입니다. 박스 크기는 시가총액(닛케이225는 공식 편입 비중)이라 유동주식·수정시총 기준인 지수 비중과는 조금 다를 수 있습니다.",
           "sources": {"membership": ["api.nasdaq.com nasdaq100", "datasets/s-and-p-500-companies",
                                      "m.stock.naver.com", "indexes.nikkei.co.jp weight csv", "openapi.twse.com.tw"],
                       "market_cap": "api.nasdaq.com (US), Yahoo Finance (KR/JP/TW)", "prices": "Yahoo Finance spark"},
           "errors": errors, "indices": indices}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
