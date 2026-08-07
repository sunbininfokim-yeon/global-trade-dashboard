"""Offline tests — no network, no API key."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel.analyze import FlowRules, detect_flow, short_volume_stats, summarize_premium
from derivatives_intel.finra import parse_daily_short_volume
from derivatives_intel.flow_source import parent_symbols
from derivatives_intel.models import OptionTrade, ShortVolumeRow
from derivatives_intel.osi import build_osi, parse_osi
from derivatives_intel.storage import connect, load_short_volume, upsert_short_volume

FIXTURES = ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------- OSI parsing

def test_parse_osi_padded():
    c = parse_osi("TSLA  260116C00400000")
    assert c is not None
    assert c.underlying == "TSLA"
    assert c.expiry == date(2026, 1, 16)
    assert c.right == "C"
    assert c.strike == 400.0


def test_parse_osi_compact_form():
    c = parse_osi("NVDA260918P00125500")
    assert c is not None
    assert c.underlying == "NVDA"
    assert c.right == "P"
    assert c.strike == 125.5


def test_osi_roundtrip():
    osi = build_osi("AMD", date(2026, 3, 20), "C", 187.5)
    c = parse_osi(osi)
    assert c is not None and c.strike == 187.5 and c.underlying == "AMD"


@pytest.mark.parametrize("bad", ["", "TSLA", "NOT-AN-OSI-SYMBOL!!", "TSLA  269916C00400000"])
def test_parse_osi_rejects_junk(bad):
    assert parse_osi(bad) is None


def test_parent_symbols_does_not_mangle_tickers():
    # A naive rstrip('.OPT') turns SPOT into "S" — guard against that regression.
    assert parent_symbols(["TSLA", "SPOT", "NVDA.OPT"]) == ["TSLA.OPT", "SPOT.OPT", "NVDA.OPT"]


# ------------------------------------------------------------- FINRA parsing

def test_parse_daily_short_volume_real_fixture():
    rows = parse_daily_short_volume((FIXTURES / "finra_cnms_sample.txt").read_text())
    assert len(rows) == 4
    tsla = next(r for r in rows if r.symbol == "TSLA")
    assert tsla.date == date(2026, 8, 6)
    assert tsla.short_ratio == pytest.approx(0.4852, abs=1e-3)


def test_parse_daily_short_volume_symbol_filter():
    rows = parse_daily_short_volume(
        (FIXTURES / "finra_cnms_sample.txt").read_text(), symbols=["nvda"]
    )
    assert [r.symbol for r in rows] == ["NVDA"]


def test_short_ratio_none_when_no_volume():
    row = ShortVolumeRow(date(2026, 8, 6), "ZZZZ", 0.0, 0.0, 0.0)
    assert row.short_ratio is None


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _CapturingSession:
    """Records the POST body so we can assert on the query we build."""

    def __init__(self, payload):
        self.payload = payload
        self.sent = None

    def post(self, url, json=None, **kwargs):  # noqa: A002
        self.sent = json
        return _FakeResponse(self.payload)


def test_short_interest_window_is_narrow_enough_to_reach_latest():
    """Regression: a 365-day window with a small limit truncates from the START.

    FINRA rejects server-side sorting on settlementDate, so the limit cuts the
    oldest-first result set — which once made the dashboard show a six-month-old
    short interest as if it were current.
    """
    from derivatives_intel.finra import fetch_short_interest

    session = _CapturingSession([])
    fetch_short_interest(session, "TSLA")

    window = session.sent["dateRangeFilters"][0]
    span = date.fromisoformat(window["endDate"]) - date.fromisoformat(window["startDate"])
    settlements_in_window = span.days / 15  # positions settle twice a month
    assert session.sent["limit"] > settlements_in_window * 2


def test_short_interest_picks_the_newest_settlement():
    from derivatives_intel.finra import fetch_short_interest

    payload = [
        {"settlementDate": "2026-01-30", "symbolCode": "TSLA", "currentShortPositionQuantity": 1,
         "previousShortPositionQuantity": 0, "averageDailyVolumeQuantity": 10,
         "daysToCoverQuantity": 0.1, "changePercent": 1.0},
        {"settlementDate": "2026-07-15", "symbolCode": "TSLA", "currentShortPositionQuantity": 70646375,
         "previousShortPositionQuantity": 79109257, "averageDailyVolumeQuantity": 39663962,
         "daysToCoverQuantity": 1.78, "changePercent": -10.7},
        {"settlementDate": "2026-04-15", "symbolCode": "TSLA", "currentShortPositionQuantity": 5,
         "previousShortPositionQuantity": 4, "averageDailyVolumeQuantity": 10,
         "daysToCoverQuantity": 0.5, "changePercent": 2.0},
    ]
    rows = fetch_short_interest(_CapturingSession(payload), "TSLA")
    assert [r.settlement_date.isoformat() for r in rows] == ["2026-01-30", "2026-04-15", "2026-07-15"]
    assert rows[-1].days_to_cover == 1.78


# ------------------------------------------------------- aggressor / sentiment

def _trade(price, bid, ask, right="C", size=10, ts=None, pub=1):
    return OptionTrade(
        contract=parse_osi(build_osi("TSLA", date(2026, 12, 18), right, 500.0)),
        ts=ts or datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc),
        price=price,
        size=size,
        bid=bid,
        ask=ask,
        publisher_id=pub,
    )


def test_aggressor_at_ask_is_buy():
    assert _trade(2.50, 2.40, 2.50).aggressor == "BUY"


def test_aggressor_at_bid_is_sell():
    assert _trade(2.40, 2.40, 2.50).aggressor == "SELL"


def test_aggressor_midpoint_is_mid():
    assert _trade(2.45, 2.40, 2.50).aggressor == "MID"


def test_aggressor_without_quote_is_mid():
    assert _trade(2.45, None, None).aggressor == "MID"


def test_sentiment_bought_put_is_bearish():
    assert _trade(2.50, 2.40, 2.50, right="P").sentiment == "bearish"


def test_sentiment_sold_put_is_bullish():
    assert _trade(2.40, 2.40, 2.50, right="P").sentiment == "bullish"


def test_notional_uses_contract_multiplier():
    assert _trade(2.50, 2.40, 2.50, size=100).notional == pytest.approx(25_000.0)


# ------------------------------------------------------------ flow detection

def test_sweep_across_venues_is_detected():
    base = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
    trades = [
        _trade(3.00, 2.90, 3.00, size=800, ts=base + timedelta(milliseconds=i * 100), pub=pub)
        for i, pub in enumerate((1, 2, 3))
    ]
    alerts = detect_flow(trades, FlowRules(), asof=date(2026, 8, 6))
    assert len(alerts) == 1
    a = alerts[0]
    assert a.kind == "sweep"
    assert a.venues == 3 and a.prints == 3
    assert a.size == 2400
    assert a.notional == pytest.approx(720_000.0)


def test_small_prints_are_filtered_out():
    trades = [_trade(0.10, 0.05, 0.10, size=1)]
    assert detect_flow(trades, FlowRules(), asof=date(2026, 8, 6)) == []


def test_mid_prints_excluded_by_default():
    trades = [_trade(2.45, 2.40, 2.50, size=100_000)]
    assert detect_flow(trades, FlowRules(), asof=date(2026, 8, 6)) == []
    kept = detect_flow(trades, FlowRules(exclude_mid=False), asof=date(2026, 8, 6))
    assert len(kept) == 1 and kept[0].sentiment == "neutral"


def test_dte_window_filters_expired_contracts():
    trades = [_trade(50.0, 49.0, 50.0, size=1000)]
    assert detect_flow(trades, FlowRules(max_dte=10), asof=date(2026, 8, 6)) == []


def test_summarize_premium_splits_by_right_and_direction():
    out = summarize_premium([
        _trade(3.00, 2.90, 3.00, right="C", size=100),   # bought call -> bullish
        _trade(1.00, 1.00, 1.10, right="P", size=200),   # sold put   -> bullish
    ])
    assert out["call_premium"] == pytest.approx(30_000.0)
    assert out["put_premium"] == pytest.approx(20_000.0)
    assert out["bullish_premium"] == pytest.approx(50_000.0)
    assert out["bearish_premium"] == 0.0


# --------------------------------------------------------- short-vol baseline

def test_short_volume_zscore_flags_an_outlier():
    rows = [
        ShortVolumeRow(date(2026, 7, 1) + timedelta(days=i), "TSLA", 33.0, 0.0, 100.0)
        for i in range(20)
    ]
    # nudge the baseline off a perfectly flat line so stdev > 0
    rows[3].short_volume = 34.0
    rows[9].short_volume = 32.0
    rows.append(ShortVolumeRow(date(2026, 7, 25), "TSLA", 48.0, 0.0, 100.0))

    latest, mean, z = short_volume_stats(rows)
    assert latest.short_ratio == pytest.approx(0.48)
    assert mean == pytest.approx(0.33, abs=0.01)
    assert z is not None and z > 3


def test_short_volume_stats_without_history():
    rows = [ShortVolumeRow(date(2026, 8, 6), "TSLA", 40.0, 0.0, 100.0)]
    latest, mean, z = short_volume_stats(rows)
    assert latest is not None and mean is None and z is None


def test_short_volume_stats_empty():
    assert short_volume_stats([]) == (None, None, None)


# ------------------------------------------------------------------- storage

def test_storage_roundtrip_and_upsert(tmp_path):
    db = tmp_path / "cache" / "t.sqlite"
    rows = parse_daily_short_volume((FIXTURES / "finra_cnms_sample.txt").read_text())

    with connect(db) as conn:
        assert upsert_short_volume(conn, rows) == 4
        upsert_short_volume(conn, rows)  # idempotent
        stored = load_short_volume(conn, "TSLA")

    assert len(stored) == 1
    assert stored[0].short_volume == pytest.approx(5991772.316831)
