#!/usr/bin/env python3
"""Build real-data KOSPI investor×price tables.

Default: 시총 상위 N + 시총 100위 내 고변동 N (union). Live Naver/FDR only.

  python build_investor_price_levels.py --live --universe both --top 10 --pool 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.investor_price_levels import (  # noqa: E402
    KospiUniverseError,
    build_investor_price_levels_report,
    build_kospi_index_levels,
    markdown_investor_price_levels,
)


def main() -> int:
    """One listing fetch per run, shared by the levels universe and the holders block."""
    from market_microstructure import investor_price_levels as ipl

    ipl._LISTING_CACHE = {}
    try:
        return _main()
    finally:
        ipl._LISTING_CACHE = None


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--index-only", action="store_true",
                   help="Refresh only KOSPI index flows in an existing report; preserve ticker data")
    # 180 trading days ~ 8 months, so the UI's 6-month window is fully covered.
    # Naver serves 60 rows a request, so this costs 3 paged calls per ticker.
    p.add_argument("--page-size", type=int, default=250)  # one year of trading days
    p.add_argument("--bins", type=int, default=12)
    p.add_argument("--top", type=int, default=10, help="Marcap top-N and/or high-vol top-N")
    p.add_argument(
        "--pool",
        type=int,
        default=100,
        help="Marcap pool for high-vol screen (default 100)",
    )
    p.add_argument(
        "--universe",
        choices=["both", "high_vol", "marcap"],
        default="both",
        help="both=시총상위+시총pool내고변동 (default)",
    )
    p.add_argument(
        "--tickers",
        default=None,
        help="Optional override code:label,... (skips universe)",
    )
    p.add_argument(
        "--krx-month-paste",
        default=os.environ.get("KRX_MONTH_PASTE_DIR") or None,
        help="krx-month-paste checkout; KOSPI market flow then comes from the stock-scoped "
        "KRX 12008 export when present (default: $KRX_MONTH_PASTE_DIR, else Naver mobile JSON)",
    )
    p.add_argument("--print-stats", action="store_true")
    p.add_argument("--holders-only", action="store_true",
                   help="Refresh only kospi_holders_v1.json (foreign ownership + NPS room)")
    p.add_argument("--foreign-days", type=int, default=60,
                   help="Naver rows per ticker for foreign ownership; earlier days are kept from "
                   "the previous file, so a longer value is only needed once to backfill")
    args = p.parse_args()

    if not args.live:
        print("Use --live (real fetch only; no demo).", file=sys.stderr)
        return 2

    pairs: list[tuple[str, str]] | None = None
    if args.tickers:
        pairs = []
        for part in args.tickers.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                code, label = part.split(":", 1)
            else:
                code, label = part, part
            pairs.append((code.strip(), label.strip()))

    # The published index block: its stock-only days are carried forward when
    # today's source returns nothing, instead of the block blanking to missing.
    out = ROOT / "../../public/data" / "investor_price_levels_v1.json"
    previous_report = None
    previous_index_levels = None
    if out.is_file():
        try:
            previous_report = json.loads(out.read_text(encoding="utf-8"))
            previous_index_levels = previous_report.get("kospi_index_levels")
        except (json.JSONDecodeError, OSError, AttributeError):
            previous_report = None
            previous_index_levels = None

    if args.holders_only:
        return 0 if write_kospi_holders(ROOT / "../../public/data", foreign_days=args.foreign_days) else 1

    if args.index_only:
        if not isinstance(previous_report, dict) or not previous_report.get("tickers"):
            print("ERROR: --index-only requires an existing report with ticker data", file=sys.stderr)
            return 1
        index = build_kospi_index_levels(max_days=args.page_size, krx_root=args.krx_month_paste,
                                         previous=previous_index_levels)
        if index.get("quality") != "observed" or index.get("carried_forward_days", 0) >= index.get("n_days", 0):
            print("ERROR: no fresh index observations; existing report kept unchanged", file=sys.stderr)
            return 1
        # Do not refresh report-wide timestamps: ticker observations did not run.
        previous_report["kospi_index_levels"] = index
        out.write_text(json.dumps(previous_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (ROOT / "INVESTOR_PRICE_LEVELS.md").write_text(
            markdown_investor_price_levels(previous_report) + "\n", encoding="utf-8")
        print(f"Wrote KOSPI index only: {index['n_days']} days through {index['date_end']}; ticker data unchanged")
        return 0

    try:
        rep = build_investor_price_levels_report(
            pairs,
            page_size=args.page_size,
            n_bins=args.bins,
            kospi_top_n=args.top,
            universe_mode=args.universe if not pairs else "custom",
            high_vol_pool=args.pool,
            krx_root=args.krx_month_paste,
            previous_index_levels=previous_index_levels,
        )
    except KospiUniverseError as exc:
        message = f"{exc}; existing investor-price snapshot kept unchanged"
        print(f"ERROR: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=KOSPI universe unavailable::{escaped}", file=sys.stderr)
        return 1
    # Refuse to ship if everything missing
    ok_n = sum(1 for t in (rep.get("tickers") or {}).values() if t.get("quality") == "observed")
    if ok_n == 0 and (rep.get("kospi_index_levels") or {}).get("quality") != "observed":
        print("ERROR: no observed data — refuse to write demo snapshot", file=sys.stderr)
        return 1

    pub = ROOT / "../../public/data"
    pub.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = markdown_investor_price_levels(rep)
    (ROOT / "INVESTOR_PRICE_LEVELS.md").write_text(md + "\n", encoding="utf-8")
    print(f"Wrote {out} (observed tickers={ok_n})")
    # The holders file is a side product: a failure there must not stop the
    # levels snapshot from being committed, so it leaves a marker that the
    # workflow's last step turns into a red run after the commit.
    if not pairs and not write_kospi_holders(pub, foreign_days=args.foreign_days):
        (ROOT / "kospi_holders_failed.txt").write_text("see build log\n", encoding="utf-8")
    print(f"Wrote {ROOT / 'INVESTOR_PRICE_LEVELS.md'}")
    if args.print_stats:
        print(md)
    return 0 if not rep.get("errors") else 1


def write_kospi_holders(pub: Path, *, foreign_days: int = 60) -> bool:
    """코스피 보유 구조 + 국민연금 여력 (kospi_holders_v1.json). Never blocks the levels file."""
    import FinanceDataReader as fdr

    from market_microstructure import kospi_holders as kh
    from market_microstructure.investor_price_levels import (
        _kospi_common_listing, fetch_naver_investor_trend)

    path = pub / "kospi_holders_v1.json"
    previous = None
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None
    errors: list[str] = []
    try:
        snap = kh.fetch_nps_portfolio()
    except Exception as e:  # noqa: BLE001
        snap = None
        errors.append(f"nps portfolio: {type(e).__name__}: {e}")
    try:
        year_ends = kh.fetch_nps_year_ends(current_year=(snap or {}).get("month", "0000")[:4])
    except Exception as e:  # noqa: BLE001
        year_ends = None
        errors.append(f"nps yearly: {type(e).__name__}: {e}")
    # Market series from the December before the latest snapshot's year: the
    # daily path starts at that year end.
    year = int(((snap or {}).get("month") or f"{datetime.now().year}")[:4])
    start = f"{year - 1}-12-01"
    try:
        listing = _kospi_common_listing(minimum_n=100)
        close = lambda sym: fdr.DataReader(sym, start)["Close"]  # noqa: E731
        import requests

        from market_microstructure import nps_stocks as ns

        def get(url: str) -> requests.Response:
            # fund.nps.or.kr dropped a TLS handshake once on a runner
            # (SSLEOFError, 2026-11-19); two more tries, a few seconds apart.
            import time
            for attempt in range(3):
                try:
                    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
                    r.raise_for_status()
                    return r
                except (requests.ConnectionError, requests.Timeout):
                    if attempt == 2:
                        raise
                    time.sleep(5 * (attempt + 1))
            raise AssertionError("unreachable")

        try:
            links = ns.parse_holdings_links(get(ns.NPS_EQUITY_PAGE).text)
            if not links:
                errors.append("NPS holdings: no year-end file links on the page")
        except Exception as e:  # noqa: BLE001
            links = None
            errors.append(f"NPS holdings page: {type(e).__name__}: {e}")
        dart_key = next((os.environ[k].strip() for k in ("DART_API_KEY", "DART_API", "OPENDART_API_KEY")
                         if (os.environ.get(k) or "").strip()), None)
        if not dart_key:
            errors.append("DART key not set (DART_API_KEY); 5% reports kept from the previous file")
        corp_file = ROOT / "../../public/data/dart_corp_codes_v1.json"
        corp_index = json.loads(corp_file.read_text(encoding="utf-8")).get("index", {}) if corp_file.is_file() else {}
        rep = kh.build_report(
            listing=listing, fetch_trend=lambda c: fetch_naver_investor_trend(c, page_size=foreign_days),
            previous=previous, nps_snapshot=snap, year_ends=year_ends,
            holdings_links=links, fetch_file=lambda u: get(u).content, corp_index=corp_index,
            fetch_dart=(lambda c: ns.fetch_dart_majorstock(c, dart_key)) if dart_key else None,
            kospi=close("KS11"), acwi=close("ACWI"), usdkrw=close("USD/KRW"))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: kospi holders: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    rep["errors"] = errors + rep["errors"]
    if rep["foreign_ownership"].get("quality") != "observed" and rep["nps"].get("quality") == "missing":
        print("ERROR: kospi holders: nothing observed; existing file kept", file=sys.stderr)
        return False
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fo, nps = rep["foreign_ownership"], rep["nps"]
    print(f"Wrote {path}: foreign {(fo.get('latest') or {}).get('foreign_pct')}% "
          f"({len(fo.get('history') or [])} days) · NPS {(nps.get('now') or {}).get('weight_pct')}%")
    for e in rep["errors"]:
        print(f"WARN: {e}", file=sys.stderr)
    return not rep["errors"]


if __name__ == "__main__":
    raise SystemExit(main())
