"""Orchestrator: collectors -> analytics -> ``derivatives_intel_v1.json``.

Every source here is free and key-free. Output shape follows the house style
established by ``liquidity_intel_v1``: ``schema_version`` / ``generated_at`` /
payload / ``feed_status`` / ``stats``, with each section degrading to an explicit
"unavailable" flag rather than vanishing, so the dashboard never has to guess
why a panel is empty.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from . import cboe, finra
from .analyze import ChainRules, build_snapshot
from .httputil import make_session
from .models import ChainSummary, TickerSnapshot
from .storage import (
    connect,
    known_dates,
    load_short_volume,
    record_unusual,
    recurring_strikes,
    upsert_short_volume,
)

log = logging.getLogger(__name__)

SCHEMA_VERSION = "derivatives_intel_v1"


def build_derivatives_intel(
    tickers: Sequence[str],
    rules: ChainRules,
    db_path: Path,
    fetch_live: bool = True,
    with_chain: bool = True,
    baseline_days: int = 20,
    short_lookback_days: int = 40,
) -> dict:
    """Collect everything available and assemble the dashboard document."""
    tickers = [t.upper() for t in tickers]
    feed_status: list[dict] = []
    session = make_session()
    asof = date.today()

    short_by_symbol: dict[str, list] = {t: [] for t in tickers}
    interest_by_symbol: dict[str, list] = {t: [] for t in tickers}
    chains: dict[str, object] = {}
    recurring: dict[str, list] = {t: [] for t in tickers}

    with connect(db_path) as conn:
        # ------------------ FINRA daily short volume ------------------
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
                feed_status.append({
                    "source": "finra_daily_short_volume", "ok": bool(days),
                    "error": None, "days_retrieved": len(days), "cost": "free",
                })
            except Exception as exc:  # a collector must never take the build down
                log.exception("short volume fetch failed")
                feed_status.append(
                    {"source": "finra_daily_short_volume", "ok": False, "error": str(exc)}
                )
        else:
            feed_status.append({
                "source": "finra_daily_short_volume", "ok": True,
                "error": None, "note": "cache only",
            })

        for ticker in tickers:
            short_by_symbol[ticker] = load_short_volume(conn, ticker, limit=baseline_days * 3)

        # ------------------ FINRA short interest ------------------
        if fetch_live:
            ok = 0
            for ticker in tickers:
                try:
                    interest_by_symbol[ticker] = finra.fetch_short_interest(session, ticker)
                    ok += 1
                except Exception as exc:
                    log.warning("short interest failed for %s: %s", ticker, exc)
            feed_status.append({
                "source": "finra_short_interest", "ok": ok > 0,
                "error": None, "symbols_ok": ok, "cost": "free",
            })

        # ------------------ CBOE delayed option chains ------------------
        if fetch_live and with_chain:
            try:
                chains, failed = cboe.fetch_chains(session, tickers)
                feed_status.append({
                    "source": "cboe_delayed_chain", "ok": bool(chains), "error": None,
                    "symbols_ok": len(chains), "failed": failed, "cost": "free",
                    "note": "15분 지연 스냅샷 — 체결 단위 테이프가 아님",
                })
            except Exception as exc:
                log.exception("chain fetch failed")
                feed_status.append({"source": "cboe_delayed_chain", "ok": False, "error": str(exc)})
        else:
            feed_status.append({
                "source": "cboe_delayed_chain", "ok": False, "error": None,
                "note": "disabled (--no-chain or --no-fetch)",
            })

        # ------------------ assemble ------------------
        snapshots = [
            build_snapshot(
                ticker,
                chains.get(ticker),  # type: ignore[arg-type]
                rules,
                short_by_symbol[ticker],
                interest_by_symbol[ticker],
                baseline_days=baseline_days,
                asof=asof,
            )
            for ticker in tickers
        ]

        for snap in snapshots:
            if snap.unusual:
                record_unusual(conn, asof, snap.unusual)
            recurring[snap.symbol] = recurring_strikes(conn, snap.symbol)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "name": "Derivatives Intel",
            "description": (
                "CBOE 지연 옵션 체인 + FINRA 공매도 거래량·잔고. 전부 무료·무키 소스. "
                "공매도 비율은 절대값이 아니라 종목별 20일 baseline 대비 z-score로 읽고, "
                "옵션은 체결 방향이 아니라 volume/OI(신규 포지셔닝)로 읽는다."
            ),
            "limitations": [
                "체인 스냅샷이라 sweep(수 백 ms 다중 거래소 체결) 탐지는 불가능하다.",
                "체결별 매수/매도 주체(aggressor) 판정도 불가능하므로 방향 라벨을 붙이지 않는다.",
                "CBOE 체인은 약 15분 지연이다.",
                "위 둘은 OPRA 틱 데이터(유료)가 있어야만 가능하다.",
            ],
        },
        "chain_available": bool(chains),
        "short_volume_available": any(s.short_volume is not None for s in snapshots),
        "rules": {
            "min_notional": rules.min_notional,
            "min_volume": rules.min_volume,
            "min_vol_oi_ratio": rules.min_vol_oi_ratio,
            "max_abs_delta": rules.max_abs_delta,
            "baseline_days": baseline_days,
        },
        "tickers": [_snapshot_json(s, recurring.get(s.symbol, [])) for s in snapshots],
        "top_unusual": [
            u.to_json()
            for u in sorted(
                (u for s in snapshots for u in s.unusual),
                key=lambda u: u.score,
                reverse=True,
            )[:25]
        ],
        "feed_status": feed_status,
        "stats": {
            "tickers": len(snapshots),
            "unusual_contracts": sum(len(s.unusual) for s in snapshots),
            "chains_ok": len(chains),
            "short_volume_days": {s.symbol: len(short_by_symbol[s.symbol]) for s in snapshots},
            "sources_ok": sum(1 for f in feed_status if f.get("ok")),
            "sources_failed": sum(1 for f in feed_status if not f.get("ok")),
            "cost_usd": 0.0,
        },
    }


def _chain_json(c: Optional[ChainSummary]) -> Optional[dict]:
    if c is None:
        return None
    return {
        "spot": round(c.spot, 4),
        "as_of": c.as_of.isoformat() if c.as_of else None,
        "iv30": round(c.iv30, 3) if c.iv30 is not None else None,
        "call_volume": c.call_volume,
        "put_volume": c.put_volume,
        "call_oi": c.call_oi,
        "put_oi": c.put_oi,
        "call_premium": round(c.call_premium, 2),
        "put_premium": round(c.put_premium, 2),
        "put_call_volume_ratio": round(c.put_call_volume_ratio, 4)
        if c.put_call_volume_ratio is not None else None,
        "put_call_premium_ratio": round(c.put_call_premium_ratio, 4)
        if c.put_call_premium_ratio is not None else None,
        "put_call_oi_ratio": round(c.put_call_oi_ratio, 4)
        if c.put_call_oi_ratio is not None else None,
        "net_delta_notional": round(c.net_delta_notional, 2),
        "gamma_exposure": round(c.gamma_exposure, 2),
        "contracts_considered": c.contracts_considered,
    }


def _snapshot_json(snap: TickerSnapshot, recurring: list[dict]) -> dict:
    sv = snap.short_volume
    si = snap.short_interest
    return {
        "symbol": snap.symbol,
        "short_volume": None if sv is None else {
            "date": sv.date.isoformat(),
            "short_volume": round(sv.short_volume, 2),
            "short_exempt_volume": round(sv.short_exempt_volume, 2),
            "total_volume": round(sv.total_volume, 2),
            "short_ratio": round(sv.short_ratio, 5) if sv.short_ratio is not None else None,
            "markets": sv.markets,
        },
        "short_ratio_mean_20d": round(snap.short_ratio_mean_20d, 5)
        if snap.short_ratio_mean_20d is not None else None,
        "short_ratio_z": round(snap.short_ratio_z, 3)
        if snap.short_ratio_z is not None else None,
        "short_interest": None if si is None else {
            "settlement_date": si.settlement_date.isoformat(),
            "current_short": si.current_short,
            "previous_short": si.previous_short,
            "avg_daily_volume": si.avg_daily_volume,
            "days_to_cover": si.days_to_cover,
            "change_pct": si.change_pct,
        },
        "chain": _chain_json(snap.chain),
        "unusual": [u.to_json() for u in snap.unusual],
        "recurring_strikes": recurring,
    }


def write_json(doc: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    log.info("wrote %s (%d bytes)", output, output.stat().st_size)
