"""Statistics Norway (SSB) table 11008 monthly HS trade adapter.

The official table provides ``All countries`` directly, avoiding a synthetic
sum over partner countries.  Norway publishes current national tariff lines,
so dashboard HS4/HS6 buckets are calculated only from explicit current lines
whose source label states Q1=kg.  The selected line codes remain on every
point for auditability.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TABLE_URL = "https://data.ssb.no/api/v0/en/table/11008"
CURRENT_LINE = re.compile(r"\(\d{4}-\)")


def _metadata_cache_path(cache_dir: Path) -> Path:
    return cache_dir / "norway_ssb_11008_metadata.json"


def _response_cache_path(cache_dir: Path, *, period: str, flow: str, hs_codes: list[str]) -> Path:
    key = "-".join(sorted(hs_codes))
    return cache_dir / f"norway_ssb_11008_{flow}_{period}_{key}.json"


def _fetch_json(url: str, *, body: dict[str, Any] | None = None, timeout: int = 90) -> dict[str, Any]:
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=encoded,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json" if encoded else "application/json",
            "User-Agent": "commodity-trade-national-adapter/1.0",
        },
        method="POST" if encoded else "GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _load_metadata(cache_dir: Path, *, allow_fetch: bool, timeout: int) -> tuple[dict[str, Any] | None, bool, str | None]:
    path = _metadata_cache_path(cache_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")), True, None
        except (OSError, json.JSONDecodeError) as exc:
            return None, True, f"invalid SSB metadata cache: {exc}"
    if not allow_fetch:
        return None, False, "SSB metadata cache miss with fetch disabled"
    try:
        metadata = _fetch_json(TABLE_URL, timeout=timeout)
        path.write_text(json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8")
        return metadata, False, None
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, False, str(exc)


def select_current_lines(metadata: dict[str, Any], hs_codes: list[str]) -> dict[str, list[str]]:
    """Map each requested HS prefix to current, mass-normalizable SSB lines."""
    variable = next((item for item in metadata.get("variables") or [] if item.get("code") == "Varekoder"), None)
    if not variable:
        raise ValueError("SSB metadata has no Varekoder variable")
    requested = {code for code in hs_codes if len(code) in {4, 6} and code.isdigit()}
    lines: dict[str, list[str]] = {code: [] for code in requested}
    for code, label in zip(variable.get("values") or [], variable.get("valueTexts") or []):
        tariff_line = str(code).split("_", 1)[0]
        if not CURRENT_LINE.search(str(label)) or "Q1=kg" not in str(label):
            continue
        for requested_hs in requested:
            if tariff_line.startswith(requested_hs):
                lines[requested_hs].append(str(code))
    return {hs: sorted(values) for hs, values in lines.items()}


def _ordered_dimension_codes(dataset: dict[str, Any], dimension: str) -> list[str]:
    category = ((dataset.get("dimension") or {}).get(dimension) or {}).get("category") or {}
    index = category.get("index") or {}
    if isinstance(index, list):
        return [str(value) for value in index]
    return [code for code, _ in sorted(index.items(), key=lambda item: item[1])]


def _dataset_values(dataset: dict[str, Any]) -> list[tuple[dict[str, str], float | None]]:
    dimensions = [str(value) for value in dataset.get("id") or []]
    sizes = [int(value) for value in dataset.get("size") or []]
    values = dataset.get("value") or []
    if not dimensions or len(dimensions) != len(sizes):
        raise ValueError("invalid SSB json-stat dimensions")
    codes = [_ordered_dimension_codes(dataset, dimension) for dimension in dimensions]
    if any(len(items) != size for items, size in zip(codes, sizes)):
        raise ValueError("SSB json-stat category size mismatch")
    result: list[tuple[dict[str, str], float | None]] = []
    for flat, coordinates in enumerate(product(*(range(size) for size in sizes))):
        raw = values[flat] if flat < len(values) else None
        try:
            numeric = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            numeric = None
        result.append(({dimension: codes[index][coordinate] for index, (dimension, coordinate) in enumerate(zip(dimensions, coordinates))}, numeric))
    return result


def fetch_monthly_hs_world(
    *,
    period: str,
    flow: str,
    hs_codes: list[str],
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one Norway World-total monthly report and aggregate explicit lines."""
    if len(period) != 6 or not period.isdigit():
        return {"available": False, "reason": "period must be YYYYMM", "series_by_hs": {}}
    if flow not in {"X", "M"}:
        return {"available": False, "reason": "flow must be X or M", "series_by_hs": {}}
    requested_hs = sorted({code for code in hs_codes if len(code) in {4, 6} and code.isdigit()})
    if not requested_hs:
        return {"available": False, "reason": "no valid four- or six-digit HS codes", "series_by_hs": {}}
    cache_dir.mkdir(parents=True, exist_ok=True)
    metadata, metadata_hit, metadata_error = _load_metadata(cache_dir, allow_fetch=allow_fetch, timeout=timeout)
    if metadata is None:
        return {"available": False, "reason": metadata_error or "SSB metadata unavailable", "series_by_hs": {}}
    try:
        lines_by_hs = select_current_lines(metadata, requested_hs)
    except ValueError as exc:
        return {"available": False, "reason": str(exc), "series_by_hs": {}}
    selected_lines = sorted({line for lines in lines_by_hs.values() for line in lines})
    if not selected_lines:
        return {"available": False, "reason": "no current SSB mass lines for requested HS codes", "series_by_hs": {}}
    path = _response_cache_path(cache_dir, period=period, flow=flow, hs_codes=requested_hs)
    response_hit = path.exists()
    try:
        if response_hit:
            dataset = json.loads(path.read_text(encoding="utf-8"))
        elif not allow_fetch:
            return {"available": False, "reason": "SSB response cache miss with fetch disabled", "series_by_hs": {}}
        else:
            query = {
                "query": [
                    {"code": "Varekoder", "selection": {"filter": "item", "values": selected_lines}},
                    {"code": "ImpEks", "selection": {"filter": "item", "values": ["2" if flow == "X" else "1"]}},
                    {"code": "Land", "selection": {"filter": "item", "values": ["00"]}},
                    {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Mengde1", "Verdi"]}},
                    {"code": "Tid", "selection": {"filter": "item", "values": [f"{period[:4]}M{period[4:]}"]}},
                ],
                "response": {"format": "json-stat2"},
            }
            dataset = _fetch_json(TABLE_URL, body=query, timeout=timeout)
            path.write_text(json.dumps(dataset, ensure_ascii=False) + "\n", encoding="utf-8")
        rows = _dataset_values(dataset)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc), "series_by_hs": {}}
    mass_by_line: dict[str, float] = {}
    value_by_line: dict[str, float] = {}
    for coordinates, value in rows:
        if value is None:
            continue
        line = coordinates.get("Varekoder")
        if coordinates.get("ContentsCode") == "Mengde1":
            mass_by_line[line] = value
        elif coordinates.get("ContentsCode") == "Verdi":
            value_by_line[line] = value
    month = f"{period[:4]}-{period[4:]}"
    series_by_hs: dict[str, list[dict[str, Any]]] = {hs: [] for hs in requested_hs}
    for hs, lines in lines_by_hs.items():
        observed_lines = [line for line in lines if line in mass_by_line]
        if not observed_lines:
            continue
        series_by_hs[hs].append(
            {
                "month": month,
                "value": sum(mass_by_line[line] for line in observed_lines),
                "unit": "kg",
                "source": "norway_ssb_11008",
                "source_access": "official_public_api",
                "hs": hs,
                "flow": flow,
                "partner_m49": "0",
                "primary_value_nok": sum(value_by_line.get(line, 0.0) for line in observed_lines),
                "quality": {
                    "partner_scope": "All countries",
                    "source_line_codes": observed_lines,
                    "source_line_count": len(observed_lines),
                    "zero_may_include_confidentiality": True,
                },
            }
        )
    return {
        "available": True,
        "source": "norway_ssb_11008",
        "period": period,
        "flow": flow,
        "series_by_hs": series_by_hs,
        "cache": {
            "path": str(path),
            "hit": response_hit,
            "metadata_hit": metadata_hit,
        },
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
