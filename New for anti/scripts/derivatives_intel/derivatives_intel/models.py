"""Core dataclasses shared by collectors, analytics and alerting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional

Right = Literal["C", "P"]
Aggressor = Literal["BUY", "SELL", "MID"]
Sentiment = Literal["bullish", "bearish", "neutral"]

CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True, slots=True)
class OptionContract:
    """A single listed option, decoded from its OSI symbol."""

    osi: str
    underlying: str
    expiry: date
    right: Right
    strike: float

    @property
    def label(self) -> str:
        return f"{self.underlying} {self.expiry:%y%m%d} {self.right}{self.strike:g}"

    def dte(self, asof: date) -> int:
        return (self.expiry - asof).days


@dataclass(slots=True)
class OptionTrade:
    """One OPRA print, enriched with the NBBO captured at trade time."""

    contract: OptionContract
    ts: datetime
    price: float
    size: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    publisher_id: int = 0
    sequence: int = 0

    @property
    def notional(self) -> float:
        return self.price * self.size * CONTRACT_MULTIPLIER

    @property
    def aggressor(self) -> Aggressor:
        """Who crossed the spread.

        OPRA prints carry no side flag, so the only honest classifier is the
        trade price against the NBBO at the moment of the print. Anything that
        lands strictly inside the spread is left as MID rather than guessed.
        """
        if self.bid is None or self.ask is None or self.ask <= 0 or self.ask < self.bid:
            return "MID"
        if self.price >= self.ask:
            return "BUY"
        if self.price <= self.bid:
            return "SELL"
        mid = (self.bid + self.ask) / 2
        span = self.ask - self.bid
        if span > 0 and self.price > mid + span * 0.25:
            return "BUY"
        if span > 0 and self.price < mid - span * 0.25:
            return "SELL"
        return "MID"

    @property
    def sentiment(self) -> Sentiment:
        """Directional read on the underlying, not on the option."""
        agg = self.aggressor
        if agg == "MID":
            return "neutral"
        bullish = (self.contract.right == "C") == (agg == "BUY")
        return "bullish" if bullish else "bearish"


@dataclass(slots=True)
class FlowAlert:
    """An aggregated print (or burst of prints) that cleared the filters."""

    contract: OptionContract
    ts: datetime
    kind: Literal["block", "sweep", "large"]
    aggressor: Aggressor
    sentiment: Sentiment
    size: int
    notional: float
    vwap: float
    venues: int = 1
    prints: int = 1
    dte: int = 0
    spot_ref: Optional[float] = None

    def to_json(self) -> dict:
        return {
            "osi": self.contract.osi,
            "underlying": self.contract.underlying,
            "label": self.contract.label,
            "expiry": self.contract.expiry.isoformat(),
            "right": self.contract.right,
            "strike": self.contract.strike,
            "ts": self.ts.isoformat(),
            "kind": self.kind,
            "aggressor": self.aggressor,
            "sentiment": self.sentiment,
            "size": self.size,
            "notional": round(self.notional, 2),
            "vwap": round(self.vwap, 4),
            "venues": self.venues,
            "prints": self.prints,
            "dte": self.dte,
        }


@dataclass(slots=True)
class ShortVolumeRow:
    """One row of FINRA's daily consolidated short-sale volume file."""

    date: date
    symbol: str
    short_volume: float
    short_exempt_volume: float
    total_volume: float
    markets: str = ""

    @property
    def short_ratio(self) -> Optional[float]:
        if self.total_volume <= 0:
            return None
        return self.short_volume / self.total_volume


@dataclass(slots=True)
class ShortInterestRow:
    """One settlement of FINRA's bi-monthly consolidated short interest."""

    settlement_date: date
    symbol: str
    current_short: int
    previous_short: int
    avg_daily_volume: int
    days_to_cover: Optional[float]
    change_pct: Optional[float]


@dataclass(slots=True)
class TickerSnapshot:
    """Everything the dashboard shows for one underlying."""

    symbol: str
    short_volume: Optional[ShortVolumeRow] = None
    short_ratio_mean_20d: Optional[float] = None
    short_ratio_z: Optional[float] = None
    short_interest: Optional[ShortInterestRow] = None
    flow_alerts: list[FlowAlert] = field(default_factory=list)
    call_premium: float = 0.0
    put_premium: float = 0.0
    bullish_premium: float = 0.0
    bearish_premium: float = 0.0

    @property
    def put_call_premium_ratio(self) -> Optional[float]:
        if self.call_premium <= 0:
            return None
        return self.put_premium / self.call_premium
