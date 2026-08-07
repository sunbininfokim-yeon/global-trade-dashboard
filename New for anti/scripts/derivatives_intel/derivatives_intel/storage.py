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

from .models import ShortVolumeRow, UnusualActivity

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

CREATE TABLE IF NOT EXISTS unusual_activity (
    date        TEXT NOT NULL,
    osi         TEXT NOT NULL,
    underlying  TEXT NOT NULL,
    volume      INTEGER NOT NULL,
    open_interest INTEGER NOT NULL,
    vol_oi      REAL,
    notional    REAL NOT NULL,
    dte         INTEGER NOT NULL,
    score       REAL NOT NULL,
    reasons     TEXT,
    PRIMARY KEY (date, osi)
);

CREATE INDEX IF NOT EXISTS idx_short_volume_symbol ON short_volume(symbol, date);
CREATE INDEX IF NOT EXISTS idx_unusual_underlying ON unusual_activity(underlying, date);
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


def record_unusual(conn: sqlite3.Connection, day: date, items: Sequence[UnusualActivity]) -> int:
    """Persist a day's standouts so the panel can show what recurs.

    Same-day reruns overwrite rather than duplicate: the chain is a snapshot, so
    a later run of the same session is a better reading of it, not a new event.
    """
    payload = [
        (
            day.isoformat(),
            u.contract.osi,
            u.contract.underlying,
            u.volume,
            u.open_interest,
            u.vol_oi_ratio,
            u.notional,
            u.dte,
            u.score,
            ", ".join(u.reasons),
        )
        for u in items
    ]
    if not payload:
        return 0
    conn.executemany(
        "INSERT INTO unusual_activity "
        "(date, osi, underlying, volume, open_interest, vol_oi, notional, dte, score, reasons) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(date, osi) DO UPDATE SET "
        "volume=excluded.volume, open_interest=excluded.open_interest, vol_oi=excluded.vol_oi, "
        "notional=excluded.notional, score=excluded.score, reasons=excluded.reasons",
        payload,
    )
    return len(payload)


def recurring_strikes(conn: sqlite3.Connection, underlying: str, days: int = 5) -> list[dict]:
    """Contracts that flagged on more than one of the last N sessions.

    A strike showing up day after day is a position being built, which is a very
    different thing from a single loud print.
    """
    cur = conn.execute(
        "SELECT osi, COUNT(*) AS hits, SUM(notional) AS total_notional, MAX(score) AS best "
        "FROM unusual_activity WHERE underlying = ? "
        "AND date >= date('now', ?) GROUP BY osi HAVING hits > 1 "
        "ORDER BY hits DESC, total_notional DESC LIMIT 10",
        (underlying.upper(), f"-{days} days"),
    )
    return [dict(r) for r in cur.fetchall()]
