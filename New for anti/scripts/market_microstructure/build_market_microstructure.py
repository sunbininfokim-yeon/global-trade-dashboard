#!/usr/bin/env python3
"""Build market_microstructure_v1.json (+ TABLES.md).

Live:
  export KRX_API=...   # optional; Cloudflare secret name
  python build_market_microstructure.py --live --source auto --print-stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.ai_casino_brief import (  # noqa: E402
    build_ai_casino_brief,
    markdown_ai_casino_brief,
)
from market_microstructure.engine import build_snapshot, load_json, markdown_tables  # noqa: E402


def _fetch_trading_share() -> dict:
    """FDR: cash vs levered/inverse ETF turnover shares (Amount unit=백만원 for ETF)."""
    import FinanceDataReader as fdr

    unit = 1_000_000.0
    etfs = fdr.StockListing("ETF/KR")
    kospi = fdr.StockListing("KOSPI")
    kosdaq = fdr.StockListing("KOSDAQ")
    lev = etfs[etfs["Name"].astype(str).str.contains("레버리지|인버스", na=False)]
    ss = etfs[etfs["Name"].astype(str).str.contains("단일종목", na=False)]
    kospi_tv = float(kospi["Amount"].sum())
    kosdaq_tv = float(kosdaq["Amount"].sum())
    etf_tv = float(etfs["Amount"].sum()) * unit
    lev_tv = float(lev["Amount"].sum()) * unit
    ss_tv = float(ss["Amount"].sum()) * unit
    return {
        "kospi_jo": round(kospi_tv / 1e12, 2),
        "kosdaq_jo": round(kosdaq_tv / 1e12, 2),
        "etf_jo": round(etf_tv / 1e12, 2),
        "lev_jo": round(lev_tv / 1e12, 2),
        "ss_jo": round(ss_tv / 1e12, 2),
        "lev_of_etf_pct": round(100.0 * lev_tv / etf_tv, 1) if etf_tv else None,
        "lev_of_kospi_pct": round(100.0 * lev_tv / kospi_tv, 1) if kospi_tv else None,
        "lev_of_cash_pct": round(100.0 * lev_tv / (kospi_tv + kosdaq_tv), 1)
        if (kospi_tv + kosdaq_tv)
        else None,
        "ss_of_kospi_pct": round(100.0 * ss_tv / kospi_tv, 2) if kospi_tv else None,
        "source": "FinanceDataReader ETF/KR Amount(백만원) + KOSPI/KOSDAQ Amount",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--day",
        type=Path,
        default=ROOT / "tests/fixtures/demo_day.json",
        help="Day input JSON (fixture or live export)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Fetch KR day + HK/crypto venues, then build",
    )
    p.add_argument(
        "--source",
        choices=["auto", "krx", "fdr"],
        default="auto",
        help="KR live source: auto uses env KRX_API when present",
    )
    p.add_argument("--bas-dd", default=None, help="KRX basDd YYYYMMDD")
    p.add_argument("--fx", type=float, default=1400.0)
    p.add_argument("--usdhkd", type=float, default=7.8)
    p.add_argument(
        "--skip-external",
        action="store_true",
        help="Do not fetch HK/Yahoo + Binance venues",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/market_microstructure_v1.json",
    )
    p.add_argument(
        "--tables",
        type=Path,
        default=ROOT / "TABLES.md",
        help="Markdown tables path",
    )
    p.add_argument(
        "--brief",
        type=Path,
        default=ROOT / "../../public/data/ai_casino_brief_v1.json",
        help="AI Casino–style brief JSON",
    )
    p.add_argument(
        "--brief-md",
        type=Path,
        default=ROOT / "AI_CASINO_BRIEF.md",
        help="AI Casino–style brief markdown",
    )
    p.add_argument(
        "--skip-extras",
        action="store_true",
        help="Skip Naver deposit/credit, KOSPI flows, LETF categories, shorts",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if args.live:
        from fetch_kr_live import build_day

        day = build_day(
            source=args.source,
            fx_usdkrw=args.fx,
            bas_dd=args.bas_dd,
            skip_extras=args.skip_extras,
        )
        if not args.skip_external:
            from fetch_external_venues import build_external_venues

            day["external_venues"] = build_external_venues(
                usdkrw=args.fx, usdhkd=args.usdhkd
            )
            ext_path = ROOT / "tests/fixtures/external_venues.json"
            ext_path.write_text(
                json.dumps(day["external_venues"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Fetched external venues → {ext_path}")
        try:
            day["trading_share"] = _fetch_trading_share()
        except Exception as e:  # noqa: BLE001
            print(f"trading_share skip: {e}")
        live_path = ROOT / "tests/fixtures/live_day.json"
        live_path.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Fetched live day mode={day.get('source_mode')} → {live_path}")
    else:
        day = load_json(args.day)
        # optional attach saved external fixture
        ext_path = ROOT / "tests/fixtures/external_venues.json"
        if "external_venues" not in day and ext_path.exists() and not args.skip_external:
            day["external_venues"] = load_json(ext_path)
        if "trading_share" not in day:
            try:
                day["trading_share"] = _fetch_trading_share()
            except Exception:
                pass
        if not args.skip_extras and "public_extras" not in day:
            try:
                from fetch_kr_live import _attach_public_extras

                _attach_public_extras(day)
            except Exception as e:  # noqa: BLE001
                print(f"public_extras skip: {e}")

    snap = build_snapshot(day)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = markdown_tables(snap)
    args.tables.write_text(md, encoding="utf-8")

    brief = build_ai_casino_brief(snap, day=day)
    args.brief.parent.mkdir(parents=True, exist_ok=True)
    args.brief.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    brief_md = markdown_ai_casino_brief(brief)
    args.brief_md.write_text(brief_md, encoding="utf-8")

    if args.print_stats:
        print(brief_md)
        print("---")
        print(md)
    print(f"Wrote {args.out}")
    print(f"Wrote {args.tables}")
    print(f"Wrote {args.brief}")
    print(f"Wrote {args.brief_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
