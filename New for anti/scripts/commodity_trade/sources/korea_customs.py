"""Korea Customs Itemtrade monthly HS World-total adapter.

The public data.go.kr service returns Korea's total trade by HS code and month,
including both export and import net mass (kg) and USD amounts in one XML
response.  The service key is read only from ``KOREA_CUSTOMS_SERVICE_KEY``;
it is never written to the cache, output JSON, or source tree.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ITEMTRADE_URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"


def _cache_path(cache_dir: Path, *, period: str, hs_code: str) -> Path:
    return cache_dir / f"korea_customs_itemtrade_{period}_{hs_code}.xml"


def _number(value: str | None) -> float | None:
    try:
        return float((value or "").replace(",", "").strip())
    except ValueError:
        return None


def _text(item: ET.Element, name: str) -> str | None:
    node = item.find(name)
    return node.text.strip() if node is not None and node.text else None


def parse_itemtrade_xml(document: bytes, *, period: str, hs_code: str) -> dict[str, list[dict[str, Any]]]:
    """Parse one Itemtrade response, rejecting its aggregate ``총계`` row."""
    root = ET.fromstring(document)
    result_code = (root.findtext("./header/resultCode") or "").strip()
    result_message = (root.findtext("./header/resultMsg") or "").strip()
    if result_code and result_code != "00":
        raise ValueError(f"Korea Customs API {result_code}: {result_message or 'unknown error'}")
    month_label = f"{period[:4]}.{period[4:]}"
    matched = next(
        (
            item
            for item in root.findall("./body/items/item")
            if _text(item, "year") == month_label and _text(item, "hsCode") == hs_code
        ),
        None,
    )
    if matched is None:
        return {"X": [], "M": []}
    export_mass, import_mass = _number(_text(matched, "expWgt")), _number(_text(matched, "impWgt"))
    export_usd, import_usd = _number(_text(matched, "expDlr")), _number(_text(matched, "impDlr"))
    month = f"{period[:4]}-{period[4:]}"

    def point(flow: str, mass: float | None, usd: float | None) -> list[dict[str, Any]]:
        if mass is None:
            return []
        return [
            {
                "month": month,
                "value": mass,
                "unit": "kg",
                "source": "korea_customs_itemtrade",
                "source_access": "official_api_service_key",
                "hs": hs_code,
                "flow": flow,
                "partner_m49": "0",
                "primary_value_usd": usd,
                "quality": {
                    "partner_scope": "Korea total trade (all partner countries)",
                    "amount_basis": "FOB declared USD" if flow == "X" else "CIF dutiable USD",
                    "mass_basis": "net weight kg",
                },
            }
        ]

    return {"X": point("X", export_mass, export_usd), "M": point("M", import_mass, import_usd)}


def fetch_monthly_hs_world(
    *,
    period: str,
    hs_code: str,
    cache_dir: Path,
    service_key: str | None = None,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch Korea total monthly trade for one exact HS4/HS6 target."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM"}
    if len(hs_code) not in {4, 6} or not hs_code.isdigit():
        return {"available": False, "reason": "HS code must be four or six digits"}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, period=period, hs_code=hs_code)
    cache_hit = path.exists()
    try:
        if cache_hit:
            document = path.read_bytes()
        elif not allow_fetch:
            return {"available": False, "reason": "Korea Customs response cache miss with fetch disabled"}
        else:
            key = service_key or os.getenv("KOREA_CUSTOMS_SERVICE_KEY")
            if not key:
                return {"available": False, "reason": "KOREA_CUSTOMS_SERVICE_KEY is not configured"}
            # Accept either the portal's encoded display value or its decoded value.
            query = urlencode({"serviceKey": unquote(key), "strtYymm": period, "endYymm": period, "hsSgn": hs_code})
            request = Request(ITEMTRADE_URL + "?" + query, headers={"Accept": "application/xml", "User-Agent": "commodity-trade-national-adapter/1.0"})
            with urlopen(request, timeout=timeout) as response:
                document = response.read()
            # Upstream errors may echo a query URL containing the service key.
            if unquote(key).encode() in document or key.encode() in document:
                raise ValueError("credential echo rejected")
        series_by_flow = parse_itemtrade_xml(document, period=period, hs_code=hs_code)
        if not cache_hit:
            path.write_bytes(document)
    except (ET.ParseError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        error_type = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__
        return {"available": False, "reason": f"Korea Customs request/parse failed: {error_type}", "cache": {"path": str(path), "hit": cache_hit}}
    return {
        "available": True,
        "series_by_flow": series_by_flow,
        "cache": {"path": str(path), "hit": cache_hit},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
