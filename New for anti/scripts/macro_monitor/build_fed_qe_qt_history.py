#!/usr/bin/env python3
"""Monthly Fed Treasury and MBS purchases/runoff, back through QE1.

fed_ust_ops' 추이 tab was drawing a fixed fixture line frozen around -29B --
untouched even after the headline switched to real data, because the fixture
lived in a separate `history` array the earlier fix never touched. Rather
than patch that array with another synthetic shape, this builds the actual
month-over-month change in Fed holdings, split by security type, over the
full span FRED publishes: TREAST and WALCL both start 2002-12, WSHOMCB (the
MBS program) starts flat zero until QE1 begins buying agency MBS in 2009.

One row per month: net_treasuries and net_mbs, each signed -- positive when
that month's holdings rose (QE-style purchases), negative when they fell
(QT-style runoff, redemptions not reinvested). Nothing here labels a month
"QE" or "QT" by name; the sign of the bar already carries that, and drawing
in a policy-era label would need a curated calendar of announcement dates
this repo does not have and should not guess at.
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.request
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "fed_qe_qt_history_v1.json"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

SERIES = {"treasuries": "TREAST", "mbs": "WSHOMCB"}


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


def month_end_snapshot(weekly: list[tuple[str, float]]) -> dict[str, float]:
    """Last weekly observation on or before each calendar month's end."""
    by_month: dict[str, float] = {}
    for date, val in weekly:
        ym = date[:7]
        by_month[ym] = val  # weekly rows are already date-ascending
    return by_month


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    monthly: dict[str, dict[str, float]] = {}
    for key, sid in SERIES.items():
        weekly = [(d, v) for d, v in fetch(sid) if d >= args.start]
        if not weekly:
            print(f"refusing to write: {sid} returned nothing")
            return 1
        monthly[key] = month_end_snapshot(weekly)

    months = sorted(set(monthly["treasuries"]) & set(monthly["mbs"]))
    rows = []
    prev: dict[str, float] | None = None
    for ym in months:
        cur = {k: monthly[k][ym] for k in SERIES}
        if prev is not None:
            rows.append({
                "month": ym,
                # mn USD -> bn USD, one decimal is enough at monthly resolution.
                "treasuries_bn": round((cur["treasuries"] - prev["treasuries"]) * 1e-3, 1),
                "mbs_bn": round((cur["mbs"] - prev["mbs"]) * 1e-3, 1),
            })
        prev = cur

    total_treas = round(sum(r["treasuries_bn"] for r in rows), 1)
    total_mbs = round(sum(r["mbs_bn"] for r in rows), 1)

    doc = {
        "schema_version": "fed_qe_qt_history_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "source": "FRED (Federal Reserve H.4.1: TREAST, WSHOMCB) — public CSV, no API key",
        "data_status": "live",
        "frequency": "monthly",
        "unit": "bn_usd",
        "sign_convention_ko": ("월간 보유액 증감입니다. 양수(+)는 그 달 순매입, "
                               "음수(-)는 만기상환 후 재투자 미실시(런오프)입니다. "
                               "'QE'/'QT' 명칭은 붙이지 않습니다 — 이 저장소에 정책 국면을 "
                               "판정할 공식 발표일 목록이 없어, 라벨을 붙이면 추측이 됩니다."),
        "rows": rows,
        "totals_since_start_bn": {"treasuries": total_treas, "mbs": total_mbs},
        "limitations": [
            "WSHOMCB는 2009년 이전 사실상 0이라, 그 이전 달은 국채 매입만 표시됩니다.",
            "월말 인접 주간 관측치를 그 달 대표값으로 썼습니다 (H.4.1은 수요일 기준 주간 자료).",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {args.out} ({len(rows)} months, {rows[0]['month']} -> {rows[-1]['month']})")
    print(f"  totals since start: treasuries {total_treas:+.1f}B, mbs {total_mbs:+.1f}B")
    last = rows[-1]
    print(f"  latest ({last['month']}): treasuries {last['treasuries_bn']:+.1f}B, mbs {last['mbs_bn']:+.1f}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
