"""Offline tests — no network, no API key."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel.analyze import ChainRules, find_unusual, short_volume_stats, summarize_chain
from derivatives_intel.cboe import chain_url, parse_chain
from derivatives_intel.finra import parse_daily_short_volume
from derivatives_intel.models import ChainQuote, ShortVolumeRow
from derivatives_intel.osi import build_osi, parse_osi
from derivatives_intel.rehydrate import snapshots_from_doc
from derivatives_intel.storage import (
    connect,
    load_short_volume,
    record_unusual,
    recurring_strikes,
    upsert_short_volume,
)

FIXTURES = ROOT / "tests" / "fixtures"
CHAIN_ASOF = date(2026, 8, 6)


@pytest.fixture
def tsla_chain():
    payload = json.loads((FIXTURES / "cboe_tsla_sample.json").read_text())
    return parse_chain(payload, "TSLA")


# ---------------------------------------------------------------- OSI parsing

def test_parse_osi_padded():
    c = parse_osi("TSLA  260116C00400000")
    assert c is not None
    assert (c.underlying, c.expiry, c.right, c.strike) == ("TSLA", date(2026, 1, 16), "C", 400.0)


def test_parse_osi_compact_form():
    # CBOE emits the compact form, so this path is load-bearing.
    c = parse_osi("NVDA260918P00125500")
    assert c is not None and c.right == "P" and c.strike == 125.5


def test_osi_roundtrip():
    c = parse_osi(build_osi("AMD", date(2026, 3, 20), "C", 187.5))
    assert c is not None and c.strike == 187.5 and c.underlying == "AMD"


@pytest.mark.parametrize("bad", ["", "TSLA", "NOT-AN-OSI-SYMBOL!!", "TSLA  269916C00400000"])
def test_parse_osi_rejects_junk(bad):
    assert parse_osi(bad) is None


def test_chain_url_prefixes_index_products():
    assert chain_url("TSLA").endswith("/TSLA.json")
    assert chain_url("SPX").endswith("/_SPX.json")


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
    assert ShortVolumeRow(date(2026, 8, 6), "ZZZZ", 0.0, 0.0, 0.0).short_ratio is None


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
        {"settlementDate": "2026-07-15", "symbolCode": "TSLA",
         "currentShortPositionQuantity": 70646375, "previousShortPositionQuantity": 79109257,
         "averageDailyVolumeQuantity": 39663962, "daysToCoverQuantity": 1.78,
         "changePercent": -10.7},
        {"settlementDate": "2026-04-15", "symbolCode": "TSLA", "currentShortPositionQuantity": 5,
         "previousShortPositionQuantity": 4, "averageDailyVolumeQuantity": 10,
         "daysToCoverQuantity": 0.5, "changePercent": 2.0},
    ]
    rows = fetch_short_interest(_CapturingSession(payload), "TSLA")
    assert [r.settlement_date.isoformat() for r in rows] == [
        "2026-01-30", "2026-04-15", "2026-07-15"
    ]
    assert rows[-1].days_to_cover == 1.78


# --------------------------------------------------------------- chain parsing

def test_parse_chain_reads_real_cboe_payload(tsla_chain):
    assert tsla_chain is not None
    assert tsla_chain.symbol == "TSLA"
    assert tsla_chain.spot > 0
    assert len(tsla_chain.quotes) == 10
    q = tsla_chain.quotes[0]
    assert q.contract.underlying == "TSLA"
    assert q.volume > 0 and q.delta is not None


def test_parse_chain_returns_none_when_empty():
    assert parse_chain({"data": {"options": []}}, "TSLA") is None


def test_vol_oi_ratio_none_without_open_interest():
    c = parse_osi(build_osi("TSLA", date(2026, 12, 18), "C", 500.0))
    assert ChainQuote(c, 1.0, 1.2, 1.1, volume=50, open_interest=0).vol_oi_ratio is None


def test_notional_uses_mid_and_multiplier():
    c = parse_osi(build_osi("TSLA", date(2026, 12, 18), "C", 500.0))
    q = ChainQuote(c, bid=2.0, ask=3.0, last=99.0, volume=100, open_interest=10)
    assert q.mid == 2.5
    assert q.notional == pytest.approx(25_000.0)  # mid, not the stale last


def test_notional_falls_back_to_last_without_quotes():
    c = parse_osi(build_osi("TSLA", date(2026, 12, 18), "C", 500.0))
    q = ChainQuote(c, bid=0.0, ask=0.0, last=4.0, volume=10, open_interest=1)
    assert q.notional == pytest.approx(4_000.0)


# ------------------------------------------------------------ unusual activity

def test_finds_unusual_contracts_in_real_chain(tsla_chain):
    items = find_unusual(tsla_chain, ChainRules(), asof=CHAIN_ASOF)
    assert items
    assert all(i.volume >= 100 for i in items)
    assert all(i.notional >= 250_000 for i in items)
    assert items == sorted(items, key=lambda i: i.score, reverse=True)


def test_deep_itm_is_excluded(tsla_chain):
    """Deep ITM prints are exercise/assignment noise, not directional bets."""
    items = find_unusual(tsla_chain, ChainRules(), asof=CHAIN_ASOF)
    assert all(i.delta is None or abs(i.delta) <= 0.95 for i in items)
    # the 500-strike put (delta -0.996) carries huge notional but must not rank
    assert not any(i.contract.strike == 500.0 for i in items)


def test_relaxing_delta_cap_lets_deep_itm_back_in(tsla_chain):
    items = find_unusual(tsla_chain, ChainRules(max_abs_delta=1.0), asof=CHAIN_ASOF)
    assert any(i.contract.strike == 500.0 for i in items)


def test_new_strike_with_no_open_interest_scores(tsla_chain):
    items = find_unusual(
        tsla_chain, ChainRules(min_notional=0, min_volume=1, max_abs_delta=1.0), asof=CHAIN_ASOF
    )
    fresh = [i for i in items if i.open_interest == 0]
    assert fresh and any("new strike" in r for r in fresh[0].reasons)


def test_low_volume_contracts_filtered(tsla_chain):
    assert find_unusual(tsla_chain, ChainRules(min_volume=10**9), asof=CHAIN_ASOF) == []


def test_top_n_is_respected(tsla_chain):
    items = find_unusual(tsla_chain, ChainRules(min_notional=0, min_volume=1, top_n=3),
                         asof=CHAIN_ASOF)
    assert len(items) <= 3


def test_summarize_chain_splits_calls_and_puts(tsla_chain):
    s = summarize_chain(tsla_chain, asof=CHAIN_ASOF)
    assert s.call_volume > 0 and s.put_volume > 0
    assert s.put_call_volume_ratio == pytest.approx(s.put_volume / s.call_volume)
    assert s.contracts_considered == 10


def test_put_call_ratios_none_without_calls():
    from derivatives_intel.models import ChainSnapshot

    c = parse_osi(build_osi("TSLA", date(2026, 12, 18), "P", 300.0))
    snap = ChainSnapshot("TSLA", None, 320.0, [ChainQuote(c, 1.0, 1.2, 1.1, 10, 5)])
    assert summarize_chain(snap, asof=CHAIN_ASOF).put_call_volume_ratio is None


# --------------------------------------------------------- short-vol baseline

def test_short_volume_zscore_flags_an_outlier():
    rows = [
        ShortVolumeRow(date(2026, 7, 1) + timedelta(days=i), "TSLA", 33.0, 0.0, 100.0)
        for i in range(20)
    ]
    rows[3].short_volume = 34.0   # give the baseline a non-zero stdev
    rows[9].short_volume = 32.0
    rows.append(ShortVolumeRow(date(2026, 7, 25), "TSLA", 48.0, 0.0, 100.0))

    latest, mean, z = short_volume_stats(rows)
    assert latest.short_ratio == pytest.approx(0.48)
    assert mean == pytest.approx(0.33, abs=0.01)
    assert z is not None and z > 3


def test_short_volume_stats_without_history():
    latest, mean, z = short_volume_stats(
        [ShortVolumeRow(date(2026, 8, 6), "TSLA", 40.0, 0.0, 100.0)]
    )
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


def test_unusual_rerun_same_day_overwrites(tmp_path, tsla_chain):
    db = tmp_path / "cache" / "t.sqlite"
    items = find_unusual(tsla_chain, ChainRules(), asof=CHAIN_ASOF)

    with connect(db) as conn:
        record_unusual(conn, CHAIN_ASOF, items)
        record_unusual(conn, CHAIN_ASOF, items)
        (count,) = conn.execute("SELECT COUNT(*) FROM unusual_activity").fetchone()

    assert count == len(items)


def test_recurring_strikes_needs_more_than_one_day(tmp_path, tsla_chain):
    db = tmp_path / "cache" / "t.sqlite"
    items = find_unusual(tsla_chain, ChainRules(), asof=CHAIN_ASOF)
    today = date.today()

    with connect(db) as conn:
        record_unusual(conn, today, items)
        assert recurring_strikes(conn, "TSLA") == []
        record_unusual(conn, today - timedelta(days=1), items)
        again = recurring_strikes(conn, "TSLA")

    assert again and all(r["hits"] == 2 for r in again)


# ----------------------------------------------------------------- rehydrate

def test_rehydrate_roundtrips_the_emitted_document(tsla_chain):
    """The digest is rendered from the JSON, so it must survive the round trip."""
    from derivatives_intel.build import _chain_json, _snapshot_json
    from derivatives_intel.models import TickerSnapshot

    original = TickerSnapshot(
        symbol="TSLA",
        chain=summarize_chain(tsla_chain, asof=CHAIN_ASOF),
        unusual=find_unusual(tsla_chain, ChainRules(), asof=CHAIN_ASOF),
    )
    doc = {"tickers": [_snapshot_json(original, [])]}

    back = snapshots_from_doc(doc)[0]
    assert back.symbol == "TSLA"
    assert len(back.unusual) == len(original.unusual)
    assert back.chain.call_volume == original.chain.call_volume
    assert back.unusual[0].contract.osi == original.unusual[0].contract.osi
    assert _chain_json(back.chain) == _chain_json(original.chain)
