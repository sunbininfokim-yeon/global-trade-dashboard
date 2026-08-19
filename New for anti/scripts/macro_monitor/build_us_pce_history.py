#!/usr/bin/env python3
"""Fetch observed U.S. PCE price indexes from FRED into the CPI history shape.

PCE is BEA's measure, so it is absent from the BLS pull that produces
us_cpi_api_history_v1.json -- but the inflation panel shows headline/core CPI
and headline/core PCE side by side, and mixing an observed CPI series with a
synthetic PCE one would put a real number and a fixture on the same axis.

FRED publishes both indexes as plain CSV with no key: PCEPI (headline) and
PCEPILFE (core, ex food & energy). MoM/YoY are computed here from the index
rather than taken from a second FRED series, so the two come from one vintage
and cannot disagree.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_pce_history_v1.json"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

SERIES = [
    {"id": "headline", "series_id": "PCEPI", "label_ko": "PCE", "label_en": "PCE price index"},
    {"id": "core", "series_id": "PCEPILFE", "label_ko": "근원 PCE", "label_en": "PCE excl. food & energy"},
]


def fetch_fred_csv(series_id: str, timeout: int = 30) -> list[tuple[str, float]]:
    url = FRED_CSV.format(series_id=series_id)
    req = urllib.request.Request(url, headers={"User-Agent": "macro-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        date = (row.get("observation_date") or row.get("DATE") or "").strip()
        # FRED writes "." for a missing observation; skip rather than zero-fill.
        raw = (row.get(series_id) or "").strip()
        if not date or not raw or raw == ".":
            continue
        try:
            rows.append((date[:7], float(raw)))
        except ValueError:
            continue
    return rows


def to_observations(points: list[tuple[str, float]]) -> list[dict]:
    out: list[dict] = []
    by_month = {m: v for m, v in points}
    for i, (month, index) in enumerate(points):
        prev = points[i - 1][1] if i > 0 else None
        y, m = month.split("-")
        year_ago = by_month.get(f"{int(y) - 1}-{m}")
        out.append({
            "date": month,
            "index": round(index, 4),
            "data_status": "observed",
            "footnotes": [],
            "mom_pct": round((index / prev - 1) * 100, 4) if prev else None,
            "yoy_pct": round((index / year_ago - 1) * 100, 4) if year_ago else None,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    series = []
    for spec in SERIES:
        points = fetch_fred_csv(spec["series_id"])
        if not points:
            print(f"WARNING: {spec['series_id']} returned no observations -- not writing a placeholder")
            continue
        series.append({
            "id": spec["id"],
            "label_ko": spec["label_ko"],
            "label_en": spec["label_en"],
            "fred_series_id": spec["series_id"],
            "observations": to_observations(points),
        })

    if not series:
        print("refusing to write: no series fetched")
        return 1

    latest = max(s["observations"][-1]["date"] for s in series)
    doc = {
        "schema_version": "us_pce_history_v1",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "FRED (BEA underlying) — public CSV, no API key",
        "coverage": {"returned_series": len(series), "latest_reference_period": latest},
        "limitations": [
            "PCE는 BEA 발표를 FRED가 재배포한 값이다. 개정(revision)이 잦아 최신 1~2개월은 바뀔 수 있다.",
            "MoM·YoY는 지수에서 계산한 값이며, BEA 보도자료의 반올림 표기와 소수점에서 다를 수 있다.",
            "시장 예상치(컨센서스)는 포함하지 않는다 — 무료 공개 출처가 없다.",
        ],
        "series": series,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out} (latest {latest})")
    if args.print_stats:
        for s in series:
            o = s["observations"][-1]
            print(f"  {s['id']}: {o['date']} MoM {o['mom_pct']:+.2f}% YoY {o['yoy_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
