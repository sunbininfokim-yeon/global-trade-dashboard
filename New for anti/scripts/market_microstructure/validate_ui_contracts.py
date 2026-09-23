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


def validate_15007_leg(value: Any, *, where: str) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{where} must be object")
    values = [value.get(key) for key in ("buy_krw", "sell_krw", "net_krw")]
    if any(item is None for item in values):
        if any(item is not None for item in values):
            raise ContractError(f"{where} must be all-null or all-numeric")
        return
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise ContractError(f"{where} values must be numeric or all null")
    if values[0] - values[1] != values[2]:
        raise ContractError(f"{where}.buy_krw - sell_krw must equal net_krw")


def validate_krx_deriv_flow(value: dict[str, Any]) -> None:
    """Columnar KRX 15007 history: every column must line up with `dates`."""
    if value.get("schema_version") != "krx-deriv-flow-v1":
        raise ContractError("krx_deriv_flow schema_version mismatch")
    dates = value.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ContractError("krx_deriv_flow.dates must be a non-empty list")
    if dates != sorted(set(dates)):
        raise ContractError("krx_deriv_flow.dates must be sorted and unique")
    if value.get("as_of") != dates[-1]:
        raise ContractError("krx_deriv_flow.as_of must equal the last date")
    flow = require_object(value, "flow", where="krx_deriv_flow")
    for product in ("futures", "options_call", "options_put"):
        cols = require_object(flow, product, where="krx_deriv_flow.flow")
        for col in ("foreign_net", "institution_net", "retail_net", "other_corp_net",
                    "foreign_buy", "foreign_sell", "market_total_buy"):
            arr = cols.get(col)
            if not isinstance(arr, list) or len(arr) != len(dates):
                raise ContractError(f"krx_deriv_flow.flow.{product}.{col} must align with dates")
            if any(v is not None and (isinstance(v, bool) or not isinstance(v, int)) for v in arr):
                raise ContractError(f"krx_deriv_flow.flow.{product}.{col} must be int or null")
    front = require_object(value, "futures_front", where="krx_deriv_flow")
    for col in ("close", "open_interest"):
        if len(front.get(col) or []) != len(dates):
            raise ContractError(f"krx_deriv_flow.futures_front.{col} must align with dates")
    options = require_object(value, "option_oi", where="krx_deriv_flow")
    for col in ("expiry", "call_oi", "put_oi", "pc_oi", "call_wall", "put_wall", "atm_strike", "atm_iv"):
        if len(options.get(col) or []) != len(dates):
            raise ContractError(f"krx_deriv_flow.option_oi.{col} must align with dates")
    program = require_object(value, "program", where="krx_deriv_flow")
    pdates = program.get("dates")
    if not isinstance(pdates, list) or pdates != sorted(set(pdates)):
        raise ContractError("krx_deriv_flow.program.dates must be sorted and unique")
    for col in ("arbitrage_net", "non_arbitrage_net", "total_net"):
        if len(program.get(col) or []) != len(pdates):
            raise ContractError(f"krx_deriv_flow.program.{col} must align with program.dates")
    last = require_object(value, "last_dates", where="krx_deriv_flow")
    for key in ("flow", "option_oi"):
        if last.get(key) is not None and last[key] not in dates:
            raise ContractError(f"krx_deriv_flow.last_dates.{key} must be one of dates")


def validate_detailed_15007(value: Any) -> None:
    if not isinstance(value, dict):
        raise ContractError("derivatives_board.kr.investor_nets.detailed_15007 must be object")
    if value.get("schema_version") != "krx-15007-call-put-v2":
        raise ContractError("detailed_15007 schema_version mismatch")
    query = require_object(value, "query", where="detailed_15007")
    for key, expected in (("market", "KOSPI200"), ("metric", "trading_value"),
                          ("side", "buy_sell_and_net"), ("unit", "KRW")):
        if query.get(key) != expected:
            raise ContractError(f"detailed_15007.query.{key} must be {expected}")
    products = require_object(value, "products", where="detailed_15007")
    for name in ("options_call", "options_put"):
        product = require_object(products, name, where="detailed_15007.products")
        if product.get("quality") not in {"observed", "partial_observed", "missing"}:
            raise ContractError(f"detailed_15007.products.{name}.quality invalid")
        validate_15007_leg(product.get("foreign"), where=f"detailed_15007.products.{name}.foreign")
        validate_15007_leg(product.get("market_total"), where=f"detailed_15007.products.{name}.market_total")
        series = product.get("series")
        if not isinstance(series, list):
            raise ContractError(f"detailed_15007.products.{name}.series must be list")
        seen_dates: set[str] = set()
        for index, row in enumerate(series):
            if not isinstance(row, dict):
                raise ContractError(f"detailed_15007.products.{name}.series[{index}] must be object")
            day = require(row, "date", where=f"detailed_15007.products.{name}.series[{index}]")
            if day in seen_dates:
                raise ContractError(f"detailed_15007.products.{name}.series has duplicate {day}")
            seen_dates.add(day)
            quality = row.get("quality")
            if quality not in {"observed", "partial_observed", "missing"}:
                raise ContractError(f"detailed_15007.products.{name}.series[{index}].quality invalid")
            validate_15007_leg(row.get("foreign"), where=f"detailed_15007.products.{name}.series[{index}].foreign")
            validate_15007_leg(row.get("market_total"), where=f"detailed_15007.products.{name}.series[{index}].market_total")
            if quality == "observed" and (
                row["foreign"].get("net_krw") is None or row["market_total"].get("net_krw") is None
            ):
                raise ContractError(f"detailed_15007.products.{name}.series[{index}] observed needs both legs")


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
    investor_nets = require_object(kr, "investor_nets", where="derivatives_board.kr")
    validate_detailed_15007(require(investor_nets, "detailed_15007", where="derivatives_board.kr.investor_nets"))

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

    validate_krx_deriv_flow(load_json("krx_deriv_flow_v1.json"))

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
