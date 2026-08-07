"""Orchestrator: collectors -> analytics -> ``derivatives_intel_v1.json``.

Output shape follows the house style established by ``liquidity_intel_v1``:
``schema_version`` / ``generated_at`` / payload / ``feed_status`` / ``stats``,
with every section degrading to an explicit "unavailable" flag rather than
vanishing, so the dashboard never has to guess why a panel is empty.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from . import finra
from .analyze import FlowRules, build_snapshot, detect_flow
from .httputil import make_session
from .models import FlowAlert, OptionTrade, TickerSnapshot
from .storage import connect, known_dates, load_short_volume, record_alerts, upsert_short_volume

log = logging.getLogger(__name__)

SCHEMA_VERSION = "derivatives_intel_v1"


def build_derivatives_intel(
    tickers: Sequence[str],
    rules: FlowRules,
    db_path: Path,
    fetch_live: bool = True,
    flow_session: Optional[date] = None,
    databento_key: Optional[str] = None,
    max_cost_usd: float = 1.0,
    baseline_days: int = 20,
    short_lookback_days: int = 40,
) -> dict:
    """Collect everything available and assemble the dashboard document."""
    tickers = [t.upper() for t in tickers]
    feed_status: list[dict] = []
    session = make_session()

    # ---------------- short volume + short interest (free) ----------------
    short_by_symbol: dict[str, list] = {t: [] for t in tickers}
    interest_by_symbol: dict[str, list] = {t: [] for t in tickers}

    with connect(db_path) as conn:
        if fetch_live:
            # Backfill depth is driven by the *least* covered ticker, not the
            # first one: adding a symbol to the watchlist must trigger a full
            # backfill for it even when the incumbents are already warm.
            coverage = min((len(known_dates(conn, t)) for t in tickers), default=0)
            missing_window = short_lookback_days if coverage < baseline_days else 5
            try:
                rows, days = finra.fetch_recent_short_volume(
                    session, tickers, lookback_days=missing_window
                )
                upsert_short_volume(conn, rows)
                feed_status.append(
                    {"source": "finra_daily_short_volume", "ok": bool(days), "error": None,
                     "days_retrieved": len(days)}
                )
            except Exception as exc:  # collector must never take the build down
                log.exception("short volume fetch failed")
                feed_status.append(
                    {"source": "finra_daily_short_volume", "ok": False, "error": str(exc)}
                )
        else:
            feed_status.append(
                {"source": "finra_daily_short_volume", "ok": True, "error": None, "note": "cache only"}
            )

        for ticker in tickers:
            short_by_symbol[ticker] = load_short_volume(conn, ticker, limit=baseline_days * 3)

        if fetch_live:
            ok = 0
            for ticker in tickers:
                try:
                    interest_by_symbol[ticker] = finra.fetch_short_interest(session, ticker)
                    ok += 1
                except Exception as exc:
                    log.warning("short interest failed for %s: %s", ticker, exc)
            feed_status.append(
                {"source": "finra_short_interest", "ok": ok > 0, "error": None, "symbols_ok": ok}
            )

        # ---------------- options flow (billable, optional) ----------------
        trades_by_symbol: dict[str, list[OptionTrade]] = {t: [] for t in tickers}
        alerts_by_symbol: dict[str, list[FlowAlert]] = {t: [] for t in tickers}
        flow_cost: Optional[float] = None

        if fetch_live and databento_key:
            asof = flow_session or _last_weekday()
            try:
                from .flow_source import EodFlowLoader

                loader = EodFlowLoader(databento_key, max_cost_usd=max_cost_usd)
                costs: list[float] = []
                trades = loader.load(tickers, asof, on_cost=costs.append)
                flow_cost = costs[0] if costs else None

                for trade in trades:
                    bucket = trades_by_symbol.get(trade.contract.underlying)
                    if bucket is not None:
                        bucket.append(trade)

                for ticker in tickers:
                    alerts_by_symbol[ticker] = detect_flow(trades_by_symbol[ticker], rules, asof)
                    record_alerts(conn, alerts_by_symbol[ticker])

                feed_status.append(
                    {"source": "databento_opra", "ok": True, "error": None,
                     "session": asof.isoformat(), "trades": len(trades),
                     "cost_usd": round(flow_cost, 4) if flow_cost is not None else None}
                )
            except Exception as exc:
                log.exception("options flow fetch failed")
                feed_status.append({"source": "databento_opra", "ok": False, "error": str(exc)})
        else:
            feed_status.append(
                {"source": "databento_opra", "ok": False, "error": None,
                 "note": "no DATABENTO_API_KEY — flow section disabled"}
            )

    # ---------------- assemble ----------------
    snapshots = [
        build_snapshot(
            ticker,
            trades_by_symbol[ticker],
            alerts_by_symbol[ticker],
            short_by_symbol[ticker],
            interest_by_symbol[ticker],
            baseline_days=baseline_days,
        )
        for ticker in tickers
    ]

    flow_available = any(s.flow_alerts or s.call_premium or s.put_premium for s in snapshots)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "name": "Derivatives Intel",
            "description": (
                "OPRA 옵션 플로우(Databento) + FINRA 공매도 거래량·잔고. "
                "공매도 비율은 절대값이 아니라 종목별 20일 baseline 대비 z-score로 해석."
            ),
        },
        "flow_available": flow_available,
        "short_volume_available": any(s.short_volume is not None for s in snapshots),
        "rules": {
            "min_notional": rules.min_notional,
            "block_min_size": rules.block_min_size,
            "sweep_window_ms": rules.sweep_window_ms,
            "sweep_min_venues": rules.sweep_min_venues,
            "baseline_days": baseline_days,
        },
        "tickers": [_snapshot_json(s) for s in snapshots],
        "top_alerts": [
            a.to_json()
            for a in sorted(
                (a for s in snapshots for a in s.flow_alerts),
                key=lambda a: a.notional,
                reverse=True,
            )[:25]
        ],
        "feed_status": feed_status,
        "stats": {
            "tickers": len(snapshots),
            "flow_alerts": sum(len(s.flow_alerts) for s in snapshots),
            "short_volume_days": {s.symbol: len(short_by_symbol[s.symbol]) for s in snapshots},
            "flow_cost_usd": round(flow_cost, 4) if flow_cost is not None else None,
            "sources_ok": sum(1 for f in feed_status if f.get("ok")),
            "sources_failed": sum(1 for f in feed_status if not f.get("ok")),
        },
    }


def _snapshot_json(snap: TickerSnapshot) -> dict:
    sv = snap.short_volume
    si = snap.short_interest
    return {
        "symbol": snap.symbol,
        "short_volume": None
        if sv is None
        else {
            "date": sv.date.isoformat(),
            "short_volume": round(sv.short_volume, 2),
            "short_exempt_volume": round(sv.short_exempt_volume, 2),
            "total_volume": round(sv.total_volume, 2),
            "short_ratio": round(sv.short_ratio, 5) if sv.short_ratio is not None else None,
            "markets": sv.markets,
        },
        "short_ratio_mean_20d": round(snap.short_ratio_mean_20d, 5)
        if snap.short_ratio_mean_20d is not None
        else None,
        "short_ratio_z": round(snap.short_ratio_z, 3) if snap.short_ratio_z is not None else None,
        "short_interest": None
        if si is None
        else {
            "settlement_date": si.settlement_date.isoformat(),
            "current_short": si.current_short,
            "previous_short": si.previous_short,
            "avg_daily_volume": si.avg_daily_volume,
            "days_to_cover": si.days_to_cover,
            "change_pct": si.change_pct,
        },
        "call_premium": round(snap.call_premium, 2),
        "put_premium": round(snap.put_premium, 2),
        "bullish_premium": round(snap.bullish_premium, 2),
        "bearish_premium": round(snap.bearish_premium, 2),
        "put_call_premium_ratio": round(snap.put_call_premium_ratio, 4)
        if snap.put_call_premium_ratio is not None
        else None,
        "flow_alerts": [a.to_json() for a in snap.flow_alerts[:20]],
    }


def _last_weekday(today: Optional[date] = None) -> date:
    from datetime import timedelta

    day = today or date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def write_json(doc: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    log.info("wrote %s (%d bytes)", output, output.stat().st_size)
