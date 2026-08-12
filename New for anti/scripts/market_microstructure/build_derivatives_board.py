#!/usr/bin/env python3
"""Build KR derivatives + US daily OI archive + rule-based KR watches.

  export KRX_API=...   # for KR OI/skew via OpenAPI
  # optional CSVs from data.krx 투자자별 거래실적 (콜/풋/선물 각각):
  #   --csv-opt-call path --csv-opt-put path --csv-fut path

  ../../.venv/bin/python build_derivatives_board.py --live --print-stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from collect_us_oi_daily import (  # noqa: E402
    append_archive,
    rule_based_kr_watch,
    snapshot_symbols,
)
from fetch_kr_derivatives import fetch_kr_derivatives_bundle  # noqa: E402


FLOW_PRODUCTS = ("futures", "options_call", "options_put")
FLOW_FIELDS = ("foreign_buy_mn_krw", "foreign_sell_mn_krw", "foreign_net_mn_krw")


def foreign_flow_points(investor: dict) -> list[dict]:
    """Pivot three CSV series into observed, date-keyed daily flow points."""
    by_date: dict[str, dict] = {}
    for product in FLOW_PRODUCTS:
        for row in investor.get(product) or []:
            date = str(row.get("date") or "")
            if not date or not any(row.get(k) is not None for k in FLOW_FIELDS):
                continue
            point = by_date.setdefault(date, {"date": date})
            point[product] = {k: row.get(k) for k in FLOW_FIELDS}
    return [by_date[k] for k in sorted(by_date)]


def append_foreign_flow_history(path: Path, investor: dict) -> dict:
    """Merge observed CSV points only; demo/missing never enter the archive."""
    previous: dict = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = {}
    merged = {str(p.get("date")): p for p in previous.get("points") or [] if p.get("date")}
    for fresh in foreign_flow_points(investor):
        old = merged.get(fresh["date"], {"date": fresh["date"]})
        merged[fresh["date"]] = {**old, **fresh}
    points = [merged[k] for k in sorted(merged)]
    return {
        "schema_version": "kr-foreign-derivatives-flow-history-v1",
        "as_of": points[-1]["date"] if points else None,
        "unit": "백만원 (당일 매수·매도·순매수)",
        "quality": "observed" if points else "missing",
        "points": points,
        "note_ko": (
            "외국인 선물·콜·풋의 일별 거래수급 아카이브. "
            "보유 미결제약정(OI)·포지션·만기별 노출이 아니다. demo 데이터는 적재하지 않는다."
        ),
    }


def _md(kr: dict, us: dict, rules: dict) -> str:
    lines = [
        f"# Derivatives board — {us.get('as_of') or kr.get('as_of')}",
        "",
        "## 오늘의 코스피200 · 외인 파생 (순매수 백만원)",
        "",
    ]
    inv = kr.get("investor_nets") or {}
    seed = inv.get("options_total_seed_from_ui") or []
    if seed:
        latest = seed[-1]
        lines.append(
            f"- UI시드(옵션 전체): {latest.get('date')} 외인 순매수 **{latest.get('foreign_net_mn_krw')}**백만원 "
            f"(quality={inv.get('quality')})"
        )
        lines.append("- 콜/풋 분리는 data.krx에서 권리유형 바꿔 CSV export 후 플래그로 주입")
    opt = kr.get("kospi200_options") or {}
    lines += [
        "",
        f"- K200 옵션 OI: call={opt.get('call_oi')} put={opt.get('put_oi')} "
        f"P/C OI={opt.get('put_call_oi')} ({opt.get('quality')})",
        f"- K200 선물 OI: {(kr.get('kospi200_futures_oi') or {}).get('open_interest_qty')} "
        f"({(kr.get('kospi200_futures_oi') or {}).get('quality')})",
        "",
        "## 한국 개별주 옵션 OI / 스큐",
        "",
    ]
    for e in kr.get("equity_options_oi_skew") or []:
        lines.append(
            f"- {e.get('underlying')}: P/C OI={e.get('put_call_oi')} "
            f"skew(put−call IV)={e.get('skew_put_minus_call_iv')} ({e.get('quality')})"
        )
    if not (kr.get("equity_options_oi_skew")):
        lines.append("- (KRX_API + eqsop 이용신청 필요)")
    lines += ["", f"## US→KR 룰 헤드라인: **{rules.get('headline_level')}**", ""]
    for a in (rules.get("alerts") or [])[:20]:
        lines.append(
            f"- [{a.get('level')}/{a.get('channel')}] {a.get('us')}→{a.get('kr')} "
            f"{', '.join(a.get('reasons') or [])}"
        )
    if kr.get("errors"):
        lines += ["", "## Errors", ""] + [f"- {e}" for e in kr["errors"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--csv-opt-call", type=Path, default=None)
    p.add_argument("--csv-opt-put", type=Path, default=None)
    p.add_argument("--csv-fut", type=Path, default=None)
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    pub = ROOT / "../../public/data"
    graph = json.loads((ROOT / "config/us_kr_link_graph.json").read_text(encoding="utf-8"))

    kr = fetch_kr_derivatives_bundle(
        investor_opt_call_csv=args.csv_opt_call,
        investor_opt_put_csv=args.csv_opt_put,
        investor_fut_csv=args.csv_fut,
    )
    if args.live:
        us = snapshot_symbols()
        append_archive(us)
        print(f"Appended US OI archive ({len(us.get('names') or [])} names)")
    else:
        # last archive line or empty
        arch = ROOT / "../../public/data/us_oi_daily_archive.jsonl"
        us = {"as_of": kr.get("as_of"), "names": []}
        if arch.exists():
            last = arch.read_text(encoding="utf-8").strip().splitlines()[-1]
            us = json.loads(last)

    rules = rule_based_kr_watch(us, graph)
    out = {
        "schema_version": "derivatives-board-v1",
        "kr": kr,
        "us_oi_snap": us,
        "us_kr_rules": rules,
    }
    path = pub / "derivatives_board_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history_path = pub / "kr_foreign_derivatives_history_v1.json"
    history = append_foreign_flow_history(history_path, kr.get("investor_nets") or {})
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = _md(kr, us, rules)
    (ROOT / "DERIVATIVES_BOARD.md").write_text(md, encoding="utf-8")
    print(f"Wrote {path}")
    print(f"Wrote {history_path}")
    print(f"Wrote {ROOT / 'DERIVATIVES_BOARD.md'}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
