#!/usr/bin/env python3
"""Publish the KOSPI200 derivatives microstructure history for the UI.

Reads the normalized KRX radar hive in the private ``krx-month-paste`` repo
(checked out by the daily Action) and writes one compact, columnar file:

  public/data/krx_deriv_flow_v1.json

Inputs (all under ``<krx-month-paste>/data/normalized``):

  krx_15007_k200_investor   KRX 15007 투자자별 거래실적 (일별추이, 거래대금) --
                            K200 futures, calls and puts, each with foreign /
                            institution / retail / other-corp buy/sell/net.
                            Investor *flow*, not open interest.
  kospi200_futures_oi       KRX 15003 front-month K200 futures quote and
                            market-wide listed OI (regular session).
  kospi200_option_oi        KRX 15018 front-month K200 option chain -- per
                            strike OI and IV (regular session).  Market-wide,
                            NOT foreign-held OI.
  kospi_program             KRX 12012 KOSPI program trading (arbitrage /
                            non-arbitrage / total).  Own date axis: the hive
                            has long gaps and is not a KRX trading calendar.

Rules, same as the rest of this directory: a day KRX did not publish has no
value (the axis is observed days, never a filled calendar), a missing number
stays ``null``, and a row whose buy - sell does not reproduce its own net is
dropped to ``null`` rather than trusted on its quality tag.  Money keeps
KRX's source unit (백만원) as integers.

History is never lost when collection stalls or a checkout comes back
partial: the new build is merged onto the file already published, so a date
the source no longer carries keeps its last observed values, and a date it
does carry is replaced by the fresh observation.  ``last_dates`` records the
newest observed day per dataset, which is what the UI uses to say that a
block stopped updating while still drawing everything up to that day.

Usage:
  python build_krx_deriv_flow.py --source ../../../../krx-month-paste --print-stats
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "../../public/data/krx_deriv_flow_v1.json"

SCHEMA_VERSION = "krx-deriv-flow-v1"
PRODUCTS = ("futures", "options_call", "options_put")
INVESTORS = ("foreign", "institution", "retail", "other_corp")
PROGRAM_TYPES = ("arbitrage", "non_arbitrage", "total")
# KRX rounds each side to 백만원 independently, so buy - sell may differ from
# the reported net by one unit of rounding.  Anything wider is a broken row.
NET_TOLERANCE_KRW = 1_000_000
# Strike profile published for the latest option day: strikes this far from
# the front-month futures close.  Deep wings hold stale OI that only flattens
# the chart.
PROFILE_BAND = 0.15
# An IV print outside this band is a deep-ITM/no-bid artefact, not a quote.
IV_RANGE = (1.0, 150.0)


def _read_hive(base: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part in sorted(base.glob("year=*/month=*/part.jsonl.gz")):
        with gzip.open(part, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # One bad line must not void a month of observations.
                    continue
    return rows


# Raw 15007 exports Cursor drops at data/raw/krx_15007/<date>/<product>_<side>.csv.
# The column names are KRX's own; values are 백만원.
RAW_INVESTOR_COLUMNS = {"foreign": "외국인합계", "institution": "기관합계",
                        "retail": "개인", "other_corp": "기타법인", "market_total": "전체"}


def _read_raw_side(path: Path, day: str) -> dict[str, float] | None:
    """One raw 15007 BUY or SELL export -> {investor: 백만원} for ``day``."""
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    except (OSError, UnicodeDecodeError):
        return None
    header_index = next((i for i, r in enumerate(rows) if any(c.strip() == "일자" for c in r)), None)
    if header_index is None:
        return None
    header = [c.replace(" ", "").strip() for c in rows[header_index]]
    for row in rows[header_index + 1:]:
        cells = dict(zip(header, row))
        if (cells.get("일자") or "").strip().replace("/", "-") != day:
            continue
        out: dict[str, float] = {}
        for inv, col in RAW_INVESTOR_COLUMNS.items():
            text = (cells.get(col) or "").replace(",", "").strip()
            try:
                out[inv] = float(text)
            except ValueError:
                # A blank cell is an unavailable observation, not zero.
                return None
        return out
    return None


def _read_raw_15007(base: Path) -> list[dict[str, Any]]:
    """Hive-shaped rows from the raw per-day 15007 exports.

    Cursor publishes the raw CSVs every day but rebuilds the normalized hive
    less often (it stopped at 2026-09-21 while the raw folder ran to 09-30).
    These rows only fill (date, product) pairs the hive does not carry; the
    hive stays authoritative wherever it has the day.
    """
    rows: list[dict[str, Any]] = []
    if not base.is_dir():
        return rows
    for day_dir in sorted(base.iterdir()):
        day = day_dir.name
        if not day_dir.is_dir() or len(day) != 10:
            continue
        for product in PRODUCTS:
            buy = _read_raw_side(day_dir / f"{product}_buy.csv", day)
            sell = _read_raw_side(day_dir / f"{product}_sell.csv", day)
            if buy is None or sell is None:
                continue
            row: dict[str, Any] = {"date": day, "product": product, "quality": "observed",
                                   "collected_at": "", "origin": "raw_15007_csv"}
            for inv in (*INVESTORS, "market_total"):
                b, s = buy[inv] * 1_000_000, sell[inv] * 1_000_000
                row[f"{inv}_buy_krw"], row[f"{inv}_sell_krw"], row[f"{inv}_net_krw"] = b, s, b - s
            rows.append(row)
    return rows


def _latest_by_key(rows: Iterable[dict[str, Any]], key: Callable) -> dict[Any, dict[str, Any]]:
    """Re-collected days appear more than once; the latest collection wins."""
    out: dict[Any, dict[str, Any]] = {}
    for row in rows:
        k = key(row)
        if k is None:
            continue
        prev = out.get(k)
        if prev is None or str(row.get("collected_at") or "") >= str(prev.get("collected_at") or ""):
            out[k] = row
    return out


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _mn(value: Any) -> int | None:
    """KRW float -> integer 백만원 (KRX's own unit).  None stays None."""
    v = _num(value)
    return None if v is None else int(round(v / 1_000_000))


def _pos_int(value: Any) -> int | None:
    """KRX prints an empty cell as 0; a zero OI/volume/close is not a print."""
    v = _num(value)
    return int(v) if v is not None and v > 0 else None


def _consistent(row: dict[str, Any], prefix: str) -> bool:
    b, s, n = (_num(row.get(f"{prefix}{side}_krw")) for side in ("buy", "sell", "net"))
    if b is None or s is None or n is None:
        return False
    return abs((b - s) - n) <= NET_TOLERANCE_KRW


def _last_observed(dates: list[str], *columns: list) -> str | None:
    for i in range(len(dates) - 1, -1, -1):
        if any(col[i] is not None for col in columns):
            return dates[i]
    return None


def _load_manifest(source: Path, name: str) -> dict[str, Any]:
    path = source / "data" / "manifests" / f"{name}.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


# --- per-dataset builders ----------------------------------------------------

def _build_flow(rows, dates, stats):
    flows = _latest_by_key(
        rows, lambda r: (r.get("date"), r.get("product")) if r.get("product") in PRODUCTS and r.get("date") else None)
    flow: dict[str, dict[str, list]] = {}
    partial_days: dict[str, list[str]] = {}
    for product in PRODUCTS:
        cols: dict[str, list] = {f"{inv}_net": [] for inv in INVESTORS}
        cols.update({"foreign_buy": [], "foreign_sell": [], "market_total_buy": []})
        partial: list[str] = []
        for day in dates:
            row = flows.get((day, product))
            if row is None:
                stats["missing_product_days"] += 1
                for col in cols.values():
                    col.append(None)
                continue
            if row.get("quality") != "observed":
                partial.append(day)
                stats["partial_rows"] += 1
            for inv in INVESTORS:
                ok = _consistent(row, f"{inv}_")
                if not ok and row.get(f"{inv}_net_krw") is not None:
                    stats["inconsistent_cells"] += 1
                cols[f"{inv}_net"].append(_mn(row.get(f"{inv}_net_krw")) if ok else None)
                if inv == "foreign":
                    cols["foreign_buy"].append(_mn(row.get("foreign_buy_krw")) if ok else None)
                    cols["foreign_sell"].append(_mn(row.get("foreign_sell_krw")) if ok else None)
            cols["market_total_buy"].append(_mn(row.get("market_total_buy_krw")))
        flow[product] = cols
        partial_days[product] = partial
    return flow, partial_days


def _build_front(fut, dates):
    front = {"contract": [], "close": [], "open_interest": [], "volume": []}
    for day in dates:
        row = fut.get(day) or {}
        close = _num(row.get("close"))
        front["contract"].append(row.get("expiry_or_contract_month"))
        front["close"].append(close if close is not None and close > 0 else None)
        front["open_interest"].append(_pos_int(row.get("open_interest_contracts")))
        front["volume"].append(_pos_int(row.get("volume_contracts")))
    return front


def _second_thursday(yyyymm: str) -> str | None:
    try:
        first = datetime(int(yyyymm[:4]), int(yyyymm[4:6]), 1)
    except (TypeError, ValueError):
        return None
    offset = (3 - first.weekday()) % 7  # Thursday == 3
    return first.replace(day=1 + offset + 7).strftime("%Y-%m-%d")


def _build_option_oi(rows, dates, fut):
    """Front-month chain -> per-day totals, walls and ATM IV + latest profile."""
    by_day: dict[str, dict[tuple, dict]] = {}
    for key, row in _latest_by_key(
        rows,
        lambda r: (r.get("date"), r.get("option_type"), r.get("strike"))
        if r.get("session") == "regular" and r.get("date") and r.get("option_type") in ("call", "put")
        and _num(r.get("strike")) is not None else None,
    ).items():
        by_day.setdefault(key[0], {})[(key[1], float(key[2]))] = row

    cols = {k: [] for k in ("expiry", "call_oi", "put_oi", "pc_oi", "call_wall", "put_wall", "atm_strike", "atm_iv")}
    for day in dates:
        chain = by_day.get(day)
        if not chain:
            for col in cols.values():
                col.append(None)
            continue
        oi = {k: _pos_int(r.get("open_interest_contracts")) for k, r in chain.items()}
        calls = {s: v for (t, s), v in oi.items() if t == "call" and v}
        puts = {s: v for (t, s), v in oi.items() if t == "put" and v}
        call_oi = sum(calls.values()) if calls else None
        put_oi = sum(puts.values()) if puts else None
        cols["expiry"].append(next(iter(chain.values())).get("expiry_or_contract_month"))
        cols["call_oi"].append(call_oi)
        cols["put_oi"].append(put_oi)
        cols["pc_oi"].append(round(put_oi / call_oi, 4) if call_oi and put_oi else None)
        cols["call_wall"].append(max(calls, key=calls.get) if calls else None)
        cols["put_wall"].append(max(puts, key=puts.get) if puts else None)
        # ATM = listed strike nearest the front-month futures close that day.
        f_close = _num((fut.get(day) or {}).get("close"))
        strikes = sorted({s for (_t, s) in chain})
        atm = min(strikes, key=lambda s: abs(s - f_close)) if f_close and strikes else None
        ivs = []
        if atm is not None:
            for t in ("call", "put"):
                iv = _num((chain.get((t, atm)) or {}).get("implied_volatility"))
                if iv is not None and IV_RANGE[0] <= iv <= IV_RANGE[1]:
                    ivs.append(iv)
        cols["atm_strike"].append(atm)
        cols["atm_iv"].append(round(sum(ivs) / len(ivs), 2) if ivs else None)

    # On the expiring contract's last day there is no time value left, so the
    # IV KRX prints (3-7%) is an artefact.  The last day before the front
    # month rolls, or the month's 2nd Thursday (KRX monthly expiry), is null.
    for i, day in enumerate(dates):
        exp = cols["expiry"][i]
        rolls = i + 1 < len(dates) and cols["expiry"][i + 1] and exp and cols["expiry"][i + 1] != exp
        if rolls or (exp and day == _second_thursday(exp)):
            cols["atm_iv"][i] = None

    profile = None
    last = _last_observed(dates, cols["call_oi"], cols["put_oi"])
    if last:
        chain = by_day[last]
        f_close = _num((fut.get(last) or {}).get("close"))
        strikes = sorted({s for (_t, s) in chain})
        if f_close:
            strikes = [s for s in strikes if abs(s / f_close - 1) <= PROFILE_BAND]
        rows_out = []
        for s in strikes:
            c = _pos_int((chain.get(("call", s)) or {}).get("open_interest_contracts"))
            p = _pos_int((chain.get(("put", s)) or {}).get("open_interest_contracts"))
            if c or p:
                rows_out.append([s, c, p])
        profile = {"date": last, "expiry": next(iter(chain.values())).get("expiry_or_contract_month"),
                   "futures_close": f_close, "strikes": rows_out}
    return cols, profile


def _build_program(rows, stats):
    prog = _latest_by_key(
        rows, lambda r: (r.get("date"), r.get("program_type")) if r.get("program_type") in PROGRAM_TYPES and r.get("date") else None)
    pdates = sorted({d for (d, _t) in prog})
    cols: dict[str, list] = {f"{t}_net": [] for t in PROGRAM_TYPES}
    for day in pdates:
        for t in PROGRAM_TYPES:
            row = prog.get((day, t))
            ok = row is not None and _consistent(row, "")
            if row is not None and not ok:
                stats["program_inconsistent"] += 1
            cols[f"{t}_net"].append(_mn(row.get("net_krw")) if ok else None)
    return pdates, cols


def build(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = source / "data" / "normalized"
    flow_dir = normalized / "krx_15007_k200_investor"
    if not flow_dir.is_dir():
        raise FileNotFoundError(f"missing KRX 15007 hive: {flow_dir}")

    flow_rows = _read_hive(flow_dir)
    have = {(r.get("date"), r.get("product")) for r in flow_rows}
    raw_rows = [r for r in _read_raw_15007(source / "data" / "raw" / "krx_15007")
                if (r["date"], r["product"]) not in have]
    flow_rows += raw_rows
    fut_dir = normalized / "kospi200_futures_oi"
    opt_dir = normalized / "kospi200_option_oi"
    prog_dir = normalized / "kospi_program"
    fut_rows = _read_hive(fut_dir) if fut_dir.is_dir() else []
    opt_rows = _read_hive(opt_dir) if opt_dir.is_dir() else []
    prog_rows = _read_hive(prog_dir) if prog_dir.is_dir() else []

    # Regular session only: the night session trades the same contract on a
    # different clock and would double a day.
    fut = _latest_by_key(fut_rows, lambda r: r.get("date") if r.get("session") == "regular" and r.get("date") else None)

    # One axis for the K200 blocks: every day any of them observed.
    dates = sorted({r["date"] for r in flow_rows if r.get("product") in PRODUCTS and r.get("date")}
                   | set(fut)
                   | {r["date"] for r in opt_rows if r.get("session") == "regular" and r.get("date")})

    stats = {"flow_rows_read": len(flow_rows), "raw_csv_rows": len(raw_rows), "dates": len(dates), "inconsistent_cells": 0,
             "partial_rows": 0, "missing_product_days": 0, "program_inconsistent": 0}
    flow, partial_days = _build_flow(flow_rows, dates, stats)
    front = _build_front(fut, dates)
    option_oi, profile = _build_option_oi(opt_rows, dates, fut)
    pdates, program = _build_program(prog_rows, stats)

    stats.update({
        "futures_front_days": sum(1 for v in front["close"] if v is not None),
        "option_oi_days": sum(1 for v in option_oi["call_oi"] if v is not None),
        "program_days": len(pdates),
    })

    flow_manifest = _load_manifest(source, "krx_15007_k200_investor")
    prog_manifest = _load_manifest(source, "kospi_program")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": dates[-1] if dates else None,
        "range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
        "unit": "million_krw",
        "unit_ko": "백만원",
        "source": {
            "flow": "KRX 15007 투자자별 거래실적 (MDC0201050302) · 일별추이 · 거래대금",
            "futures_front": "KRX 15003 최근월물 시세 추이 (MDC0201050103) · 정규장",
            "option_oi": "KRX 15018 최근월물 시세 추이(옵션) (MDC0201050104) · 정규장",
            "program": "KRX 12012 프로그램매매 일별 (MDC0201020305) · 유가증권",
            "repo": "krx-month-paste data/normalized",
            "manifest_generated_at": flow_manifest.get("generated_at"),
        },
        "products": list(PRODUCTS),
        "investors": list(INVESTORS),
        "dates": dates,
        "flow": flow,
        "partial_days": partial_days,
        "futures_front": {
            **front,
            "scope_ko": "코스피200 선물 최근월물 1개 종목 · 시장 전체 미결제약정 (외국인 보유분 아님) · 롤오버일에 OI가 끊김",
        },
        "option_oi": {
            **option_oi,
            "profile": profile,
            "scope_ko": "코스피200 옵션 최근월물 체인 · 시장 전체 미결제약정 (외국인 보유분 아님) · 위클리 제외 · 만기 다음 날 월물이 바뀜",
        },
        "program": {
            "dates": pdates,
            **program,
            "coverage_pct": prog_manifest.get("coverage_pct"),
            "scope_ko": "유가증권시장 프로그램매매 순매수 (차익·비차익·전체) · 현물 주식 거래 · 수집이 빈 날은 날짜가 없음",
        },
        "last_dates": {
            "flow": _last_observed(dates, *(flow[p]["foreign_net"] for p in PRODUCTS)),
            "futures_front": _last_observed(dates, front["close"]),
            "option_oi": _last_observed(dates, option_oi["call_oi"], option_oi["put_oi"]),
            "program": pdates[-1] if pdates else None,
        },
        "missing_trading_days": flow_manifest.get("missing_trading_days") or [],
        "notes_ko": [
            "매수·매도·순매수는 당일 거래대금 흐름입니다. 미결제약정·보유 포지션·헤지 의도가 아닙니다.",
            "매수−매도가 순매수와 맞지 않는 행은 null로 비웁니다. 휴장일은 날짜 자체가 없습니다.",
            "수집이 멈춘 데이터셋은 마지막 관측일까지의 값을 그대로 유지합니다 (last_dates).",
        ],
    }
    return payload, stats


# --- merge onto the published file -------------------------------------------

def _columns(block: Any, prefix: tuple = ()) -> Iterable[tuple[tuple, list]]:
    if isinstance(block, dict):
        for k, v in block.items():
            yield from _columns(v, prefix + (k,))
    elif isinstance(block, list):
        yield prefix, block


def _set(block: dict, path: tuple, value: Any) -> None:
    for k in path[:-1]:
        block = block.setdefault(k, {})
    block[path[-1]] = value


def _merge_axis(prev_dates: list, prev_block: dict, new_dates: list, new_block: dict) -> tuple[list, dict]:
    """Union of two date-aligned column blocks; fresh observations win.

    A date only in the published file keeps its published values -- that is
    the whole point: a stalled or partial source must not erase history.
    """
    union = sorted(set(prev_dates) | set(new_dates))
    new_idx = {d: i for i, d in enumerate(new_dates)}
    prev_idx = {d: i for i, d in enumerate(prev_dates)}
    out: dict = json.loads(json.dumps({k: v for k, v in new_block.items()}))  # deep copy, keeps scalars
    paths = {p for p, col in _columns(new_block) if len(col) == len(new_dates)}
    paths |= {p for p, col in _columns(prev_block) if len(col) == len(prev_dates)}
    for path in paths:
        new_col = _get(new_block, path)
        prev_col = _get(prev_block, path)
        merged = []
        for d in union:
            if d in new_idx and isinstance(new_col, list) and len(new_col) == len(new_dates):
                merged.append(new_col[new_idx[d]])
            elif d in prev_idx and isinstance(prev_col, list) and len(prev_col) == len(prev_dates):
                merged.append(prev_col[prev_idx[d]])
            else:
                merged.append(None)
        _set(out, path, merged)
    return union, out


def _get(block: Any, path: tuple) -> Any:
    for k in path:
        if not isinstance(block, dict):
            return None
        block = block.get(k)
    return block


def merge_with_previous(prev: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    if not prev or prev.get("schema_version") != SCHEMA_VERSION or not prev.get("dates"):
        return new
    out = dict(new)
    main_new = {k: new.get(k) or {} for k in ("flow", "futures_front", "option_oi")}
    main_prev = {k: prev.get(k) or {} for k in ("flow", "futures_front", "option_oi")}
    # The strike profile is one day's snapshot, not a column.
    for blk in (main_new, main_prev):
        blk["option_oi"] = {k: v for k, v in blk["option_oi"].items() if k != "profile"}
    dates, merged = _merge_axis(prev["dates"], main_prev, new["dates"], main_new)
    out["dates"] = dates
    out["flow"] = merged["flow"]
    out["futures_front"] = merged["futures_front"]
    out["option_oi"] = {**merged["option_oi"],
                        "profile": (new.get("option_oi") or {}).get("profile") or (prev.get("option_oi") or {}).get("profile")}

    new_set = set(new["dates"])
    out["partial_days"] = {
        p: sorted({d for d in (prev.get("partial_days") or {}).get(p, []) if d not in new_set}
                  | set((new.get("partial_days") or {}).get(p, [])))
        for p in PRODUCTS
    }

    pn, pp = new.get("program") or {}, prev.get("program") or {}
    pdates, pmerged = _merge_axis(pp.get("dates") or [], {k: v for k, v in pp.items() if k != "dates"},
                                  pn.get("dates") or [], {k: v for k, v in pn.items() if k != "dates"})
    out["program"] = {**pmerged, "dates": pdates}

    out["as_of"] = dates[-1]
    out["range"] = {"start": dates[0], "end": dates[-1]}
    out["last_dates"] = {
        "flow": _last_observed(dates, *(out["flow"][p]["foreign_net"] for p in PRODUCTS)),
        "futures_front": _last_observed(dates, out["futures_front"]["close"]),
        "option_oi": _last_observed(dates, out["option_oi"]["call_oi"], out["option_oi"]["put_oi"]),
        "program": pdates[-1] if pdates else None,
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="krx-month-paste checkout root")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    payload, stats = build(args.source)
    if not payload["dates"]:
        print("no KRX observations found; keeping the existing file", file=sys.stderr)
        return 1
    prev = None
    if args.out.is_file():
        try:
            prev = json.loads(args.out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = None
    merged = merge_with_previous(prev, payload)
    kept = len(merged["dates"]) - len(payload["dates"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.print_stats:
        print(json.dumps({**stats, "kept_from_previous": kept, "as_of": merged["as_of"],
                          "last_dates": merged["last_dates"], "bytes": args.out.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
