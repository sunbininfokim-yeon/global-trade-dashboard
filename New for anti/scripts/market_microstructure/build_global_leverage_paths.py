#!/usr/bin/env python3
"""Build paper-style leveraged ETF versus unlevered benchmark price paths.

These are external-regime comparisons only.  SOXL/KORU are not added to the
Korean cash-market LETF turnover or rebalance calculation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent

PAIRS = (
    {
        "id": "us_semis",
        "title_ko": "미국 반도체: SOXL vs SMH",
        "paper_role_ko": "The AI Trade의 Leveraged pain 공개 프록시",
        "leveraged": "SOXL",
        "benchmark": "SMH",
        "benchmark_note_ko": "원 도표의 SOX 지수 대신 상장 반도체 ETF SMH를 사용",
    },
    {
        "id": "korea_equity",
        "title_ko": "한국: KORU vs EWY",
        "paper_role_ko": "The AI Trade의 Korea leading 보조 비교",
        "leveraged": "KORU",
        "benchmark": "EWY",
        "benchmark_note_ko": "KORU는 미국 상장 3배 ETF, EWY는 한국 주식 ETF. 국내 현물 영향도 계산에 합산하지 않음",
    },
)


def rebased_pair(leveraged: pd.Series, benchmark: pd.Series) -> list[dict[str, Any]]:
    """Align two close series and index both to 100 at their shared start."""
    frame = pd.concat([leveraged.rename("leveraged"), benchmark.rename("benchmark")], axis=1).dropna()
    if frame.empty:
        return []
    base_l = float(frame.iloc[0]["leveraged"])
    base_b = float(frame.iloc[0]["benchmark"])
    if base_l <= 0 or base_b <= 0:
        return []
    return [
        {
            "date": str(index.date()),
            "leveraged_index": round(float(row["leveraged"]) / base_l * 100.0, 4),
            "benchmark_index": round(float(row["benchmark"]) / base_b * 100.0, 4),
        }
        for index, row in frame.iterrows()
    ]


def _close(symbol: str, period: str) -> pd.Series:
    import yfinance as yf

    frame = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if frame is None or frame.empty or "Close" not in frame:
        raise RuntimeError(f"Yahoo history unavailable for {symbol}")
    close = frame["Close"].dropna().copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def build_payload(*, period: str = "1y") -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    errors: list[str] = []
    for pair in PAIRS:
        try:
            points = rebased_pair(_close(pair["leveraged"], period), _close(pair["benchmark"], period))
            if not points:
                raise RuntimeError("no overlapping adjusted closes")
            latest = points[-1]
            series.append({
                **pair,
                "points": points,
                "n_points": len(points),
                "as_of": latest["date"],
                "leveraged_return_pct": round(latest["leveraged_index"] - 100.0, 3),
                "benchmark_return_pct": round(latest["benchmark_index"] - 100.0, 3),
                "quality": "observed",
                "source": "Yahoo Finance adjusted close via yfinance",
            })
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{pair['id']}: {type(exc).__name__}: {exc}")
            series.append({**pair, "points": [], "n_points": 0, "quality": "missing"})
    observed = [row for row in series if row.get("quality") == "observed"]
    return {
        "schema_version": "global-leverage-price-paths-v1",
        "as_of": max((row.get("as_of") for row in observed), default=None),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "quality": "observed" if observed else "missing",
        "series": series,
        "errors": errors,
        "note_ko": "가격 성과 비교이며 AUM·순자금유입·현물 리밸런싱 거래량이 아니다. 한국 상장 LETF 및 KRX 수급과 합산하지 않는다.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="1y")
    parser.add_argument("--out", type=Path, default=ROOT / "../../public/data/global_leverage_price_paths_v1.json")
    args = parser.parse_args()
    payload = build_payload(period=args.period)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({payload['quality']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
