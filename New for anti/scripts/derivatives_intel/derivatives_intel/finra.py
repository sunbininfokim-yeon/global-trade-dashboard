"""FINRA collectors — the free half of the pipeline.

Two public, key-free endpoints carry the whole short-selling picture:

``daily short volume``
    ``https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt``
    Pipe-delimited, posted the evening of each trading day. Consolidated NMS
    short-sale volume — i.e. how much of the day's tape printed short.

``consolidated short interest``
    ``https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest``
    The bi-monthly settled short position. Accepts anonymous POST queries.

A caveat worth keeping in front of anyone reading the dashboard: **short volume
is not short interest.** Market makers print short constantly while hedging, so
a 40-50% short-volume ratio is an ordinary resting state for a liquid name, not
a bear raid. Only the deviation from a symbol's own baseline carries signal,
which is why :mod:`derivatives_intel.analyze` reports a z-score rather than the
raw ratio alone.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, timedelta
from typing import Iterable, Optional

import requests

from .httputil import get_text, post_json
from .models import ShortInterestRow, ShortVolumeRow

log = logging.getLogger(__name__)

DAILY_SHORT_VOLUME_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt"
SHORT_INTEREST_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


# --------------------------------------------------------------------------
# Daily short volume
# --------------------------------------------------------------------------

def fetch_daily_short_volume(
    session: requests.Session,
    day: date,
    symbols: Optional[Iterable[str]] = None,
) -> Optional[list[ShortVolumeRow]]:
    """Fetch and parse one trading day's consolidated short volume file.

    Returns None when the file is not published for that date (weekend,
    holiday, or simply not posted yet), which the caller uses as the cue to
    walk back a day.
    """
    url = DAILY_SHORT_VOLUME_URL.format(yyyymmdd=day.strftime("%Y%m%d"))
    body = get_text(session, url)
    if not body:
        return None
    return parse_daily_short_volume(body, symbols)


def parse_daily_short_volume(
    body: str,
    symbols: Optional[Iterable[str]] = None,
) -> list[ShortVolumeRow]:
    """Parse the pipe-delimited FINRA daily file.

    Volumes are floats, not ints: FINRA reports fractional-share activity.
    """
    wanted = {s.upper() for s in symbols} if symbols else None
    rows: list[ShortVolumeRow] = []

    reader = csv.DictReader(io.StringIO(body), delimiter="|")
    for raw in reader:
        symbol = (raw.get("Symbol") or "").strip().upper()
        if not symbol or (wanted is not None and symbol not in wanted):
            continue
        day = _parse_yyyymmdd(raw.get("Date"))
        if day is None:
            continue
        try:
            rows.append(
                ShortVolumeRow(
                    date=day,
                    symbol=symbol,
                    short_volume=float(raw.get("ShortVolume") or 0),
                    short_exempt_volume=float(raw.get("ShortExemptVolume") or 0),
                    total_volume=float(raw.get("TotalVolume") or 0),
                    markets=(raw.get("Market") or "").strip(),
                )
            )
        except ValueError:
            log.debug("skipping unparseable short-volume row for %s", symbol)
    return rows


def fetch_recent_short_volume(
    session: requests.Session,
    symbols: Iterable[str],
    lookback_days: int = 40,
    end: Optional[date] = None,
) -> tuple[list[ShortVolumeRow], list[date]]:
    """Walk back over calendar days collecting whatever files exist.

    ``lookback_days`` is a calendar window; weekends and holidays simply come
    back empty. Returns the rows plus the trading dates actually retrieved, so
    the caller can tell "no data" apart from "market was closed".
    """
    symbols = [s.upper() for s in symbols]
    end = end or date.today()
    rows: list[ShortVolumeRow] = []
    found: list[date] = []

    for offset in range(lookback_days):
        day = end - timedelta(days=offset)
        if day.weekday() >= 5:  # cheap skip; holidays still cost one request
            continue
        day_rows = fetch_daily_short_volume(session, day, symbols)
        if day_rows is None:
            continue
        found.append(day)
        rows.extend(day_rows)

    rows.sort(key=lambda r: (r.symbol, r.date))
    return rows, sorted(found)


# --------------------------------------------------------------------------
# Bi-monthly short interest
# --------------------------------------------------------------------------

def fetch_short_interest(
    session: requests.Session,
    symbol: str,
    since: Optional[date] = None,
    limit: int = 60,
) -> list[ShortInterestRow]:
    """Query FINRA's consolidated short interest for one symbol.

    The API refuses server-side sorting unless every partition key is pinned to
    an equality filter (``settlementDate`` is one), so we cannot ask for "newest
    first". ``limit`` therefore truncates from the *start* of the window — which
    means the window must be short enough, and the limit high enough, that every
    settlement in range comes back. Positions settle twice a month, so 180 days
    is ~12 rows against a limit of 60: comfortable headroom.

    Note FINRA publishes on roughly a three-week lag, so the newest settlement
    available is normally a few weeks behind today.
    """
    since = since or (date.today() - timedelta(days=180))
    payload = {
        "limit": limit,
        "compareFilters": [
            {"fieldName": "symbolCode", "fieldValue": symbol.upper(), "compareType": "equal"}
        ],
        "dateRangeFilters": [
            {
                "fieldName": "settlementDate",
                "startDate": since.isoformat(),
                "endDate": date.today().isoformat(),
            }
        ],
    }

    data = post_json(session, SHORT_INTEREST_URL, payload)
    if not isinstance(data, list):
        return []

    if len(data) >= limit:
        # We hit the cap, so the tail of the window was almost certainly cut off
        # and "latest" would silently be stale. Loud, because a stale short
        # interest number on the dashboard looks exactly like a fresh one.
        log.warning(
            "%s: short interest hit the %d-row limit — newest settlements may be missing; "
            "shorten `since` or raise `limit`",
            symbol,
            limit,
        )

    rows: list[ShortInterestRow] = []
    for raw in data:
        settle = _parse_iso_date(raw.get("settlementDate"))
        if settle is None:
            continue
        rows.append(
            ShortInterestRow(
                settlement_date=settle,
                symbol=(raw.get("symbolCode") or symbol).upper(),
                current_short=_as_int(raw.get("currentShortPositionQuantity")),
                previous_short=_as_int(raw.get("previousShortPositionQuantity")),
                avg_daily_volume=_as_int(raw.get("averageDailyVolumeQuantity")),
                days_to_cover=_as_float(raw.get("daysToCoverQuantity")),
                change_pct=_as_float(raw.get("changePercent")),
            )
        )

    rows.sort(key=lambda r: r.settlement_date)
    return rows


# --------------------------------------------------------------------------
# small parse helpers
# --------------------------------------------------------------------------

def _parse_yyyymmdd(value: Optional[str]) -> Optional[date]:
    raw = (value or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _as_int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> Optional[float]:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
