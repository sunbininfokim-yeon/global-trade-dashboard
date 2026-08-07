#!/usr/bin/env python3
"""Run personal portfolio diagnosis → public/data/portfolio_analysis_v1.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_lab.report import build_report
from portfolio_lab.resolve import InstrumentRegistry, resolve_portfolio
from portfolio_lab.returns import aligned_returns
from portfolio_lab.structure import load_profile, suggest_aliases


def main() -> int:
    ap = argparse.ArgumentParser(description="금융_재무분석 portfolio pipeline")
    ap.add_argument(
        "--portfolio",
        type=Path,
        default=ROOT / "samples" / "demo_portfolio.json",
    )
    ap.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "instruments" / "registry.json",
    )
    ap.add_argument(
        "--profiles",
        type=Path,
        default=ROOT / "instruments" / "risk_profiles.json",
    )
    ap.add_argument("--risk-profile", default=None, help="conservative|balanced|aggressive")
    ap.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "cache" / "prices",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / ".." / ".." / "public" / "data" / "portfolio_analysis_v1.json",
    )
    ap.add_argument("--base-currency", default=None)
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--suggest", default=None, help="typeahead query, e.g. 삼성전")
    ap.add_argument("--print-summary", action="store_true", default=True)
    args = ap.parse_args()

    registry = InstrumentRegistry(args.registry)

    if args.suggest is not None:
        hits = suggest_aliases(registry, args.suggest)
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0

    portfolio = json.loads(args.portfolio.read_text(encoding="utf-8"))
    base = args.base_currency or portfolio.get("base_currency") or "KRW"
    rf = float(portfolio.get("risk_free_rate_ann") or 0.03)
    profile_id = args.risk_profile or portfolio.get("risk_profile") or "balanced"
    profile_id, profile = load_profile(args.profiles, profile_id)

    positions, unresolved = resolve_portfolio(portfolio, registry)
    if not positions:
        print("ERROR: no positions resolved", unresolved, file=sys.stderr)
        return 1
    if unresolved:
        print("WARN unresolved:", unresolved, file=sys.stderr)

    rets, weights, meta = aligned_returns(
        positions,
        args.cache_dir,
        base_currency=base,
        years=args.years,
        cache_only=args.cache_only,
    )

    report = build_report(
        portfolio_id=str(portfolio.get("portfolio_id") or args.portfolio.stem),
        base_currency=base,
        positions=positions,
        rets=rets,
        weights=weights,
        meta=meta,
        rf_ann=rf,
        unresolved=unresolved,
        risk_profile_id=profile_id,
        risk_profile=profile,
    )

    out_path: Path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.print_summary:
        ui = report["ui_copy_ko"]
        print(f"wrote {out_path}")
        print(f"[{ui['profile']['label_ko']}] {ui['headline_ko']}")
        print(ui["risk_contribution_plain_ko"])
        for card in ui["metric_cards"]:
            print(f"- {card['title_ko']}: {card['value_ko']}")
            print(f"  {card['plain_ko']}")
        if ui["moves_down_ko"]:
            print("줄이기:")
            for m in ui["moves_down_ko"][:3]:
                print(f"  · {m['plain_ko']}")
        if ui["moves_up_ko"]:
            print("늘리기:")
            for m in ui["moves_up_ko"][:3]:
                print(f"  · {m['plain_ko']}")
        print(ui["footer_ko"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
