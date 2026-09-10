#!/usr/bin/env python3
"""Build KR derivatives + US daily OI archive + rule-based KR watches.

  export KRX_API=...   # for KR futures/options EOD activity via OpenAPI
  # optional legacy CSVs from data.krx 투자자별 거래실적 (콜/풋/선물 각각):
  #   --csv-opt-call path --csv-opt-put path --csv-fut path
  # KRX 15007 authenticated BUY/SELL exports (백만원 → KRW, 콜/풋 분리):
  #   --15007-call-buy path --15007-call-sell path \
  #   --15007-put-buy path --15007-put-sell path
  #   --bas-dd 20260813  # explicit KRX EOD day (manual rerun/backfill)

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


def _md(kr: dict, us: dict, rules: dict) -> str:
    kr_as_of = kr.get("as_of") or "—"
    us_as_of = us.get("as_of") or "—"
    lines = [
        f"# Derivatives board — KR {kr_as_of} / US {us_as_of}",
        "",
        "## 오늘의 코스피200 · 외국인 파생 관찰",
        "",
    ]
    inv = kr.get("investor_nets") or {}
    public_flow = inv.get("public_dashboard") or {}

    def krw(value: object, *, signed: bool = False) -> str:
        if not isinstance(value, (int, float)):
            return "—"
        prefix = "+" if signed and value >= 0 else ""
        return f"{prefix}{value / 1e12:.3f}조원"

    for key, label in (("futures", "K200 선물"), ("options_total", "K200 옵션 전체")):
        item = public_flow.get(key) or {}
        foreign = (item.get("investors") or {}).get("foreign") or {}
        if item.get("quality") == "observed":
            lines.append(
                f"- {label} 외국인: 매수 **{krw(foreign.get('buy_krw'))}** / "
                f"매도 **{krw(foreign.get('sell_krw'))}** / 순매수 **{krw(foreign.get('net_krw'), signed=True)}** "
                f"(거래일 {item.get('as_of')}, KRX 표출 {item.get('observed_at_krx')})"
            )
    detailed = inv.get("detailed_15007") or {}
    detailed_products = detailed.get("products") if isinstance(detailed, dict) else {}
    if not isinstance(detailed_products, dict):
        detailed_products = {}
    call = detailed_products.get("options_call") or {}
    put = detailed_products.get("options_put") or {}
    if call.get("quality") == "observed" and put.get("quality") == "observed":
        for label, item in (("K200 콜", call), ("K200 풋", put)):
            foreign = item.get("foreign") or {}
            total = item.get("market_total") or {}
            lines.append(
                f"- {label} 외국인: 매수 **{krw(foreign.get('buy_krw'))}** / "
                f"매도 **{krw(foreign.get('sell_krw'))}** / 순매수 **{krw(foreign.get('net_krw'), signed=True)}** "
                f"(거래일 {item.get('as_of')}, 인증된 KRX 15007)"
            )
            lines.append(
                f"  - 시장 전체 활동: 매수 {krw(total.get('buy_krw'))} / "
                f"매도 {krw(total.get('sell_krw'))}; 방향 해석 없음"
            )
    else:
        lines.append("- 옵션 콜/풋 외국인 분리: 인증된 KRX 15007 매수·매도 export가 모두 필요하며, 현재 수치를 추정하지 않음.")
    opt = kr.get("kospi200_options") or {}
    lines += [
        "",
        "## 코스피200 시장 전체 거래 활동 (투자자별 아님)",
        "",
        f"- K200 옵션 거래량: call={opt.get('call_volume')} put={opt.get('put_volume')} "
        f"P/C 거래량={opt.get('put_call_volume')} ({opt.get('quality')})",
        f"- K200 옵션 거래대금: call={opt.get('call_trading_value_krw')} "
        f"put={opt.get('put_trading_value_krw')} P/C={opt.get('put_call_trading_value')}",
        f"- K200 선물 거래량: {(kr.get('kospi200_futures') or {}).get('volume')} · "
        f"거래대금: {(kr.get('kospi200_futures') or {}).get('trading_value_krw')} "
        f"({(kr.get('kospi200_futures') or {}).get('quality')})",
        "",
    ]
    lines += ["", f"## US→KR 관찰 레벨: **{rules.get('headline_level')}**", ""]
    for a in (rules.get("alerts") or [])[:20]:
        lines.append(
            f"- [{a.get('level')}/{a.get('channel')}] {a.get('us')}→{a.get('kr')} "
            f"{', '.join(a.get('reasons') or [])}"
        )
    if kr.get("errors"):
        lines += ["", "## Errors", ""] + [f"- {e}" for e in kr["errors"]]
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--csv-opt-call", type=Path, default=None)
    p.add_argument("--csv-opt-put", type=Path, default=None)
    p.add_argument("--csv-fut", type=Path, default=None)
    p.add_argument("--15007-call-buy", dest="detail_15007_call_buy", type=Path, default=None)
    p.add_argument("--15007-call-sell", dest="detail_15007_call_sell", type=Path, default=None)
    p.add_argument("--15007-put-buy", dest="detail_15007_put_buy", type=Path, default=None)
    p.add_argument("--15007-put-sell", dest="detail_15007_put_sell", type=Path, default=None)
    p.add_argument("--15007-futures-buy", dest="detail_15007_futures_buy", type=Path, default=None)
    p.add_argument("--15007-futures-sell", dest="detail_15007_futures_sell", type=Path, default=None)
    p.add_argument("--bas-dd", default=None, help="KRX EOD day YYYYMMDD (optional)")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    pub = ROOT / "../../public/data"
    graph = json.loads((ROOT / "config/us_kr_link_graph.json").read_text(encoding="utf-8"))

    path = pub / "derivatives_board_v1.json"
    existing: dict = {}
    previous_detailed_15007 = None
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            previous_detailed_15007 = (
                ((existing.get("kr") or {}).get("investor_nets") or {}).get("detailed_15007")
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            # A malformed prior board must never be treated as observations.
            previous_detailed_15007 = None

    kr = fetch_kr_derivatives_bundle(
        bas_dd=args.bas_dd,
        investor_opt_call_csv=args.csv_opt_call,
        investor_opt_put_csv=args.csv_opt_put,
        investor_fut_csv=args.csv_fut,
        detailed_15007_option_call_buy=args.detail_15007_call_buy,
        detailed_15007_option_call_sell=args.detail_15007_call_sell,
        detailed_15007_option_put_buy=args.detail_15007_put_buy,
        detailed_15007_option_put_sell=args.detail_15007_put_sell,
        detailed_15007_futures_buy=args.detail_15007_futures_buy,
        detailed_15007_futures_sell=args.detail_15007_futures_sell,
        previous_detailed_15007=previous_detailed_15007,
    )
    # A manual 15007 import must not erase a previously fetched OpenAPI/public
    # dashboard snapshot merely because this machine lacks KRX_API or network
    # access.  The detailed product has its own as_of date, so retaining the
    # last independently observed activity is more honest than overwriting it
    # with a synthetic "missing" same-day record.
    previous_kr = existing.get("kr") if isinstance(existing, dict) else None
    if isinstance(previous_kr, dict):
        for key in ("kospi200_futures", "kospi200_options"):
            current = kr.get(key) or {}
            prior = previous_kr.get(key) or {}
            if current.get("quality") != "observed" and prior.get("quality") == "observed":
                kr[key] = prior
        current_investor = kr.get("investor_nets") or {}
        prior_investor = previous_kr.get("investor_nets") or {}
        if not current_investor.get("public_dashboard") and prior_investor.get("public_dashboard"):
            current_investor["public_dashboard"] = prior_investor["public_dashboard"]
            if current_investor.get("quality") == "missing":
                current_investor["quality"] = prior_investor.get("quality", "partial_observed")
        if (kr.get("kospi200_futures") or {}).get("quality") == "observed" and (
            kr.get("kospi200_options") or {}
        ).get("quality") == "observed" and kr.get("as_of") != previous_kr.get("as_of"):
            # The current activity is retained from its own source date.
            kr["as_of"] = previous_kr.get("as_of") or kr.get("as_of")
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = _md(kr, us, rules)
    (ROOT / "DERIVATIVES_BOARD.md").write_text(md, encoding="utf-8")
    print(f"Wrote {path}")
    print(f"Wrote {ROOT / 'DERIVATIVES_BOARD.md'}")
    if args.print_stats:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
