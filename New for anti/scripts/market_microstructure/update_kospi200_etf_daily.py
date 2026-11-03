#!/usr/bin/env python3
"""Append completed trading days to the KOSPI200 ETF candidate panel.

Rows come from FinanceDataReader (Naver fchart, cash-distribution adjusted),
the same source as the existing history. A day is appended only when:

* every overlapping day still has the stored open/high/low/close, so the
  provider has not re-based past prices after a new distribution;
* the day is present in the unadjusted Naver daily price table with the same
  open/high/low/close (no distribution since the last stored day);
* the session is over: an earlier KST date, or today after 18:30 KST
  (after-hours single-price trading ends at 18:00).

Stored rows are never rewritten. Volume differences on stored days are
reported only. Nothing is carried forward from a previous day.

  python update_kospi200_etf_daily.py --tickers 069500
  python update_kospi200_etf_daily.py --tickers 069500 --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from build_kospi200_price_panel import ETF_PATH, ROOT, _number, fetch_naver_price_table, write_json

KST = timezone(timedelta(hours=9))
SESSION_DONE_KST = time(18, 30)
PRICE_TOL = 0.5
# Adjusted prices are rounded to whole won, so the ratio wobbles by ~1e-5 on ordinary days.
RATIO_STEP = 1e-4
OHLC = ("open", "high", "low", "close")
SOURCE = "FinanceDataReader DataReader (Naver fchart, cash-distribution adjusted)"
MANIFEST_DIR = ROOT.parent / "data/manifests"


def completed(day: str, now: datetime) -> bool:
    local = now.astimezone(KST)
    d = date.fromisoformat(day)
    return d < local.date() or (d == local.date() and local.time() >= SESSION_DONE_KST)


def fetch_adjusted(ticker: str, start: str) -> dict[str, dict[str, float]]:
    import FinanceDataReader as fdr

    df = fdr.DataReader(ticker, start)
    return {
        ts.strftime("%Y-%m-%d"): {
            "open": float(r["Open"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "close": float(r["Close"]),
            "volume": float(r["Volume"]),
        }
        for ts, r in df.iterrows()
    }


def fetch_unadjusted(ticker: str) -> dict[str, dict[str, float]]:
    out = {}
    for day, row in fetch_naver_price_table(ticker, pages=2).items():
        out[day] = {
            "open": _number(row["openPrice"]),
            "high": _number(row["highPrice"]),
            "low": _number(row["lowPrice"]),
            "close": _number(row["closePrice"]),
            "volume": float(row["accumulatedTradingVolume"]),
        }
    return out


def plan_ticker(
    candidate: dict[str, Any],
    adjusted: dict[str, dict[str, float]],
    unadjusted: dict[str, dict[str, float]],
    now: datetime,
) -> dict[str, Any]:
    """Return the rows to append and the checks behind them. Never mutates the candidate."""
    stored = {r["date"]: r for r in candidate.get("rows") or []}
    last = max(stored) if stored else None
    overlap = sorted(set(stored) & set(adjusted))
    rebased = [
        {"date": d, "field": k, "stored": stored[d][k], "source": adjusted[d][k]}
        for d in overlap
        for k in OHLC
        if abs(float(stored[d][k]) - adjusted[d][k]) > PRICE_TOL
    ]
    volume_diffs = [
        {"date": d, "stored": stored[d]["volume"], "source": adjusted[d]["volume"]}
        for d in overlap
        if stored[d].get("volume") is not None and float(stored[d]["volume"]) != adjusted[d]["volume"]
    ]
    both = sorted(set(adjusted) & set(unadjusted))
    ratio = {d: adjusted[d]["close"] / unadjusted[d]["close"] for d in both if unadjusted[d]["close"]}
    ratio_steps = [
        {"date": b, "ratio_before": round(ratio[a], 6), "ratio_after": round(ratio[b], 6)}
        for a, b in zip(both, both[1:])
        if a in ratio and b in ratio and abs(ratio[b] - ratio[a]) > RATIO_STEP
    ]
    report: dict[str, Any] = {
        "ticker": candidate["ticker"],
        "last_stored": last,
        "adjusted_over_unadjusted_close_steps": ratio_steps,
        "overlap_days": len(overlap),
        "overlap_ohlc_mismatch": rebased,
        "stored_volume_differs": volume_diffs,
        "appended": [],
        "skipped": [],
    }
    if not overlap:
        report["status"] = "no_overlap"
        return report
    if rebased:
        report["status"] = "provider_rebased"
        return report
    for day in sorted(d for d in adjusted if last is None or d > last):
        bar = adjusted[day]
        if not completed(day, now):
            report["skipped"].append({"date": day, "reason": "session not finished (before 18:30 KST)"})
            continue
        raw = unadjusted.get(day)
        if raw is None:
            report["skipped"].append({"date": day, "reason": "absent from unadjusted daily table"})
            continue
        diff = [k for k in OHLC if abs(raw[k] - bar[k]) > PRICE_TOL]
        if diff:
            report["skipped"].append({"date": day, "reason": f"adjusted != unadjusted on {diff}; new distribution?"})
            continue
        report["appended"].append(
            {
                "date": day,
                **{k: bar[k] for k in OHLC},
                "volume": bar["volume"],
                "volume_quality": (
                    "provisional_same_day" if date.fromisoformat(day) == now.astimezone(KST).date() else "observed"
                ),
                "trading_value_krw": None,
                "trading_value_quality": "missing",
                "session": "regular_close_after_after_hours",
                "source": SOURCE,
                "price_adjustment": candidate.get("price_adjustment") or "unknown",
                "unadjusted_close": raw["close"],
                "collected_at": now.astimezone(timezone.utc).isoformat(),
                "provider_published_at": "unknown",
                "quality": "observed",
            }
        )
    report["status"] = "ok"
    return report


def apply(candidate: dict[str, Any], report: dict[str, Any]) -> None:
    rows = list(candidate.get("rows") or []) + report["appended"]
    rows.sort(key=lambda r: r["date"])
    candidate["rows"] = rows
    candidate["n"] = len(rows)
    candidate["date_start"] = rows[0]["date"] if rows else None
    candidate["date_end"] = rows[-1]["date"] if rows else None


def run(
    tickers: list[str],
    *,
    path: Path = ETF_PATH,
    now: datetime | None = None,
    adjusted_fn: Callable[[str, str], dict[str, dict[str, float]]] = fetch_adjusted,
    unadjusted_fn: Callable[[str], dict[str, dict[str, float]]] = fetch_unadjusted,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_ticker = {c["ticker"]: c for c in doc.get("candidates") or []}
    reports = []
    for ticker in tickers:
        candidate = by_ticker[ticker]
        last = (candidate.get("rows") or [{}])[-1].get("date") or "2019-01-02"
        start = (date.fromisoformat(last) - timedelta(days=60)).isoformat()
        report = plan_ticker(candidate, adjusted_fn(ticker, start), unadjusted_fn(ticker), now)
        if report["status"] == "ok" and not dry_run:
            apply(candidate, report)
        reports.append(report)
    summary = {
        "schema": "kospi200-etf-daily-update-v1",
        "run_at": now.astimezone(timezone.utc).isoformat(),
        "run_at_kst_date": now.astimezone(KST).date().isoformat(),
        "provider_published_at": "unknown",
        "session_rule_ko": "KST 기준 오늘 이전 거래일, 또는 오늘이면 18:30 KST 이후(시간외 단일가 18:00 종료)만 완료로 본다.",
        "dry_run": dry_run,
        "reports": reports,
    }
    if not dry_run and any(r["appended"] for r in reports):
        doc.setdefault("daily_updates", []).append(
            {
                "run_at": summary["run_at"],
                "provider_published_at": "unknown",
                "appended": {r["ticker"]: [x["date"] for x in r["appended"]] for r in reports},
            }
        )
        write_json(path, doc)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="069500")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    summary = run(args.tickers.split(","), dry_run=args.dry_run)
    if args.manifest:
        args.manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if any(r["status"] != "ok" for r in summary["reports"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
