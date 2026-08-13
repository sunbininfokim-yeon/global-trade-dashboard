#!/usr/bin/env python3
"""Build US microstructure + US→KR transmission alerts.

  ../../.venv/bin/python build_us_kr_cross_market.py --live --print-stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.us_scenarios import build_transmission, classify_universe  # noqa: E402


def _md(us: dict, regimes: dict, tx: dict) -> str:
    lines = [
        f"# US→KR cross-market — {us.get('as_of')}",
        "",
        us.get("disclaimer_ko") or "",
        "",
        f"Sources: {', '.join(us.get('source_priority_used') or [])}",
        "",
        f"## Headline: `{tx.get('headline')}`",
        "",
        tx.get("note_ko") or "",
        "",
        "## Channels",
        "",
        "| channel | level | heat | KR tickers |",
        "|---------|-------|-----:|------------|",
    ]
    for ch, b in (tx.get("channels") or {}).items():
        lines.append(
            f"| {ch} | {b.get('level')} | {b.get('heat')} | {', '.join(b.get('kr_tickers') or [])} |"
        )
    lines += ["", "## US names (regime)", "", "| symbol | primary | level | regimes | P/C vol | day_R | short_chg% |", "|--------|---------|-------|---------|--------:|------:|-----------:|"]
    by_reg = {r["symbol"]: r for r in regimes.get("names") or []}
    by_us = {n["symbol"]: n for n in us.get("names") or []}
    for sym, reg in by_reg.items():
        n = by_us.get(sym) or {}
        opt = n.get("options") or {}
        sh = n.get("finra_short") or {}
        spot = n.get("spot") or {}
        lines.append(
            f"| {sym} | {reg.get('primary_channel')} | {reg.get('stress_level')} | "
            f"{','.join(reg.get('regimes') or [])} | {opt.get('put_call_volume')} | "
            f"{spot.get('day_return')} | {sh.get('short_chg_pct')} |"
        )
    lines += ["", "## Top transmission edges", "", "| heat | channel | US→KR | type | regimes |", "|-----:|---------|-------|------|---------|"]
    for e in (tx.get("edges_active") or [])[:15]:
        lines.append(
            f"| {e.get('heat')} | {e.get('channel')} | {e.get('us')}→{e.get('kr')} | "
            f"{e.get('edge_type')} | {','.join(e.get('us_regimes') or [])} |"
        )
    vol = us.get("vol_indices") or {}
    idx = vol.get("indices") or {}
    if idx:
        lines += ["", "## Cboe vol indices", "", "| index | as_of | close | day_R |", "|-------|-------|------:|------:|"]
        for name in ("VIX", "VVIX", "SKEW"):
            row = idx.get(name) or {}
            lines.append(
                f"| {name} | {row.get('as_of')} | {row.get('close')} | {row.get('day_return')} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument(
        "--symbols",
        default=None,
        help="Comma list; default = link graph options_priority",
    )
    p.add_argument(
        "--graph",
        type=Path,
        default=ROOT / "config/us_kr_link_graph.json",
    )
    p.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "tests/fixtures/us_day.json",
    )
    p.add_argument(
        "--out-us",
        type=Path,
        default=ROOT / "../../public/data/us_microstructure_v1.json",
    )
    p.add_argument(
        "--out-tx",
        type=Path,
        default=ROOT / "../../public/data/us_kr_transmission_v1.json",
    )
    p.add_argument(
        "--tables",
        type=Path,
        default=ROOT / "US_KR_TABLES.md",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if args.live:
        from fetch_us_public import fetch_us_names

        syms = (
            [s.strip() for s in args.symbols.split(",") if s.strip()]
            if args.symbols
            else list(graph.get("options_priority") or graph.get("us_watchlist") or [])
        )
        us = fetch_us_names(syms)
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(us, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Fetched US → {args.fixture}")
    else:
        us = json.loads(args.fixture.read_text(encoding="utf-8"))

    regimes = classify_universe(us)
    discovered = None
    disc_path = ROOT / "../../public/data/us_kr_discovered_edges_v1.json"
    if disc_path.exists():
        discovered = json.loads(disc_path.read_text(encoding="utf-8"))
    bt = None
    bt_path = ROOT / "../../public/data/us_kr_open30m_backtest_v1.json"
    if bt_path.exists():
        bt = json.loads(bt_path.read_text(encoding="utf-8"))
    tx = build_transmission(us, regimes, graph, discovered=discovered, open30m_backtest=bt)
    md = _md(us, regimes, tx)

    for path, obj in (
        (args.out_us, us),
        (ROOT / "../../public/data/us_regime_v1.json", regimes),
        (args.out_tx, tx),
    ):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path}")

    args.tables.write_text(md, encoding="utf-8")
    print(f"Wrote {args.tables}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
