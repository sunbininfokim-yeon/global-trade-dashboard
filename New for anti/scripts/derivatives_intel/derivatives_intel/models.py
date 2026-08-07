"""Core dataclasses shared by collectors, analytics and alerting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional

Right = Literal["C", "P"]

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
        return f"{self.underlying} {self.expiry:%y%m%d} {self.strike:g}{self.right}"

    def dte(self, asof: date) -> int:
        return (self.expiry - asof).days


@dataclass(slots=True)
class ChainQuote:
    """One contract's line in a delayed chain snapshot."""

    contract: OptionContract
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    theo: Optional[float] = None
    last_trade_time: Optional[datetime] = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def notional(self) -> float:
        """Today's traded premium. Mid is steadier than a possibly stale last."""
        return self.volume * self.mid * CONTRACT_MULTIPLIER

    @property
    def vol_oi_ratio(self) -> Optional[float]:
        """Volume against resting open interest.

        Above 1.0 means more contracts changed hands today than existed at the
        open — i.e. this is new positioning, not inventory being shuffled. It is
        the workhorse signal for unusual activity when you have no tape.
        """
        if self.open_interest <= 0:
            return None
        return self.volume / self.open_interest

    @property
    def spread_pct(self) -> Optional[float]:
        if self.bid <= 0 or self.ask <= 0:
            return None
        mid = (self.bid + self.ask) / 2
        return (self.ask - self.bid) / mid if mid > 0 else None


@dataclass(slots=True)
class ChainSnapshot:
    """A whole underlying's chain at one moment."""

    symbol: str
    as_of: Optional[datetime]
    spot: float
    quotes: list[ChainQuote]
    iv30: Optional[float] = None
    underlying_volume: Optional[float] = None
    price_change_pct: Optional[float] = None


@dataclass(slots=True)
class UnusualActivity:
    """A contract that stood out in today's chain."""

    contract: OptionContract
    volume: int
    open_interest: int
    vol_oi_ratio: Optional[float]
    notional: float
    mid: float
    last: float
    dte: int
    delta: Optional[float] = None
    iv: Optional[float] = None
    moneyness: Optional[float] = None
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "osi": self.contract.osi,
            "underlying": self.contract.underlying,
            "label": self.contract.label,
            "expiry": self.contract.expiry.isoformat(),
            "right": self.contract.right,
            "strike": self.contract.strike,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "vol_oi_ratio": round(self.vol_oi_ratio, 3) if self.vol_oi_ratio is not None else None,
            "notional": round(self.notional, 2),
            "mid": round(self.mid, 4),
            "last": round(self.last, 4),
            "dte": self.dte,
            "delta": round(self.delta, 4) if self.delta is not None else None,
            "iv": round(self.iv, 4) if self.iv is not None else None,
            "moneyness": round(self.moneyness, 4) if self.moneyness is not None else None,
            "score": round(self.score, 2),
            "reasons": self.reasons,
        }


@dataclass(slots=True)
class ChainSummary:
    """Aggregate positioning read for one underlying."""

    symbol: str
    spot: float
    as_of: Optional[datetime]
    iv30: Optional[float] = None
    call_volume: int = 0
    put_volume: int = 0
    call_oi: int = 0
    put_oi: int = 0
    call_premium: float = 0.0
    put_premium: float = 0.0
    net_delta_notional: float = 0.0
    gamma_exposure: float = 0.0
    contracts_considered: int = 0

    @property
    def put_call_volume_ratio(self) -> Optional[float]:
        return self.put_volume / self.call_volume if self.call_volume > 0 else None

    @property
    def put_call_premium_ratio(self) -> Optional[float]:
        return self.put_premium / self.call_premium if self.call_premium > 0 else None

    @property
    def put_call_oi_ratio(self) -> Optional[float]:
        return self.put_oi / self.call_oi if self.call_oi > 0 else None


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
    chain: Optional[ChainSummary] = None
    unusual: list[UnusualActivity] = field(default_factory=list)
