#!/usr/bin/env python3
"""Paper vs engine calibration + US stress event-study backtest.

  ../../.venv/bin/python build_validation_backtest.py --live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.paper_vs_engine import (  # noqa: E402
    compare_paper_vs_engine,
    event_study_us_stress,
    fetch_path_stats,
)


def _md(cal: dict, study: dict) -> str:
    lines = [
        f"# Validation backtest — {study.get('as_of')}",
        "",
        "## 1. Paper anchors vs engine",
        "",
        cal.get("verdict_ko") or "",
        "",
        "| field | paper | model | Δ% | band | sim |",
        "|-------|------:|------:|---:|------|----:|",
    ]
    for r in cal.get("rows") or []:
        pa = r.get("paper_anchor")
        if isinstance(pa, float) and pa > 1e6:
            pa = f"{pa/1e9:.1f}bn"
        mv = r.get("model_value")
        if isinstance(mv, float) and mv > 1e6:
            mv = f"{mv/1e9:.1f}bn"
        lines.append(
            f"| {r.get('field')} | {pa} | {mv} | {r.get('delta_pct')} | "
            f"{r.get('band')} | {r.get('similarity_score')} |"
        )

    lines += ["", "## 2. US stress → KR open (Hynix / Samsung)", "", study.get("definition_ko") or "", ""]
    for kr, s in (study.get("summary") or {}).items():
        base = (study.get("baseline_overnight") or {}).get(kr) or {}
        lines += [
            f"### {kr}",
            f"- stress n={s.get('n_stress_events')} · KR open frac_neg=**{s.get('frac_neg_kr_open') or s.get('frac_kr_open_neg')}** "
            f"(baseline {base.get('frac_neg')}) · mean={s.get('mean_kr_open')} (base {base.get('mean')})",
            f"- alert fires: n={((s.get('when_alert_fires') or {}).get('n'))} "
            f"frac_neg={((s.get('when_alert_fires') or {}).get('frac_neg'))} "
            f"mean={((s.get('when_alert_fires') or {}).get('mean'))}",
            f"- high stress: n={((s.get('when_high') or {}).get('n'))} "
            f"frac_neg={((s.get('when_high') or {}).get('frac_neg'))} "
            f"mean={((s.get('when_high') or {}).get('mean'))}",
            "",
        ]
    lines += ["## Top SOXL stress → Hynix open", "", "| US day | SOXL | MU | KR open | alert | level |", "|--------|-----:|---:|--------:|:-----:|-------|"]
    for e in study.get("top_soxl_stress_hynix") or []:
        dr = e.get("driver_returns") or {}
        lines.append(
            f"| {e.get('us_day')} | {dr.get('SOXL')} | {dr.get('MU')} | {e.get('r_kr_open')} | "
            f"{e.get('alert_would_fire')} | {e.get('proxy_stress_level')} |"
        )
    lines += ["", study.get("disclaimer_ko") or "", ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="Fetch Yahoo paths + run event study")
    p.add_argument(
        "--snap",
        type=Path,
        default=ROOT / "../../public/data/market_microstructure_v1.json",
    )
    p.add_argument(
        "--anchors",
        type=Path,
        default=ROOT / "config/paper_anchors.json",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/validation_backtest_v1.json",
    )
    p.add_argument("--tables", type=Path, default=ROOT / "VALIDATION_BACKTEST.md")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    snap = json.loads(args.snap.read_text(encoding="utf-8"))
    anchors = json.loads(args.anchors.read_text(encoding="utf-8"))

    path_stats = fetch_path_stats() if args.live else None
    cal = compare_paper_vs_engine(snap, anchors, path_stats=path_stats)
    study = event_study_us_stress() if args.live else {"summary": {}, "as_of": snap.get("as_of")}

    out = {
        "schema_version": "validation-backtest-v1",
        "paper_vs_engine": cal,
        "us_stress_event_study": study,
        "path_stats": path_stats,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = _md(cal, study)
    args.tables.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"Wrote {args.tables}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
