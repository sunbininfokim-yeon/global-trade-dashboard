#!/usr/bin/env python3
"""Build real-data-only alert level thresholds (no options price proxies).

  ../../.venv/bin/python build_alert_levels.py --live --print-stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.alert_levels import build_alert_levels_report  # noqa: E402


def _md(rep: dict) -> str:
    put = rep.get("put_oi") or {}
    kr = rep.get("kr_hynix_letf") or {}
    us = rep.get("us_vix_to_kr") or {}
    lines = [
        f"# Alert levels (real data only) — {rep.get('as_of')}",
        "",
        "## Put OI란?",
        "",
        put.get("put_oi_ko") or "",
        "",
        put.get("availability_ko") or "",
        "",
        "## 할 수 없는 것",
        "",
    ]
    for x in rep.get("cannot_do_ko") or []:
        lines.append(f"- {x}")
    lines += ["", "## KR — 하닉 레버 ETF / 현물 거래대금", ""]
    lines.append(kr.get("sample", {}).get("note_ko") or "")
    lines.append("")
    lines.append(f"오늘 비율 **{kr.get('today_ratio')}** → 레벨 **{kr.get('today_level')}**")
    lines += ["", "| 레벨 | 기준 | n | 익일 −2%↓ 비율 | 익일 \|R\| 평균 |", "|------|------|--:|---------------:|---------------:|"]
    rules = kr.get("rule_ko") or {}
    for name in ("관찰", "주의", "경계"):
        lv = (kr.get("levels") or {}).get(name) or {}
        lines.append(
            f"| {name} | {rules.get(name)} | {lv.get('n')} | {lv.get('frac_next_down2')} | {lv.get('mean_next_abs')} |"
        )
    base = (kr.get("sample") or {}).get("baseline") or {}
    lines += ["", f"베이스라인(전체): frac_down2={base.get('frac_next_down2')} mean\|R\|={base.get('mean_next_abs')}", ""]
    lines += ["## US→KR — Cboe VIX 일변화 (풋 OI 아님)", ""]
    lines.append(us.get("put_oi_status_ko") or "")
    lines.append("")
    lines.append(
        f"최신 VIX **{us.get('latest_vix')}** (Δ {us.get('latest_vix_r')}) → **{us.get('latest_level')}**"
    )
    lines += ["", "| 레벨 | 기준 | n | 익일 하닉 open 음수비율 | 평균 |", "|------|------|--:|------------------------:|-----:|"]
    ur = us.get("rule_ko") or {}
    for name in ("관찰", "주의", "경계"):
        lv = (us.get("levels") or {}).get(name) or {}
        lines.append(
            f"| {name} | {ur.get(name)} | {lv.get('n')} | {lv.get('frac_kr_open_neg')} | {lv.get('mean_kr_open')} |"
        )
    lines += ["", us.get("limitation_ko") or "", "", rep.get("disclaimer_ko") or "", ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/alert_levels_v1.json",
    )
    p.add_argument("--tables", type=Path, default=ROOT / "ALERT_LEVELS.md")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()
    if not args.live:
        print("Pass --live")
        return 2
    rep = build_alert_levels_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = _md(rep)
    args.tables.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"Wrote {args.tables}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
