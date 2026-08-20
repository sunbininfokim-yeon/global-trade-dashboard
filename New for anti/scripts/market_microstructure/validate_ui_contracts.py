#!/usr/bin/env python3
"""Fail the daily job when a dashboard data contract is absent or malformed.

This is deliberately a lightweight, no-network check.  It runs after the
builders and verifies the fields consumed by the market-microstructure UI;
it does not invent observations, align dates, or judge market signals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from market_microstructure.derivatives_history import (
    HistoryValidationError,
    validate_stock_record,
)
from market_microstructure.external_history import validate_external_record

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "../../public/data"


class ContractError(RuntimeError):
    pass


def load_json(name: str) -> dict[str, Any]:
    path = DATA / name
    if not path.is_file():
        raise ContractError(f"missing required output: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON root must be object: {path}")
    return value


def require(obj: dict[str, Any], key: str, *, where: str) -> Any:
    value = obj.get(key)
    if value is None or value == "":
        raise ContractError(f"missing {where}.{key}")
    return value


def require_object(obj: dict[str, Any], key: str, *, where: str) -> dict[str, Any]:
    value = require(obj, key, where=where)
    if not isinstance(value, dict):
        raise ContractError(f"{where}.{key} must be object")
    return value


def validate_history(name: str, *, stock: bool = False) -> None:
    path = DATA / name
    if not path.is_file():
        raise ContractError(f"missing required history: {path}")
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSONL: {path}:{line_no}") from exc
        if not isinstance(row, dict):
            raise ContractError(f"JSONL row must be object: {path}:{line_no}")
        for key in ("date", "as_of", "source", "quality"):
            require(row, key, where=f"{name}:{line_no}")
        if stock:
            require(row, "ticker", where=f"{name}:{line_no}")
            if "spot_trading_value_krw" not in row:
                raise ContractError(
                    f"missing {name}:{line_no}.spot_trading_value_krw"
                )
            try:
                validate_stock_record(row)
            except HistoryValidationError as exc:
                raise ContractError(f"invalid stock history: {path}:{line_no}: {exc}") from exc


def validate_optional_external_history() -> None:
    """Validate external archive when the live venue step has produced it.

    External venues are optional (Yahoo/Bloomberg can be unavailable), so a
    missing file is not a failed daily run.  If present, every row must still
    carry provenance and partial/observed quality honestly.
    """
    path = DATA / "external_leverage_history_v1.jsonl"
    if not path.is_file():
        return
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSONL: {path}:{line_no}") from exc
        if not isinstance(row, dict):
            raise ContractError(f"JSONL row must be object: {path}:{line_no}")
        try:
            validate_external_record(row)
        except HistoryValidationError as exc:
            raise ContractError(f"invalid external history: {path}:{line_no}: {exc}") from exc


def validate() -> None:
    transmission = load_json("us_kr_transmission_v1.json")
    require(transmission, "as_of", where="transmission")
    require_object(transmission, "channels", where="transmission")
    prior = require_object(transmission, "kospi_open30m_prior", where="transmission")
    require_object(prior, "channels", where="transmission.kospi_open30m_prior")

    alerts = load_json("alert_levels_v1.json")
    require(alerts, "as_of", where="alerts")
    require_object(alerts, "kr_hynix_letf", where="alerts")
    require_object(alerts, "us_vix_to_kr", where="alerts")

    credit = load_json("deposit_credit_v1.json")
    credit_payload = require_object(credit, "deposit_credit", where="deposit_credit")
    require(credit_payload, "as_of", where="deposit_credit.deposit_credit")
    require(credit_payload, "quality", where="deposit_credit.deposit_credit")

    board = load_json("derivatives_board_v1.json")
    kr = require_object(board, "kr", where="derivatives_board")
    require(kr, "as_of", where="derivatives_board.kr")
    require_object(kr, "kospi200_futures", where="derivatives_board.kr")
    require_object(kr, "kospi200_options", where="derivatives_board.kr")

    micro = load_json("market_microstructure_v1.json")
    require(micro, "as_of", where="market_microstructure")
    ratios = require_object(micro, "market_letf_derivatives_ratios", where="market_microstructure")
    require_object(ratios, "by_direction", where="market_microstructure.market_letf_derivatives_ratios")
    stocks = require(micro, "stocks", where="market_microstructure")
    if not isinstance(stocks, list):
        raise ContractError("market_microstructure.stocks must be list")
    for stock in stocks:
        if not isinstance(stock, dict):
            raise ContractError("market_microstructure.stocks row must be object")
        require(stock, "ticker", where="market_microstructure.stocks")
        require(stock, "spot_trading_value_krw", where="market_microstructure.stocks")

    levels = load_json("investor_price_levels_v1.json")
    require(levels, "as_of", where="investor_price_levels")
    require_object(levels, "kospi_index_levels", where="investor_price_levels")

    concentration = load_json("kospi_concentration_history_v1.json")
    require(concentration, "as_of", where="kospi_concentration_history")

    validate_history("derivatives_activity_history_v1.jsonl")
    validate_history("leverage_direction_history_v1.jsonl")
    validate_history("stock_letf_history_v1.jsonl", stock=True)
    validate_optional_external_history()


def main() -> int:
    try:
        validate()
    except ContractError as exc:
        print(f"UI contract validation failed: {exc}", file=sys.stderr)
        return 1
    print("UI contract validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
