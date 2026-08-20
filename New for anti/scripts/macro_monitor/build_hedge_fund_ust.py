#!/usr/bin/env python3
"""Hedge fund Treasury holdings, from the Fed's Z.1 Financial Accounts.

This sits next to ON RRP because the two describe the same trade from opposite
ends: RRP is cash parked at the Fed overnight, and the hedge fund Treasury book
is the leveraged basis position that cash largely funds. RRP has drained to
roughly zero through 2026 while the fund book kept growing, which is the part
worth being able to see side by side.

Z.1 is not H.4.1. It is published quarterly with about a one-quarter lag, so
this series is always months behind the weekly balance sheet next to it, and
the card says so rather than implying both are current.

  BOGZ1FL623061103Q  quarterly Treasury holdings, hedge funds (mn)
  BOGZ1LM623061103A  annual market-value level of the same book (mn)
  BOGZ1FL624090005A  annual total financial assets, hedge funds (mn)

The share-of-assets figure only pairs the two annual series, never the
quarterly holdings against an annual asset base -- those are different
as-of dates, and dividing across them would invent a ratio for a quarter
whose denominator was never published.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "hedge_fund_ust_v1.json"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

QUARTERLY_HOLDINGS = "BOGZ1FL623061103Q"
ANNUAL_HOLDINGS = "BOGZ1LM623061103A"
ANNUAL_TOTAL_ASSETS = "BOGZ1FL624090005A"


def fetch(sid: str, timeout: int = 30) -> list[tuple[str, float]]:
    req = urllib.request.Request(FRED_CSV.format(sid=sid),
                                 headers={"User-Agent": "macro-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        date = (row.get("observation_date") or row.get("DATE") or "").strip()
        raw = (row.get(sid) or "").strip()
        if not date or not raw or raw == ".":
            continue
        try:
            rows.append((date, float(raw)))
        except ValueError:
            continue
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--start", default="2012-01-01")
    args = ap.parse_args()

    q = [(d, v) for d, v in fetch(QUARTERLY_HOLDINGS) if d >= args.start]
    a_hold = {d: v for d, v in fetch(ANNUAL_HOLDINGS) if d >= args.start}
    a_tot = {d: v for d, v in fetch(ANNUAL_TOTAL_ASSETS) if d >= args.start}

    if not q:
        print("refusing to write: quarterly holdings returned nothing")
        return 1

    # Share of total financial assets, annual pairs only -- see module docstring.
    share = []
    for d in sorted(set(a_hold) & set(a_tot)):
        if a_tot[d]:
            share.append({"date": d, "pct": round(a_hold[d] / a_tot[d] * 100, 2),
                          "holdings_bn": round(a_hold[d] * 1e-3, 1),
                          "total_assets_bn": round(a_tot[d] * 1e-3, 1)})

    latest = q[-1]
    doc = {
        "schema_version": "hedge_fund_ust_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "source": "FRED — Federal Reserve Z.1 Financial Accounts (public CSV, no API key)",
        "data_status": "live",
        "frequency": "quarterly",
        "asof": latest[0],
        "label_ko": "헤지펀드 국채 보유",
        "value_bn": round(latest[1] * 1e-3, 1),
        "unit": "bn_usd",
        "series": {
            "label_ko": "분기말 보유액",
            "fred_series_id": QUARTERLY_HOLDINGS,
            "dates": [d for d, _ in q],
            "values": [round(v * 1e-3, 1) for _, v in q],
        },
        "share_of_assets": {
            "label_ko": "총 금융자산 대비 비중",
            "fred_series_ids": [ANNUAL_HOLDINGS, ANNUAL_TOTAL_ASSETS],
            "frequency": "annual",
            "note_ko": ("연간 시리즈끼리만 짝지어 계산합니다. 분기 보유액을 연간 자산으로 "
                        "나누면 기준 시점이 어긋나므로 그렇게 하지 않습니다."),
            "points": share,
        },
        "rrp_link_note_ko": ("역레포(ON RRP)와 함께 보도록 배치했습니다. RRP는 하루짜리로 "
                             "연준에 맡긴 현금이고, 헤지펀드 국채 보유는 그 자금이 흘러가는 "
                             "베이시스 거래 쪽입니다. 다만 인과관계를 측정한 값은 아닙니다."),
        "limitations": [
            "Z.1은 분기 발표에 약 1개 분기 시차가 있어, 옆의 주간 대차대조표보다 항상 뒤처집니다.",
            "'헤지펀드'는 Z.1의 분류 기준을 따르며, 업계에서 쓰는 범위와 다를 수 있습니다.",
            "보유액은 시장가치 기준이라 가격 변동만으로도 움직입니다 — 매수·매도량이 아닙니다.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"  latest {doc['asof']}: ${doc['value_bn']}bn ({len(q)} quarters)")
    if share:
        s = share[-1]
        print(f"  share {s['date']}: {s['pct']}% of ${s['total_assets_bn']}bn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
