"""Rebuild snapshot objects from an emitted document.

Used so the notification digest is rendered from exactly the JSON the dashboard
will read, rather than from a parallel in-memory path that could drift from it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .models import (
    ChainSummary,
    OptionContract,
    ShortInterestRow,
    ShortVolumeRow,
    TickerSnapshot,
    UnusualActivity,
)


def snapshots_from_doc(doc: dict) -> list[TickerSnapshot]:
    return [_snapshot(entry) for entry in doc.get("tickers", [])]


def _snapshot(entry: dict) -> TickerSnapshot:
    symbol = entry["symbol"]
    sv = entry.get("short_volume")
    si = entry.get("short_interest")
    chain = entry.get("chain")

    return TickerSnapshot(
        symbol=symbol,
        short_volume=None if not sv else ShortVolumeRow(
            date=date.fromisoformat(sv["date"]),
            symbol=symbol,
            short_volume=sv["short_volume"],
            short_exempt_volume=sv["short_exempt_volume"],
            total_volume=sv["total_volume"],
            markets=sv.get("markets", ""),
        ),
        short_ratio_mean_20d=entry.get("short_ratio_mean_20d"),
        short_ratio_z=entry.get("short_ratio_z"),
        short_interest=None if not si else ShortInterestRow(
            settlement_date=date.fromisoformat(si["settlement_date"]),
            symbol=symbol,
            current_short=si["current_short"],
            previous_short=si["previous_short"],
            avg_daily_volume=si["avg_daily_volume"],
            days_to_cover=si.get("days_to_cover"),
            change_pct=si.get("change_pct"),
        ),
        chain=None if not chain else ChainSummary(
            symbol=symbol,
            spot=chain["spot"],
            as_of=_dt(chain.get("as_of")),
            iv30=chain.get("iv30"),
            call_volume=chain.get("call_volume", 0),
            put_volume=chain.get("put_volume", 0),
            call_oi=chain.get("call_oi", 0),
            put_oi=chain.get("put_oi", 0),
            call_premium=chain.get("call_premium", 0.0),
            put_premium=chain.get("put_premium", 0.0),
            net_delta_notional=chain.get("net_delta_notional", 0.0),
            gamma_exposure=chain.get("gamma_exposure", 0.0),
            contracts_considered=chain.get("contracts_considered", 0),
        ),
        unusual=[_unusual(u) for u in entry.get("unusual", [])],
    )


def _unusual(u: dict) -> UnusualActivity:
    return UnusualActivity(
        contract=OptionContract(
            osi=u["osi"],
            underlying=u["underlying"],
            expiry=date.fromisoformat(u["expiry"]),
            right=u["right"],
            strike=u["strike"],
        ),
        volume=u["volume"],
        open_interest=u["open_interest"],
        vol_oi_ratio=u.get("vol_oi_ratio"),
        notional=u["notional"],
        mid=u.get("mid", 0.0),
        last=u.get("last", 0.0),
        dte=u.get("dte", 0),
        delta=u.get("delta"),
        iv=u.get("iv"),
        moneyness=u.get("moneyness"),
        score=u.get("score", 0.0),
        reasons=list(u.get("reasons", [])),
    )


def _dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
