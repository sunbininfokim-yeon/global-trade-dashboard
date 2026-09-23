#!/usr/bin/env python3
"""Publish the KOSPI200 investor derivatives-flow history for the UI.

Reads the normalized KRX radar hive in the private ``krx-month-paste`` repo
(checked out by the daily Action) and writes one compact, columnar file:

  public/data/krx_deriv_flow_v1.json

Inputs (all under ``<krx-month-paste>/data/normalized``):

  krx_15007_k200_investor/year=*/month=*/part.jsonl.gz
      KRX 15007 투자자별 거래실적 (일별추이, 거래대금) -- K200 futures, calls
      and puts, each with foreign / institution / retail / other-corp
      buy / sell / net.  Investor *flow*, not open interest.
  kospi200_futures_oi/year=*/month=*/part.jsonl.gz
      KRX 15003 front-month K200 futures quote + market-wide listed OI
      (regular session).  Market-wide, NOT foreign-held OI.

Rules, same as the rest of this directory: a day KRX did not publish has no
column (the date axis is observed trading days, never a filled calendar), a
missing number stays ``null``, and a row whose buy - sell does not reproduce
its own net is dropped to ``null`` rather than trusted on its quality tag.
Values keep KRX's source unit (백만원) as integers so nothing is rescaled
twice between here and the UI.

Usage:
  python build_krx_deriv_flow.py --source ../../../../krx-month-paste --print-stats
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "../../public/data/krx_deriv_flow_v1.json"

SCHEMA_VERSION = "krx-deriv-flow-v1"
PRODUCTS = ("futures", "options_call", "options_put")
INVESTORS = ("foreign", "institution", "retail", "other_corp")
# KRX rounds each side to 백만원 independently, so buy - sell may differ from
# the reported net by one unit of rounding.  Anything wider is a broken row.
NET_TOLERANCE_KRW = 1_000_000


def _read_hive(base: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part in sorted(base.glob("year=*/month=*/part.jsonl.gz")):
        with gzip.open(part, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # One bad line must not void a month of observations.
                    continue
    return rows


def _latest_by_key(rows: Iterable[dict[str, Any]], key) -> dict[Any, dict[str, Any]]:
    """Re-collected days appear more than once; the latest collection wins."""
    out: dict[Any, dict[str, Any]] = {}
    for row in rows:
        k = key(row)
        if k is None:
            continue
        prev = out.get(k)
        if prev is None or str(row.get("collected_at") or "") >= str(prev.get("collected_at") or ""):
            out[k] = row
    return out


def _mn(value: Any) -> int | None:
    """KRW float -> integer 백만원 (KRX's own unit).  None stays None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return int(round(v / 1_000_000))


def _consistent(row: dict[str, Any], investor: str) -> bool:
    b, s, n = (row.get(f"{investor}_{side}_krw") for side in ("buy", "sell", "net"))
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (b, s, n)):
        return False
    return abs((b - s) - n) <= NET_TOLERANCE_KRW


def build(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = source / "data" / "normalized"
    flow_dir = normalized / "krx_15007_k200_investor"
    fut_dir = normalized / "kospi200_futures_oi"
    if not flow_dir.is_dir():
        raise FileNotFoundError(f"missing KRX 15007 hive: {flow_dir}")

    flow_rows = _read_hive(flow_dir)
    flows = _latest_by_key(
        flow_rows,
        lambda r: (r.get("date"), r.get("product")) if r.get("product") in PRODUCTS and r.get("date") else None,
    )
    dates = sorted({d for (d, _p) in flows})

    stats = {"flow_rows_read": len(flow_rows), "flow_rows_used": len(flows), "dates": len(dates),
             "inconsistent_cells": 0, "partial_rows": 0, "missing_product_days": 0}

    flow: dict[str, dict[str, list]] = {}
    partial_days: dict[str, list[str]] = {}
    for product in PRODUCTS:
        cols: dict[str, list] = {f"{inv}_net": [] for inv in INVESTORS}
        cols.update({"foreign_buy": [], "foreign_sell": [], "market_total_buy": []})
        partial: list[str] = []
        for day in dates:
            row = flows.get((day, product))
            if row is None:
                stats["missing_product_days"] += 1
                for col in cols.values():
                    col.append(None)
                continue
            if row.get("quality") != "observed":
                partial.append(day)
                stats["partial_rows"] += 1
            for inv in INVESTORS:
                ok = _consistent(row, inv)
                if not ok and row.get(f"{inv}_net_krw") is not None:
                    stats["inconsistent_cells"] += 1
                cols[f"{inv}_net"].append(_mn(row.get(f"{inv}_net_krw")) if ok else None)
                if inv == "foreign":
                    cols["foreign_buy"].append(_mn(row.get("foreign_buy_krw")) if ok else None)
                    cols["foreign_sell"].append(_mn(row.get("foreign_sell_krw")) if ok else None)
            cols["market_total_buy"].append(_mn(row.get("market_total_buy_krw")))
        flow[product] = cols
        partial_days[product] = partial

    # Front-month futures: regular session only.  The night session trades
    # the same contract on a different clock and would double a day.
    fut_rows = _read_hive(fut_dir) if fut_dir.is_dir() else []
    fut = _latest_by_key(
        fut_rows,
        lambda r: r.get("date") if r.get("session") == "regular" and r.get("date") else None,
    )
    front = {"contract": [], "close": [], "open_interest": [], "volume": []}
    for day in dates:
        row = fut.get(day)
        oi = (row or {}).get("open_interest_contracts")
        close = (row or {}).get("close")
        vol = (row or {}).get("volume_contracts")
        front["contract"].append((row or {}).get("expiry_or_contract_month"))
        # A zero close or zero OI is KRX's blank cell, not a real print.
        front["close"].append(close if isinstance(close, (int, float)) and close > 0 else None)
        front["open_interest"].append(int(oi) if isinstance(oi, (int, float)) and oi > 0 else None)
        front["volume"].append(int(vol) if isinstance(vol, (int, float)) and vol > 0 else None)
    stats["futures_front_days"] = sum(1 for v in front["close"] if v is not None)

    manifest = {}
    manifest_path = source / "data" / "manifests" / "krx_15007_k200_investor.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": dates[-1] if dates else None,
        "range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
        "unit": "million_krw",
        "unit_ko": "백만원",
        "source": {
            "flow": "KRX 15007 투자자별 거래실적 (MDC0201050302) · 일별추이 · 거래대금",
            "futures_front": "KRX 15003 최근월물 시세 추이 (MDC0201050103) · 정규장",
            "repo": "krx-month-paste data/normalized",
            "manifest_generated_at": manifest.get("generated_at"),
        },
        "products": list(PRODUCTS),
        "investors": list(INVESTORS),
        "dates": dates,
        "flow": flow,
        "partial_days": partial_days,
        "futures_front": {
            **front,
            "scope_ko": "코스피200 선물 최근월물 1개 종목 · 시장 전체 미결제약정 (외국인 보유분 아님) · 롤오버일에 OI가 끊김",
        },
        "missing_trading_days": manifest.get("missing_trading_days") or [],
        "notes_ko": [
            "매수·매도·순매수는 당일 거래대금 흐름입니다. 미결제약정·보유 포지션·헤지 의도가 아닙니다.",
            "매수−매도가 순매수와 맞지 않는 행은 null로 비웁니다. 휴장일은 날짜 자체가 없습니다.",
            "기타법인 포함 4개 주체 순매수 합은 반올림 오차 범위에서 0입니다.",
        ],
    }
    return payload, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="krx-month-paste checkout root")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    payload, stats = build(args.source)
    if not payload["dates"]:
        print("no KRX 15007 observations found; keeping the existing file", file=sys.stderr)
        return 1
    # Never let a partial checkout shrink the published history.
    if args.out.is_file():
        try:
            prev = json.loads(args.out.read_text(encoding="utf-8"))
            prev_dates = prev.get("dates") or []
            if len(prev_dates) > len(payload["dates"]) and (prev.get("as_of") or "") >= (payload["as_of"] or ""):
                print(f"refusing to shrink history ({len(prev_dates)} -> {len(payload['dates'])} days)", file=sys.stderr)
                return 1
        except (json.JSONDecodeError, OSError):
            pass
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.print_stats:
        print(json.dumps({**stats, "as_of": payload["as_of"], "range": payload["range"],
                          "bytes": args.out.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
