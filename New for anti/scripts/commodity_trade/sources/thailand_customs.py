"""Thailand Customs monthly HS World-total value adapter.

Thailand Customs exposes a public, session-backed monthly search form.  The
result has a direct month and a year-to-date column; this adapter takes only
the direct-month ``SUM`` value.  The public form exposes quantity only for
11-digit Thai tariff lines, while this pipeline's commodity contract is HS4/
HS6.  Consequently these observations are explicitly THB monetary series,
not mass-normalizable series.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


FORM_URL = (
    "https://www.customs.go.th/statistic_report.php?ini_content=statistics_report"
    "&ini_menu=nmenu_esevice_007&lang=en&left_menu=nmenu_esevice_007_190422_01"
    "&root_left_menu=nmenu_esevice_007"
)
TOKEN = re.compile(r"statistic_report\.php\?show_search=1&s=([A-Za-z0-9]+)")
TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL = re.compile(r"<(?:td|th)\b[^>]*>(.*?)</(?:td|th)>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")


def _response_cache_path(cache_dir: Path, *, period: str, flow: str, hs_code: str) -> Path:
    return cache_dir / f"thailand_customs_{flow}_{period}_{hs_code}.html"


def _text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).split())


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").strip())
    except (AttributeError, ValueError):
        return None


def parse_monthly_sum(document: str, *, period: str, flow: str) -> dict[str, Any] | None:
    """Return the direct-month total and source YTD total from a result page."""
    expected_measure = "FOB (Baht)" if flow == "X" else "CIF (Baht)"
    expected_label = datetime.strptime(period, "%Y%m").strftime("%b %Y")
    for table in TABLE.findall(document):
        cells = [_text(cell) for cell in CELL.findall(table)]
        if expected_measure not in cells or expected_label not in cells:
            continue
        for row in ROW.findall(table):
            values = [_text(cell) for cell in CELL.findall(row)]
            if not values or values[0] != "SUM":
                continue
            numbers = [_number(value) for value in values[1:]]
            if not numbers or numbers[0] is None:
                continue
            return {"value": numbers[0], "source_ytd_value": numbers[1] if len(numbers) > 1 else None}
    return None


def _fetch_response(*, period: str, flow: str, hs_code: str, timeout: int) -> str:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    headers = {"User-Agent": "commodity-trade-national-adapter/1.0", "Accept": "text/html"}
    with opener.open(Request(FORM_URL, headers=headers), timeout=timeout) as response:
        form = response.read().decode("utf-8", errors="replace")
    match = TOKEN.search(form)
    if not match:
        raise ValueError("Thailand Customs search token missing from form")
    post_url = "https://www.customs.go.th/statistic_report.php?show_search=1&s=" + match.group(1)
    fields = {
        "imex_type": "export" if flow == "X" else "import",
        "tariff_code": hs_code,
        "country_code": "",
        "month": str(int(period[4:])),
        "year": period[:4],
    }
    body = urlencode(fields).encode("utf-8")
    post_headers = {**headers, "Referer": FORM_URL, "Content-Type": "application/x-www-form-urlencoded"}
    with opener.open(Request(post_url, data=body, headers=post_headers, method="POST"), timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_monthly_hs_world(
    *,
    period: str,
    flow: str,
    hs_code: str,
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one official Thailand monthly HS World-total value observation."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM"}
    if flow not in {"X", "M"}:
        return {"available": False, "reason": "flow must be X or M"}
    if len(hs_code) not in {4, 6} or not hs_code.isdigit():
        return {"available": False, "reason": "HS code must be four or six digits"}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _response_cache_path(cache_dir, period=period, flow=flow, hs_code=hs_code)
    cache_hit = path.exists()
    try:
        if cache_hit:
            document = path.read_text(encoding="utf-8")
        elif not allow_fetch:
            return {"available": False, "reason": "Thailand Customs response cache miss with fetch disabled"}
        else:
            document = _fetch_response(period=period, flow=flow, hs_code=hs_code, timeout=timeout)
            path.write_text(document, encoding="utf-8")
        observed = parse_monthly_sum(document, period=period, flow=flow)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc), "cache": {"path": str(path), "hit": cache_hit}}
    if observed is None:
        return {
            "available": False,
            "reason": "no matching direct-month SUM in Thailand Customs response",
            "cache": {"path": str(path), "hit": cache_hit},
        }
    unit = "THB_FOB" if flow == "X" else "THB_CIF"
    return {
        "available": True,
        "series_by_hs": {
            hs_code: [
                {
                    "month": f"{period[:4]}-{period[4:]}",
                    "value": observed["value"],
                    "unit": unit,
                    "source": "thailand_customs_statistics_report",
                    "source_access": "official_public_session_form",
                    "hs": hs_code,
                    "flow": flow,
                    "partner_m49": "0",
                    "source_ytd_value_thb": observed["source_ytd_value"],
                    "quality": {
                        "partner_scope": "All countries (official source SUM)",
                        "measurement_scope": "direct_month_only; source YTD retained separately",
                        "quantity_not_used": "official public form provides quantity detail only at Thai HS11",
                    },
                }
            ]
        },
        "cache": {"path": str(path), "hit": cache_hit},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
