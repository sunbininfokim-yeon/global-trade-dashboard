#!/usr/bin/env python3
"""Build dart_universe_v1.json from universe_seed fixtures and/or live OpenDART."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dart_kfa.analyze import analyze_payload, universe_summary  # noqa: E402
from dart_kfa.fetch import (  # noqa: E402
    DartApiError,
    api_key_from_env,
    fetch_fnltt_singl_acnt_all,
    load_fixture,
)
from dart_kfa.industry import load_universe_seed  # noqa: E402

DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "dart_universe_v1.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description="KFA-Engine universe snapshot builder")
    ap.add_argument("--seed", action="store_true", help="Use config/universe_seed.json fixtures")
    ap.add_argument("--fixture", action="append", default=[], help="Extra fixture paths")
    ap.add_argument(
        "--corp",
        action="append",
        default=[],
        help="Live corp_code:year:reprt:fs (needs DART_API_KEY)",
    )
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--print-stats", action="store_true")
    ap.add_argument("--no-valuation", action="store_true")
    args = ap.parse_args()

    companies: list[dict] = []
    errors: list[dict] = []
    include_val = not args.no_valuation

    if args.seed or (not args.fixture and not args.corp):
        seed = load_universe_seed()
        for row in seed.get("companies") or []:
            fx = row.get("fixture")
            if not fx:
                errors.append({"source": row.get("id"), "error": "no_fixture_yet"})
                continue
            p = ROOT / fx
            try:
                payload = load_fixture(p)
                company = analyze_payload(
                    payload,
                    corp={
                        "name": row.get("name_ko"),
                        "code": row.get("stock_code"),
                        "corp_code": row.get("corp_code"),
                        "industry_kit": row.get("industry_kit"),
                        "industry": row.get("industry"),
                    },
                    include_valuation=include_val,
                )
                companies.append(company)
            except Exception as e:  # noqa: BLE001
                errors.append({"source": str(p), "error": str(e)})

    for path in args.fixture:
        p = Path(path)
        try:
            company = analyze_payload(
                load_fixture(p),
                corp={"name": p.stem.split("_")[0]},
                include_valuation=include_val,
            )
            companies.append(company)
        except Exception as e:  # noqa: BLE001
            errors.append({"source": str(p), "error": str(e)})

    for spec in args.corp:
        parts = spec.split(":")
        if len(parts) < 2:
            errors.append({"source": spec, "error": "need corp_code:year[:reprt[:fs]]"})
            continue
        corp_code, year = parts[0], parts[1]
        reprt = parts[2] if len(parts) > 2 else "11011"
        fs = parts[3] if len(parts) > 3 else "CFS"
        try:
            payload = fetch_fnltt_singl_acnt_all(
                corp_code=corp_code,
                bsns_year=year,
                reprt_code=reprt,
                fs_div=fs,
            )
            company = analyze_payload(
                payload,
                corp={"corp_code": corp_code, "fs_div": fs, "reprt": reprt},
                include_valuation=include_val,
            )
            companies.append(company)
        except DartApiError as e:
            errors.append({"source": spec, "error": str(e)})

    snap = {
        "schema_version": "dart-universe-v1",
        "generated_at": _now(),
        "model": {
            "name": "kfa_engine",
            "engine_version": "kfa-1.0.0",
            "description": "Industry kits + M&A metrics + assumption DCF. No LLM.",
            "api_key_present": bool(api_key_from_env()),
        },
        "companies": [universe_summary(c) for c in companies],
        "detail": companies,
        "errors": errors,
        "disclaimer_ko": "계산·가정 모형이며 투자 권유가 아닙니다.",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if args.print_stats:
        print(f"companies={len(companies)} errors={len(errors)} → {args.output}")
        for c in companies:
            m = c.get("metrics") or {}
            kit = (c.get("industry") or {}).get("industry_kit")
            om = (m.get("operating_margin") or {}).get("value")
            band = (c.get("valuation") or {}).get("value_band")
            print(f"  {c.get('corp')} kit={kit} om={om} band={band}")

    # seed may list companies without fixtures → errors expected; success if we have companies
    return 0 if companies else 1


if __name__ == "__main__":
    raise SystemExit(main())
