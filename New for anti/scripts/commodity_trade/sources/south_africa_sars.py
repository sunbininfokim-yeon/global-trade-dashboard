"""South African Revenue Service (SARS) public monthly tariff download adapter.

SARS publishes a session-backed public download form rather than a documented
JSON API.  Its selector state is server-side: trade flow, focus area, chapter,
tariff, year, month, and country selections each issue an ASP.NET postback.
The final export request has not yet returned a stable downloadable response
outside an interactive browser, so this module currently exposes only the
verified tariff-discovery step.  It deliberately does not fabricate an
automated series from the form labels.

The module is intentionally not wired into the national build until a live
request has verified the exact downloadable response and column contract.
"""

from __future__ import annotations

import html
import re
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


FORM_URL = "https://tools.sars.gov.za/tradestatsportal/data_download.aspx"
USER_AGENT = "commodity-trade-national-adapter/1.0"

HIDDEN_INPUT = re.compile(
    r'<input\b(?=[^>]*\btype=["\']hidden["\'])(?=[^>]*\bname=["\']([^"\']+)["\'])[^>]*\bvalue=["\']([^"\']*)["\'][^>]*>',
    re.IGNORECASE,
)
CHECKBOX_LABEL = re.compile(
    r'<input\b(?=[^>]*\bid=["\']([^"\']+)["\'])(?=[^>]*\bname=["\']([^"\']+)["\'])[^>]*\btype=["\']checkbox["\'][^>]*>\s*<label\b[^>]*\bfor=["\'][^"\']+["\'][^>]*>(.*?)</label>',
    re.IGNORECASE | re.DOTALL,
)
TAG = re.compile(r"<[^>]+>")

TRADE_TYPE = {"X": "rdbExports", "M": "rdbImports"}
CHAPTER_INDEX = {chapter: chapter - 1 for chapter in range(1, 100)}


def _text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).split())


def _hidden_fields(document: str) -> dict[str, str]:
    """Extract ASP.NET state fields from a SARS form response."""
    return {name: html.unescape(value) for name, value in HIDDEN_INPUT.findall(document)}


def _checkboxes(document: str, *, control: str) -> list[dict[str, str]]:
    """Return checkbox controls and visible labels for one SARS selector."""
    prefix = f"ctl00$ContentPlaceHolder1${control}$"
    result: list[dict[str, str]] = []
    for element_id, name, label in CHECKBOX_LABEL.findall(document):
        if name.startswith(prefix):
            result.append({"id": element_id, "name": name, "label": _text(label)})
    return result


def _chapter_selection_name(chapter: int) -> str:
    if chapter not in CHAPTER_INDEX:
        raise ValueError(f"unsupported HS chapter: {chapter}")
    return f"ctl00$ContentPlaceHolder1$ddlChapters${CHAPTER_INDEX[chapter]}"


def _open_session():
    jar = CookieJar()
    return build_opener(HTTPCookieProcessor(jar))


def _get(opener: Any, *, timeout: int) -> str:
    with opener.open(Request(FORM_URL, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}), timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _post(opener: Any, fields: dict[str, str], *, timeout: int, headers: dict[str, str] | None = None) -> str:
    body = urlencode(fields).encode("utf-8")
    request = Request(
        FORM_URL,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": FORM_URL,
            **(headers or {}),
        },
        method="POST",
    )
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def list_tariffs_for_chapter(*, chapter: int, flow: str, timeout: int = 90) -> dict[str, Any]:
    """Probe the official form and return its tariff labels for one HS chapter.

    This is a read-only request used to establish the portal's live selection
    contract before data downloads are enabled in the monthly builder.
    """
    if flow not in TRADE_TYPE:
        return {"available": False, "reason": "flow must be X or M", "tariffs": []}
    try:
        opener = _open_session()
        form = _get(opener, timeout=timeout)
        fields = _hidden_fields(form)
        if "__VIEWSTATE" not in fields:
            return {"available": False, "reason": "SARS form has no ASP.NET view state", "tariffs": []}
        # The selector is a normal posted form field.  Supplying the page's
        # JavaScript-only ``__EVENTTARGET`` here resets the selection on the
        # server's full-page fallback, so keep this probe to the same minimal
        # field set that the non-JavaScript form accepts.
        fields.update({_chapter_selection_name(chapter): "on"})
        response = _post(opener, fields, timeout=timeout)
        tariffs = _checkboxes(response, control="ddlTariffs")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc), "tariffs": []}
    if not tariffs:
        return {
            "available": False,
            "reason": "SARS chapter postback returned no tariff selectors",
            "tariffs": [],
        }
    return {"available": True, "chapter": chapter, "flow": flow, "tariffs": tariffs}
