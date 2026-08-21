"""Append-only history records for the derivatives and LETF observation UI.

The dashboard reads three JSONL logs.  This module deliberately derives them
only from the already-published daily snapshots: it never invents a value to
fill a non-trading day and it never upgrades a source's quality flag.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .formulas import impact_ratio, total_rebalance


COMMON_FIELDS = ("date", "as_of", "source", "quality")
DIRECTIONS = ("long", "inverse", "inverse_2x", "gobus_inverse_2x")


class HistoryValidationError(ValueError):
    """Raised before a malformed observation can enter a JSONL log."""


def _iso_day(value: Any, *, field: str) -> str:
    text = str(value or "")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise HistoryValidationError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc
    if parsed.isoformat() != text:
        raise HistoryValidationError(f"{field} must be YYYY-MM-DD, got {value!r}")
    return text


def _number(value: Any, *, field: str, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryValidationError(f"{field} must be numeric, got {value!r}")
    return float(value)


def _common(record: dict[str, Any]) -> None:
    missing = [key for key in COMMON_FIELDS if key not in record]
    if missing:
        raise HistoryValidationError(f"missing common history fields: {', '.join(missing)}")
    _iso_day(record["date"], field="date")
    _iso_day(record["as_of"], field="as_of")
    if not isinstance(record["source"], str) or not record["source"].strip():
        raise HistoryValidationError("source must be a non-empty string")
    if record["quality"] not in {"observed", "partial", "estimated"}:
        raise HistoryValidationError("quality must be observed, partial, or estimated")


def validate_activity_record(record: dict[str, Any]) -> None:
    """Validate the exact activity fields consumed by the UI chart map."""
    _common(record)
    futures = record.get("kospi200_futures")
    options = record.get("kospi200_options")
    if not isinstance(futures, dict) or not isinstance(options, dict):
        raise HistoryValidationError("activity record needs futures and options objects")
    _number(futures.get("volume"), field="kospi200_futures.volume")
    _number(futures.get("trading_value_krw"), field="kospi200_futures.trading_value_krw")
    for key in (
        "call_volume",
        "put_volume",
        "call_trading_value_krw",
        "put_trading_value_krw",
        "put_call_volume",
        "put_call_trading_value",
    ):
        _number(options.get(key), field=f"kospi200_options.{key}")


def validate_direction_record(record: dict[str, Any]) -> None:
    """Keep the two different denominators explicit in every observation."""
    _common(record)
    _number(record.get("kospi_cash_tv_krw"), field="kospi_cash_tv_krw")
    _number(
        record.get("levered_inverse_etf_tv_over_kospi_cash_tv_pct"),
        field="levered_inverse_etf_tv_over_kospi_cash_tv_pct",
    )
    by_direction = record.get("by_direction")
    if not isinstance(by_direction, dict):
        raise HistoryValidationError("by_direction must be an object")
    for direction in DIRECTIONS:
        row = by_direction.get(direction)
        if not isinstance(row, dict):
            raise HistoryValidationError(f"by_direction.{direction} is required")
        for key in ("trading_value_krw", "share_of_lev_tv_pct", "share_of_kospi_tv_pct"):
            _number(row.get(key), field=f"by_direction.{direction}.{key}")


def validate_stock_record(record: dict[str, Any]) -> None:
    """Validate one ticker row in the shared single-stock LETF log."""
    _common(record)
    if not isinstance(record.get("ticker"), str) or not record["ticker"].strip():
        raise HistoryValidationError("ticker must be a non-empty string")
    for key in (
        "spot_trading_value_krw",
        "letf_trading_value_krw",
        "letf_turnover_ratio",
        "letf_aum_sum_krw",
        "letf_aum_long_krw",
        "letf_aum_inverse_krw",
    ):
        _number(record.get(key), field=key, allow_none=True)
    products = record.get("products")
    if not isinstance(products, list):
        raise HistoryValidationError("products must be a list, including an empty list when unavailable")
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise HistoryValidationError(f"products[{index}] must be an object")
        for key in ("ticker", "name", "aum_krw", "trading_value_krw"):
            if key not in product:
                raise HistoryValidationError(f"products[{index}].{key} is required")
        _number(product["aum_krw"], field=f"products[{index}].aum_krw", allow_none=True)
        _number(
            product["trading_value_krw"],
            field=f"products[{index}].trading_value_krw",
            allow_none=True,
        )

    implied_keys = (
        "underlying_day_return",
        "implied_rebalance_krw",
        "implied_ir_pct",
        "implied_rebalance_quality",
        "implied_rebalance_formula",
    )
    present = [key for key in implied_keys if key in record]
    if present and len(present) != len(implied_keys):
        raise HistoryValidationError("implied rebalance fields must be written together")
    if present:
        for key in implied_keys[:3]:
            _number(record[key], field=key, allow_none=True)
        if record["implied_rebalance_quality"] != "estimated":
            raise HistoryValidationError("implied_rebalance_quality must be estimated")
        formula = record["implied_rebalance_formula"]
        if not isinstance(formula, str) or not formula.strip():
            raise HistoryValidationError("implied_rebalance_formula must be non-empty")


def _quality(*values: Any) -> str:
    """Preserve the weakest source quality without manufacturing precision."""
    labels = {str(value) for value in values if value}
    if "estimated" in labels:
        return "estimated"
    if "partial" in labels or "partial_observed" in labels:
        return "partial"
    return "observed"


def activity_record_from_board(board: dict[str, Any]) -> dict[str, Any] | None:
    """Return an observed K200 activity row, or None if the API did not yield it."""
    kr = board.get("kr") or {}
    futures = kr.get("kospi200_futures") or {}
    options = kr.get("kospi200_options") or {}
    if futures.get("quality") != "observed" or options.get("quality") != "observed":
        return None
    as_of = _iso_day(kr.get("as_of"), field="kr.as_of")
    record = {
        "date": as_of,
        "as_of": as_of,
        "source": "; ".join(
            part
            for part in (futures.get("source"), options.get("source"))
            if isinstance(part, str) and part
        ),
        "quality": _quality(futures.get("quality"), options.get("quality")),
        "kospi200_futures": {
            "volume": futures.get("volume"),
            "trading_value_krw": futures.get("trading_value_krw"),
        },
        "kospi200_options": {
            key: options.get(key)
            for key in (
                "call_volume",
                "put_volume",
                "call_trading_value_krw",
                "put_trading_value_krw",
                "put_call_volume",
                "put_call_trading_value",
            )
        },
    }
    validate_activity_record(record)
    return record


def direction_record_from_micro(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a market-wide lever/inverse turnover observation."""
    ratios = snapshot.get("market_letf_derivatives_ratios") or {}
    category = snapshot.get("letf_category_share") or {}
    by_direction = ratios.get("by_direction") or {}
    if ratios.get("quality") not in {"observed", "partial", "partial_observed", "estimated"}:
        return None
    as_of = _iso_day(snapshot.get("as_of"), field="market_microstructure.as_of")
    record = {
        "date": as_of,
        "as_of": as_of,
        "source": str(ratios.get("source") or "market_microstructure snapshot"),
        "quality": _quality(ratios.get("quality")),
        "kospi_cash_tv_krw": category.get("kospi_cash_tv_krw"),
        "levered_inverse_etf_tv_over_kospi_cash_tv_pct": ratios.get(
            "levered_inverse_etf_tv_over_kospi_cash_tv_pct"
        ),
        "by_direction": {
            direction: {
                key: (by_direction.get(direction) or {}).get(key)
                for key in (
                    "trading_value_krw",
                    "share_of_lev_tv_pct",
                    "share_of_kospi_tv_pct",
                )
            }
            for direction in DIRECTIONS
        },
    }
    validate_direction_record(record)
    return record


def _product_record(product: dict[str, Any]) -> dict[str, Any]:
    record = {
        "ticker": product.get("ticker"),
        "name": product.get("name"),
        "aum_krw": product.get("aum"),
        "trading_value_krw": product.get("trading_value"),
    }
    for key in ("L", "direction", "aum_source", "aum_quality"):
        if product.get(key) is not None:
            record[key] = product.get(key)
    return record


IMPLIED_REBALANCE_FORMULA = (
    "signed Σ[AUM × (L² − L) × underlying_day_return]; "
    "implied_ir_pct=abs(net sum)/spot daily trading value ×100; "
    "model estimate, not observed ETF trades or price impact"
)


def _implied_rebalance(
    stock: dict[str, Any], products: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the signed daily-reset estimate from auditable raw inputs.

    The UI may calculate moving averages from these daily records.  The data
    layer stores no calendar-filled or smoothed value.
    """
    day_return = stock.get("day_return")
    spot_tv = stock.get("spot_trading_value_krw", stock.get("adv_spot_krw"))
    null_result = {
        "underlying_day_return": day_return,
        "implied_rebalance_krw": None,
        "implied_ir_pct": None,
        "implied_rebalance_quality": "estimated",
        "implied_rebalance_formula": IMPLIED_REBALANCE_FORMULA,
    }
    if day_return is None or spot_tv is None or float(spot_tv) <= 0 or not products:
        return null_result

    model_products: list[dict[str, float]] = []
    for product in products:
        aum = product.get("aum_krw")
        leverage = product.get("L")
        if aum is None or leverage is None:
            return null_result
        model_products.append({"aum": float(aum), "L": float(leverage)})

    totals = total_rebalance(model_products, r=float(day_return))
    signed_net = totals["tr_total"]
    return {
        "underlying_day_return": float(day_return),
        "implied_rebalance_krw": signed_net,
        "implied_ir_pct": impact_ratio(signed_net, float(spot_tv)),
        "implied_rebalance_quality": "estimated",
        "implied_rebalance_formula": IMPLIED_REBALANCE_FORMULA,
    }


def stock_records_from_micro(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract one shared-log row per observable single-stock LETF ticker."""
    as_of = _iso_day(snapshot.get("as_of"), field="market_microstructure.as_of")
    records: list[dict[str, Any]] = []
    for stock in snapshot.get("stocks") or []:
        if not isinstance(stock, dict) or not stock.get("ticker"):
            continue
        # No total LETF turnover means this is not an LETF observation.  Do not
        # create a hollow calendar row just because the underlying was listed.
        if stock.get("letf_trading_value_krw") is None:
            continue
        products = [_product_record(product) for product in stock.get("products") or []]
        partial_products = not products or any(
            product["aum_krw"] is None or product["trading_value_krw"] is None
            or product.get("aum_quality") in {"proxy", "missing"}
            for product in products
        )
        record = {
            "date": as_of,
            "as_of": as_of,
            "source": str(stock.get("source") or "market_microstructure snapshot"),
            "quality": _quality(stock.get("quality"), "partial" if partial_products else None),
            "ticker": str(stock["ticker"]),
            # `adv_spot_krw` is the day's KRX/FDR ACC_TRDVAL/Amount, retained
            # as a legacy snapshot name.  New snapshots expose the clear alias.
            "spot_trading_value_krw": stock.get("spot_trading_value_krw", stock.get("adv_spot_krw")),
            "letf_trading_value_krw": stock.get("letf_trading_value_krw"),
            "letf_turnover_ratio": stock.get("letf_turnover_ratio"),
            "letf_aum_sum_krw": stock.get("letf_aum_sum_krw"),
            "letf_aum_long_krw": stock.get("letf_aum_long_krw"),
            "letf_aum_inverse_krw": stock.get("letf_aum_inverse_krw"),
            "products": products,
        }
        record.update(_implied_rebalance(stock, products))
        validate_stock_record(record)
        records.append(record)
    return records


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HistoryValidationError(f"{path}:{line_no}: invalid JSONL") from exc
        if not isinstance(row, dict):
            raise HistoryValidationError(f"{path}:{line_no}: JSONL row must be an object")
        rows.append(row)
    return rows


def append_jsonl(
    path: Path,
    records: Iterable[dict[str, Any]],
    *,
    validator,
    key_fields: tuple[str, ...],
) -> int:
    """Merge a day's records atomically; newest observation wins on duplicate key."""
    incoming = list(records)
    for record in incoming:
        validator(record)
    existing = _read_jsonl(path)
    for record in existing:
        validator(record)

    by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in [*existing, *incoming]:
        key = tuple(str(record[field]) for field in key_fields)
        by_key[key] = record
    ordered = [by_key[key] for key in sorted(by_key)]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in ordered)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return len(incoming)
