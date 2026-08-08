#!/usr/bin/env python3
"""Build Tier B discovery + KR open30m backtest artifacts.

  ../../.venv/bin/python build_us_kr_discovery.py --live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.kr_open30m_backtest import run_open30m_backtest  # noqa: E402
from market_microstructure.us_kr_discovery import discover_edges  # noqa: E402


def _md(disc: dict, bt: dict) -> str:
    lines = [
        f"# US→KR discovery + open30m — {disc.get('as_of')}",
        "",
        disc.get("disclaimer_ko") or "",
        "",
        f"Discovered edges: **{disc.get('n_edges')}** (min |corr|={disc.get('min_abs_corr')})",
        "",
        "## Top discovered edges",
        "",
        "| score | US→KR | corr(open) | corr↓ | corr(open30m) |",
        "|------:|-------|-----------:|------:|--------------:|",
    ]
    for e in (disc.get("discovered_edges") or [])[:20]:
        o = e.get("corr_us_close_kr_open") or {}
        t = e.get("corr_us_close_kr_open30m") or {}
        lines.append(
            f"| {e.get('score')} | {e.get('us')}→{e.get('kr')} | {o.get('corr')} | "
            f"{o.get('corr_us_down')} | {t.get('corr')} |"
        )

    lines += ["", "## Open30m / overnight channel summary", ""]
    ch = (bt.get("channel_summary") or {})
    for name in ("downside", "upside"):
        s = ch.get(name) or {}
        lines.append(
            f"- **{name}**: hit_rate_mean={s.get('hit_rate_mean')} "
            f"mean_of_means={s.get('mean_of_means')} drivers={s.get('drivers')}"
        )
    vu = ch.get("vol_up") or {}
    if vu.get("quality") == "estimated":
        vix = ((vu.get("open_overnight") or {}).get("vix_up") or {})
        lines.append(
            f"- **vol_up (VIX+5%)**: n={vix.get('n')} mean={vix.get('mean')} "
            f"frac_neg={vix.get('frac_neg')}"
        )
    lines += ["", bt.get("open30m_note_ko") or "", ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="Fetch yfinance history")
    p.add_argument("--period", default="1y")
    p.add_argument(
        "--out-disc",
        type=Path,
        default=ROOT / "../../public/data/us_kr_discovered_edges_v1.json",
    )
    p.add_argument(
        "--out-bt",
        type=Path,
        default=ROOT / "../../public/data/us_kr_open30m_backtest_v1.json",
    )
    p.add_argument("--tables", type=Path, default=ROOT / "US_KR_DISCOVERY.md")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if not args.live:
        print("Pass --live to download history (no offline fixture for discovery).")
        return 2

    disc = discover_edges(period=args.period)
    bt = run_open30m_backtest(period=args.period)
    # also Samsung overnight
    bt_ss = run_open30m_backtest(
        kr_yahoo="005930.KS", kr_id="005930", period=args.period
    )
    bt["also_005930"] = {
        "channel_summary": bt_ss.get("channel_summary"),
        "per_driver_n": len(bt_ss.get("per_driver") or []),
    }

    md = _md(disc, bt)
    for path, obj in ((args.out_disc, disc), (args.out_bt, bt)):
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
