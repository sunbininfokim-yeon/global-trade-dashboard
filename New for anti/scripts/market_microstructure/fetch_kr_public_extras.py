"""Public Korean market extras used by the microstructure snapshot.

This module deliberately contains market-wide public aggregates only.  It does
not infer broker-client leverage, dealer gamma, or an investor's derivative
position.  FreeSIS is preferred for deposit/credit because it also publishes
uncollected receivables and forced-sale statistics; Naver is a narrow fallback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

import pandas as pd
import requests

from fetch_freesis_credit import fetch_freesis_funding_credit

UA = {"User-Agent": "Mozilla/5.0 (compatible; market-microstructure/1.0)"}


def _num(value: Any) -> float | None:
    """Parse a public table value without turning missing values into zero."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip().replace(",", "").replace("+", "")
        if text in {"", "-", "nan", "None"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _iso_date(raw: Any) -> str | None:
    text = str(raw or "").strip()
    parts = text.replace(".", "-").replace("/", "-").split("-")
    if len(parts) != 3 or not all(parts):
        return None
    year, month, day = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except ValueError:
        return None


def fetch_naver_deposit_credit() -> dict[str, Any]:
    """Fallback: market-wide investor deposit and margin-credit balance only."""
    url = "https://finance.naver.com/sise/sise_deposit.naver"
    response = requests.get(url, headers=UA, timeout=25)
    response.raise_for_status()
    response.encoding = "euc-kr"
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise RuntimeError("Naver deposit table is empty")
    frame = tables[0].copy().dropna(how="all")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [
            "_".join(str(part) for part in col if "Unnamed" not in str(part)).strip("_")
            for col in frame.columns.values
        ]
    date_cols = [col for col in frame.columns if "날짜" in str(col)]
    deposit_cols = [col for col in frame.columns if "고객예탁금" in str(col)]
    credit_cols = [col for col in frame.columns if "신용잔고" in str(col)]
    if not date_cols or not deposit_cols or not credit_cols:
        raise RuntimeError("Naver deposit columns changed")
    row = next((r for _, r in frame.iterrows() if _num(r.get(deposit_cols[0])) is not None), None)
    if row is None:
        raise RuntimeError("Naver deposit has no numeric row")
    deposit = _num(row.get(deposit_cols[0]))
    credit = _num(row.get(credit_cols[0]))
    return {
        "as_of": _iso_date(row.get(date_cols[0])) or str(row.get(date_cols[0])),
        "unit_native": "억원",
        "investor_deposit_eok": deposit,
        "investor_deposit_chg_eok": _num(row.get(deposit_cols[1])) if len(deposit_cols) > 1 else None,
        "investor_deposit_krw": None if deposit is None else deposit * 1e8,
        "credit_balance_eok": credit,
        "credit_balance_chg_eok": _num(row.get(credit_cols[1])) if len(credit_cols) > 1 else None,
        "credit_balance_krw": None if credit is None else credit * 1e8,
        "credit_over_deposit_pct": None if not deposit or credit is None else round(100 * credit / deposit, 3),
        "quality": "observed",
        "source": url,
        "note_ko": "시장 전체 예탁금·신용잔고 공개 집계. 미수·반대매매는 FreeSIS 연결 시에만 제공.",
    }


def fetch_naver_kospi_investor_flows(*, lookback_days: int = 8) -> dict[str, Any]:
    """KOSPI cash-market investor net flow; never substitute it for positions."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset in range(lookback_days + 5):
        day = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={day}&page=1"
        try:
            response = requests.get(url, headers=UA, timeout=25)
            response.raise_for_status()
            response.encoding = "euc-kr"
            tables = pd.read_html(StringIO(response.text))
        except Exception:  # noqa: BLE001
            continue
        if not tables:
            continue
        frame = tables[0].copy()
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [str(col[0]) for col in frame.columns.values]
        date_cols = [col for col in frame.columns if "날짜" in str(col)]
        if not date_cols:
            continue
        for _, row in frame.iterrows():
            raw = str(row.get(date_cols[0]) or "").strip()
            if not raw or raw in seen:
                continue
            retail = _num(row.get("개인"))
            foreign = _num(row.get("외국인"))
            institution = _num(row.get("기관계"))
            if retail is None and foreign is None and institution is None:
                continue
            seen.add(raw)
            records.append({
                "date_raw": raw,
                "observed_as_of": _iso_date(raw),
                "retail_net_eok": retail,
                "foreign_net_eok": foreign,
                "institution_net_eok": institution,
                "retail_net_krw": None if retail is None else retail * 1e8,
                "foreign_net_krw": None if foreign is None else foreign * 1e8,
                "institution_net_krw": None if institution is None else institution * 1e8,
            })
        if len(records) >= lookback_days:
            break
    records.sort(key=lambda item: item.get("observed_as_of") or item["date_raw"], reverse=True)
    return {
        "scope": "kospi_cash",
        "unit_native": "억원",
        "latest": records[0] if records else None,
        "history": records[:lookback_days],
        "quality": "observed" if records else "missing",
        "source": "https://finance.naver.com/sise/investorDealTrendDay.naver",
        "note_ko": "코스피 시장 전체 투자자별 순매수. 보유 포지션·종목별 체결·파생 수급이 아님.",
    }


def classify_letf_name(name: str) -> str:
    text = str(name)
    if "단일종목" in text:
        return "single_stock"
    if any(token in text for token in ("반도체", "2차전지", "바이오", "은행", "증권", "건설", "자동차", "IT", "헬스케어")):
        return "sector"
    if any(token in text for token in ("나스닥", "필라델피아", "미국", "중국", "일본", "홍콩", "대만", "인도")):
        return "overseas"
    if any(token in text for token in ("코스닥", "코스피", "200", "레버리지", "인버스", "선물", "곱버스")):
        return "index"
    return "other_levered"


def classify_letf_direction(name: str) -> str:
    """Keep single-stock inverse 2x separate from index '곱버스'."""
    text = str(name)
    inverse = any(token in text.upper() for token in ("인버스", "INVERSE", "곱버스", "(-2", "(-1"))
    two_x = any(token in text.upper() for token in ("2X", "2배", "곱버스", "(-2"))
    if inverse and two_x:
        return "inverse_2x" if "단일종목" in text else "gobus_inverse_2x"
    if inverse:
        return "inverse"
    if "레버리지" in text:
        return "long"
    return "other"


def fetch_letf_category_share() -> dict[str, Any]:
    """Observed ETF turnover split by category and direction, not client leverage."""
    import FinanceDataReader as fdr

    etfs = fdr.StockListing("ETF/KR")
    kospi = fdr.StockListing("KOSPI")
    unit = 1_000_000.0  # FDR ETF Amount/MarCap are in KRW million units.
    lev = etfs[etfs["Name"].astype(str).str.contains("레버리지|인버스|곱버스", na=False)].copy()
    lev["category"] = lev["Name"].map(classify_letf_name)
    lev["direction"] = lev["Name"].map(classify_letf_direction)
    cash_tv = float(kospi["Amount"].sum())
    lev_tv = float(lev["Amount"].sum()) * unit

    def summarize(frame: pd.DataFrame) -> dict[str, Any]:
        tv = float(frame["Amount"].sum()) * unit
        aum = float(frame["MarCap"].sum()) * unit if "MarCap" in frame else None
        return {
            "n_products": int(len(frame)),
            "trading_value_krw": tv,
            "trading_value_jo": round(tv / 1e12, 3),
            "aum_proxy_krw": aum,
            "share_of_lev_tv_pct": None if not lev_tv else round(100 * tv / lev_tv, 2),
            "share_of_kospi_tv_pct": None if not cash_tv else round(100 * tv / cash_tv, 3),
        }

    by_category = {str(key): summarize(group) for key, group in lev.groupby("category")}
    by_direction = {str(key): summarize(group) for key, group in lev.groupby("direction")}
    inverse = lev[lev["direction"].isin(["inverse", "inverse_2x", "gobus_inverse_2x"])]
    long = lev[lev["direction"] == "long"]
    gobus = lev[lev["direction"] == "gobus_inverse_2x"]

    def top_rows(frame: pd.DataFrame, n: int) -> list[dict[str, Any]]:
        if frame.empty:
            return []
        return [{
            "ticker": str(row["Symbol"]), "name": str(row["Name"]),
            "category": str(row["category"]), "direction": str(row["direction"]),
            "trading_value_jo": round(float(row["Amount"]) * unit / 1e12, 6),
        } for _, row in frame.sort_values("Amount", ascending=False).head(n).iterrows()]

    inv_tv = float(inverse["Amount"].sum()) * unit
    long_tv = float(long["Amount"].sum()) * unit
    gobus_tv = float(gobus["Amount"].sum()) * unit
    return {
        "kospi_cash_tv_krw": cash_tv,
        "kospi_cash_tv_jo": round(cash_tv / 1e12, 2),
        "levered_inverse_tv_krw": lev_tv,
        "levered_inverse_tv_jo": round(lev_tv / 1e12, 2),
        "long_tv_krw": long_tv, "long_tv_jo": round(long_tv / 1e12, 3),
        "inverse_tv_krw": inv_tv, "inverse_tv_jo": round(inv_tv / 1e12, 3),
        "gobus_tv_krw": gobus_tv, "gobus_tv_jo": round(gobus_tv / 1e12, 3),
        "inverse_share_of_lev_tv_pct": None if not lev_tv else round(100 * inv_tv / lev_tv, 2),
        "by_category": by_category, "by_direction": by_direction,
        "top_products_by_tv": top_rows(lev, 12),
        "top_inverse_gobus_by_tv": top_rows(inverse, 8),
        "quality": "observed",
        "source": "FinanceDataReader ETF/KR Amount(백만원) + Name classify",
        "note_ko": "레버·인버스 ETF 거래대금 분해. 지수/섹터 비중은 단일종목 현물 회전율과 합산하지 않음.",
    }


def fetch_short_interest(tickers: list[str]) -> dict[str, Any]:
    """Best-effort public short balance; missing is an honest outcome."""
    out: dict[str, Any] = {
        "by_ticker": {}, "quality": "missing", "source": None,
        "note_ko": "공매도 잔고는 data.krx 로그인/이용신청 상태에 따라 missing일 수 있음.",
    }
    try:
        from pykrx import stock
    except Exception:  # noqa: BLE001
        return out
    for back in range(1, 10):
        day = (datetime.now() - timedelta(days=back)).strftime("%Y%m%d")
        found = False
        for ticker in tickers:
            try:
                frame = stock.get_shorting_balance_by_date(day, day, ticker)
            except Exception:  # noqa: BLE001
                continue
            if frame is None or frame.empty:
                continue
            row = frame.iloc[-1]
            shares = _num(row.get("공매도잔고"))
            ratio = _num(row.get("비중")) if "비중" in row.index else _num(row.get("공매도비중"))
            out["by_ticker"][ticker] = {"short_interest_shares": shares, "short_ratio_pct": ratio, "as_of": day}
            found = True
        if found:
            out.update({"quality": "observed", "source": f"pykrx short balance @{day}"})
            return out
    return out


def fetch_deposit_credit() -> dict[str, Any]:
    """Prefer FreeSIS; retain the narrow Naver fallback with explicit quality."""
    try:
        data = fetch_freesis_funding_credit()
        if data.get("quality") == "observed":
            data["source_mode"] = "freesis"
            return data
    except Exception as exc:  # noqa: BLE001
        freesis_error = f"{type(exc).__name__}: {exc}"
    else:
        freesis_error = "FreeSIS returned missing"
    fallback = fetch_naver_deposit_credit()
    fallback["source_mode"] = "naver_fallback"
    fallback["staleness_reason"] = freesis_error
    return fallback


def build_public_extras(tickers: list[str] | None = None) -> dict[str, Any]:
    """Assemble independent public sources; one failed source must not kill D&S."""
    tickers = tickers or ["000660", "005930"]
    errors: list[str] = []

    def collect(label: str, func, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            return default

    deposit = collect("deposit_credit", fetch_deposit_credit, None)
    flows = collect("kospi_flows", fetch_naver_kospi_investor_flows, {"quality": "missing"})
    categories = collect("letf_category", fetch_letf_category_share, {"quality": "missing"})
    shorts = collect("short_interest", lambda: fetch_short_interest(tickers), {"quality": "missing", "by_ticker": {}})
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "deposit_credit": deposit,
        "kospi_investor_flows": flows,
        "letf_category_share": categories,
        "short_interest": shorts,
        "errors": errors,
        "excluded_ko": "증권사 고객 레버리지 비율(비공시) · 딜러 감마 장부",
    }


__all__ = [
    "build_public_extras", "classify_letf_direction", "classify_letf_name",
    "fetch_deposit_credit", "fetch_freesis_funding_credit", "fetch_letf_category_share",
    "fetch_naver_deposit_credit", "fetch_naver_kospi_investor_flows", "fetch_short_interest",
]
