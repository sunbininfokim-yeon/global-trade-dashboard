"""Normalize comparison metadata for fragmented monthly public-source series.

Raw observations stay untouched.  This module adds transparent metadata so a
consumer can distinguish exact mass conversions from volume, monetary, and
industry-proxy series that must never be silently aggregated.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from world_link import to_kg


QUALITY_SCHEMA_VERSION = "commodity-trade-quality-v1"


def _month_to_date(value: str | None) -> date | None:
    try:
        year, month = (int(part) for part in (value or "").split("-"))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return None


def _months_between(reference_month: str, observed_month: str | None) -> int | None:
    reference = _month_to_date(reference_month)
    observed = _month_to_date(observed_month)
    if not reference or not observed:
        return None
    return (reference.year - observed.year) * 12 + reference.month - observed.month


def unit_class(unit: str | None) -> str:
    """Classify only what can safely be inferred from the supplied unit."""
    normalized = (unit or "").strip()
    if to_kg(1, normalized) is not None:
        return "mass"
    if normalized == "CONVBBL":
        return "conversion_factor"
    if normalized in {"KBBL", "M3"}:
        return "volume"
    if normalized.lower() in {"usd", "usd_million", "aud_million_fob"} or normalized.lower().endswith(("_fob", "_cif")):
        return "monetary"
    return "unknown"


def annotate_point(point: dict[str, Any]) -> None:
    """Attach a non-destructive normalized comparison descriptor to one point."""
    unit = point.get("unit")
    category = unit_class(unit)
    raw_value = point.get("value")
    normalized: dict[str, Any] = {
        "comparison_class": category,
        "native_unit": unit,
        "comparable_across_reporters": False,
        "value": None,
        "unit": None,
        "method": None,
    }
    if category == "mass":
        try:
            value_kg = to_kg(float(raw_value), unit)
        except (TypeError, ValueError):
            value_kg = None
        if value_kg is not None:
            normalized.update(
                {
                    "comparison_class": "mass_kg",
                    "comparable_across_reporters": True,
                    "value": value_kg,
                    "unit": "kg",
                    "method": "exact_unit_conversion",
                }
            )
    elif category == "conversion_factor":
        normalized["method"] = "not_a_trade_observation"
    elif category == "volume":
        normalized["method"] = "not_converted_density_required"
    elif category == "monetary":
        normalized["method"] = "not_converted_price_or_fx_required"
    else:
        normalized["method"] = "not_converted_unknown_unit"
    point["normalized"] = normalized


def _quality_flags(points: list[dict[str, Any]], reference_month: str) -> list[str]:
    flags: list[str] = []
    units = {str(point.get("unit") or "") for point in points}
    classes = {unit_class(point.get("unit")) for point in points}
    months = [point.get("month") for point in points if point.get("month")]
    latest = max(months) if months else None
    staleness = _months_between(reference_month, latest)
    if len(points) < 12:
        flags.append("shorter_than_trailing_12_months")
    if len(units) > 1:
        flags.append("native_unit_changed_within_series")
    if len(classes) > 1:
        flags.append("mixed_comparison_classes")
    if classes and classes != {"mass"}:
        flags.append("not_mass_normalizable")
    if staleness is not None and staleness > 3:
        flags.append("stale_more_than_3_months")

    values = [point.get("value") for point in points]
    pairs = [(left, right) for left, right in zip(values, values[1:]) if left is not None and right is not None]
    repeated = sum(left == right for left, right in pairs)
    if len(pairs) >= 6 and repeated / len(pairs) >= 0.5:
        flags.append("high_adjacent_value_repeat_rate")
    if any("proxy" in str(point.get("hs_relation") or "") for point in points):
        flags.append("proxy_series_not_pure_hs_commodity")
    return flags


def annotate_country_series(country: dict[str, Any], reference_month: str) -> None:
    points = country.get("points") or []
    for point in points:
        annotate_point(point)
    months = sorted({point.get("month") for point in points if point.get("month")})
    units = sorted({str(point.get("unit") or "") for point in points if point.get("unit")})
    sources = sorted({str(point.get("source") or "") for point in points if point.get("source")})
    classes = sorted({point["normalized"]["comparison_class"] for point in points if point.get("normalized")})
    latest = max(months) if months else None
    country["series_quality"] = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "observed_point_count": len(points),
        "observed_month_count": len(months),
        "trailing_12_coverage_ratio": round(min(len(months), 12) / 12, 4),
        "earliest_month": min(months) if months else None,
        "latest_month": latest,
        "staleness_months": _months_between(reference_month, latest),
        "native_units": units,
        "comparison_classes": classes,
        "sources": sources,
        "flags": _quality_flags(points, reference_month),
    }


def annotate_monthly_payload(sectors: dict[str, Any], reference_month: str) -> dict[str, Any]:
    """Annotate all current commodity/country series and return contract metadata."""
    for sector, block in sectors.items():
        for commodity in (block.get("commodities") or {}).values():
            countries = commodity.get("countries") or {}
            for country in countries.values():
                annotate_country_series(country, reference_month)

            all_classes = sorted(
                {
                    comparison_class
                    for country in countries.values()
                    for comparison_class in (country.get("series_quality") or {}).get("comparison_classes", [])
                }
            )
            all_flags = sorted(
                {
                    flag
                    for country in countries.values()
                    for flag in (country.get("series_quality") or {}).get("flags", [])
                }
            )
            mass_only = bool(all_classes) and set(all_classes) == {"mass_kg"}
            commodity["comparison_policy"] = {
                "schema_version": QUALITY_SCHEMA_VERSION,
                "cross_reporter_numeric_comparison": "allowed_as_kg" if mass_only else "not_allowed",
                "aggregation": "partial_sum_only_never_official_world",
                "comparison_classes_present": all_classes,
                "country_quality_flags": all_flags,
                "coverage_scope": "reported_countries_only",
            }
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "reference_month": reference_month,
        "principles_ko": [
            "원본 value와 unit은 보존한다.",
            "mass만 명시적 환산계수로 kg 표준값을 제공한다.",
            "부피·금액·산업 프록시는 자동 환산·합산하지 않는다.",
            "부분 국가 합계는 official_world로 표기하지 않는다.",
        ],
    }
