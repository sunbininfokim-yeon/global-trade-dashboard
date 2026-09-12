"""Append-only history for external leveraged ETF observations.

The external venue collector currently gives us a Yahoo Finance end-of-day
bar plus a current ``totalAssets`` snapshot.  Those are useful for building a
future series, but they are not the same observation.  This module keeps that
distinction explicit: rows are marked ``partial`` and ``aum_quality`` is
``observed_snapshot_unstamped`` until a source (for example Bloomberg) gives
an AUM value with its own as-of date.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .derivatives_history import HistoryValidationError, append_jsonl


VENUES = ("hk", "us")
QUALITY = {"observed", "partial", "estimated"}


def _iso_day(value: Any, *, field: str) -> str:
    text = str(value or "")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise HistoryValidationError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc
    if parsed.isoformat() != text:
        raise HistoryValidationError(f"{field} must be YYYY-MM-DD, got {value!r}")
    return text


def _number(value: Any, *, field: str, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryValidationError(f"{field} must be numeric, got {value!r}")


def validate_external_record(record: dict[str, Any]) -> None:
    """Validate one row consumed by an optional external-product chart."""
    for key in ("date", "as_of", "source", "quality", "venue", "ticker"):
        if key not in record:
            raise HistoryValidationError(f"external history missing {key}")
    _iso_day(record["date"], field="date")
    _iso_day(record["as_of"], field="as_of")
    if not isinstance(record["source"], str) or not record["source"].strip():
        raise HistoryValidationError("source must be a non-empty string")
    if record["quality"] not in QUALITY:
        raise HistoryValidationError("quality must be observed, partial, or estimated")
    if record["venue"] not in VENUES:
        raise HistoryValidationError(f"venue must be one of {VENUES}")
    if not isinstance(record["ticker"], str) or not record["ticker"].strip():
        raise HistoryValidationError("ticker must be a non-empty string")
    if record.get("underlying") is not None and not isinstance(record["underlying"], str):
        raise HistoryValidationError("underlying must be a string or null")

    for key in (
        "L",
        "aum_usd",
        "notional_exposure_usd",
        "trading_value_usd",
        "close_native",
        "volume",
        "fx_usdhkd",
    ):
        _number(record.get(key), field=key)
    if record.get("aum_quality") not in {
        None,
        "observed",
        "observed_snapshot_unstamped",
        "partial",
        "proxy",
        "missing",
    }:
        raise HistoryValidationError("invalid aum_quality")
    if record.get("trading_value_quality") not in {
        None,
        "observed",
        "proxy",
        "missing",
    }:
        raise HistoryValidationError("invalid trading_value_quality")
    if "snapshot_fetched_at" not in record or not isinstance(record["snapshot_fetched_at"], str):
        raise HistoryValidationError("snapshot_fetched_at must be present as a string")
    if "aum_as_of" in record and record["aum_as_of"] is not None:
        _iso_day(record["aum_as_of"], field="aum_as_of")


def _row_from_product(
    product: dict[str, Any],
    *,
    venue: str,
    fetched_at: str,
    fx: dict[str, Any],
) -> dict[str, Any] | None:
    if product.get("error") or not product.get("ticker"):
        return None
    # HK rows come from the overseas board and carry no Yahoo payload; their
    # `observed_on` is the board's trading day, which is a better dated
    # observation than a Yahoo bar, not a worse one. Without this the board
    # switch silently stopped appending HK lines to the history log.
    bar = product.get("yahoo", {}).get("last_bar") or {}
    bar_date = bar.get("as_of")
    observed_on = product.get("observed_on")
    if bar_date:
        as_of = _iso_day(bar_date, field="last_bar.as_of")
    elif observed_on:
        as_of = _iso_day(observed_on, field="observed_on")
    else:
        # A current AUM with no dated observation is not one.  Do not invent a
        # date from fetch time or create a holiday placeholder.
        return None
    aum = product.get("aum_usd")
    tv = product.get("trading_value_usd")
    # Yahoo's totalAssets has no timestamp in this payload, while volume×close
    # is a turnover proxy rather than an exchange trading-value field.
    row_quality = "partial"
    return {
        "date": as_of,
        "as_of": as_of,
        "source": str(product.get("source") or f"Yahoo Finance ({venue})"),
        "quality": row_quality,
        "venue": venue,
        "ticker": str(product["ticker"]),
        "underlying": product.get("underlying"),
        "structure": product.get("structure"),
        "direction": product.get("direction"),
        "L": product.get("L"),
        "L_flexible": product.get("L_flexible"),
        "aum_usd": aum,
        "aum_as_of": None,
        "aum_quality": "observed_snapshot_unstamped" if aum is not None else "missing",
        "notional_exposure_usd": product.get("notional_exposure_usd"),
        "trading_value_usd": tv,
        "trading_value_quality": "proxy" if tv is not None else "missing",
        "close_native": bar.get("close"),
        "volume": bar.get("volume"),
        "currency": product.get("aum_currency") or product.get("yahoo", {}).get("currency"),
        "fx_usdhkd": fx.get("usdhkd"),
        "kr_spot_impact": product.get("kr_spot_impact"),
        "snapshot_fetched_at": fetched_at,
        "note_ko": (
            "Yahoo EOD bar 날짜에 현재 totalAssets 스냅샷을 붙인 부분 관측. "
            "AUM as-of가 없으므로 역사적 AUM 시계열로 단정하지 않음; Bloomberg 보강 전까지 proxy."
        ),
    }


def external_records_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract dated HK/US ETF rows from one external snapshot.

    Crypto perpetuals are intentionally excluded: their OI is a different
    contract and belongs in the separate crypto snapshot/OI history.
    """
    fetched_at = str(snapshot.get("fetched_at") or "")
    if not fetched_at:
        raise HistoryValidationError("external snapshot is missing fetched_at")
    fx = snapshot.get("fx") or {}
    records: list[dict[str, Any]] = []
    for venue, key in (("hk", "hk"), ("us", "us_proxy")):
        rows = (snapshot.get(key) or {}).get("products") or []
        for product in rows:
            row = _row_from_product(product, venue=venue, fetched_at=fetched_at, fx=fx)
            if row is None:
                continue
            validate_external_record(row)
            records.append(row)
    return records


def append_external_history(path, records: list[dict[str, Any]]) -> int:
    """Merge rows by date+venue+ticker; never calendar-fill missing dates."""
    return append_jsonl(
        path,
        records,
        validator=validate_external_record,
        key_fields=("date", "venue", "ticker"),
    )
