"""Saudi GASTAT monthly HS4 World-total trade adapter.

GASTAT publishes authenticated-looking developer pages separately from its
public trade data tables.  The latter are anonymous Tableau crosstabs and can
be exported directly as CSV.  This adapter deliberately uses only that public
contract: HS section, chapter, and *four-digit heading* filters, with the
Country filter omitted to retain Saudi Arabia's official all-country total.

The dashboard's current public filter hierarchy has been verified through HS4
only.  It must not be used to infer a six-digit result (for example LNG
HS271111) or to turn a failed Country-label lookup into a bilateral zero.
"""

from __future__ import annotations

import csv
import io
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from time import sleep, time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "commodity-trade-national-adapter/1.0"
MONTH = re.compile(r"^\s*(\d{4})\s*/\s*(\d{1,2})\s*$")

VIEWS: dict[str, dict[str, str]] = {
    "X": {
        "value": "https://tableau.stats.gov.sa/views/Exports-Monthly-Value_17298816519090/"
        "NW-ExportsValuebyHarmonizedSystemandCountry.csv",
        "weight": "https://tableau.stats.gov.sa/views/Exports-Monthly-Weight_17298818154970/"
        "NW-ExportsWeightbyHarmonizedSystemandCountry.csv",
    },
    "M": {
        "value": "https://tableau.stats.gov.sa/views/Imports-Monthly-Value_17428940280990/"
        "NW-ImportsValuebyHarmonizedSystemandCountry.csv",
        "weight": "https://tableau.stats.gov.sa/views/Imports-Monthly-Weight/"
        "NW-ImportsWeightbyHarmonizedSystemandCountry.csv",
    },
}

# Exact English labels emitted by the official Tableau crosstabs.  The source
# needs the section selection even when the chapter and heading are supplied.
SECTION_BY_CHAPTER = {
    "10": "Plant Products",
    "12": "Plant Products",
    "15": "Animal and Vegetable fats; oils; waxes and Their Products;",
    "17": "Prepared Foodstuffs; Beverages and Vinegar; Tobacco",
    "23": "Prepared Foodstuffs; Beverages and Vinegar; Tobacco",
    "25": "Mineral products.",
    "26": "Mineral products.",
    "27": "Mineral products.",
    "28": "Products of The Chemical and Allied Industries",
    "52": "Textiles and Textile Articles",
    "75": "Base Metals and Articles of Base Metals",
    "76": "Base Metals and Articles of Base Metals",
    "81": "Base Metals and Articles of Base Metals",
}


def _cache_path(cache_dir: Path, *, flow: str, hs_code: str, metric: str) -> Path:
    return cache_dir / f"saudi_gastat_tableau_{flow}_{hs_code}_{metric}.csv"


def _number(value: str | None) -> float | None:
    try:
        number = float(str(value or "").replace(",", "").strip())
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0:
        raise ValueError("invalid trade observation")
    return number


def _month(value: str | None) -> str | None:
    match = MONTH.match(value or "")
    if not match:
        return None
    year, month = (int(part) for part in match.groups())
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def parse_tableau_csv(document: str, *, metric: str) -> dict[str, float]:
    """Parse one GASTAT Tableau crosstab into a month-to-value mapping.

    Export-weight tables name their measure ``Weight`` while the import-weight
    table currently names the same displayed measure ``Value``.  The caller
    specifies the table type, so a header change fails closed rather than
    quietly selecting an unrelated column.
    """
    if not document.strip():
        return {}
    reader = csv.DictReader(io.StringIO(document))
    if not reader.fieldnames:
        return {}
    if metric == "value":
        candidates = ("Value",)
    elif metric == "weight":
        candidates = ("Weight", "Value")
    else:
        raise ValueError(f"unknown GASTAT Tableau metric: {metric}")
    field = next((item for item in candidates if item in reader.fieldnames), None)
    if field is None or "Year Month" not in reader.fieldnames:
        raise ValueError(f"unexpected GASTAT Tableau {metric} CSV columns: {reader.fieldnames}")
    values: dict[str, float] = {}
    for row in reader:
        month = _month(row.get("Year Month"))
        value = _number(row.get(field))
        if month and value is not None:
            if month in values:
                raise ValueError(f"duplicate GASTAT month: {month}; refusing ambiguous aggregation")
            values[month] = value
    return values


def select_observed_months(
    monetary: dict[str, float],
    weights: dict[str, float],
    *,
    requested_months: set[str],
    fallback_latest_months: int,
) -> tuple[list[str], bool]:
    """Prefer requested periods, otherwise retain a transparent stale tail.

    GASTAT can publish a newer monthly bulletin before its detailed Tableau
    crosstabs are refreshed.  Returning an empty current-period response as a
    zero would be worse than retaining the table's last observed months and
    letting the common quality layer mark their staleness.
    """
    available = sorted(set(monetary) | set(weights))
    requested = sorted(requested_months & set(available))
    if requested or fallback_latest_months <= 0:
        return requested, False
    return available[-fallback_latest_months:], bool(available)


def _fetch_csv(*, flow: str, hs_code: str, metric: str, timeout: int) -> str:
    chapter = hs_code[:2]
    section = SECTION_BY_CHAPTER.get(chapter)
    if not section:
        raise ValueError(f"Saudi Tableau section mapping missing for HS chapter {chapter}")
    query = urlencode(
        {
            ":showVizHome": "no",
            "HS Section": section,
            "Hs Chapter Cd": chapter,
            "Hs Heading Cd": hs_code,
        }
    )
    request = Request(
        f"{VIEWS[flow][metric]}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv"},
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def fetch_monthly_hs_world(
    *,
    periods: list[str],
    flow: str,
    hs_code: str,
    cache_dir: Path,
    allow_fetch: bool = True,
    timeout: int = 90,
    max_requests: int | None = None,
    min_interval_seconds: float = 0.0,
    fallback_latest_months: int = 0,
    cache_max_age_seconds: float = 86400,
) -> dict[str, Any]:
    """Fetch selected months of official Saudi all-country HS4 trade.

    Each official CSV contains a long monthly history.  Fetching it once per
    flow/heading (value and weight) then selecting requested months keeps the
    public endpoint load bounded and allows cache-backed retries.
    """
    requested_periods = sorted({period for period in periods if re.fullmatch(r"\d{6}", period or "")})
    if len(requested_periods) != len(set(periods)) or not requested_periods:
        return {"available": False, "reason": "periods must be non-empty YYYYMM strings"}
    if flow not in VIEWS:
        return {"available": False, "reason": "flow must be X or M"}
    if len(hs_code) != 4 or not hs_code.isdigit():
        return {
            "available": False,
            "reason": "Saudi Tableau public filter contract is verified for exact HS4 only",
            "series_by_hs": {},
        }
    if hs_code[:2] not in SECTION_BY_CHAPTER:
        return {"available": False, "reason": f"Saudi Tableau section mapping missing for {hs_code[:2]}"}
    if fallback_latest_months < 0:
        return {"available": False, "reason": "fallback_latest_months must be non-negative"}

    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = {metric: _cache_path(cache_dir, flow=flow, hs_code=hs_code, metric=metric) for metric in ("value", "weight")}
    if cache_max_age_seconds < 0 or not math.isfinite(cache_max_age_seconds):
        raise ValueError("cache_max_age_seconds must be finite and non-negative")
    # Offline mode can use an older valid cache; live runs must recheck daily.
    missing = [metric for metric, path in paths.items()
               if not path.exists() or (allow_fetch and time() - path.stat().st_mtime >= cache_max_age_seconds)]
    if missing and not allow_fetch:
        return {
            "available": False,
            "reason": "Saudi Tableau response cache miss with fetch disabled",
            "series_by_hs": {},
            "cache": {"paths": {metric: str(path) for metric, path in paths.items()}, "hit": False, "network_requests": 0},
        }
    if max_requests is not None and len(missing) > max_requests:
        return {
            "available": False,
            "reason": "Saudi Tableau request budget exhausted before value/weight pair",
            "series_by_hs": {},
            "cache": {"paths": {metric: str(path) for metric, path in paths.items()}, "hit": False, "network_requests": 0},
        }

    network_requests = 0
    try:
        documents: dict[str, str] = {}
        for metric, path in paths.items():
            if metric not in missing:
                documents[metric] = path.read_text(encoding="utf-8")
                continue
            if network_requests and min_interval_seconds > 0:
                sleep(min_interval_seconds)
            network_requests += 1
            document = _fetch_csv(flow=flow, hs_code=hs_code, metric=metric, timeout=timeout)
            # Validate before replacing a known-good cache. A failed second
            # metric must not publish a half-refreshed pair.
            parse_tableau_csv(document, metric=metric)
            documents[metric] = document
        monetary = parse_tableau_csv(documents["value"], metric="value")
        weights = parse_tableau_csv(documents["weight"], metric="weight")
        for metric in missing:
            path = paths[metric]
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_text(documents[metric], encoding="utf-8")
            temporary.replace(path)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "available": False,
            "reason": str(exc),
            "series_by_hs": {},
            "cache": {
                "paths": {metric: str(path) for metric, path in paths.items()},
                "hit": not missing,
                "network_requests": network_requests,
            },
        }

    requested_months = {f"{period[:4]}-{period[4:]}" for period in requested_periods}
    observed_months, used_stale_fallback = select_observed_months(
        monetary,
        weights,
        requested_months=requested_months,
        fallback_latest_months=fallback_latest_months,
    )
    points: list[dict[str, Any]] = []
    for month in observed_months:
        weight = weights.get(month)
        value = monetary.get(month)
        if weight is None and value is None:
            continue
        point: dict[str, Any] = {
            "month": month,
            "value": weight if weight is not None else value,
            "unit": "metric_tons" if weight is not None else "SAR_million",
            "source": "saudi_gastat_tableau_monthly",
            "source_access": "official_public_tableau_csv",
            "hs": hs_code,
            "flow": flow,
            "partner_m49": "0",
            "quality": {
                "partner_scope": "All countries (official Tableau Country filter omitted)",
                "classification": "official Saudi monthly HS heading (exact HS4)",
                "weight_scope": "net weight in tons when the official weight crosstab returns a value",
                "value_scope": "official Tableau value, million Saudi riyals",
                "bilateral_note": "country-specific Tableau labels are not mapped by this World-total adapter",
                "selection_scope": (
                    "requested months available in official Tableau crosstab"
                    if not used_stale_fallback
                    else "requested months absent; retained latest available official Tableau months"
                ),
            },
        }
        if value is not None:
            point["primary_value_sar_million"] = value
        if weight is None:
            point["quality"]["weight_unavailable"] = "official value row present; no weight row returned"
        points.append(point)
    return {
        "available": True,
        "source": "saudi_gastat_tableau_monthly",
        "flow": flow,
        "series_by_hs": {hs_code: points},
        "source_latest_month": max(set(monetary) | set(weights), default=None),
        "used_stale_fallback": used_stale_fallback,
        "cache": {
            "paths": {metric: str(path) for metric, path in paths.items()},
            "hit": not missing,
            "network_requests": network_requests,
        },
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
