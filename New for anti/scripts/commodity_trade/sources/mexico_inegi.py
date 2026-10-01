"""Mexico INEGI BCMM monthly TIGIE value adapter.

INEGI's public OLAP cube exposes monthly Mexican merchandise trade by TIGIE
heading.  The request is a server-side MDX form, not a documented JSON API;
this adapter uses its public query contract and caches the unmodified HTML
response.  The primary observation is USD FOB value.  Quantity is deliberately
not used: INEGI documents it as the original customs-declaration unit, which
can differ by tariff line.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


QUERY_URL = "https://www.inegi.org.mx/sistemas/olap/consulta/general_ver4/MDXQueryDatos.asp"
USER_AGENT = "commodity-trade-national-adapter/1.0"
RESULT_TABLE = re.compile(
    r"<table\b[^>]*id=[\"']ResultTable[\"'][^>]*>(.*?)</table>\s*<br>\s*<script[^>]*>\s*var llamada=Actualiza",
    re.IGNORECASE | re.DOTALL,
)
TABLE = re.compile(r"<table\b[^>]*id=[\"']ResultTable[\"'][^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
MEMBER_CODE = re.compile(r"&\[(\d{4,10})\]")


def _response_cache_path(cache_dir: Path, *, period: str, chapter: int, page: int) -> Path:
    return cache_dir / f"mexico_inegi_{period}_chapter_{chapter:02d}_page_{page}.html"


def _text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).split())


def _number(value: str) -> float | None:
    value = value.replace(",", "").strip()
    if not value or value.upper() == "C":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _page_count(document: str) -> int:
    match = re.search(r"Actualiza\(\s*'\d+'\s*,\s*'\d+'\s*,\s*'(\d+)'\s*,\s*'(\d+)'", document)
    if not match:
        return 1
    rows, page_size = (int(value) for value in match.groups())
    return max(1, (rows + page_size - 1) // page_size)


def parse_chapter_value_page(document: str) -> dict[str, dict[str, float]]:
    """Parse direct HS4 USD values by flow from one INEGI result page.

    Confidential observations are emitted as ``C`` by the official cube and
    are intentionally omitted rather than converted to zero.
    """
    tables = RESULT_TABLE.findall(document) or TABLE.findall(document)
    if not tables:
        raise ValueError("INEGI result table missing")
    result: dict[str, dict[str, float]] = {"X": {}, "M": {}}
    for row in ROW.findall(tables[0]):
        cells = CELL.findall(row)
        if len(cells) < 3:
            continue
        flow_text = _text(cells[0]).lower()
        if "importaciones" in flow_text:
            flow = "M"
        elif "exportaciones" in flow_text:
            flow = "X"
        else:
            continue
        codes = MEMBER_CODE.findall(html.unescape(cells[1]))
        if not codes:
            continue
        hs_code = codes[-1]
        if len(hs_code) != 4:
            continue
        value = _number(_text(cells[-1]))
        if value is not None:
            result[flow][hs_code] = value
    return result


def _query_rows(*, chapter: int) -> str:
    chapter_member = f"[Tarifa].[Tarifa].[DES CAPITULO].&[{chapter:02d}]"
    operation_total = "[Tipo operación].[Tipo operación].[Total]"
    tariff_rows = f"ToggleDrillState({{{chapter_member}}},{{{chapter_member}}})"
    base = (
        f"crossjoin(ToggleDrillState({{{operation_total}}},{{{operation_total}}}),"
        f"{tariff_rows})"
    )
    return f"ToggleDrillState({base},{{{operation_total}}})"


def _fetch_page(*, period: str, chapter: int, page: int, timeout: int) -> str:
    year, month = int(period[:4]), int(period[4:])
    if not 1 <= month <= 12:
        raise ValueError("period month must be 01..12")
    fields = {
        "s": "est",
        "server": "W-OLAPCLPRO25",
        "database": "COMEX_BCMM_MENSUAL",
        "cube": "COMEX_BCMM_MENSUAL_2023",
        "columns": "ToggleDrillState({[Measures].levels(0).allmembers},{[Measures].levels(0).allmembers})",
        "rows": _query_rows(chapter=chapter),
        "NomDimFila": "Tipo operación|Tarifa",
        "NomDimCol": "Measures",
        "NumPagCol": "1",
        "NumPagFil": str(page),
        "Paq_PagCol": "0",
        "Paq_PagFil": str((page - 1) // 10),
        "DimVisible": "Measures|Tipo operación|Tipo moneda|Año|Mes|Tarifa",
        "NDim": "7",
        "ed": "0,0,2,0,0,0",
        "Where_Año": f"[Año].[ID FECHA REGISTRO].&[{year}]",
        "Where_Mes": f"[Mes].[Mes].[DES MES].&[{month}]",
        "Where_Tarifa": "[Tarifa].levels(0).allmembers",
        "Where_Tipo moneda": "[Tipo moneda].[ID TIPO MONEDA].&[1]",
        "Where_Tipo operación": "[Tipo operación].[Tipo operación].[Total]",
        "FiltroSel": "",
        "ContNuevoFiltro": "",
        "unidadmedida": "Dolares",
    }
    request = Request(
        QUERY_URL,
        data=urlencode(fields).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("cp1252", errors="replace")


def fetch_monthly_chapter_values(
    *,
    period: str,
    chapter: int,
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 120,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Fetch one Mexico month and one HS chapter's available HS4 USD values."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM"}
    if not 1 <= chapter <= 99:
        return {"available": False, "reason": "chapter must be 1..99"}
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages: list[str] = []
    cache_hits = 0
    network_requests = 0
    first_path = _response_cache_path(cache_dir, period=period, chapter=chapter, page=1)

    def load_page(page: int) -> tuple[str | None, str | None]:
        nonlocal cache_hits, network_requests
        path = _response_cache_path(cache_dir, period=period, chapter=chapter, page=page)
        if path.exists():
            cache_hits += 1
            return path.read_text(encoding="cp1252"), None
        if not allow_fetch:
            return None, "INEGI response cache miss with fetch disabled"
        if max_requests is not None and network_requests >= max_requests:
            return None, "INEGI request budget exhausted before complete chapter response"
        document = _fetch_page(period=period, chapter=chapter, page=page, timeout=timeout)
        network_requests += 1
        path.write_text(document, encoding="cp1252")
        return document, None

    try:
        first, reason = load_page(1)
        if reason:
            return {
                "available": False,
                "reason": reason,
                "cache": {"path": str(first_path), "hit": bool(cache_hits), "network_requests": network_requests},
            }
        assert first is not None
        pages.append(first)
        for page in range(2, _page_count(first) + 1):
            document, reason = load_page(page)
            if reason:
                return {
                    "available": False,
                    "reason": reason,
                    "cache": {
                        "path": str(first_path),
                        "hit": False,
                        "page_count": _page_count(first),
                        "network_requests": network_requests,
                    },
                }
            assert document is not None
            pages.append(document)
        by_flow: dict[str, dict[str, float]] = {"X": {}, "M": {}}
        for document in pages:
            parsed = parse_chapter_value_page(document)
            for flow in by_flow:
                by_flow[flow].update(parsed[flow])
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "available": False,
            "reason": str(exc),
            "cache": {"path": str(first_path), "hit": bool(cache_hits), "network_requests": network_requests},
        }
    series_by_flow: dict[str, dict[str, list[dict[str, Any]]]] = {"X": {}, "M": {}}
    for flow, values in by_flow.items():
        for hs_code, value in values.items():
            series_by_flow[flow][hs_code] = [
                {
                    "month": f"{period[:4]}-{period[4:]}",
                    "value": value,
                    "unit": "USD_FOB",
                    "primary_value_usd": value,
                    "source": "mexico_inegi_bcmm_monthly",
                    "source_access": "official_public_olap",
                    "hs": hs_code,
                    "flow": flow,
                    "partner_m49": "0",
                    "quality": {
                        "partner_scope": "Mexico total (official cube; no partner dimension selected)",
                        "classification": "TIGIE HS4 heading at source reporting time",
                        "quantity_not_used": "INEGI quantity uses tariff-specific original customs units",
                        "confidentiality": "official C cells omitted; they are not zeros",
                    },
                }
            ]
    return {
        "available": True,
        "series_by_flow": series_by_flow,
        "cache": {
            "path": str(first_path),
            "hit": cache_hits == len(pages),
            "page_count": len(pages),
            "network_requests": network_requests,
        },
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
