"""L0 — SEC EDGAR data.sec.gov client (no API key; User-Agent required)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

# SEC fair-access: identify the client. Override with SEC_USER_AGENT.
DEFAULT_UA = os.environ.get(
    "SEC_USER_AGENT",
    "GlobalTradeDashboard KFA-Engine research@example.com",
)


class SecApiError(RuntimeError):
    pass


def _cache_path(kind: str, key: str) -> Path:
    safe = key.replace("/", "_")
    return CACHE_DIR / f"sec_{kind}__{safe}.json"


def _http_get_json(url: str, *, timeout: float = 60.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8")
    except urllib.error.HTTPError as e:
        raise SecApiError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise SecApiError(f"network error: {e}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SecApiError("response is not JSON") from e


def fetch_company_tickers(*, use_cache: bool = True) -> dict[str, Any]:
    cpath = _cache_path("tickers", "all")
    if use_cache and cpath.exists():
        return json.loads(cpath.read_text(encoding="utf-8"))
    data = _http_get_json(TICKERS_URL)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.2)
    return data


def ticker_to_cik(ticker: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Return {cik, ticker, title} for a US ticker."""
    t = ticker.strip().upper()
    data = fetch_company_tickers(use_cache=use_cache)
    # company_tickers.json is { "0": {cik_str, ticker, title}, ... }
    for _k, row in data.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("ticker", "")).upper() == t:
            cik_num = int(row["cik_str"])
            return {
                "cik": f"{cik_num:010d}",
                "cik_int": cik_num,
                "ticker": row.get("ticker"),
                "title": row.get("title"),
            }
    raise SecApiError(f"ticker not found: {ticker}")


def fetch_company_facts(cik: str, *, use_cache: bool = True) -> dict[str, Any]:
    cik10 = str(cik).zfill(10)
    cpath = _cache_path("facts", cik10)
    if use_cache and cpath.exists():
        return json.loads(cpath.read_text(encoding="utf-8"))
    url = FACTS_TMPL.format(cik=cik10)
    data = _http_get_json(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.2)
    return data


def fetch_submissions(cik: str, *, use_cache: bool = True) -> dict[str, Any]:
    cik10 = str(cik).zfill(10)
    cpath = _cache_path("submissions", cik10)
    if use_cache and cpath.exists():
        return json.loads(cpath.read_text(encoding="utf-8"))
    url = SUBMISSIONS_TMPL.format(cik=cik10)
    data = _http_get_json(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.2)
    return data
