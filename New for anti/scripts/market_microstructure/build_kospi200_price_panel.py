#!/usr/bin/env python3
"""Refresh the KOSPI200 price panel and record when each series was collected.

The KRX workbook remains the source for dates it actually contains. Missing
index sessions are added only from Naver's KOSPI200 chart after every
overlapping open, high, low, close, and volume matches that workbook. The
script does not overwrite LETF underlying returns or the derivatives activity
history.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public/data"
MANIFEST = ROOT.parent / "data/manifests/krx_price_panel_20261101.json"
CLOSE_COMPARE = ROOT.parent / "data/manifests/krx_close_vs_price_file_20261101.json"
INDEX_PATH = PUBLIC / "kospi200_index_daily_v1.json"
ETF_PATH = PUBLIC / "kospi200_etf_candidates_daily_v1.json"
LETF_PATH = PUBLIC / "stock_letf_history_v1.jsonl"
PRICE_PATH = PUBLIC / "investor_price_levels_v1.json"

NAVER_CHART = (
    "https://m.stock.naver.com/front-api/external/chart/domestic/info"
    "?symbol={symbol}&requestType=1&startTime={start}&endTime={end}&timeframe=day"
)
NAVER_PRICE = "https://m.stock.naver.com/api/stock/{code}/price?pageSize=40&page={page}"

# Checked only for these two tickers. Other candidates stay unknown.
CHECKED_ADJUSTMENT = {
    "069500": {
        "price_adjustment": "backward_cash_distribution",
        "checked_span": ["2024-01-30", "2026-10-29"],
        "ex_dates_fitting_formula": 12,
        "formula": "A_t / A_{t-1} - 1 = U_t / (U_{t-1} - D) - 1",
        "primary_cash_check": {
            "ex_date": "2024-10-30",
            "distribution_krw": 120,
            "source": "Samsung Kodex notice 2024-10-29",
        },
    },
    "102110": {
        "price_adjustment": "backward_cash_distribution",
        "checked_span": ["2024-01-30", "2026-07-30"],
        "ex_dates_fitting_formula": 11,
        "formula": "A_t / A_{t-1} - 1 = U_t / (U_{t-1} - D) - 1",
        "not_fit": ["2026-10-29"],
        "primary_cash_check": None,
    },
}
CONCLUSION_KO = (
    "가격 파일의 종가는 네이버 캔들과 같다. 저장돼 있는 underlying_day_return은 가격 파일 종가 수익률과 "
    "부호가 다른 날이 있지만, KRX 일별 시세의 종가로 계산한 등락률과는 연속한 거래일 36쌍이 모두 일치한다 "
    f"(삼성전자·SK하이닉스, 근거 {CLOSE_COMPARE.relative_to(ROOT.parent)}). KRX 종가와 가격 파일 종가는 "
    "2026-09-14부터 서로 다른 날이 많다. 그래서 부호가 갈리는 날은 저장값의 오류가 아니라 두 종가의 정의 차이다. "
    "값을 덮어쓰지 않는다. 차이의 원인(거래소 통합 시세 여부 등)은 확인하지 못했다. 네이버가 발표한 등락률의 "
    "기준가격이 전일 캔들 종가와 다른 날은 종가 수익률과 발표 등락률이 서로 다른 질문이다."
)
SIGNAL_USE_KO = (
    "신호 함수는 underlying_day_return_quality가 observed_krx일 때만 저장 수익률과 리밸런싱 추정치를 돌려준다. "
    "2026-08-07부터 스냅샷의 연속 KRX 종가로 재현되는 날이 그 상태다. 그 이전 행은 네이버 캔들과 맞지만 "
    "KRX 종가 대조가 없다. 표시용 implied_rebalance_krw는 바꾸지 않는다. "
    "가격 파일 종가는 2026-09-14부터 KRX 종가와 다를 수 있으므로 두 종가를 섞지 않는다. "
    "069500은 2024-01-30부터 2026-10-29까지 분배락 12회, 102110은 2024-01-30부터 2026-07-30까지 11회가 "
    "A_t/A_{t-1}-1 = U_t/(U_{t-1}-D)-1 이다. 102110의 2026-10-29는 종가 비율이 0.9924에서 1로 한 번에 붙어 "
    "단일 분배금 식과 맞지 않아 제외한다. 같은 D를 조정 수익률에 다시 더하면 분배금이 두 번 들어간다. "
    "다른 상품의 조정 방식은 unknown이다. LETF AUM 결측과 파생상품 활동 결측은 채우지 않는다."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def fetch_naver_chart(symbol: str, start: str, end: str) -> dict[str, dict[str, float]]:
    """Return daily bars keyed by YYYY-MM-DD from the Naver fchart endpoint."""
    text = _get(NAVER_CHART.format(symbol=symbol, start=start, end=end))
    bars: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("["):
            continue
        try:
            item = json.loads(line.replace("'", '"'))
        except json.JSONDecodeError:
            continue
        if not item or not str(item[0]).isdigit():
            continue
        raw = str(item[0])
        bars[f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"] = {
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        }
    return bars


def fetch_naver_price_table(code: str, *, pages: int = 12) -> dict[str, dict[str, Any]]:
    """Official Naver daily row, including the published fluctuation rate."""
    out: dict[str, dict[str, Any]] = {}
    for page in range(1, pages + 1):
        batch = json.loads(_get(NAVER_PRICE.format(code=code, page=page)))
        if not batch:
            break
        for row in batch:
            out.setdefault(row["localTradedAt"][:10], row)
    return out


def _number(text: Any) -> float:
    return float(str(text).replace(",", ""))


def reconcile_index_gaps(
    index_doc: dict[str, Any],
    naver_bars: dict[str, dict[str, float]],
    *,
    collected_at: str,
) -> dict[str, Any]:
    """Add Naver sessions that the workbook lacks, after an exact overlap check.

    Existing workbook rows are kept. A mismatch on the overlap aborts the fill
    instead of choosing one source.
    """
    rows = list(index_doc.get("rows") or [])
    by_date = {row["date"]: row for row in rows}
    if len(by_date) != len(rows):
        raise ValueError("index rows contain duplicate dates")
    overlap = sorted(set(by_date) & set(naver_bars))
    for day in overlap:
        left = by_date[day]
        right = naver_bars[day]
        for key in ("open", "high", "low", "close"):
            if abs(float(left[key]) - right[key]) > 0.02:
                raise ValueError(f"KOSPI200 {key} mismatch on {day}")
        # Workbook and Naver volumes differ by at most one screen unit.
        if abs(float(left["volume_screen"]) - right["volume"]) > 1:
            raise ValueError(f"KOSPI200 volume mismatch on {day}")
    added = []
    for day in sorted(set(naver_bars) - set(by_date)):
        bar = naver_bars[day]
        added.append(
            {
                "date": day,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "change": None,
                "change_pct_screen": None,
                "volume_screen": bar["volume"],
                "volume_unit": "천주",
                "volume_unit_confirmed": False,
                "trading_value_screen": None,
                "trading_value_unit": "백만원",
                "trading_value_unit_confirmed": False,
                "trading_value_krw": None,
                "trading_value_quality": "missing",
                "listed_market_cap_screen": None,
                "source_span": "naver_fchart_KPI200",
                "source": "Naver fchart KPI200",
                "collected_at": collected_at,
                "provider_published_at": "unknown",
                "quality": "observed",
                "reconciled_to": (
                    "KRX index_kospi200 workbook OHLC and volume on every overlapping day"
                ),
            }
        )
    merged = sorted(rows + added, key=lambda row: row["date"])
    index_doc["rows"] = merged
    index_doc["n"] = len(merged)
    index_doc["date_start"] = merged[0]["date"] if merged else None
    index_doc["date_end"] = merged[-1]["date"] if merged else None
    if added or "gap_fill" not in index_doc:
        index_doc["gap_fill"] = {
            "collected_at": collected_at,
            "provider_published_at": "unknown",
            "overlap_matched": len(overlap),
            "rows_added": len(added),
            "added_dates": [row["date"] for row in added],
            "trading_value_quality": "missing",
            "note_ko": (
                "겹치는 날의 시가·고가·저가·종가는 거래소 원본과 같고, 거래량은 화면 단위로 최대 1 차이이다. "
                "원본에 없는 날만 네이버 차트로 채운다. 그 날의 거래대금은 차트에 없어 결측이다. "
                "수집 시각은 이번 조회 시각이고, 과거 공개 시각은 unknown이다."
            ),
        }
    return {
        "overlap_matched": len(overlap),
        "rows_added": len(added),
        "added_dates": [row["date"] for row in added],
    }


def apply_etf_definition(etf_doc: dict[str, Any], *, collected_at: str) -> None:
    """Record per-ticker adjustment checks. Unchecked products stay unknown."""
    formula_ko = (
        "A는 네이버 fchart 종가, U는 네이버 일별시세표 종가, D는 분배락일 현금 분배금이다. "
        "확인된 분배락일에는 A_t/A_{t-1}-1 = U_t/(U_{t-1}-D)-1 이고 오차는 0.02%포인트 이내다. "
        "이 식은 현금 분배금만큼의 가격 하락을 종가 수익률에서 뺀다. "
        "조정 종가 수익률에 같은 D를 다시 더하면 D가 두 번 들어간다. "
        "같은 날 시가에서 종가까지의 수익률은 두 시세가 같다."
    )
    etf_doc["price_adjustment"] = "mixed"
    etf_doc["dividend_treatment"] = formula_ko
    etf_doc["provider_published_at"] = "unknown"
    etf_doc["definition_collected_at"] = collected_at
    etf_doc["adjustment_evidence"] = {
        "collected_at": collected_at,
        "provider_published_at": "unknown",
        "adjusted_source": "FinanceDataReader via Naver fchart",
        "unadjusted_source": "Naver daily price table OHLC",
        "krx_workbook": "not_compared",
        "formula": "A_t / A_{t-1} - 1 = U_t / (U_{t-1} - D) - 1",
        "double_count_ko": "조정 종가 수익률과 현금 분배금을 더하면 분배금이 두 번 계산된다.",
        "checked": CHECKED_ADJUSTMENT,
        "before_2024_ko": (
            "2020-01-30부터 2023-10-30까지도 두 종목 모두 분기마다 한 번만 종가 비율이 바뀐다. "
            "그 금액은 발행사 원문과 대조하지 않아 확정하지 않는다. 2019년은 비율 변화가 없어 이 식으로 확인하지 않는다."
        ),
    }
    for candidate in etf_doc.get("candidates") or []:
        candidate["strategy_target"] = False
        checked = CHECKED_ADJUSTMENT.get(candidate["ticker"])
        if checked is None:
            candidate["price_adjustment"] = "unknown"
            candidate["dividend_treatment"] = "unknown"
            candidate.pop("adjustment_checked", None)
            continue
        candidate["price_adjustment"] = checked["price_adjustment"]
        candidate["dividend_treatment"] = formula_ko
        candidate["adjustment_checked"] = checked


def audit_stored_returns(
    price_doc: dict[str, Any],
    letf_rows: list[dict[str, Any]],
    naver_tables: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Compare stored underlying returns with candle returns. Do not edit them."""
    stored: dict[str, dict[str, float]] = {}
    for row in letf_rows:
        ticker = row.get("ticker")
        if ticker in {"005930", "000660"} and row.get("underlying_day_return") is not None:
            stored.setdefault(ticker, {})[row["date"]] = float(row["underlying_day_return"])
    report: dict[str, Any] = {
        "usable_as_close_to_close_signal": False,
        "overwrite": False,
        "definition_price_file": "investor_price_levels days close divided by the previous stored close",
        "definition_letf_history": "stock_letf_history underlying_day_return, ingested as KRX FLUC_RT/100",
        "by_ticker": {},
    }
    for ticker, history in stored.items():
        days = price_doc["tickers"][ticker]["days"]
        closes = {row["date"]: float(row["close"]) for row in days}
        ordered = [row["date"] for row in days]
        sign_flips = []
        over = 0
        for index, day in enumerate(ordered):
            if day not in history or index == 0 or ordered[index - 1] not in closes:
                continue
            candle = closes[day] / closes[ordered[index - 1]] - 1
            gap = candle - history[day]
            if abs(gap) >= 0.001:
                over += 1
            if candle * history[day] < 0 and abs(candle) >= 0.001 and abs(history[day]) >= 0.001:
                item = {
                    "date": day,
                    "price_file_close_to_close": candle,
                    "letf_history_underlying_day_return": history[day],
                }
                table = (naver_tables or {}).get(ticker, {}).get(day)
                if table is not None:
                    item["naver_fluctuations_ratio"] = _number(table["fluctuationsRatio"]) / 100
                    item["naver_direction"] = table["compareToPreviousPrice"]["name"]
                    item["naver_base_price"] = _number(table["closePrice"]) - _number(
                        table["compareToPreviousClosePrice"]
                    )
                    item["previous_candle_close"] = closes[ordered[index - 1]]
                sign_flips.append(item)
        base_splits = []
        table = (naver_tables or {}).get(ticker) or {}
        table_days = sorted(table)
        for index, day in enumerate(table_days):
            if index == 0:
                continue
            close = _number(table[day]["closePrice"])
            change = _number(table[day]["compareToPreviousClosePrice"])
            previous = _number(table[table_days[index - 1]]["closePrice"])
            if abs(close - change - previous) > 1:
                base_splits.append(day)
        report["by_ticker"][ticker] = {
            "n_abs_diff_at_least_0_1pp": over,
            "sign_flips_versus_price_file": sign_flips,
            "naver_base_differs_from_previous_close": base_splits,
        }
    report["conclusion_ko"] = CONCLUSION_KO
    return report


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def update_manifest(patch: dict[str, Any], *, drop: tuple[str, ...] = ()) -> None:
    manifest = load_json(MANIFEST) if MANIFEST.is_file() else {"schema_version": "krx-price-panel-manifest-v1"}
    for key in drop:
        manifest.pop(key, None)
    manifest.update(patch)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fill(start: str = "20190102", end: str = "20261030") -> dict[str, Any]:
    collected_at = now_iso()
    index_doc = load_json(INDEX_PATH)
    etf_doc = load_json(ETF_PATH)
    report = reconcile_index_gaps(index_doc, fetch_naver_chart("KPI200", start, end), collected_at=collected_at)
    definition_at = etf_doc.get("definition_collected_at") or collected_at
    before_definition = json.dumps(etf_doc, sort_keys=True, ensure_ascii=False)
    apply_etf_definition(etf_doc, collected_at=definition_at)
    if json.dumps(etf_doc, sort_keys=True, ensure_ascii=False) != before_definition:
        apply_etf_definition(etf_doc, collected_at=collected_at)
        definition_at = collected_at
    write_json(INDEX_PATH, index_doc)
    write_json(ETF_PATH, etf_doc)
    tables = {
        code: fetch_naver_price_table(code)
        for code in ("005930", "000660")
    }
    letf_rows = [
        json.loads(line)
        for line in LETF_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audit = audit_stored_returns(load_json(PRICE_PATH), letf_rows, tables)
    audit["collected_at"] = collected_at
    audit["provider_published_at"] = "unknown"
    update_manifest(
        {
            "definition_collected_at": definition_at,
            "provider_published_at": "unknown",
            "index_gap_fill": index_doc["gap_fill"],
            "etf_price_definition": etf_doc["adjustment_evidence"],
            "return_mismatch_audit": audit,
            "signal_use_ko": SIGNAL_USE_KO,
        }
    )
    return {"collected_at": collected_at, **report, "sign_flips": {
        ticker: len(item["sign_flips_versus_price_file"])
        for ticker, item in audit["by_ticker"].items()
    }}


def reproduced_krx_returns(path: Path = CLOSE_COMPARE) -> set[tuple[str, str]]:
    """Dates whose stored return equals two consecutive snapshot KRX closes."""
    if not path.is_file():
        return set()
    doc = load_json(path)
    tolerance = float(doc.get("match_tolerance") or 0)
    found: set[tuple[str, str]] = set()
    for ticker, item in (doc.get("by_ticker") or {}).items():
        rows = item.get("rows") or []
        for prev, cur in zip(rows, rows[1:]):
            if not prev.get("krx_close") or not cur.get("krx_close"):
                continue
            reproduced = cur["krx_close"] / prev["krx_close"] - 1
            stored = cur.get("stored_underlying_day_return")
            if stored is not None and abs(reproduced - stored) <= tolerance:
                found.add((ticker, cur["date"]))
    return found


def return_quality(ticker: str, day: str, reproduced: set[tuple[str, str]]) -> str:
    """Per-row check status. A missing KRX comparison is not an exclusion."""
    if (ticker, day) in reproduced:
        return "observed_krx"
    if day < "2026-08-07":
        return "naver_candle_match_krx_close_unchecked"
    return "krx_close_unchecked"


def stamp_letf_return_quality(path: Path) -> dict[str, Any]:
    """Label each stored return. Do not change the return or the rebalance estimate."""
    reproduced = reproduced_krx_returns()
    counts: dict[str, int] = {}
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        before_return = row.get("underlying_day_return")
        before_rebalance = row.get("implied_rebalance_krw")
        row.pop("implied_rebalance_signal_quality", None)
        if row.get("ticker") in {"005930", "000660"}:
            quality = return_quality(str(row["ticker"]), str(row["date"]), reproduced)
            row["underlying_day_return_quality"] = quality
            counts[quality] = counts.get(quality, 0) + 1
        if row.get("underlying_day_return") != before_return or row.get("implied_rebalance_krw") != before_rebalance:
            raise RuntimeError("quality stamp changed a stored number")
        out.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    text = "\n".join(out) + "\n"
    if path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return {"rows": len(out), "by_quality": counts, "reproduced_pairs": len(reproduced)}


def stamp_definition() -> dict[str, Any]:
    """Rewrite labels only. A second run does not add rows or change prices."""
    etf_doc = load_json(ETF_PATH)
    before = json.dumps(etf_doc, sort_keys=True, ensure_ascii=False)
    collected_at = etf_doc.get("definition_collected_at") or now_iso()
    apply_etf_definition(etf_doc, collected_at=collected_at)
    if json.dumps(etf_doc, sort_keys=True, ensure_ascii=False) == before:
        collected_at = etf_doc.get("definition_collected_at") or collected_at
    else:
        collected_at = now_iso()
        apply_etf_definition(etf_doc, collected_at=collected_at)
        write_json(ETF_PATH, etf_doc)
    letf_report = stamp_letf_return_quality(LETF_PATH)
    patch = {
        "definition_collected_at": collected_at,
        "provider_published_at": "unknown",
        "etf_price_definition": etf_doc["adjustment_evidence"],
        "return_source_check": {
            "collected_at": collected_at,
            "provider_published_at": "unknown",
            "request": "git history of market_microstructure_v1.json stocks[].close",
            "result": "36 consecutive pairs match the stored return for both stocks",
            "rows_changed": 0,
            "openapi_stk_bydd_trd_20261023": "401 Unauthorized, not retried",
            "note_ko": (
                "저장 수익률은 스냅샷 KRX 종가로 계산한 등락률과 삼성전자·SK하이닉스 연속 36쌍이 모두 같다. "
                "근거는 data/manifests/krx_close_vs_price_file_20261101.json. "
                "가격 파일 종가는 2026-09-14부터 KRX 종가와 다른 날이 많다. "
                "부호가 갈리는 날은 저장값의 오류가 아니라 종가 정의 차이다. 값은 한 행도 바꾸지 않았다."
            ),
        },
        "remaining_gaps": {
            "letf_aum": "16 rows stay null. No same-definition original was fetched. Not filled with 0.",
            "derivatives_activity": (
                "19 October 2026 dates stay missing. 15001 quotes were not substituted and gaps were not filled with 0."
            ),
        },
        "letf_return_quality": letf_report,
        "price_basis_reconciliation": {
            "file": "data/manifests/krx_close_vs_price_file_20261101.json",
            "summary_ko": (
                "KRX 종가와 가격 파일 종가는 2026-09-14부터 서로 다른 날이 많고, "
                "저장된 underlying_day_return은 KRX 종가 수익률과 36쌍 모두 일치한다."
            ),
        },
        "ui_handoff_ko": (
            "market-microstructure.js는 표시용 implied_rebalance_krw를 그대로 그린다. "
            "신호 계산은 underlying_day_return_quality가 observed_krx일 때만 한다."
        ),
        "signal_use_ko": SIGNAL_USE_KO,
    }
    current = load_json(MANIFEST) if MANIFEST.is_file() else {}
    if any(current.get(key) != value for key, value in patch.items()) or "letf_signal_exclusion" in current:
        update_manifest(patch, drop=("letf_signal_exclusion",))
    return {"collected_at": collected_at, **letf_report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fill-index-gaps", action="store_true")
    parser.add_argument("--stamp-definition", action="store_true")
    args = parser.parse_args()
    if args.stamp_definition:
        print(json.dumps(stamp_definition(), ensure_ascii=False))
        return
    if args.fill_index_gaps:
        print(json.dumps(fill(), ensure_ascii=False))
        return
    parser.error("pass --fill-index-gaps or --stamp-definition")


if __name__ == "__main__":
    main()
