"""Databento OPRA collectors — live stream and end-of-day batch.

Cost is the whole design constraint here, so two things are non-negotiable:

1. **Parent symbology.** Subscribing to ``TSLA.OPT`` with ``stype_in="parent"``
   delivers every listed TSLA option and nothing else. The full OPRA feed is
   multiple TB/day; a handful of parents is a rounding error against that.

2. **The ``tbbo`` schema.** OPRA trade prints carry no aggressor flag, so
   ``trades`` alone cannot tell a bought call from a sold one — which is the
   entire point of options flow. ``tbbo`` staples the NBBO onto each print, and
   is dramatically cheaper than reconstructing a book from ``mbp-1``.

For anything that does not need to fire intraday, prefer :class:`EodFlowLoader`:
historical bytes are cheaper than live ones and you pull exactly one session.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator, Optional

from .models import OptionTrade
from .osi import parse_osi

log = logging.getLogger(__name__)

OPRA_DATASET = "OPRA.PILLAR"
FLOW_SCHEMA = "tbbo"
PRICE_SCALE = 1_000_000_000  # databento.FIXED_PRICE_SCALE
UNDEF_PRICE = 9223372036854775807  # INT64_MAX sentinel for "no quote"


def parent_symbols(tickers: Iterable[str]) -> list[str]:
    """``["TSLA", "NVDA"]`` -> ``["TSLA.OPT", "NVDA.OPT"]``.

    Already-suffixed inputs pass through untouched. (Note: no ``rstrip('.OPT')``
    here — that strips a *character set*, which would turn ``SPOT`` into ``S``.)
    """
    out: list[str] = []
    for ticker in tickers:
        sym = ticker.strip().upper()
        out.append(sym if sym.endswith(".OPT") else f"{sym}.OPT")
    return out


def _px(raw: int) -> Optional[float]:
    if raw is None or raw == UNDEF_PRICE or raw == 0:
        return None
    return raw / PRICE_SCALE


class _RecordDecoder:
    """Turns databento records into :class:`OptionTrade`, tracking symbology.

    Both the live and historical paths emit ``SymbolMappingMsg`` records that
    bind ``instrument_id`` to an OSI symbol; we keep that map so each print can
    be resolved to a real contract without a definition subscription.
    """

    def __init__(self) -> None:
        self._contracts: dict[int, object] = {}
        self.unmapped = 0

    def note_mapping(self, instrument_id: int, osi_symbol: str) -> None:
        contract = parse_osi(osi_symbol)
        if contract is not None:
            self._contracts[instrument_id] = contract

    def decode_trade(self, rec) -> Optional[OptionTrade]:
        contract = self._contracts.get(rec.instrument_id)
        if contract is None:
            self.unmapped += 1
            return None

        price = _px(rec.price)
        if price is None or rec.size <= 0:
            return None

        return OptionTrade(
            contract=contract,  # type: ignore[arg-type]
            ts=datetime.fromtimestamp(rec.ts_recv / 1e9, tz=timezone.utc),
            price=price,
            size=int(rec.size),
            bid=_px(getattr(rec, "bid_px_00", None)),
            ask=_px(getattr(rec, "ask_px_00", None)),
            publisher_id=int(getattr(rec, "publisher_id", 0)),
            sequence=int(getattr(rec, "sequence", 0)),
        )


def _consume(decoder: _RecordDecoder, records: Iterable) -> Iterator[OptionTrade]:
    import databento as db

    for rec in records:
        if isinstance(rec, db.SymbolMappingMsg):
            decoder.note_mapping(rec.instrument_id, rec.stype_out_symbol)
            continue
        if isinstance(rec, (db.TBBOMsg, db.TradeMsg)):
            trade = decoder.decode_trade(rec)
            if trade is not None:
                yield trade


class LiveFlowStream:
    """Streaming OPRA prints for a watchlist, as :class:`OptionTrade` objects."""

    def __init__(self, api_key: str, tickers: Iterable[str], schema: str = FLOW_SCHEMA) -> None:
        self.api_key = api_key
        self.symbols = parent_symbols(tickers)
        self.schema = schema
        self._decoder = _RecordDecoder()
        self._client = None

    def __enter__(self) -> "LiveFlowStream":
        import databento as db

        self._client = db.Live(key=self.api_key)
        self._client.subscribe(
            dataset=OPRA_DATASET,
            schema=self.schema,
            stype_in="parent",
            symbols=self.symbols,
        )
        log.info("subscribed to %s %s for %s", OPRA_DATASET, self.schema, ", ".join(self.symbols))
        return self

    def __exit__(self, *exc) -> None:
        if self._client is not None:
            self._client.stop()
        return None

    def trades(self) -> Iterator[OptionTrade]:
        if self._client is None:
            raise RuntimeError("use LiveFlowStream as a context manager")
        yield from _consume(self._decoder, self._client)


class EodFlowLoader:
    """One session of OPRA prints, pulled after the close.

    Every request is cost-checked first. ``max_cost_usd`` is a hard stop, so a
    fat-fingered date range cannot quietly burn the free credit.
    """

    def __init__(self, api_key: str, max_cost_usd: float = 1.0) -> None:
        self.api_key = api_key
        self.max_cost_usd = max_cost_usd
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import databento as db

            self._client = db.Historical(key=self.api_key)
        return self._client

    def estimate_cost(self, tickers: Iterable[str], session: date, schema: str = FLOW_SCHEMA) -> float:
        start, end = _session_bounds(session)
        return float(
            self.client.metadata.get_cost(
                dataset=OPRA_DATASET,
                schema=schema,
                symbols=parent_symbols(tickers),
                stype_in="parent",
                start=start,
                end=end,
            )
        )

    def load(
        self,
        tickers: Iterable[str],
        session: date,
        schema: str = FLOW_SCHEMA,
        on_cost: Optional[Callable[[float], None]] = None,
    ) -> list[OptionTrade]:
        """Download one session, refusing anything over ``max_cost_usd``."""
        cost = self.estimate_cost(tickers, session, schema)
        if on_cost:
            on_cost(cost)
        log.info("databento quoted $%.4f for %s on %s", cost, ",".join(tickers), session)
        if cost > self.max_cost_usd:
            raise CostLimitExceeded(
                f"quoted ${cost:.4f} exceeds max_cost_usd=${self.max_cost_usd:.2f}; "
                "narrow the watchlist, shorten the window, or raise the limit"
            )

        start, end = _session_bounds(session)
        store = self.client.timeseries.get_range(
            dataset=OPRA_DATASET,
            schema=schema,
            symbols=parent_symbols(tickers),
            stype_in="parent",
            start=start,
            end=end,
        )
        decoder = _RecordDecoder()
        trades = list(_consume(decoder, store))
        if decoder.unmapped:
            log.warning("%d prints had no symbol mapping and were dropped", decoder.unmapped)
        return trades


class CostLimitExceeded(RuntimeError):
    """Raised before any billable download when the quote is too high."""


def _session_bounds(session: date) -> tuple[str, str]:
    """UTC bounds covering a US session including the extended options tape."""
    start = datetime(session.year, session.month, session.day, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=12)
    return start.isoformat(), end.isoformat()
