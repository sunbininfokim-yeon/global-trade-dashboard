#!/usr/bin/env python3
"""Build KOSPI Conc_top2/5/10 history JSON (+ markdown summary).

  ../../.venv/bin/python build_conc_history.py --live --months 6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.conc_history import (  # noqa: E402
    append_observed,
    build_concentration_history,
)


def _md(hist: dict) -> str:
    st = hist.get("stats") or {}
    latest = hist.get("latest") or {}
    lines = [
        f"# KOSPI concentration history — {hist.get('as_of')}",
        "",
        hist.get("note_ko") or "",
        "",
        f"Points: **{hist.get('n_points')}** · last Conc_top2 **{st.get('conc_top2_last')}%** "
        f"(60d Δ {st.get('conc_top2_chg_60d')})",
        "",
        f"Range top2: {st.get('conc_top2_min')} – {st.get('conc_top2_max')}",
        "",
        "## Latest",
        "",
        f"| Conc_top2 | Conc_top5 | Conc_top10 | quality |",
        f"|----------:|----------:|-----------:|---------|",
        f"| {latest.get('conc_top2_samsung_hynix_pct')} | {latest.get('conc_top5_pct')} | "
        f"{latest.get('conc_top10_pct')} | {latest.get('quality')} |",
        "",
        "## Tail (last 10)",
        "",
        "| date | top2 | top5 | top10 | q |",
        "|------|-----:|-----:|------:|---|",
    ]
    for p in (hist.get("points") or [])[-10:]:
        lines.append(
            f"| {p.get('date')} | {p.get('conc_top2_samsung_hynix_pct')} | "
            f"{p.get('conc_top5_pct')} | {p.get('conc_top10_pct')} | {p.get('quality')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="Backfill + observed today")
    p.add_argument("--append-only", action="store_true", help="Append today's observed only")
    p.add_argument("--months", type=int, default=6)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/kospi_concentration_history_v1.json",
    )
    p.add_argument("--tables", type=Path, default=ROOT / "CONC_HISTORY.md")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if args.append_only and args.out.exists():
        hist = json.loads(args.out.read_text(encoding="utf-8"))
        hist = append_observed(hist)
    elif args.live:
        hist = build_concentration_history(months=args.months)
    else:
        print("Pass --live or --append-only")
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = _md(hist)
    args.tables.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} ({hist.get('n_points')} points)")
    print(f"Wrote {args.tables}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
