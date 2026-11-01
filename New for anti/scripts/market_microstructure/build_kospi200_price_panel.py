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
INDEX_PATH = PUBLIC / "kospi200_index_daily_v1.json"
ETF_PATH = PUBLIC / "kospi200_etf_candidates_daily_v1.json"
LETF_PATH = PUBLIC / "stock_letf_history_v1.jsonl"
PRICE_PATH = PUBLIC / "investor_price_levels_v1.json"

NAVER_CHART = (
    "https://m.stock.naver.com/front-api/external/chart/domestic/info"
    "?symbol={symbol}&requestType=1&startTime={start}&endTime={end}&timeframe=day"
)
NAVER_PRICE = "https://m.stock.naver.com/api/stock/{code}/price?pageSize=40&page={page}"

# Samsung Kodex notice, 2024-10-29: KODEX 200 ex-date 2024-10-30, 120 won.
# The close-to-close residual versus the KOSPI200 index on that date is a few
# won, not the cash distribution. Naver fchart is therefore the adjusted series.
KODEX_EX_DATE = {
    "ticker": "069500",
    "ex_date": "2024-10-30",
    "distribution_krw": 120,
    "source": "Samsung Kodex notice, 2024-10-29, KODEX 200 distribution schedule",
}


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


# What was actually checked, per ticker. The chart endpoint is shared, so the
# other candidates probably behave the same, but "probably" is not a label.
ETF_VERIFICATION = {
    "069500": "issuer_notice_and_price_test",
    "102110": "price_test_only",
}
ETF_ADJUSTMENT_NOTE_KO = (
    "후보는 이름상 비레버리지 코스피200 추종 상품과 총수익(TR) 상품이다. "
    "레버리지·인버스·섹터·커버드콜은 제외했다. 어느 상품도 매매 대상으로 고정하지 않았다. "
    "FinanceDataReader 응답에는 거래대금이 없다. "
    "수정주가(분배금 제외) 여부는 KODEX 200만 발행사 공지와 가격으로 확인했고(2024-10-30, 좌당 120원), "
    "TIGER 200은 가격만 봤고 공지는 인용하지 않았다. 나머지 후보는 같은 차트 출처일 뿐 확인하지 않았다."
)


def apply_etf_definition(etf_doc: dict[str, Any], *, collected_at: str) -> None:
    """Record the verified adjustment definition without changing OHLC rows."""
    evidence = {
        "collected_at": collected_at,
        "provider_published_at": "unknown",
        "endpoint": "https://fchart.stock.naver.com/sise.nhn?timeframe=day&count=6000&requestType=0",
        "reader": "FinanceDataReader NaverDailyReader",
        "price_adjustment": "distribution_adjusted",
        "dividend_treatment": (
            "현금 분배금은 종가 수익률에 남아 있지 않다. 분배락일 전후 수익률은 코스피200 지수와 같이 움직인다."
        ),
        "checked": KODEX_EX_DATE,
        "same_endpoint_tickers": ["069500", "102110"],
        "not_individually_checked_against_issuer_notice": [
            candidate["ticker"]
            for candidate in etf_doc.get("candidates") or []
            if candidate["ticker"] not in {"069500", "102110"}
        ],
        "tradable_price_ko": (
            "같은 날 시가 대비 종가 수익률은 막대 전체에 같은 배수가 곱해지면 수정 여부와 같다. "
            "분배락일을 가로지르는 종가 수익률은 현금 분배금을 뺀 수정 수익률이다. "
            "실제 체결 가격인 미수정 시세는 이 파일에 없다."
        ),
    }
    evidence["verified_tickers"] = [
        t for t, how in ETF_VERIFICATION.items() if how == "issuer_notice_and_price_test"
    ]
    evidence["price_test_only_tickers"] = [
        t for t, how in ETF_VERIFICATION.items() if how == "price_test_only"
    ]
    etf_doc["price_adjustment"] = "see_candidates"
    etf_doc["adjustment_note_ko"] = ETF_ADJUSTMENT_NOTE_KO
    etf_doc["dividend_treatment"] = evidence["dividend_treatment"]
    etf_doc["adjustment_evidence"] = evidence
    etf_doc["definition_collected_at"] = collected_at
    for candidate in etf_doc.get("candidates") or []:
        how = ETF_VERIFICATION.get(candidate["ticker"], "not_checked")
        candidate["price_adjustment_verification"] = how
        candidate["price_adjustment"] = (
            "distribution_adjusted" if how == "issuer_notice_and_price_test"
            else "unverified_same_chart_source"
        )
        candidate["dividend_treatment"] = (
            "naver_fchart_same_endpoint"
            if candidate["ticker"] in {"069500", "102110"}
            else "same_endpoint_not_checked_against_own_issuer_notice"
        )
        candidate["strategy_target"] = False


RECONCILIATION = "data/manifests/krx_close_vs_price_file_20261101.json"
CONCLUSION_KO = (
    "가격 파일의 종가는 네이버 캔들과 같다. 저장돼 있는 underlying_day_return은 가격 파일 종가 수익률과 "
    "부호가 다른 날이 있지만, KRX 일별 시세의 종가로 계산한 등락률과는 연속한 거래일 36쌍이 모두 일치한다 "
    f"(삼성전자·SK하이닉스, 근거 {RECONCILIATION}). KRX 종가와 가격 파일 종가는 2026-09-14부터 서로 다른 날이 "
    "많다. 그래서 부호가 갈리는 날은 저장값의 오류가 아니라 두 종가의 정의 차이다. 값을 덮어쓰지 않는다. "
    "차이의 원인(거래소 통합 시세 여부 등)은 확인하지 못했다. 네이버가 발표한 등락률의 기준가격이 전일 "
    "캔들 종가와 다른 날은 종가 수익률과 발표 등락률이 서로 다른 질문이다."
)
SIGNAL_USE_KO = (
    "LETF 리밸런싱 추정이 쓰는 underlying_day_return은 KRX 종가 기준이라 그대로 유효하다. "
    "가격 파일(investor_price_levels)의 종가는 2026-09-14부터 KRX 종가와 다를 수 있으므로, 두 종가를 섞어 "
    "수익률을 만들지 않는다. LETF AUM 결측과 파생상품 활동 결측을 쓰는 전략은 보류한다. "
    "옵션 수급과 ETF 다음 날 수익률을 보는 탐색은, ETF 가격이 분배금이 빠진 수정 종가라는 전제에서만 가능하며 "
    "그 전제는 KODEX 200만 확인됐다. 탐색이 가능하다는 것은 실전 수익이 확인됐다는 뜻이 아니다."
)


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
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def update_manifest(patch: dict[str, Any]) -> None:
    manifest = load_json(MANIFEST) if MANIFEST.is_file() else {"schema_version": "krx-price-panel-manifest-v1"}
    manifest.update(patch)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fill(start: str = "20190102", end: str = "20261030") -> dict[str, Any]:
    collected_at = now_iso()
    index_doc = load_json(INDEX_PATH)
    etf_doc = load_json(ETF_PATH)
    report = reconcile_index_gaps(index_doc, fetch_naver_chart("KPI200", start, end), collected_at=collected_at)
    apply_etf_definition(etf_doc, collected_at=collected_at)
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
            "definition_collected_at": collected_at,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fill-index-gaps", action="store_true")
    args = parser.parse_args()
    if args.fill_index_gaps:
        print(json.dumps(fill(), ensure_ascii=False))
        return
    parser.error("pass --fill-index-gaps")


if __name__ == "__main__":
    main()
