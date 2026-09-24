"""Public KR market extras used by the microstructure snapshot.

The inputs are aggregate public observations, not broker account positions:

* FreeSIS: deposit, margin-credit, uncollected and forced-sale aggregates;
* Naver Finance: KOSPI investor net-flow aggregate;
* FinanceDataReader: listed ETF and KOSPI daily turnover.

Every collector can fail independently.  ``build_public_extras`` preserves
that fact as a missing block plus an error; it must never substitute a demo
number, because these values feed the turnover-history charts.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import pandas as pd
import requests

from fetch_freesis_credit import fetch_freesis_funding_credit

UA = {"User-Agent": "Mozilla/5.0 (compatible; market-microstructure/1.0)"}


def _number(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def classify_letf_name(name: str) -> str:
    """Classify ETF names without pretending the class is a position direction."""
    text = str(name)
    if "단일종목" in text:
        return "single_stock"
    if any(word in text for word in ("반도체", "2차전지", "바이오", "은행", "증권", "건설", "자동차", "IT", "헬스케어")):
        return "sector"
    if any(word in text for word in ("나스닥", "필라델피아", "미국", "중국", "일본", "홍콩", "대만", "인도")):
        return "overseas"
    if any(word in text for word in ("코스닥", "코스피", "200", "레버리지", "인버스", "선물", "곱버스")):
        return "index"
    return "other_levered"


def classify_letf_direction(name: str) -> str:
    """Map the disclosed product name to the UI's four turnover buckets."""
    text = str(name)
    upper = text.upper()
    single_stock = "단일종목" in text
    inverse = "인버스" in text or "INVERSE" in upper or "곱버스" in text or "(-" in text
    two_x = "2X" in upper or "2배" in text or "곱버스" in text or "(-2" in text
    if inverse and two_x:
        return "inverse_2x" if single_stock else "gobus_inverse_2x"
    if inverse:
        return "inverse"
    if "레버리지" in text:
        return "long"
    return "other"


def _amount_krw(frame: Any, column: str, *, multiplier: float) -> float:
    return float(frame[column].fillna(0).astype(float).sum()) * multiplier


def fetch_letf_category_share() -> dict[str, Any]:
    """Observed turnover split, with both pool and KOSPI-cash denominators."""
    import FinanceDataReader as fdr

    etfs = fdr.StockListing("ETF/KR")
    kospi = fdr.StockListing("KOSPI")
    required = {"Name", "Amount", "MarCap", "Symbol"}
    missing = required.difference(etfs.columns)
    if missing or "Amount" not in kospi.columns:
        raise RuntimeError(f"FDR listing missing columns: ETF={sorted(missing)}, KOSPI Amount={'Amount' in kospi.columns}")

    # FDR's ETF Amount and MarCap are published in 백만원; KOSPI Amount is KRW.
    etf_unit = 1_000_000.0
    cash_tv = _amount_krw(kospi, "Amount", multiplier=1.0)
    names = etfs["Name"].astype(str)
    levered = etfs.loc[names.str.contains("레버리지|인버스|곱버스", na=False)].copy()
    if levered.empty:
        raise RuntimeError("FDR ETF/KR yielded no levered or inverse products")
    levered["category"] = levered["Name"].map(classify_letf_name)
    levered["direction"] = levered["Name"].map(classify_letf_direction)

    total_tv = _amount_krw(levered, "Amount", multiplier=etf_unit)
    # A zero aggregate is not a quiet "no activity" observation here.  This
    # source is a live FDR listing (rather than an as-of KRX EOD endpoint),
    # and it has on occasion returned an all-zero Amount column before the
    # trading-day listing was published.  Recording that as observed creates
    # a false deleveraging signal and poisons the history series.
    if cash_tv <= 0 or total_tv <= 0:
        raise RuntimeError(
            "FDR listing returned non-positive turnover "
            f"(KOSPI={cash_tv}, levered/inverse ETF={total_tv}); "
            "treating LETF category data as unavailable"
        )

    def group_rows(column: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for group, rows in levered.groupby(column):
            trading_value = _amount_krw(rows, "Amount", multiplier=etf_unit)
            aum_proxy = _amount_krw(rows, "MarCap", multiplier=etf_unit)
            out[str(group)] = {
                "n_products": int(len(rows)),
                "trading_value_krw": trading_value,
                "trading_value_jo": round(trading_value / 1e12, 3),
                "aum_proxy_krw": aum_proxy,
                "share_of_lev_tv_pct": round(100.0 * trading_value / total_tv, 2) if total_tv else None,
                "share_of_kospi_tv_pct": round(100.0 * trading_value / cash_tv, 3) if cash_tv else None,
            }
        return out

    by_category = group_rows("category")
    by_direction = group_rows("direction")
    # The chart contract has four fixed directions.  A genuinely empty bucket
    # is an observed zero, not a missing field and not an interpolated value.
    for direction in ("long", "inverse", "inverse_2x", "gobus_inverse_2x"):
        by_direction.setdefault(
            direction,
            {
                "n_products": 0,
                "trading_value_krw": 0.0,
                "trading_value_jo": 0.0,
                "aum_proxy_krw": 0.0,
                "share_of_lev_tv_pct": 0.0,
                "share_of_kospi_tv_pct": 0.0,
            },
        )
    inverse_keys = {"inverse", "inverse_2x", "gobus_inverse_2x"}
    inverse = levered.loc[levered["direction"].isin(inverse_keys)]
    long = levered.loc[levered["direction"] == "long"]
    gobus = levered.loc[levered["direction"] == "gobus_inverse_2x"]

    def products(frame: Any) -> list[dict[str, Any]]:
        rows = frame.sort_values("Amount", ascending=False).head(12)
        return [
            {
                "ticker": str(row["Symbol"]),
                "name": str(row["Name"]),
                "category": str(row["category"]),
                "direction": str(row["direction"]),
                "trading_value_jo": round(float(row["Amount"]) * etf_unit / 1e12, 6),
            }
            for _, row in rows.iterrows()
        ]

    long_tv = _amount_krw(long, "Amount", multiplier=etf_unit)
    inverse_tv = _amount_krw(inverse, "Amount", multiplier=etf_unit)
    gobus_tv = _amount_krw(gobus, "Amount", multiplier=etf_unit)
    return {
        "kospi_cash_tv_krw": cash_tv,
        "kospi_cash_tv_jo": round(cash_tv / 1e12, 2),
        "levered_inverse_tv_krw": total_tv,
        "levered_inverse_tv_jo": round(total_tv / 1e12, 2),
        "long_tv_krw": long_tv,
        "long_tv_jo": round(long_tv / 1e12, 3),
        "inverse_tv_krw": inverse_tv,
        "inverse_tv_jo": round(inverse_tv / 1e12, 3),
        "gobus_tv_krw": gobus_tv,
        "gobus_tv_jo": round(gobus_tv / 1e12, 3),
        "inverse_share_of_lev_tv_pct": round(100.0 * inverse_tv / total_tv, 2) if total_tv else None,
        "by_category": by_category,
        "by_direction": by_direction,
        "top_products_by_tv": products(levered),
        "top_inverse_gobus_by_tv": products(inverse),
        "quality": "observed",
        "source": "FinanceDataReader ETF/KR Amount(백만원) + KOSPI Amount(KRW) + Name classify",
        "note_ko": (
            "이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. "
            "방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다."
        ),
    }


def fetch_naver_kospi_investor_flows(*, lookback_days: int = 7) -> dict[str, Any]:
    """KOSPI aggregate investor net flows in 억원: Naver, else KRX 12008.

    The Naver page has returned an empty table since 2026-09-17. When it
    does, and a krx-month-paste checkout is named in $KRX_MONTH_PASTE_DIR,
    the latest KRX 12008 days are used instead -- labelled as such, since
    12008 counts ETF/ETN trades that the stock-only Naver page does not.
    """
    try:
        naver = _fetch_naver_kospi_investor_flows(lookback_days=lookback_days)
    except Exception:  # noqa: BLE001
        naver = None
    if naver and naver.get("history"):
        return naver
    root = os.environ.get("KRX_MONTH_PASTE_DIR")
    if root:
        from market_microstructure.investor_price_levels import (
            KRX_12008_SCOPE_KO,
            KRX_12008_SOURCE,
            load_krx_12008_kospi_flows,
        )

        frame = load_krx_12008_kospi_flows(root)
        if not frame.empty:
            history = []
            for day, row in frame.tail(10).iloc[::-1].iterrows():
                vals = {k: (None if pd.isna(row[k]) else float(row[k]))
                        for k in ("retail_net_eok", "foreign_net_eok", "institution_net_eok")}
                history.append({
                    "date_raw": day.strftime("%y.%m.%d"),
                    **vals,
                    **{k.replace("_eok", "_krw"): (None if v is None else v * 1e8) for k, v in vals.items()},
                })
            return {
                "scope": "kospi_all_securities",
                "unit_native": "억원",
                "latest": history[0],
                "history": history,
                "quality": "observed",
                "source": KRX_12008_SOURCE,
                "note_ko": KRX_12008_SCOPE_KO,
            }
    if naver is not None:
        return naver
    raise RuntimeError("KOSPI investor flows: Naver empty and no KRX 12008 checkout")


def _fetch_naver_kospi_investor_flows(*, lookback_days: int = 7) -> dict[str, Any]:
    """Best-effort KOSPI aggregate investor net flows, reported in 억원."""
    history: list[dict[str, Any]] = []
    for offset in range(lookback_days):
        target = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={target}&page=1"
        response = requests.get(url, headers=UA, timeout=25)
        response.raise_for_status()
        response.encoding = "euc-kr"
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            continue
        frame = tables[0].dropna(how="all")
        if frame.empty:
            continue
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [str(column[0]) for column in frame.columns]
        date_column = next((column for column in frame.columns if "날짜" in str(column)), None)
        if date_column is None:
            continue
        for _, row in frame.iterrows():
            retail = _number(row.get("개인"))
            foreign = _number(row.get("외국인"))
            institution = _number(row.get("기관계"))
            if retail is None and foreign is None and institution is None:
                continue
            history.append(
                {
                    "date_raw": str(row[date_column]),
                    "retail_net_eok": retail,
                    "foreign_net_eok": foreign,
                    "institution_net_eok": institution,
                    "retail_net_krw": None if retail is None else retail * 1e8,
                    "foreign_net_krw": None if foreign is None else foreign * 1e8,
                    "institution_net_krw": None if institution is None else institution * 1e8,
                }
            )
        if history:
            break
    return {
        "scope": "kospi_cash",
        "unit_native": "억원",
        "latest": history[0] if history else None,
        "history": history[:10],
        "quality": "observed" if history else "missing",
        "source": "https://finance.naver.com/sise/investorDealTrendDay.naver",
        "note_ko": "코스피 시장 전체 투자자별 순매수. 종목별 수급과 별도.",
    }


def _missing_shorts() -> dict[str, Any]:
    return {
        "by_ticker": {},
        "quality": "missing",
        "source": None,
        "note_ko": "공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다.",
    }


def build_public_extras(tickers: list[str] | None = None) -> dict[str, Any]:
    """Collect independent public blocks and preserve each block's failure."""
    del tickers  # reserved for a future authenticated short-interest collector
    errors: list[str] = []
    blocks: dict[str, Any] = {
        "deposit_credit": None,
        "kospi_investor_flows": None,
        "letf_category_share": None,
        "short_interest": _missing_shorts(),
    }
    for key, fetch in (
        ("deposit_credit", fetch_freesis_funding_credit),
        ("kospi_investor_flows", fetch_naver_kospi_investor_flows),
        ("letf_category_share", fetch_letf_category_share),
    ):
        try:
            blocks[key] = fetch()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
    return {
        "fetched_at": datetime.now().astimezone().isoformat(),
        **blocks,
        "errors": errors,
        "excluded_ko": "증권사 고객 레버리지 비율(비공시) · 딜러 감마 장부",
    }


__all__ = [
    "build_public_extras",
    "classify_letf_direction",
    "classify_letf_name",
    "fetch_freesis_funding_credit",
    "fetch_letf_category_share",
    "fetch_naver_kospi_investor_flows",
]
