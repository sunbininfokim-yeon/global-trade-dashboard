#!/usr/bin/env python3
"""Collect -> validate -> upsert -> publish overseas LETF data.

python build_overseas_letf.py --live --print-stats
python build_overseas_letf.py --cache-dir /tmp/letf_research --as-of 2026-09-04
No UI, credentials, exchange orders or original CSV/PDF files are published.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_microstructure.overseas_letf import (
    build_board, normalize_bars, number, parse_proshares_nav, parse_leverage_shares, parse_proshares_holdings,
    parse_themes_holdings, positive, upsert_history,
)

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "../../public/data"
ARCHIVE = ROOT / "data/overseas_letf"
FX_SYMBOLS = {"HKD": "HKD=X", "KRW": "KRW=X", "GBP": "GBPUSD=X", "EUR": "EURUSD=X"}
REFERENCES = {"000660.KS": "000660.KS", "005930.KS": "005930.KS", "SKHY": "SKHY", "NASDAQ_100": "^NDX"}


def read_history(path):
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def collect(registry, cache, as_of):
    """Best-effort sources; failures do not replace existing successful cache."""
    import requests
    import yfinance as yf
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache / "yf"))
    symbols = {l["yahoo"] for p in registry["products"] for l in p["listings"] if l.get("collect", True)}
    symbols.update(FX_SYMBOLS.values())
    symbols.update(REFERENCES.values())
    diagnostics = []
    start = (datetime.fromisoformat(as_of) - timedelta(days=110)).date().isoformat()
    end = (datetime.fromisoformat(as_of) + timedelta(days=1)).date().isoformat()

    def fetch_bars(symbol):
        try:
            h = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False, timeout=20)
            rows = [dict(date=str(ix.date()), close=number(v["Close"]), volume=number(v["Volume"]),
                         splits=number(v.get("Stock Splits"))) for ix, v in h.iterrows()]
            if not rows:
                raise ValueError("empty response")
            write_json(cache / (symbol + "_bars.json"), rows)
            return dict(source=symbol, status="ok", rows=len(rows), date_max=rows[-1]["date"])
        except Exception as exc:
            return dict(source=symbol, status="failed", error=type(exc).__name__ + ": " + str(exc)[:180])

    # Source requests are independent; archive writes remain serial.
    with ThreadPoolExecutor(max_workers=3) as pool:
        diagnostics.extend(pool.map(fetch_bars, sorted(symbols)))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    for p in registry["products"]:
        if p.get("nav_history_url"):
            try:
                response = session.get(p["source_urls"][0], timeout=25)
                response.raise_for_status()
                rows = parse_proshares_holdings(response.text, p, as_of)
                (cache / (p["product_id"] + "_page.html")).write_text(response.text, encoding="utf-8")
                diagnostics.append(dict(source=p["source_urls"][0], status="ok", rows=len(rows)))
            except Exception as exc:
                diagnostics.append(dict(source=p["source_urls"][0], status="failed", error=type(exc).__name__ + ": " + str(exc)[:180]))
        if p.get("issuer_api_url"):
            try:
                slug = p["source_urls"][0].rstrip("/").split("/")[-1]
                response = session.post(p["issuer_api_url"], json={"name": slug, "documentLocaleType": "en"}, timeout=25)
                response.raise_for_status()
                payload = response.json()
                aums, capital = parse_leverage_shares(payload, p, as_of)
                if not aums:
                    raise ValueError("No eligible issuer AUM history")
                write_json(cache / (slug + ".json"), payload)
                diagnostics.append(dict(source=p["issuer_api_url"], product_id=p["product_id"], status="ok", rows=len(aums)))
            except Exception as exc:
                diagnostics.append(dict(source=p["issuer_api_url"], product_id=p["product_id"], status="failed", error=type(exc).__name__ + ": " + str(exc)[:180]))
        for field, filename in (("holdings_url", p["product_id"] + "_holdings.raw"), ("nav_history_url", p["product_id"].lower() + "_nav.raw")):
            if not p.get(field):
                continue
            try:
                response = session.get(p[field], timeout=25)
                response.raise_for_status()
                text = response.text
                # Validate before replacing the last successful source file.
                if field == "holdings_url":
                    rows, _, rejected = parse_themes_holdings(text, p, as_of)
                    if not rows:
                        raise ValueError("no eligible holdings; " + str(rejected[:1]))
                else:
                    rows = parse_proshares_nav(text, p, as_of)
                    if not rows:
                        raise ValueError("no eligible NAV records")
                (cache / filename).write_text(text, encoding="utf-8")
                diagnostics.append(dict(source=p[field], status="ok", rows=len(rows)))
            except Exception as exc:
                diagnostics.append(dict(source=p[field], status="failed", error=type(exc).__name__ + ": " + str(exc)[:180]))
    return diagnostics


def build(args):
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    if args.as_of > today:
        raise ValueError("Future as-of date is not permitted")
    diagnostics = collect(registry, args.cache_dir, args.as_of) if args.live else []
    fx = {r["date"]: r["rates"] for r in read_history(args.archive_dir / "fx.jsonl.gz")}
    for currency, symbol in FX_SYMBOLS.items():
        path = args.cache_dir / (symbol + "_bars.json")
        if path.exists():
            for b in json.loads(path.read_text()):
                if b["date"] <= args.as_of and positive(b["close"]):
                    fx.setdefault(b["date"], {})[currency] = 1 / b["close"] if currency in {"HKD", "KRW"} else b["close"]
    observations, holdings, aums, returns, capital = [], [], [], [], []
    for p in registry["products"]:
        page = args.cache_dir / (p["product_id"] + "_page.html")
        if p.get("nav_history_url") and page.exists():
            try:
                holdings.extend(parse_proshares_holdings(page.read_text(), p, args.as_of))
            except ValueError as exc:
                diagnostics.append(dict(source=p["source_urls"][0], status="rejected", reason=str(exc)))
        if p.get("issuer_api_url"):
            slug = p["source_urls"][0].rstrip("/").split("/")[-1]
            path = args.cache_dir / (slug + ".json")
            if path.exists():
                try:
                    aa, cc = parse_leverage_shares(json.loads(path.read_text()), p, args.as_of)
                    aums.extend(aa)
                    if cc:
                        capital.append(cc)
                except (ValueError, KeyError, IndexError) as exc:
                    diagnostics.append(dict(source=p["issuer_api_url"], status="rejected", reason=str(exc)))
        for listing in p["listings"]:
            path = args.cache_dir / (listing["yahoo"] + "_bars.json")
            if not path.exists():
                diagnostics.append(dict(source=listing["listing_id"], status="missing", reason="no_listing_bars"))
                continue
            try:
                observations.extend(normalize_bars(p, listing, json.loads(path.read_text()), fx, as_of=args.as_of))
            except (ValueError, KeyError) as exc:
                diagnostics.append(dict(source=listing["listing_id"], status="rejected", reason=str(exc)))
        path = args.cache_dir / (p["product_id"] + "_holdings.raw")
        if p.get("holdings_url") and path.exists():
            try:
                hs, aa, rejected = parse_themes_holdings(path.read_text(), p, args.as_of)
                holdings.extend(hs)
                aums.extend(aa)
                diagnostics.extend(dict(source=p["holdings_url"], status="rejected", **r) for r in rejected)
            except (ValueError, KeyError) as exc:
                diagnostics.append(dict(source=p["holdings_url"], status="rejected", reason=str(exc)))
        path = args.cache_dir / (p["product_id"].lower() + "_nav.raw")
        if p.get("nav_history_url") and path.exists():
            try:
                aums.extend(parse_proshares_nav(path.read_text(), p, args.as_of))
            except (ValueError, KeyError) as exc:
                diagnostics.append(dict(source=p["nav_history_url"], status="rejected", reason=str(exc)))
    for reference, symbol in REFERENCES.items():
        path = args.cache_dir / (symbol + "_bars.json")
        if not path.exists():
            continue
        bars = sorted(json.loads(path.read_text()), key=lambda b: b["date"])
        for prev, current in zip(bars, bars[1:]):
            if positive(prev["close"]) and positive(current["close"]) and not current.get("splits") and current["date"] <= args.as_of:
                returns.append(dict(date=current["date"], previous_date=prev["date"], reference=reference,
                                    currency="KRW" if symbol.endswith(".KS") else "USD", return_value=current["close"] / prev["close"] - 1))
    for r in returns:
        r["return"] = r.pop("return_value")
    # Normalized archives are durable; failed collectors cannot erase old rows.
    manifests = {}
    for name, rows, keys in (("listings", observations, ("date", "listing_id")),
                             ("holdings", holdings, ("date", "product_id", "holding_id")),
                             ("aum", aums, ("date", "product_id")),
                             ("returns", returns, ("date", "reference")),
                             ("capital", capital, ("date", "product_id")),
                             ("fx", [dict(date=d, rates=v) for d, v in fx.items()], ("date",))):
        for row in rows:
            row.setdefault("as_of", row["date"])
            row.setdefault("quality", "estimated" if name == "returns" else "observed")
            row.setdefault("source", "Yahoo Finance daily close return" if name == "returns" else "Yahoo Finance daily FX")
            row.setdefault("source_unit", "decimal_return" if name == "returns" else "USD_per_currency_unit" if name == "fx" else row.get("currency", "USD"))
        path = args.archive_dir / (name + ".jsonl.gz")
        manifests[name] = dict(path=path.name, **upsert_history(path, rows, keys, replace_groups=("date", "product_id") if name == "holdings" else None))
        manifests[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    obs = read_history(args.archive_dir / "listings.jsonl.gz")
    hs = read_history(args.archive_dir / "holdings.jsonl.gz")
    aa = read_history(args.archive_dir / "aum.jsonl.gz")
    rr = read_history(args.archive_dir / "returns.jsonl.gz")
    fx = {r["date"]: r["rates"] for r in read_history(args.archive_dir / "fx.jsonl.gz")}
    capital = read_history(args.archive_dir / "capital.jsonl.gz")
    for p in registry["products"]:
        records = sorted((c for c in capital if c["product_id"] == p["product_id"] and c["date"] <= args.as_of), key=lambda c: c["date"])
        if records:
            p["capital_structure"] = records[-1]
            p["structure"] = records[-1]["structure"]
            p["structure_as_of"] = records[-1]["date"]
    cash = [json.loads(line) for line in args.kr_history.read_text().splitlines() if line.strip()] if args.kr_history.exists() else []
    board, history = build_board(registry, obs, hs, aa, fx, cash, rr, as_of=args.as_of, diagnostics=diagnostics)
    for p in board["products"]:
        latest = p["latest"]
        p["data_age_calendar_days"] = (datetime.fromisoformat(args.as_of) - datetime.fromisoformat(latest["date"])).days if latest else None
        p["stale"] = latest is None or p["data_age_calendar_days"] > 4
        p["aum_missing"] = p["latest_aum"] is None
    active_symbols = {l["yahoo"] for p in registry["products"] for l in p["listings"] if l.get("last_trade_date", "9999-12-31") >= args.as_of and l.get("collect", True)}
    fresh_cutoff = (datetime.fromisoformat(args.as_of) - timedelta(days=4)).date().isoformat()
    live_success = any(d["status"] == "ok" and d["source"] in active_symbols and d.get("date_max", "") >= fresh_cutoff for d in diagnostics)
    failed = args.live and not live_success
    board["pipeline"] = dict(status="failed" if failed else "partial" if any(d["status"] != "ok" for d in diagnostics) else "ok",
                             fresh_product_count=sum(not p["stale"] for p in board["products"]),
                             product_count=len(board["products"]), last_attempt_at=datetime.now(timezone.utc).isoformat(),
                             source_mode="live" if args.live else "cached_rebuild")
    board["pipeline"]["metadata_review_due"] = (datetime.fromisoformat(args.as_of) - datetime.fromisoformat(registry["verified_on"])).days > 30
    # Keep the table small; time series and listing detail are separate gzip assets.
    cutoff = (datetime.fromisoformat(args.as_of) - timedelta(days=120)).date().isoformat()
    board["groups"] = [g for g in board["groups"] if g["date"] == args.as_of]
    board["history_file"] = "overseas_letf_history_v1.jsonl.gz"
    board["listing_history_file"] = "overseas_letf_listings_v1.jsonl.gz"
    counts = upsert_history(args.archive_dir / "products.jsonl.gz", history, ("date", "product_id"))
    manifests["products"] = dict(path="products.jsonl.gz", **counts)
    manifests["products"]["sha256"] = hashlib.sha256((args.archive_dir / "products.jsonl.gz").read_bytes()).hexdigest()
    # Public history is a rolling export, not an append to an unbounded download.
    for filename, rows in ((board["history_file"], history), (board["listing_history_file"], obs)):
        payload = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n" for r in rows if cutoff <= r["date"] <= args.as_of)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir / filename
        tmp = target.with_name(filename + ".tmp")
        tmp.write_bytes(gzip.compress(payload.encode(), mtime=0))
        tmp.replace(target)
    write_json(args.output_dir / "overseas_letf_board_v1.json", board)
    write_json(args.archive_dir / "manifest.json", dict(schema_version="overseas-letf-manifest-v1", as_of=args.as_of, files=manifests))
    write_json(args.output_dir / "overseas_letf_pipeline_status_v1.json", dict(as_of=args.as_of, **board["pipeline"], diagnostics=diagnostics))
    if args.print_stats:
        print(json.dumps(dict(products=len(board["products"]), listing_rows=len(obs), product_rows=len(history), holdings_rows=len(hs), pipeline=board["pipeline"]), ensure_ascii=False))
    # A total live outage must fail the scheduled job after saving diagnostics.
    return 2 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    # Run after all venues close; before 22:00 UTC use the previous calendar day.
    now = datetime.now(timezone.utc)
    parser.add_argument("--as-of", default=(now - timedelta(days=int(now.hour < 22))).date().isoformat())
    parser.add_argument("--registry", type=Path, default=ROOT / "config/overseas_letf_universe.json")
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "overseas-letf-cache")
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=PUBLIC)
    parser.add_argument("--kr-history", type=Path, default=PUBLIC / "stock_letf_history_v1.jsonl")
    parser.add_argument("--print-stats", action="store_true")
    return build(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
