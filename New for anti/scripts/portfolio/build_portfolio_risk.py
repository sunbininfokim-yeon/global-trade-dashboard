#!/usr/bin/env python3
"""Build portfolio_risk_v1.json from holdings + return fixture (or live prices later)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from portfolio_risk.engine import analyze_portfolio  # noqa: E402

DEFAULT_HOLDINGS = ROOT / "config" / "holdings.example.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "portfolio_risk_v1.json"
FIXTURE_RETURNS = ROOT / "tests" / "fixtures" / "returns_sample.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _synth_returns(tickers: list[str], n: int = 252, seed: int = 42) -> dict[str, list[float]]:
    """Correlated synthetic daily returns for offline demos (not market data)."""
    rng = random.Random(seed)
    # common factor + idiosyncratic
    market = [rng.gauss(0.0004, 0.01) for _ in range(n)]
    out: dict[str, list[float]] = {}
    betas = {t: 0.6 + 0.2 * (i % 3) for i, t in enumerate(tickers)}
    for t in tickers:
        series = []
        for m in market:
            series.append(betas[t] * m + rng.gauss(0.0, 0.012))
        out[t] = series
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Portfolio Sharpe / diversification snapshot")
    ap.add_argument("--holdings", type=Path, default=DEFAULT_HOLDINGS)
    ap.add_argument("--returns", type=Path, default=None, help="JSON {ticker: [returns]}")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--print-stats", action="store_true")
    args = ap.parse_args()

    holdings_doc = json.loads(args.holdings.read_text(encoding="utf-8"))
    holdings = holdings_doc["holdings"]
    tickers = [h["ticker"] for h in holdings]
    rf = float(holdings_doc.get("risk_free_annual") or 0.03)

    if args.returns and args.returns.exists():
        returns = json.loads(args.returns.read_text(encoding="utf-8"))
        source = str(args.returns)
    elif FIXTURE_RETURNS.exists():
        returns = json.loads(FIXTURE_RETURNS.read_text(encoding="utf-8"))
        source = str(FIXTURE_RETURNS)
    else:
        returns = _synth_returns(tickers)
        source = "synthetic_offline"

    # keep only held tickers
    returns = {t: returns[t] for t in tickers if t in returns}
    missing = [t for t in tickers if t not in returns]
    if missing and source == "synthetic_offline":
        returns = _synth_returns(tickers)
        missing = []

    result = analyze_portfolio(holdings, returns, risk_free_annual=rf)
    snap = {
        "schema_version": "portfolio-risk-v1",
        "generated_at": _now(),
        "model": {
            "name": "portfolio_risk_v1",
            "returns_source": source,
            "missing_tickers": missing,
        },
        "holdings_file": str(args.holdings.name),
        "portfolio": result,
        "link": {
            "fundamentals": "See dart_universe_v1.json industry_kit / ma_metrics for same names",
            "note_ko": "가격 수익률(포트)과 공시 재무(DART)는 서로 다른 축입니다.",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if args.print_stats:
        d = result["diversification"]
        s = result["sharpe"]
        print(
            f"sharpe={s['sharpe_annualized']} effective_n={result['concentration']['effective_n']} "
            f"avg_corr={result['avg_pairwise_correlation']} div={d['score']} ({d['band']}) → {args.output}"
        )

    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
