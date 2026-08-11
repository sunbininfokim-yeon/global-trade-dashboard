"""KRX Data Marketplace OpenAPI client.

Auth: Cloudflare / local secret name ``KRX_API`` (Workers: ``env.KRX_API``).
Never hardcode the key. Official docs put AUTH_KEY in the request header;
query-param AUTH_KEY is also accepted by some gateways — we send both.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any

import requests

BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"

# Prefer Cloudflare/local binding name; keep legacy alias for local shells.
SECRET_NAMES = ("KRX_API", "KRX_OPENAPI_KEY")


class KRXAuthError(RuntimeError):
    pass


class KRXAPIError(RuntimeError):
    pass


def get_krx_api_key() -> str:
    for name in SECRET_NAMES:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    raise KRXAuthError(
        "Missing KRX_API (Cloudflare Variables and secrets / local env). "
        "Set export KRX_API=... or wrangler .dev.vars KRX_API=..."
    )


def _bas_dd(day: str | None = None) -> str:
    if day:
        d = day.replace("-", "")
        if not re.fullmatch(r"\d{8}", d):
            raise ValueError(f"basDd must be YYYYMMDD, got {day}")
        return d
    # KRX OpenAPI often lags 1 session; start from yesterday.
    return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")


def krx_get(category: str, endpoint: str, bas_dd: str, *, timeout: int = 45) -> list[dict[str, Any]]:
    key = get_krx_api_key()
    url = f"{BASE_URL}/{category}/{endpoint}"
    headers = {
        "AUTH_KEY": key,
        "User-Agent": "market-microstructure/1.0",
        "Accept": "application/json",
    }
    # Header is the documented path; param mirrors pykrx-openapi clients.
    params = {"basDd": bas_dd, "AUTH_KEY": key}
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    if r.status_code == 401:
        raise KRXAuthError("KRX_API rejected (401 Unauthorized) — check key + API 이용신청")
    if r.status_code == 403:
        raise KRXAuthError("KRX_API forbidden (403) — endpoint may not be subscribed on mypage")
    if r.status_code >= 400:
        raise KRXAPIError(f"KRX HTTP {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise KRXAPIError(f"KRX non-JSON: {r.text[:300]}") from e
    if isinstance(data, dict) and data.get("result_cd") not in (None, "0", 0, "00"):
        # Some gateways return result_cd/msg on auth/subscription failure
        msg = data.get("result_msg") or data.get("msg") or data
        raise KRXAPIError(f"KRX result error: {msg}")
    block = data.get("OutBlock_1") if isinstance(data, dict) else None
    if block is None:
        keys = list(data.keys()) if isinstance(data, dict) else type(data)
        raise KRXAPIError(f"Unexpected KRX payload keys={keys} body={str(data)[:200]}")
    return list(block)


def fetch_stock_daily(bas_dd: str | None = None) -> list[dict[str, Any]]:
    return krx_get("sto", "stk_bydd_trd", _bas_dd(bas_dd))


def fetch_etf_daily(bas_dd: str | None = None) -> list[dict[str, Any]]:
    return krx_get("etp", "etf_bydd_trd", _bas_dd(bas_dd))


def recent_bas_dd(max_lookback: int = 10) -> str:
    """Find the latest date that returns non-empty stock rows."""
    for i in range(1, max_lookback + 1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            rows = fetch_stock_daily(d)
        except (KRXAuthError, KRXAPIError):
            raise
        except Exception:
            continue
        if rows:
            return d
    raise KRXAPIError(f"No non-empty stk_bydd_trd in last {max_lookback} days")


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k not in row or row[k] is None or row[k] == "":
            continue
        try:
            return float(str(row[k]).replace(",", ""))
        except ValueError:
            continue
    return None


def _code(row: dict[str, Any]) -> str | None:
    for k in ("ISU_SRT_CD", "ISU_CD", "ISU_CD6", "SCRT_CD"):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        # Prefer 6-digit short code; strip KR ISIN prefix if needed
        if re.fullmatch(r"\d{6}", s):
            return s
        if len(s) >= 6 and s[-6:].isdigit():
            return s[-6:]
        # ETF codes like 0193T0
        if re.fullmatch(r"[0-9A-Z]{6}", s):
            return s
    return None


def index_by_code(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        c = _code(row)
        if c:
            out[c] = row
    return out


def stock_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    close = _num(row, "TDD_CLSPRC", "CLSPRC")
    mcap = _num(row, "MKTCAP")
    trdval = _num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT")
    shares = _num(row, "LIST_SHRS", "LIST_SHRS_CNT")
    fluc = _num(row, "FLUC_RT")
    return {
        "close": close,
        "market_cap_krw": mcap,
        "adv_spot_krw": trdval,
        "listed_shares": shares,
        "day_return": None if fluc is None else fluc / 100.0,
    }


def etf_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    # MKTCAP / INVSTASST_NETASST_TOTAMT / NAV fields vary by endpoint version
    aum = _num(
        row,
        "INVSTASST_NETASST_TOTAMT",
        "NETASST_TOTAMT",
        "MKTCAP",
        "NAV_TOTAMT",
    )
    trdval = _num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT")
    nav = _num(row, "NAV", "TDD_NAV", "NAV_PRC")
    close = _num(row, "TDD_CLSPRC", "CLSPRC")
    return {
        "aum_krw": aum,
        "trading_value_krw": trdval,
        "nav": nav,
        "close": close,
    }
