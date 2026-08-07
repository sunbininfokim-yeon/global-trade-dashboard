"""Filtering and scoring: a raw chain -> the handful of lines worth reading."""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from .models import (
    CONTRACT_MULTIPLIER,
    ChainQuote,
    ChainSnapshot,
    ChainSummary,
    ShortInterestRow,
    ShortVolumeRow,
    TickerSnapshot,
    UnusualActivity,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ChainRules:
    """Thresholds for what counts as unusual. All tunable from config."""

    min_notional: float = 250_000.0
    min_volume: int = 100
    min_vol_oi_ratio: float = 1.0
    min_dte: int = 0
    max_dte: int = 400
    max_spread_pct: float = 0.6
    # Deep ITM contracts (|delta| ~ 1) are dominated by exercise, assignment and
    # box spreads rather than directional bets, and their huge premiums would
    # otherwise crowd out every real signal.
    max_abs_delta: float = 0.95
    top_n: int = 20

    @classmethod
    def from_dict(cls, raw: dict) -> "ChainRules":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def find_unusual(
    chain: ChainSnapshot,
    rules: ChainRules,
    asof: Optional[date] = None,
) -> list[UnusualActivity]:
    """Score every contract and return the standouts, best first."""
    asof = asof or date.today()
    out: list[UnusualActivity] = []

    for quote in chain.quotes:
        item = _score_quote(quote, chain, rules, asof)
        if item is not None:
            out.append(item)

    out.sort(key=lambda u: u.score, reverse=True)
    return out[: rules.top_n]


def _score_quote(
    quote: ChainQuote,
    chain: ChainSnapshot,
    rules: ChainRules,
    asof: date,
) -> Optional[UnusualActivity]:
    if quote.volume < rules.min_volume:
        return None

    dte = quote.contract.dte(asof)
    if dte < rules.min_dte or dte > rules.max_dte:
        return None

    if quote.delta is not None and abs(quote.delta) > rules.max_abs_delta:
        return None

    spread = quote.spread_pct
    if spread is not None and spread > rules.max_spread_pct:
        return None

    notional = quote.notional
    if notional < rules.min_notional:
        return None

    vol_oi = quote.vol_oi_ratio
    reasons: list[str] = []
    score = 0.0

    # Premium: log-scaled so a $30M print does not drown out everything else.
    score += math.log10(max(notional, 1.0))
    if notional >= 1_000_000:
        reasons.append("premium>=$1M")

    # New positioning is the core signal.
    if vol_oi is not None and vol_oi >= rules.min_vol_oi_ratio:
        score += min(vol_oi, 20.0) * 0.5
        reasons.append(f"vol/OI={vol_oi:.1f}")
    elif quote.open_interest == 0 and quote.volume > 0:
        score += 3.0
        reasons.append("new strike (no prior OI)")

    # Short-dated conviction reads differently from a LEAP.
    if dte <= 7:
        score += 2.0
        reasons.append(f"{dte}DTE")
    elif dte <= 30:
        score += 1.0

    moneyness = None
    if chain.spot > 0:
        moneyness = quote.contract.strike / chain.spot - 1.0
        if abs(moneyness) > 0.15:
            score += 1.0
            reasons.append("far OTM")

    if not reasons:
        return None

    return UnusualActivity(
        contract=quote.contract,
        volume=quote.volume,
        open_interest=quote.open_interest,
        vol_oi_ratio=vol_oi,
        notional=notional,
        mid=quote.mid,
        last=quote.last,
        dte=dte,
        delta=quote.delta,
        iv=quote.iv,
        moneyness=moneyness,
        score=score,
        reasons=reasons,
    )


def summarize_chain(chain: ChainSnapshot, asof: Optional[date] = None) -> ChainSummary:
    """Aggregate volume, premium, net delta and dealer gamma exposure."""
    asof = asof or date.today()
    summary = ChainSummary(
        symbol=chain.symbol,
        spot=chain.spot,
        as_of=chain.as_of,
        iv30=chain.iv30,
    )

    for quote in chain.quotes:
        if quote.volume <= 0 and quote.open_interest <= 0:
            continue
        summary.contracts_considered += 1
        is_call = quote.contract.right == "C"

        if is_call:
            summary.call_volume += quote.volume
            summary.call_oi += quote.open_interest
            summary.call_premium += quote.notional
        else:
            summary.put_volume += quote.volume
            summary.put_oi += quote.open_interest
            summary.put_premium += quote.notional

        if quote.delta is not None and chain.spot > 0:
            summary.net_delta_notional += (
                quote.delta * quote.volume * CONTRACT_MULTIPLIER * chain.spot
            )

        if quote.gamma is not None and chain.spot > 0:
            # Standard naive convention: dealers are assumed short puts and long
            # calls against retail. Sign is a modelling assumption, not a fact —
            # read the magnitude and the sign flip, not the absolute level.
            signed = quote.gamma * quote.open_interest * (1 if is_call else -1)
            summary.gamma_exposure += signed * CONTRACT_MULTIPLIER * (chain.spot ** 2) * 0.01

    return summary


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
    chain: Optional[ChainSnapshot],
    rules: ChainRules,
    short_rows: Sequence[ShortVolumeRow],
    short_interest: Sequence[ShortInterestRow],
    baseline_days: int = 20,
    asof: Optional[date] = None,
) -> TickerSnapshot:
    latest, mean, z = short_volume_stats(short_rows, baseline_days)
    return TickerSnapshot(
        symbol=symbol.upper(),
        short_volume=latest,
        short_ratio_mean_20d=mean,
        short_ratio_z=z,
        short_interest=short_interest[-1] if short_interest else None,
        chain=summarize_chain(chain, asof) if chain else None,
        unusual=find_unusual(chain, rules, asof) if chain else [],
    )
