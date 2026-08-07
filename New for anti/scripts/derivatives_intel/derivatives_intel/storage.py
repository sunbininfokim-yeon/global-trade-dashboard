"""SQLite history.

Short-volume z-scores need a per-symbol baseline, and FINRA only serves one day
per file. Rather than refetch 20 files on every run, we accumulate them here and
top up whatever is missing. The DB lives under ``cache/`` and is gitignored —
it is a local convenience, fully rebuildable from the public files.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .models import FlowAlert, ShortVolumeRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS short_volume (
    date        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    short_vol   REAL NOT NULL,
    exempt_vol  REAL NOT NULL,
    total_vol   REAL NOT NULL,
    markets     TEXT,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS flow_alerts (
    ts          TEXT NOT NULL,
    osi         TEXT NOT NULL,
    underlying  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    aggressor   TEXT NOT NULL,
    sentiment   TEXT NOT NULL,
    size        INTEGER NOT NULL,
    notional    REAL NOT NULL,
    vwap        REAL NOT NULL,
    venues      INTEGER NOT NULL,
    prints      INTEGER NOT NULL,
    PRIMARY KEY (ts, osi, aggressor, notional)
);

CREATE INDEX IF NOT EXISTS idx_short_volume_symbol ON short_volume(symbol, date);
CREATE INDEX IF NOT EXISTS idx_flow_underlying ON flow_alerts(underlying, ts);
"""


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_short_volume(conn: sqlite3.Connection, rows: Iterable[ShortVolumeRow]) -> int:
    payload = [
        (r.date.isoformat(), r.symbol, r.short_volume, r.short_exempt_volume, r.total_volume, r.markets)
        for r in rows
    ]
    if not payload:
        return 0
    conn.executemany(
        "INSERT INTO short_volume (date, symbol, short_vol, exempt_vol, total_vol, markets) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(date, symbol) DO UPDATE SET "
        "short_vol=excluded.short_vol, exempt_vol=excluded.exempt_vol, "
        "total_vol=excluded.total_vol, markets=excluded.markets",
        payload,
    )
    return len(payload)


def load_short_volume(conn: sqlite3.Connection, symbol: str, limit: int = 60) -> list[ShortVolumeRow]:
    cur = conn.execute(
        "SELECT * FROM short_volume WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    rows = [
        ShortVolumeRow(
            date=date.fromisoformat(r["date"]),
            symbol=r["symbol"],
            short_volume=r["short_vol"],
            short_exempt_volume=r["exempt_vol"],
            total_volume=r["total_vol"],
            markets=r["markets"] or "",
        )
        for r in cur.fetchall()
    ]
    rows.reverse()
    return rows


def known_dates(conn: sqlite3.Connection, symbol: str) -> set[date]:
    cur = conn.execute("SELECT DISTINCT date FROM short_volume WHERE symbol = ?", (symbol.upper(),))
    return {date.fromisoformat(r["date"]) for r in cur.fetchall()}


def record_alerts(conn: sqlite3.Connection, alerts: Sequence[FlowAlert]) -> int:
    payload = [
        (
            a.ts.isoformat(),
            a.contract.osi,
            a.contract.underlying,
            a.kind,
            a.aggressor,
            a.sentiment,
            a.size,
            a.notional,
            a.vwap,
            a.venues,
            a.prints,
        )
        for a in alerts
    ]
    if not payload:
        return 0
    conn.executemany(
        "INSERT OR IGNORE INTO flow_alerts "
        "(ts, osi, underlying, kind, aggressor, sentiment, size, notional, vwap, venues, prints) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        payload,
    )
    return len(payload)
