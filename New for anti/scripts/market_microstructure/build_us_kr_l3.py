#!/usr/bin/env python3
"""L3 full pipeline: US fetch → regimes → TierA+B tx → discovery → open30m → hitrate.

  ../../.venv/bin/python build_us_kr_l3.py --live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.kr_open30m_backtest import run_open30m_backtest  # noqa: E402
from market_microstructure.regime_proxy_backtest import run_regime_proxy_backtest  # noqa: E402
from market_microstructure.us_kr_discovery import discover_edges  # noqa: E402
from market_microstructure.us_kr_hitrate import build_hitrate_report  # noqa: E402
from market_microstructure.us_scenarios import build_transmission, classify_universe  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--period", default="1y")
    p.add_argument("--symbols", default=None, help="Comma US list; default watchlist")
    p.add_argument("--skip-fetch", action="store_true", help="Reuse fixture US snap")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    graph = json.loads((ROOT / "config/us_kr_link_graph.json").read_text(encoding="utf-8"))
    fixture = ROOT / "tests/fixtures/us_day.json"
    pub = ROOT / "../../public/data"

    if args.live and not args.skip_fetch:
        from fetch_us_public import fetch_us_names

        syms = (
            [s.strip() for s in args.symbols.split(",") if s.strip()]
            if args.symbols
            else list(graph.get("us_watchlist") or graph.get("options_priority") or [])
        )
        us = fetch_us_names(syms)
        fixture.write_text(json.dumps(us, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Fetched {len(syms)} US names → {fixture}")
    else:
        us = json.loads(fixture.read_text(encoding="utf-8"))

    print("Running Tier B discovery + open30m + hitrate…")
    disc = discover_edges(period=args.period) if args.live else json.loads(
        (pub / "us_kr_discovered_edges_v1.json").read_text(encoding="utf-8")
    )
    bt = run_open30m_backtest(period=args.period) if args.live else json.loads(
        (pub / "us_kr_open30m_backtest_v1.json").read_text(encoding="utf-8")
    )
    hit = build_hitrate_report(period=args.period, backtest_000660=bt)
    regime_bt = run_regime_proxy_backtest(period=args.period) if args.live else None

    regimes = classify_universe(us)
    tx = build_transmission(us, regimes, graph, discovered=disc, open30m_backtest=bt)

    outs = {
        pub / "us_microstructure_v1.json": us,
        pub / "us_regime_v1.json": regimes,
        pub / "us_kr_transmission_v1.json": tx,
        pub / "us_kr_discovered_edges_v1.json": disc,
        pub / "us_kr_open30m_backtest_v1.json": bt,
        pub / "us_kr_hitrate_v1.json": hit,
    }
    if regime_bt is not None:
        outs[pub / "us_kr_regime_proxy_backtest_v1.json"] = regime_bt
    for path, obj in outs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path}")

    lines = [
        f"# US→KR L3 pipeline — {tx.get('as_of')}",
        "",
        f"Headline: `{tx.get('headline')}`",
        f"Tier B edges fired: {tx.get('tier_b_edges_fired')}",
        f"Sources: {', '.join(us.get('source_priority_used') or [])}",
        "",
        "## Channels",
    ]
    for ch, b in (tx.get("channels") or {}).items():
        lines.append(f"- {ch}: {b.get('level')} heat={b.get('heat')} kr={b.get('kr_tickers')}")
    comp = hit.get("composite_any_driver_down") or {}
    alert = comp.get("alert_open") or {}
    base = comp.get("baseline_open") or {}
    sug = hit.get("recalibration_suggestions") or {}
    lines += [
        "",
        "## Hit-rate (overnight open, any driver ≤−2%)",
        f"- alert days: {comp.get('n_alert_days')} / {comp.get('n_us_days')}",
        f"- frac_neg alert={alert.get('frac_neg')} vs baseline={base.get('frac_neg')} "
        f"(lift={comp.get('lift_frac_neg')})",
        f"- mean alert R={alert.get('mean')} baseline={base.get('mean')}",
        "",
        "## Recalibration suggestions",
        f"- downside_hit_rate_mean={sug.get('downside_hit_rate_mean')}",
        f"- keep_downside_emphasis={sug.get('suggest_keep_downside_emphasis')}",
        "",
    ]
    if regime_bt:
        d = ((regime_bt.get("channel_summary") or {}).get("downside") or {}).get("overnight") or {}
        lines += [
            "## Regime-proxy backtest (downside overnight)",
            f"- n={d.get('n')} mean={d.get('mean')} frac_neg={d.get('frac_neg')}",
            "",
        ]
    lines += [tx.get("note_ko") or "", ""]
    md = "\n".join(lines)
    (ROOT / "US_KR_L3.md").write_text(md, encoding="utf-8")
    print(f"Wrote {ROOT / 'US_KR_L3.md'}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
