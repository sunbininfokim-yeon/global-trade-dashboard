#!/usr/bin/env python3
"""Fetch live filings and run KFA analyze.

Examples:
  # SEC (no key)
  python3 fetch_live.py --ticker AAPL --print

  # OpenDART (needs DART_API_KEY)
  python3 fetch_live.py --dart-corp 00126380 --year 2024 --print
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dart_kfa.analyze import analyze_payload  # noqa: E402
from dart_kfa.fetch import DartApiError, api_key_from_env, fetch_fnltt_singl_acnt_all  # noqa: E402
from dart_kfa.fundamental_pack import attach_market_to_pack  # noqa: E402
from dart_kfa.market import QuoteError, fetch_yahoo_quote, market_multiples  # noqa: E402
from dart_kfa.sec_fetch import SecApiError, fetch_company_facts, ticker_to_cik  # noqa: E402
from dart_kfa.sec_xbrl import facts_to_fnltt_payload, shares_outstanding  # noqa: E402


def _attach_market(company: dict, ticker: str | None) -> None:
    if not ticker:
        return
    try:
        q = fetch_yahoo_quote(ticker)
    except QuoteError as e:
        company["market"] = {"ok": False, "reason": str(e)}
        return
    acc = company.get("accounts") or {}
    ma = company.get("ma_metrics") or {}

    def av(key: str):
        cell = acc.get(key) or {}
        return cell.get("value")

    mm = market_multiples(
        price=q.get("price"),
        shares_out=company.get("shares_out"),
        net_income=av("NET_INCOME"),
        equity=av("EQUITY"),
        ebitda=(ma.get("ebitda_proxy") or {}).get("value"),
        net_debt=(ma.get("net_debt") or {}).get("value"),
    )
    company["market"] = {"ok": True, "quote": q, "multiples": mm}
    if company.get("fundamental_pack"):
        company["fundamental_pack"] = attach_market_to_pack(
            company["fundamental_pack"],
            market=company["market"],
            valuation=company.get("valuation"),
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Live DART/SEC → KFA analyze")
    ap.add_argument("--ticker", help="US ticker (SEC companyfacts)")
    ap.add_argument("--dart-corp", help="OpenDART corp_code")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--fs", default="CFS")
    ap.add_argument("--reprt", default="11011")
    ap.add_argument("--industry", default=None, help="KSIC or NAICS hint, e.g. C261")
    ap.add_argument("--industry-kit", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-quote", action="store_true", help="Skip Yahoo price/PER")
    args = ap.parse_args()

    use_cache = not args.no_cache

    if args.ticker:
        try:
            meta = ticker_to_cik(args.ticker, use_cache=use_cache)
            facts = fetch_company_facts(meta["cik"], use_cache=use_cache)
            payload = facts_to_fnltt_payload(
                facts,
                ticker=meta["ticker"],
                cik=meta["cik"],
                asof_fy=args.year,
            )
            shares = shares_outstanding(facts, fy=payload.get("meta", {}).get("fy"))
            corp = {
                "name": meta.get("title") or meta.get("ticker"),
                "code": meta.get("ticker"),
                "corp_code": meta.get("cik"),
                "industry": args.industry,
                "industry_kit": args.industry_kit or "general",
            }
            company = analyze_payload(payload, corp=corp, shares_out=shares)
            company["source"] = "sec_companyfacts"
            if not args.no_quote:
                _attach_market(company, meta.get("ticker"))
        except (SecApiError, ValueError) as e:
            print(f"SEC error: {e}", file=sys.stderr)
            return 1

    elif args.dart_corp:
        if not api_key_from_env():
            print("DART_API_KEY not set. export DART_API_KEY=...", file=sys.stderr)
            return 1
        year = args.year or 2024
        try:
            payload = fetch_fnltt_singl_acnt_all(
                corp_code=args.dart_corp,
                bsns_year=year,
                reprt_code=args.reprt,
                fs_div=args.fs,
                use_cache=use_cache,
            )
            company = analyze_payload(
                payload,
                corp={
                    "corp_code": args.dart_corp,
                    "industry": args.industry,
                    "industry_kit": args.industry_kit,
                },
            )
            company["source"] = "opendart"
        except DartApiError as e:
            print(f"DART error: {e}", file=sys.stderr)
            return 1
    else:
        ap.print_help()
        return 2

    out = args.out or (
        ROOT / "cache" / f"live_{(args.ticker or args.dart_corp)}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(company, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.print:
        m = company.get("metrics") or {}
        ma = company.get("ma_metrics") or {}
        print(f"source={company.get('source')} corp={company.get('corp')}")
        print(f"parse={company.get('parse_status')}")
        for k in ("current_ratio", "debt_ratio", "roe", "operating_margin", "fcf", "inventory_turnover"):
            cell = m.get(k) or ma.get(k) or {}
            print(f"  {k}: {cell.get('value')} {cell.get('reason') or ''}")
        for k in ("gross_interest_bearing_debt", "cash_and_marketable_securities", "net_debt", "net_debt_to_ebitda"):
            cell = ma.get(k) or {}
            print(f"  {k}: {cell.get('value')} {cell.get('reason') or ''}")
        if company.get("shares_out"):
            print(f"  shares_out={company['shares_out']}")
        mk = company.get("market") or {}
        if mk.get("ok"):
            mm = mk.get("multiples") or {}
            q = mk.get("quote") or {}
            print(
                f"  market price={q.get('price')} mcap={mm.get('market_cap')} "
                f"PER={mm.get('per')} PBR={mm.get('pbr')} EV/EBITDA={mm.get('ev_ebitda')}"
            )
        fp = company.get("fundamental_pack") or {}
        if fp:
            print(f"  desk: {fp.get('headline_ko')}")
            for sc in fp.get("scorecard") or []:
                print(f"    [{sc.get('status')}] {sc.get('label_ko')}: {sc.get('primary')}")
        band = (company.get("valuation") or {}).get("value_band")
        print(f"  value_band={band}")
        seed = (company.get("assumption_defaults") or {}).get("seeded_from_statements")
        if seed:
            print(
                f"  seed capex/da/nwc/tax={seed.get('capex_to_sales')}/"
                f"{seed.get('da_to_sales')}/{seed.get('sales_to_nwc')}/{seed.get('tax_rate')} "
                f"tier={seed.get('quality_tier')}"
            )
        print(f"→ {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
