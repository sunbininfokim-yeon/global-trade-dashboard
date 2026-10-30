"""India Ministry of Commerce TradeStat monthly HS4 value adapter.

TradeStat is a public form, not an advertised data API.  One request returns
all HS4 codes for a reporter flow and calendar month, so callers can stay
polite and cache the raw response.  At HS4 the source does not supply a
quantity unit; this adapter therefore deliberately uses the USD-million value
view and never labels it as mass.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "https://tradestat.commerce.gov.in/meidb/commoditywise_{}"
USER_AGENT = "commodity-trade-national-adapter/1.0 (+official-public-data)"


class _TradeStatTableParser(HTMLParser):
    """Extract the result table without relying on a third-party HTML parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_table = False
        self._table_depth = 0
        self._row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []
        self.rows: list[list[tuple[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "example1":
            self._in_table = True
            self._table_depth = 1
            return
        if not self._in_table:
            return
        if tag == "table":
            self._table_depth += 1
        elif tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell_tag = tag
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_table and self._cell_tag is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag in {"th", "td"} and tag == self._cell_tag and self._row is not None:
            text = " ".join("".join(self._cell_parts).split())
            self._row.append((tag, text))
            self._cell_tag = None
            self._cell_parts = []
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_table = False


def _cache_path(cache_dir: Path, *, period: str, flow: str, hs_code: str | None = None) -> Path:
    if hs_code:
        return cache_dir / f"india_tradestat_usd_{flow}_{period}_{hs_code}.html"
    # Preserve the original HS4 cache key so an adapter update never needlessly
    # replays public-form requests that were already collected.
    return cache_dir / f"india_tradestat_hs4_usd_{flow}_{period}.html"


def _month_label(period: str) -> str:
    return datetime.strptime(period, "%Y%m").strftime("%b-%Y")


def _to_number(value: str) -> float | None:
    compact = value.replace(",", "").strip()
    if not compact or compact in {"-", "…"}:
        return None
    try:
        return float(compact)
    except ValueError:
        return None


def parse_hs4_usd_response(html: str, *, period: str, hs_codes: list[str], flow: str) -> dict[str, list[dict[str, Any]]]:
    """Parse a saved public response into exact requested-HS value observations."""
    parser = _TradeStatTableParser()
    parser.feed(html)
    if not parser.rows:
        raise ValueError("TradeStat result table example1 was not found")
    header_row = next((row for row in parser.rows if any(tag == "th" for tag, _ in row)), None)
    if header_row is None:
        raise ValueError("TradeStat result table has no header")
    headers = [text for _, text in header_row]
    expected_label = _month_label(period)
    month_index = next((index for index, header in enumerate(headers) if header.startswith(expected_label)), None)
    if month_index is None:
        raise ValueError(f"TradeStat response lacks current-month column {expected_label}")
    status_match = re.search(r"\(([A-Z])\)", headers[month_index])
    release_status = status_match.group(1) if status_match else None
    requested = {code for code in hs_codes if len(code) in {2, 4, 6, 8} and code.isdigit()}
    series_by_hs: dict[str, list[dict[str, Any]]] = {code: [] for code in requested}
    for row in parser.rows:
        if not row or not any(tag == "td" for tag, _ in row):
            continue
        cells = [text for _, text in row]
        if len(cells) <= month_index or len(cells) < 2:
            continue
        hs = cells[1].strip()
        if hs not in requested:
            continue
        value = _to_number(cells[month_index])
        if value is None:
            continue
        series_by_hs[hs].append(
            {
                "month": f"{period[:4]}-{period[4:]}",
                "value": value,
                "unit": "USD_million",
                "source": "india_tradestat",
                "source_access": "official_public_form",
                "hs": hs,
                "flow": flow,
                "partner_m49": "0",
                "quality": {
                    "release_status": release_status,
                    "measure": "US $ Million",
                    "commodity_level": len(hs),
                    "quantity_available_at_this_hs_level": False,
                },
            }
        )
    return series_by_hs


def _download_hs4_usd_html(*, period: str, flow: str, timeout: int, hs_code: str | None = None) -> str:
    if flow not in {"X", "M"}:
        raise ValueError("flow must be X or M")
    year, month = int(period[:4]), int(period[4:])
    if not 1 <= month <= 12:
        raise ValueError("period must be YYYYMM")
    direction = "export" if flow == "X" else "import"
    url = BASE_URL.format(direction)
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with opener.open(Request(url, headers=headers), timeout=timeout) as response:
        initial_html = response.read().decode("utf-8", errors="replace")
    token_match = re.search(r'name=["\']_token["\']\s+value=["\']([^"\']+)', initial_html)
    if token_match is None:
        raise ValueError("TradeStat CSRF token not found")
    prefix = "dd" if flow == "X" else "imdd"
    form = {
        "_token": token_match.group(1),
        f"{prefix}Month": str(month),
        f"{prefix}Year": str(year),
        "comlev": "specific" if hs_code else "all",
        f"{prefix}CommodityLevel": str(len(hs_code)) if hs_code else "4",
        f"{prefix}ReportVal": "1",
        f"{prefix}ReportYear": "2",
    }
    if hs_code:
        form["comval"] = hs_code
    request = Request(
        url,
        data=urlencode(form).encode("utf-8"),
        headers={**headers, "Referer": url, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_monthly_hs4_usd(
    *,
    period: str,
    flow: str,
    hs_codes: list[str],
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one public India HS4 value report, cache it, and filter target HS."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM", "series_by_hs": {}}
    if flow not in {"X", "M"}:
        return {"available": False, "reason": "flow must be X or M", "series_by_hs": {}}
    target_hs = sorted({code for code in hs_codes if len(code) == 4 and code.isdigit()})
    if not target_hs:
        return {"available": False, "reason": "no four-digit HS codes", "series_by_hs": {}}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, period=period, flow=flow)
    from_cache = path.exists()
    try:
        if from_cache:
            html = path.read_text(encoding="utf-8")
        elif not allow_fetch:
            return {"available": False, "reason": "TradeStat cache miss with fetch disabled", "series_by_hs": {}}
        else:
            html = _download_hs4_usd_html(period=period, flow=flow, timeout=timeout)
            path.write_text(html, encoding="utf-8")
        series_by_hs = parse_hs4_usd_response(html, period=period, hs_codes=target_hs, flow=flow)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc), "series_by_hs": {}}
    return {
        "available": True,
        "source": "india_tradestat",
        "period": period,
        "flow": flow,
        "series_by_hs": series_by_hs,
        "cache": {"path": str(path), "hit": from_cache},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_monthly_specific_hs_usd(
    *,
    period: str,
    flow: str,
    hs_code: str,
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one exact HS2/4/6/8 USD report from the same official form."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM", "series_by_hs": {}}
    if flow not in {"X", "M"}:
        return {"available": False, "reason": "flow must be X or M", "series_by_hs": {}}
    if len(hs_code) not in {2, 4, 6, 8} or not hs_code.isdigit():
        return {"available": False, "reason": "hs_code must be 2, 4, 6, or 8 digits", "series_by_hs": {}}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, period=period, flow=flow, hs_code=hs_code)
    from_cache = path.exists()
    html = ""
    try:
        if from_cache:
            html = path.read_text(encoding="utf-8")
        elif not allow_fetch:
            return {"available": False, "reason": "TradeStat cache miss with fetch disabled", "series_by_hs": {}}
        else:
            html = _download_hs4_usd_html(period=period, flow=flow, timeout=timeout, hs_code=hs_code)
            path.write_text(html, encoding="utf-8")
        series_by_hs = parse_hs4_usd_response(html, period=period, hs_codes=[hs_code], flow=flow)
    except ValueError as exc:
        # TradeStat returns its blank form (HTTP 200) when an ITC-HS code is
        # not in the selected directory.  It contains no result table and no
        # echoed code, which is a classification-availability signal rather
        # than a transport error or a zero trade observation.
        if "result table example1 was not found" in str(exc) and hs_code not in html:
            return {
                "available": True,
                "source": "india_tradestat",
                "period": period,
                "flow": flow,
                "series_by_hs": {hs_code: []},
                "empty_status": "source_hs_code_not_available",
                "cache": {"path": str(path), "hit": from_cache},
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        return {"available": False, "reason": str(exc), "series_by_hs": {}}
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"available": False, "reason": str(exc), "series_by_hs": {}}
    return {
        "available": True,
        "source": "india_tradestat",
        "period": period,
        "flow": flow,
        "series_by_hs": series_by_hs,
        "cache": {"path": str(path), "hit": from_cache},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
