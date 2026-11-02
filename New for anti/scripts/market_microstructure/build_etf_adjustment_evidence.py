"""Reproduce adjustment-ratio events; inferred cash is NOT issuer evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_kospi200_price_panel import ETF_PATH, NAVER_PRICE, ROOT, _get, _number, now_iso


def collect_prices(code, start, max_pages=30):
    rows, receipts = {}, []
    for page in range(1, max_pages + 1):
        url = NAVER_PRICE.format(code=code, page=page)
        raw = _get(url)
        batch = json.loads(raw)
        if not isinstance(batch, list) or not batch:
            raise ValueError(f"{code}: history ended before predecessor of {start}")
        receipts.append({"url": url, "sha256": hashlib.sha256(raw.encode()).hexdigest()})
        old_count = len(rows)
        for row in batch:
            day = row["localTradedAt"][:10]
            value = _number(row["closePrice"])
            if day in rows and rows[day] != value:
                raise ValueError(f"{code}: conflicting daily close {day}")
            rows[day] = value
        if min(rows) < start:
            return rows, receipts
        if len(rows) == old_count:
            raise ValueError(f"{code}: repeated page without progress")
    raise ValueError(f"{code}: {max_pages} pages insufficient for {start}")


def adjustment_events(adjusted, unadjusted, start, end):
    days = sorted(day for day in adjusted if day <= end)
    if not days or days[0] >= start or days[-1] < end:
        raise ValueError("adjusted history must cover the predecessor and requested end")
    events = []
    for previous, day in zip(days, days[1:]):
        if day < start:
            continue
        if previous not in unadjusted or day not in unadjusted:
            raise ValueError(f"missing unadjusted pair {previous}/{day}")
        ap, at, up, ut = adjusted[previous], adjusted[day], unadjusted[previous], unadjusted[day]
        if min(ap, at, up, ut) <= 0:
            raise ValueError("nonpositive price")
        ratio_change = (at / ut) / (ap / up) - 1
        # A visible ratio jump, not ordinary rounded-price noise. Not an ex-date calendar.
        if abs(ratio_change) < 0.0005:
            continue
        events.append({"date": day, "previous_date": previous, "U_previous": up,
                       "U_current": ut, "A_previous": ap, "A_current": at,
                       "inferred_D_krw": up - ut * ap / at,
                       "adjustment_ratio_change": ratio_change,
                       "issuer_cash_verified": False})
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-30")
    parser.add_argument("--end", default="2026-10-30")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--output", type=Path, default=ROOT.parent / "data/manifests/etf_adjustment_evidence_20261101.json")
    args = parser.parse_args()
    source = ETF_PATH.read_bytes()
    doc = json.loads(source)
    report = {"schema_version": "etf-adjustment-evidence-v1", "collected_at": now_iso(),
              "provider_published_at": "unknown", "period": [args.start, args.end],
              "adjusted_file_sha256": hashlib.sha256(source).hexdigest(),
              "formula": "D_inferred = U_previous - U_current * A_previous / A_current",
              "event_threshold_absolute_ratio_change": 0.0005,
              "limitations": "Inverting the formula is not an independent cash-distribution test. Events are candidates, not verified ex-dates. No inference about OHLC adjustment or tradable returns.",
              "by_ticker": {}}
    for code in ("069500", "102110"):
        candidate = next(c for c in doc["candidates"] if c["ticker"] == code)
        adjusted = {r["date"]: float(r["close"]) for r in candidate["rows"]}
        unadjusted, receipts = collect_prices(code, args.start, args.max_pages)
        events = adjustment_events(adjusted, unadjusted, args.start, args.end)
        for row in events:
            row["status"] = "inferred_cash_unverified"
            if code == "102110" and row["date"] == "2026-10-29":
                row["status"] = "excluded_unexplained_ratio_reset"
        report["by_ticker"][code] = {"source_receipts": receipts,
            "unadjusted_coverage": [min(unadjusted), max(unadjusted)],
            "events": events, "n_events": len(events)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v["n_events"] for k, v in report["by_ticker"].items()}))


if __name__ == "__main__":
    main()
