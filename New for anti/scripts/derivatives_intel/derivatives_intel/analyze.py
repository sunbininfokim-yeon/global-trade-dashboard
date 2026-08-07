"""Filtering and aggregation: raw prints -> things worth waking someone for."""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Sequence

from .models import (
    CONTRACT_MULTIPLIER,
    FlowAlert,
    OptionTrade,
    ShortInterestRow,
    ShortVolumeRow,
    TickerSnapshot,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class FlowRules:
    """Thresholds for what counts as notable. All tunable from config."""

    min_notional: float = 1_000_000.0
    block_min_size: int = 250
    sweep_window_ms: int = 500
    sweep_min_venues: int = 2
    sweep_min_notional: float = 500_000.0
    min_dte: int = 0
    max_dte: int = 400
    exclude_mid: bool = True

    @classmethod
    def from_dict(cls, raw: dict) -> "FlowRules":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def detect_flow(
    trades: Sequence[OptionTrade],
    rules: FlowRules,
    asof: Optional[date] = None,
) -> list[FlowAlert]:
    """Collapse a session's prints into block / sweep / large alerts.

    Sweeps are the interesting case: one buyer lifting several venues' offers
    within a few hundred milliseconds shows up on the tape as a scatter of
    unremarkable prints, and only becomes visible once you group by contract +
    aggressor side inside a short time window.
    """
    asof = asof or date.today()
    alerts: list[FlowAlert] = []

    grouped: dict[tuple[str, str], list[OptionTrade]] = defaultdict(list)
    for trade in trades:
        if rules.exclude_mid and trade.aggressor == "MID":
            continue
        dte = trade.contract.dte(asof)
        if dte < rules.min_dte or dte > rules.max_dte:
            continue
        grouped[(trade.contract.osi, trade.aggressor)].append(trade)

    window = timedelta(milliseconds=rules.sweep_window_ms)

    for (_osi, aggressor), bucket in grouped.items():
        bucket.sort(key=lambda t: t.ts)
        for cluster in _cluster_by_time(bucket, window):
            alert = _build_alert(cluster, aggressor, rules, asof)
            if alert is not None:
                alerts.append(alert)

    alerts.sort(key=lambda a: a.notional, reverse=True)
    return alerts


def _cluster_by_time(trades: list[OptionTrade], window: timedelta) -> Iterable[list[OptionTrade]]:
    """Greedily group consecutive prints that fall inside a rolling window."""
    cluster: list[OptionTrade] = []
    anchor = None
    for trade in trades:
        if anchor is None or trade.ts - anchor <= window:
            if anchor is None:
                anchor = trade.ts
            cluster.append(trade)
        else:
            yield cluster
            cluster = [trade]
            anchor = trade.ts
    if cluster:
        yield cluster


def _build_alert(
    cluster: list[OptionTrade],
    aggressor: str,
    rules: FlowRules,
    asof: date,
) -> Optional[FlowAlert]:
    size = sum(t.size for t in cluster)
    notional = sum(t.notional for t in cluster)
    venues = len({t.publisher_id for t in cluster})
    head = cluster[0]

    is_sweep = (
        len(cluster) > 1
        and venues >= rules.sweep_min_venues
        and notional >= rules.sweep_min_notional
    )
    is_block = any(t.size >= rules.block_min_size for t in cluster)
    is_large = notional >= rules.min_notional

    if not (is_sweep or (is_block and is_large) or is_large):
        return None

    kind = "sweep" if is_sweep else ("block" if is_block else "large")
    vwap = notional / (size * CONTRACT_MULTIPLIER) if size else head.price

    return FlowAlert(
        contract=head.contract,
        ts=head.ts,
        kind=kind,  # type: ignore[arg-type]
        aggressor=aggressor,  # type: ignore[arg-type]
        sentiment=head.sentiment,
        size=size,
        notional=notional,
        vwap=vwap,
        venues=venues,
        prints=len(cluster),
        dte=head.contract.dte(asof),
    )


def summarize_premium(trades: Sequence[OptionTrade]) -> dict[str, float]:
    """Premium split by right and by directional read."""
    out = {"call_premium": 0.0, "put_premium": 0.0, "bullish_premium": 0.0, "bearish_premium": 0.0}
    for trade in trades:
        if trade.contract.right == "C":
            out["call_premium"] += trade.notional
        else:
            out["put_premium"] += trade.notional
        if trade.sentiment == "bullish":
            out["bullish_premium"] += trade.notional
        elif trade.sentiment == "bearish":
            out["bearish_premium"] += trade.notional
    return out


def short_volume_stats(
    rows: Sequence[ShortVolumeRow],
    baseline_days: int = 20,
) -> tuple[Optional[ShortVolumeRow], Optional[float], Optional[float]]:
    """Latest row plus its short ratio's mean and z-score against the baseline.

    The z-score is what actually matters. A 48% short-volume ratio means very
    little on its own; a 48% ratio on a name that sits at 33% +/- 3% is a
    four-sigma event.
    """
    if not rows:
        return None, None, None

    ordered = sorted(rows, key=lambda r: r.date)
    latest = ordered[-1]

    history = [r.short_ratio for r in ordered[:-1] if r.short_ratio is not None]
    history = history[-baseline_days:]
    if len(history) < 5:
        return latest, None, None

    mean = statistics.fmean(history)
    z: Optional[float] = None
    if len(history) >= 2:
        stdev = statistics.stdev(history)
        current = latest.short_ratio
        if stdev > 1e-9 and current is not None:
            z = (current - mean) / stdev
    return latest, mean, z


def build_snapshot(
    symbol: str,
    trades: Sequence[OptionTrade],
    alerts: Sequence[FlowAlert],
    short_rows: Sequence[ShortVolumeRow],
    short_interest: Sequence[ShortInterestRow],
    baseline_days: int = 20,
) -> TickerSnapshot:
    latest, mean, z = short_volume_stats(short_rows, baseline_days)
    premium = summarize_premium(trades)
    return TickerSnapshot(
        symbol=symbol.upper(),
        short_volume=latest,
        short_ratio_mean_20d=mean,
        short_ratio_z=z,
        short_interest=short_interest[-1] if short_interest else None,
        flow_alerts=list(alerts),
        **premium,
    )
