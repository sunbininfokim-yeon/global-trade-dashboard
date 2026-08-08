"""Public KR extras that do NOT require broker disclosure.

Sources:
  - Naver finance: 고객예탁금·신용잔고 (억원), KOSPI 투자자별 순매수
  - FDR ETF listing: 레버/인버스를 지수·섹터·단일종목으로 분해
  - Short interest: pykrx / optional KRX_API (data.krx often LOGOUT since 2026-02)

Never scrape or store broker customer leverage ratios.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; market-microstructure/1.0)"}


def _eok(x: Any) -> float | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_naver_deposit_credit() -> dict[str, Any]:
    """고객예탁금·신용잔고 (단위: 억원). FreeSIS 집계의 공개 재배포."""
    url = "https://finance.naver.com/sise/sise_deposit.naver"
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    r.encoding = "euc-kr"
    tables = pd.read_html(StringIO(r.text))
    if not tables:
        raise RuntimeError("naver deposit: no tables")
    df = tables[0].copy()
    # flatten multiindex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(c) for c in tup if "Unnamed" not in str(c)).strip("_")
            for tup in df.columns.values
        ]
    df = df.dropna(how="all")
    # expect columns like 날짜, 고객예탁금, 고객예탁금.1, 신용잔고, 신용잔고.1
    date_col = [c for c in df.columns if "날짜" in str(c)][0]
    dep_cols = [c for c in df.columns if "고객예탁금" in str(c)]
    cr_cols = [c for c in df.columns if "신용잔고" in str(c)]
    row = None
    for _, r0 in df.iterrows():
        if _eok(r0.get(dep_cols[0] if dep_cols else None)) is not None:
            row = r0
            break
    if row is None:
        raise RuntimeError("naver deposit: no numeric row")

    deposit = _eok(row[dep_cols[0]]) if dep_cols else None
    deposit_chg = _eok(row[dep_cols[1]]) if len(dep_cols) > 1 else None
    credit = _eok(row[cr_cols[0]]) if cr_cols else None
    credit_chg = _eok(row[cr_cols[1]]) if len(cr_cols) > 1 else None
    as_of_raw = str(row[date_col])
    # 26.08.05 -> 2026-08-05
    as_of = None
    try:
        parts = as_of_raw.replace(".", "-").split("-")
        if len(parts) == 3:
            yy, mm, dd = parts
            as_of = f"20{yy}-{mm}-{dd}" if len(yy) == 2 else f"{yy}-{mm}-{dd}"
    except Exception:  # noqa: BLE001
        as_of = as_of_raw

    # 억원 → KRW
    eok = 1e8
    return {
        "as_of": as_of,
        "unit_native": "억원",
        "investor_deposit_eok": deposit,
        "investor_deposit_chg_eok": deposit_chg,
        "investor_deposit_krw": None if deposit is None else deposit * eok,
        "credit_balance_eok": credit,
        "credit_balance_chg_eok": credit_chg,
        "credit_balance_krw": None if credit is None else credit * eok,
        "credit_over_deposit_pct": (
            None
            if not deposit or not credit or deposit <= 0
            else round(100.0 * credit / deposit, 3)
        ),
        "note_ko": (
            "네이버 증시자금(금투협 FreeSIS 계열 공개 재배포). "
            "종목별 고객 레버 아님. 미수·반대매매는 이 표에 없음."
        ),
        "quality": "observed",
        "source": url,
    }


def fetch_naver_kospi_investor_flows(*, lookback_days: int = 5) -> dict[str, Any]:
    """KOSPI 투자자별 순매수 (억원)."""
    rows_out: list[dict[str, Any]] = []
    latest = None
    for days in range(0, lookback_days + 3):
        d = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        url = (
            "https://finance.naver.com/sise/investorDealTrendDay.naver"
            f"?bizdate={d}&page=1"
        )
        r = requests.get(url, headers=UA, timeout=25)
        r.raise_for_status()
        r.encoding = "euc-kr"
        tables = pd.read_html(StringIO(r.text))
        if not tables:
            continue
        df = tables[0].copy()
        if isinstance(df.columns, pd.MultiIndex):
            # keep top-level useful names
            flat = []
            for tup in df.columns.values:
                a, b = tup[0], tup[1] if len(tup) > 1 else ""
                if a == b or str(b) == "nan":
                    flat.append(str(a))
                elif a in ("기관",) and b:
                    flat.append(f"{a}_{b}")
                else:
                    flat.append(str(a) if a in ("날짜", "개인", "외국인", "기관계", "기타법인") else f"{a}_{b}")
            df.columns = flat
        df = df.dropna(subset=[c for c in df.columns if "날짜" in str(c)][:1] or [df.columns[0]])
        date_col = [c for c in df.columns if "날짜" in str(c)][0]
        for _, row in df.iterrows():
            retail = _eok(row.get("개인"))
            foreign = _eok(row.get("외국인"))
            inst = _eok(row.get("기관계"))
            if retail is None and foreign is None:
                continue
            rec = {
                "date_raw": str(row[date_col]),
                "retail_net_eok": retail,
                "foreign_net_eok": foreign,
                "institution_net_eok": inst,
                "retail_net_krw": None if retail is None else retail * 1e8,
                "foreign_net_krw": None if foreign is None else foreign * 1e8,
                "institution_net_krw": None if inst is None else inst * 1e8,
            }
            rows_out.append(rec)
            if latest is None:
                latest = rec
        if latest is not None:
            break

    return {
        "scope": "kospi_cash",
        "unit_native": "억원",
        "latest": latest,
        "history": rows_out[:10],
        "quality": "observed" if latest else "missing",
        "source": "https://finance.naver.com/sise/investorDealTrendDay.naver",
        "note_ko": "코스피 시장 전체 투자자별 순매수. 단일종목 수급과 별도.",
    }


def classify_letf_name(name: str) -> str:
    n = str(name)
    if "단일종목" in n:
        return "single_stock"
    if any(k in n for k in ("반도체", "2차전지", "바이오", "은행", "증권", "건설", "자동차", "IT", "헬스케어")):
        return "sector"
    if any(k in n for k in ("나스닥", "필라델피아", "미국", "중국", "일본", "홍콩", "대만", "인도")):
        return "overseas"
    if any(k in n for k in ("코스닥", "코스피", "200", "레버리지", "인버스", "선물")):
        return "index"
    return "other_levered"


def fetch_letf_category_share() -> dict[str, Any]:
    """레버·인버스 ETF 거래대금·AUM을 카테고리별로 분해."""
    import FinanceDataReader as fdr

    etfs = fdr.StockListing("ETF/KR")
    kospi = fdr.StockListing("KOSPI")
    unit = 1_000_000.0  # ETF Amount = 백만원
    lev = etfs[etfs["Name"].astype(str).str.contains("레버리지|인버스", na=False)].copy()
    lev["category"] = lev["Name"].map(classify_letf_name)

    kospi_tv = float(kospi["Amount"].sum())
    by_cat: dict[str, dict[str, float]] = {}
    for cat, g in lev.groupby("category"):
        tv = float(g["Amount"].sum()) * unit
        # MarCap often 0 on FDR for new listings; still report Amount
        aum = float(g["MarCap"].sum()) * unit if "MarCap" in g.columns else 0.0
        by_cat[str(cat)] = {
            "n_products": int(len(g)),
            "trading_value_krw": tv,
            "trading_value_jo": round(tv / 1e12, 3),
            "aum_proxy_krw": aum,
            "share_of_lev_tv_pct": None,  # fill below
            "share_of_kospi_tv_pct": round(100.0 * tv / kospi_tv, 3) if kospi_tv else None,
        }
    lev_tv = sum(v["trading_value_krw"] for v in by_cat.values())
    for v in by_cat.values():
        v["share_of_lev_tv_pct"] = (
            round(100.0 * v["trading_value_krw"] / lev_tv, 2) if lev_tv else None
        )

    top = (
        lev.sort_values("Amount", ascending=False)
        .head(8)[["Symbol", "Name", "Amount", "category"]]
        .assign(
            trading_value_krw=lambda d: d["Amount"] * unit,
            trading_value_jo=lambda d: (d["Amount"] * unit / 1e12).round(3),
        )
    )
    top_rows = [
        {
            "ticker": str(r["Symbol"]),
            "name": str(r["Name"]),
            "category": str(r["category"]),
            "trading_value_jo": float(r["trading_value_jo"]),
        }
        for _, r in top.iterrows()
    ]

    return {
        "kospi_cash_tv_krw": kospi_tv,
        "kospi_cash_tv_jo": round(kospi_tv / 1e12, 2),
        "levered_inverse_tv_krw": lev_tv,
        "levered_inverse_tv_jo": round(lev_tv / 1e12, 2),
        "by_category": by_cat,
        "top_products_by_tv": top_rows,
        "quality": "observed",
        "source": "FinanceDataReader ETF/KR Amount(백만원) + Name classify",
        "note_ko": (
            "지수/섹터 레버는 단일종목 wag-the-dog 분모와 다름. "
            "카테고리 비중은 거래대금 기준."
        ),
    }


def fetch_short_interest(tickers: list[str]) -> dict[str, Any]:
    """종목별 공매도 잔고 시도. KRX 웹 로그인 이슈 시 missing."""
    out: dict[str, Any] = {
        "by_ticker": {},
        "quality": "missing",
        "source": None,
        "note_ko": (
            "data.krx 비회원 LOGOUT(2026-02~)으로 pykrx 공매도 다수 실패. "
            "KRX_API 공매도 엔드포인트 이용신청 또는 data.krx 로그인 필요."
        ),
    }

    # 1) optional OpenAPI — probe known-ish endpoints without hardcoding secrets
    try:
        from market_microstructure.krx_client import get_krx_api_key, krx_get, _bas_dd

        get_krx_api_key()
        bas = _bas_dd()
        for cat, ep in (
            ("sto", "srt_bydd_trd"),
            ("sto", "short_bydd_trd"),
            ("sto", "srtsl_bydd_trd"),
        ):
            try:
                rows = krx_get(cat, ep, bas)
                if rows:
                    out["source"] = f"KRX OpenAPI {cat}/{ep}"
                    out["quality"] = "observed"
                    out["note_ko"] = "KRX OpenAPI short endpoint"
                    # best-effort map — field names vary by endpoint
                    want = set(tickers)
                    for row in rows:
                        code = str(
                            row.get("isuSrtCd")
                            or row.get("ISU_SRT_CD")
                            or row.get("isuCd")
                            or ""
                        )
                        if code not in want:
                            continue
                        bal = _eok(
                            row.get("srtslBalQty")
                            or row.get("shortBal")
                            or row.get("balQty")
                        )
                        ratio = _eok(
                            row.get("srtslBalRto")
                            or row.get("shortRto")
                            or row.get("balRto")
                        )
                        out["by_ticker"][code] = {
                            "short_interest_shares": bal,
                            "short_ratio_pct": ratio,
                            "raw": {k: row[k] for k in list(row)[:12]},
                        }
                    if out["by_ticker"]:
                        return out
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass

    # 2) pykrx (often empty/LOGOUT)
    try:
        from pykrx import stock

        end = datetime.now()
        for back in range(1, 10):
            d = (end - timedelta(days=back)).strftime("%Y%m%d")
            got_any = False
            for code in tickers:
                try:
                    df = stock.get_shorting_balance_by_date(d, d, code)
                except Exception:  # noqa: BLE001
                    df = None
                if df is None or len(df) == 0:
                    continue
                last = df.iloc[-1]
                # columns: 공매도잔고, 상장주식수, 공매도금액, 시가총액, 비중
                shares = _eok(last.get("공매도잔고") if hasattr(last, "get") else last[0])
                ratio = None
                for key in ("비중", "공매도비중"):
                    if hasattr(last, "index") and key in last.index:
                        ratio = _eok(last[key])
                        break
                out["by_ticker"][code] = {
                    "short_interest_shares": shares,
                    "short_ratio_pct": ratio,
                    "as_of": d,
                }
                got_any = True
            if got_any:
                out["quality"] = "observed"
                out["source"] = f"pykrx get_shorting_balance_by_date @{d}"
                out["note_ko"] = "pykrx 공매도 잔고"
                return out
    except Exception as e:  # noqa: BLE001
        out["note_ko"] = f"pykrx short failed: {type(e).__name__}: {e}"

    return out


def build_public_extras(tickers: list[str] | None = None) -> dict[str, Any]:
    tickers = tickers or ["000660", "005930"]
    deposit = None
    flows = None
    cats = None
    shorts = None
    errors: list[str] = []

    try:
        deposit = fetch_naver_deposit_credit()
    except Exception as e:  # noqa: BLE001
        errors.append(f"deposit: {type(e).__name__}: {e}")
    try:
        flows = fetch_naver_kospi_investor_flows()
    except Exception as e:  # noqa: BLE001
        errors.append(f"flows: {type(e).__name__}: {e}")
    try:
        cats = fetch_letf_category_share()
    except Exception as e:  # noqa: BLE001
        errors.append(f"letf_cat: {type(e).__name__}: {e}")
    try:
        shorts = fetch_short_interest(tickers)
    except Exception as e:  # noqa: BLE001
        errors.append(f"short: {type(e).__name__}: {e}")
        shorts = {
            "by_ticker": {},
            "quality": "missing",
            "source": None,
            "note_ko": str(e),
        }

    return {
        "fetched_at": datetime.now().astimezone().isoformat(),
        "deposit_credit": deposit,
        "kospi_investor_flows": flows,
        "letf_category_share": cats,
        "short_interest": shorts,
        "errors": errors,
        "excluded_ko": "증권사 고객 레버리지 비율(비공시) · 딜러 감마 장부",
    }
