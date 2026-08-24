"""Canonical financial-fact and fiscal-period adapters for DART and SEC.

The contract in this module sits between source-specific filing payloads and
the metric engine.  It intentionally does not guess missing periods:

* DART interim flows are year-to-date values and are converted with
  :mod:`dart_kfa.periods`.
* balances remain point-in-time values;
* SEC duration facts must exactly match the expected fiscal start/end dates;
* missing predecessors and incompatible units are emitted as unavailable;
* proxies can only be created through :func:`make_labeled_proxy`, which
  requires an explicit method, reason, confidence and source references.

All public functions return JSON-serialisable dictionaries.  This keeps the
contract usable by the existing Python engine and by a later Worker adapter
without coupling either one to Python dataclasses.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from .periods import (
    QUARTER_ORDER,
    REPORT_ORDER,
    REPORT_TO_QUARTER,
    discrete_quarters_from_ytd,
    fiscal_period_metadata,
    point_in_time_quarters,
)
from .accounts import load_accounts_map


SCHEMA_VERSION = "canonical-financial-facts/1"

DART_REPORTS: dict[str, dict[str, str]] = {
    "11013": {"bucket": "Q1", "report_type": "quarter_report"},
    "11012": {"bucket": "H1", "report_type": "half_year_report"},
    "11014": {"bucket": "Q3", "report_type": "quarter_report"},
    "11011": {"bucket": "FY", "report_type": "business_report"},
}
DART_CODE_BY_BUCKET = {meta["bucket"]: code for code, meta in DART_REPORTS.items()}

SEC_REPORTS: dict[str, dict[str, str]] = {
    "Q1": {"report_code": "10-Q", "report_type": "quarter_report", "fp": "Q1"},
    "H1": {"report_code": "10-Q", "report_type": "half_year_report", "fp": "Q2"},
    "Q3": {"report_code": "10-Q", "report_type": "quarter_report", "fp": "Q3"},
    "FY": {"report_code": "10-K", "report_type": "annual_report", "fp": "FY"},
}

_REPORT_ALIAS = {**{code: meta["bucket"] for code, meta in DART_REPORTS.items()}, **{r: r for r in REPORT_ORDER}}
_STATEMENT_NAMES = {"BS", "IS", "CIS", "CF", "SCE"}
_NATURES = {"flow", "balance"}
_CONFIDENCE = {"low", "medium", "high"}

# A proxy is an analytical convention, not a missing filing fact filled by
# guesswork.  Keep the allowed set deliberately small and review additions as
# accounting-policy changes.  Exact filing arithmetic belongs in the
# deterministic metric layer and must not be routed through this table.
PROXY_POLICIES: dict[str, dict[str, set[str]]] = {
    "ending_balance_denominator_v1": {
        "metrics": {"roe", "roa", "asset_turnover", "inventory_turnover", "receivables_turnover"},
        "entity_classes": {"industrial", "bank", "insurer", "other_financial"},
        "visibility": {"expert", "audit"},
    },
    "operating_income_as_ebit_v1": {
        "metrics": {"interest_coverage"},
        "entity_classes": {"industrial"},
        "visibility": {"expert", "audit"},
    },
}


class CanonicalFactError(ValueError):
    """Raised when source metadata cannot satisfy the canonical contract."""


def _day(raw: str | date) -> date:
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise CanonicalFactError(f"invalid_iso_date:{raw}") from exc


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        # A 29 February fiscal endpoint maps deterministically to 28 February.
        return value.replace(year=value.year + years, day=28)


def _amount(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        raw = raw.strip().replace(",", "")
        if not raw or raw in {"-", "—", "–"}:
            return None
        negative = raw.startswith("(") and raw.endswith(")")
        if negative:
            raw = raw[1:-1]
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return None
        if not value.is_finite():
            return None
        return -value if negative else value
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _normalise_currency(raw: Any) -> str | None:
    value = str(raw or "").strip().upper()
    aliases = {"원": "KRW", "￦": "KRW", "US$": "USD", "$": "USD"}
    return aliases.get(value, value) or None


def _normalise_report_key(raw: str) -> str:
    try:
        return _REPORT_ALIAS[str(raw).upper()]
    except KeyError as exc:
        raise CanonicalFactError(f"unsupported_report:{raw}") from exc


def _normalise_specs(account_specs: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not account_specs:
        raise CanonicalFactError("missing_account_specs")
    out: dict[str, dict[str, Any]] = {}
    for account_id, raw in account_specs.items():
        spec = dict(raw)
        nature = str(spec.get("nature") or "").lower()
        if nature not in _NATURES:
            raise CanonicalFactError(f"invalid_account_nature:{account_id}")
        statement = str(spec.get("statement") or ("BS" if nature == "balance" else "IS")).upper()
        if statement not in _STATEMENT_NAMES:
            raise CanonicalFactError(f"invalid_statement:{account_id}:{statement}")
        spec["nature"] = nature
        spec["statement"] = statement
        spec["unit_kind"] = str(spec.get("unit_kind") or "currency")
        out[str(account_id)] = spec
    return out


def _normalise_report_periods(
    fiscal_year_end: str | date,
    report_periods: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    supplied: dict[str, dict[str, str]] = {}
    for raw_report, raw_period in (report_periods or {}).items():
        bucket = _normalise_report_key(str(raw_report))
        period: dict[str, str] = {}
        if raw_period.get("start") is not None:
            period["start"] = _day(raw_period["start"]).isoformat()
        if raw_period.get("end") is not None:
            period["end"] = _day(raw_period["end"]).isoformat()
        supplied[bucket] = period

    period_meta = fiscal_period_metadata(
        fiscal_year_end,
        report_ends={bucket: value["end"] for bucket, value in supplied.items() if value.get("end")},
    )
    fy_end = _day(fiscal_year_end)
    explicit_starts = {_day(period["start"]) for period in supplied.values() if period.get("start")}
    if len(explicit_starts) > 1:
        raise CanonicalFactError("report_starts_not_consistent")
    fy_start = next(iter(explicit_starts), _shift_year(fy_end, -1) + timedelta(days=1))
    quarter_starts: dict[str, date] = {"Q1": fy_start}
    for prior, current in zip(QUARTER_ORDER, QUARTER_ORDER[1:]):
        quarter_starts[current] = _day(period_meta["quarters"][prior]["period_end"]) + timedelta(days=1)

    reports: dict[str, dict[str, str]] = {}
    for bucket in REPORT_ORDER:
        quarter = REPORT_TO_QUARTER[bucket]
        explicit_start = supplied.get(bucket, {}).get("start")
        source_start = _day(explicit_start) if explicit_start else fy_start
        source_end = _day(period_meta["quarters"][quarter]["period_end"])
        if source_start > source_end:
            raise CanonicalFactError(f"period_start_after_end:{bucket}")
        reports[bucket] = {
            "source_start": source_start.isoformat(),
            "source_end": source_end.isoformat(),
            "source_start_origin": "reported" if explicit_start else "derived_from_fiscal_year_end",
            "quarter_start": quarter_starts[quarter].isoformat(),
            "quarter_end": source_end.isoformat(),
        }
    return {"metadata": period_meta, "reports": reports, "fiscal_year_start": fy_start.isoformat()}


def _unit(
    *,
    unit_kind: str,
    currency: str | None,
    source_scale: Decimal,
    source_label: str | None,
) -> dict[str, Any]:
    return {
        "kind": unit_kind,
        "currency": currency if unit_kind == "currency" else None,
        "scale": 1,
        "source_scale": _json_number(source_scale),
        "source_label": source_label,
    }


def _fact_base(
    *,
    source: str,
    account_id: str,
    source_concept: str | None,
    statement: str,
    nature: str,
    fiscal_year: int,
    fiscal_quarter: str | None,
    period_kind: str,
    period_start: str | None,
    period_end: str,
    report_code: str,
    report_type: str,
    fs_div: str,
    unit: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "account_id": account_id,
        "source_concept": source_concept,
        "statement": statement,
        "nature": nature,
        "value": None,
        "availability": "unavailable",
        "quality": "unavailable",
        "confidence": "none",
        "reason": None,
        "unit": dict(unit),
        "fs_div": fs_div,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "period_kind": period_kind,
        "period_start": period_start,
        "period_end": period_end,
        "report_code": report_code,
        "report_type": report_type,
        "provenance": {},
    }


def _finish_fact(
    base: Mapping[str, Any],
    *,
    value: Any,
    reason: str | None,
    quality: str,
    confidence: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    out = dict(base)
    out["value"] = value
    out["availability"] = "available" if value is not None else "unavailable"
    out["quality"] = quality if value is not None else "unavailable"
    out["confidence"] = confidence if value is not None else "none"
    out["reason"] = reason
    out["provenance"] = dict(provenance)
    return out


def _source_refs(source_points: Mapping[str, Mapping[str, Any]], reports: Iterable[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for report in reports:
        point = source_points.get(report)
        if point:
            refs.append(dict(point.get("provenance") or {}))
    return refs


def _reconcile_series(
    annual: Mapping[str, Any],
    quarters: Mapping[str, Mapping[str, Any]],
    *,
    nature: str,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise CanonicalFactError("negative_reconciliation_tolerance")
    annual_value = _amount(annual.get("value"))
    if nature == "balance":
        q4_value = _amount((quarters.get("Q4") or {}).get("value"))
        if annual_value is None or q4_value is None:
            return {
                "status": "incomplete",
                "reconciled": None,
                "method": "fy_balance_equals_q4_endpoint",
                "annual_value": _json_number(annual_value),
                "quarter_value": _json_number(q4_value),
                "delta": None,
                "reason": "missing:annual_or_q4_balance",
            }
        delta = q4_value - annual_value
        tolerance = max(Decimal(str(absolute_tolerance)), abs(annual_value) * Decimal(str(relative_tolerance)))
        ok = abs(delta) <= tolerance
        return {
            "status": "ok" if ok else "mismatch",
            "reconciled": ok,
            "method": "fy_balance_equals_q4_endpoint",
            "annual_value": _json_number(annual_value),
            "quarter_value": _json_number(q4_value),
            "delta": _json_number(delta),
            "tolerance": _json_number(tolerance),
            "reason": None if ok else "reconciliation:fy_balance_not_equal_to_q4",
        }

    missing = [quarter for quarter in QUARTER_ORDER if _amount((quarters.get(quarter) or {}).get("value")) is None]
    if annual_value is None or missing:
        return {
            "status": "incomplete",
            "reconciled": None,
            "method": "fy_flow_equals_sum_discrete_quarters",
            "annual_value": _json_number(annual_value),
            "quarter_sum": None,
            "delta": None,
            "missing_quarters": missing,
            "reason": "missing:annual_flow" if annual_value is None else "missing:discrete_quarters",
        }
    quarter_sum = sum((_amount(quarters[q]["value"]) or Decimal(0) for q in QUARTER_ORDER), Decimal(0))
    delta = quarter_sum - annual_value
    tolerance = max(Decimal(str(absolute_tolerance)), abs(annual_value) * Decimal(str(relative_tolerance)))
    ok = abs(delta) <= tolerance
    return {
        "status": "ok" if ok else "mismatch",
        "reconciled": ok,
        "method": "fy_flow_equals_sum_discrete_quarters",
        "annual_value": _json_number(annual_value),
        "quarter_sum": _json_number(quarter_sum),
        "delta": _json_number(delta),
        "tolerance": _json_number(tolerance),
        "missing_quarters": [],
        "reason": None if ok else "reconciliation:fy_flow_not_equal_to_sum_discrete_quarters",
    }


def _assemble_series(
    *,
    source: str,
    account_id: str,
    spec: Mapping[str, Any],
    source_points: Mapping[str, Mapping[str, Any]],
    period_layout: Mapping[str, Any],
    fiscal_year: int,
    fs_div: str,
    unit: Mapping[str, Any],
    report_descriptors: Mapping[str, Mapping[str, str]],
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    nature = str(spec["nature"])
    values = {bucket: (source_points.get(bucket) or {}).get("value") for bucket in REPORT_ORDER}
    if nature == "flow":
        converted = discrete_quarters_from_ytd(values, periods=period_layout["metadata"], metric_id=account_id)
    else:
        converted = point_in_time_quarters(values, periods=period_layout["metadata"], metric_id=account_id)

    fy_descriptor = report_descriptors["FY"]
    fy_point = source_points.get("FY") or {}
    annual_base = _fact_base(
        source=source,
        account_id=account_id,
        source_concept=fy_point.get("source_concept"),
        statement=str(spec["statement"]),
        nature=nature,
        fiscal_year=fiscal_year,
        fiscal_quarter=None,
        period_kind="flow_annual" if nature == "flow" else "balance_point_in_time",
        period_start=period_layout["fiscal_year_start"] if nature == "flow" else None,
        period_end=period_layout["reports"]["FY"]["source_end"],
        report_code=fy_descriptor["report_code"],
        report_type=fy_descriptor["report_type"],
        fs_div=fs_div,
        unit=unit,
    )
    annual_value = fy_point.get("value")
    annual = _finish_fact(
        annual_base,
        value=annual_value,
        reason=None if annual_value is not None else str(fy_point.get("reason") or "missing:FY"),
        quality="reported",
        confidence="high",
        provenance=dict(fy_point.get("provenance") or {}),
    )

    quarters: dict[str, dict[str, Any]] = {}
    for bucket in REPORT_ORDER:
        quarter = REPORT_TO_QUARTER[bucket]
        cell = converted[quarter]
        descriptor = report_descriptors[bucket]
        point = source_points.get(bucket) or {}
        base = _fact_base(
            source=source,
            account_id=account_id,
            source_concept=point.get("source_concept"),
            statement=str(spec["statement"]),
            nature=nature,
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter,
            period_kind=str(cell["period_kind"]),
            period_start=(period_layout["reports"][bucket]["quarter_start"] if nature == "flow" else None),
            period_end=str(cell["period_end"]),
            report_code=descriptor["report_code"],
            report_type=descriptor["report_type"],
            fs_div=fs_div,
            unit=unit,
        )
        report_refs = cell.get("source_ytd_reports") or [bucket]
        provenance = {
            "derivation": cell.get("derivation"),
            "source_reports": list(report_refs),
            "source_facts": _source_refs(source_points, report_refs),
            "source_period": {
                "start": period_layout["reports"][bucket]["source_start"],
                "end": period_layout["reports"][bucket]["source_end"],
            },
        }
        value = cell.get("value")
        derived = nature == "flow" and bucket != "Q1"
        quarters[quarter] = _finish_fact(
            base,
            value=value,
            reason=None if value is not None else str(cell.get("reason") or point.get("reason") or f"missing:{bucket}"),
            quality="deterministic_derived" if derived else "reported",
            confidence="high",
            provenance=provenance,
        )

    reconciliation = _reconcile_series(
        annual,
        quarters,
        nature=nature,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    return {
        "account_id": account_id,
        "nature": nature,
        "statement": spec["statement"],
        "annual": annual,
        "quarters": quarters,
        "reconciliation": reconciliation,
    }


def _rows_from_filing(raw: Any) -> list[dict[str, Any]]:
    rows = raw.get("list") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _dart_report_rows(filings: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for report_key, payload in filings.items():
        bucket = _normalise_report_key(str(report_key))
        rows = _rows_from_filing(payload)
        for row in rows:
            row_code = str(row.get("reprt_code") or DART_CODE_BY_BUCKET[bucket])
            if row_code not in DART_REPORTS or DART_REPORTS[row_code]["bucket"] != bucket:
                raise CanonicalFactError(f"dart_report_code_mismatch:{report_key}:{row_code}")
        out[bucket] = rows
    return out


def _pick_dart_rows(
    rows: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    fs_div: str,
) -> tuple[list[dict[str, Any]], str | None]:
    source_ids = [str(value) for value in (spec.get("source_ids") or [])]
    source_names = [str(value) for value in (spec.get("source_names") or [])]
    if not source_ids and not source_names:
        raise CanonicalFactError("dart_spec_requires_source_ids_or_names")
    candidates = [
        dict(row)
        for row in rows
        if str(row.get("fs_div") or "").upper() == fs_div
        and str(row.get("sj_div") or "").upper() == spec["statement"]
    ]
    aggregation = spec.get("aggregation") or {}
    if aggregation:
        for source_id in aggregation.get("total_ids") or []:
            matched = [row for row in candidates if str(row.get("account_id") or "") == source_id]
            if matched:
                matched.sort(key=lambda row: str(row.get("rcept_no") or ""))
                return [matched[-1]], None
        components: list[dict[str, Any]] = []
        for source_id in aggregation.get("component_ids") or []:
            matched = [row for row in candidates if str(row.get("account_id") or "") == source_id]
            if matched:
                matched.sort(key=lambda row: str(row.get("rcept_no") or ""))
                components.append(matched[-1])
        required = int(aggregation.get("required_components") or len(aggregation.get("component_ids") or []))
        if len(components) < required:
            return [], f"missing:aggregation_components:{len(components)}/{required}"
        return components, None
    for source_id in source_ids:
        matched = [row for row in candidates if str(row.get("account_id") or "") == source_id]
        if matched:
            matched.sort(key=lambda row: str(row.get("rcept_no") or ""))
            return [matched[-1]], None
    for source_name in source_names:
        matched = [row for row in candidates if str(row.get("account_nm") or "").strip() == source_name.strip()]
        if matched:
            matched.sort(key=lambda row: str(row.get("rcept_no") or ""))
            return [matched[-1]], None
    return [], None


def _dart_source_point(
    rows: Sequence[Mapping[str, Any]],
    *,
    bucket: str,
    spec: Mapping[str, Any],
    currency: str,
    scale: Decimal,
    source_label: str | None,
    fiscal_year: int,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"value": None, "reason": missing_reason or f"missing:dart_fact_{bucket}", "provenance": {}}
    business_years = {str(row.get("bsns_year") or "") for row in rows if row.get("bsns_year")}
    if business_years and business_years != {str(fiscal_year)}:
        return {
            "value": None,
            "reason": f"fiscal_year_mismatch:{','.join(sorted(business_years))}:{fiscal_year}",
            "source_concept": "+".join(str(row.get("account_id") or "") for row in rows),
            "provenance": {"business_years": sorted(business_years)},
        }
    row_currencies = {_normalise_currency(row.get("currency") or currency) for row in rows}
    if spec["unit_kind"] == "currency" and row_currencies != {currency}:
        return {
            "value": None,
            "reason": f"incompatible_currency:{','.join(sorted(str(item) for item in row_currencies))}:{currency}",
            "source_concept": "+".join(str(row.get("account_id") or "") for row in rows),
            "provenance": {"source_field": None},
        }

    nature = spec["nature"]
    statement = str(spec["statement"])
    field: str | None = None
    if nature == "balance" or bucket == "FY":
        field = "thstrm_amount"
    elif all(_amount(row.get("thstrm_add_amount")) is not None for row in rows):
        field = "thstrm_add_amount"
    elif bucket == "Q1" or statement == "CF" or all(str(row.get("period_value_kind") or "").lower() == "cumulative" for row in rows):
        field = "thstrm_amount"

    raw_values = [_amount(row.get(field)) for row in rows] if field else []
    if not raw_values or any(value is None for value in raw_values):
        reason = "missing:cumulative_flow_amount" if nature == "flow" and bucket not in {"Q1", "FY"} else f"missing:amount_{bucket}"
        value = None
    else:
        reason = None
        value = _json_number(sum((value for value in raw_values if value is not None), Decimal(0)) * scale)
    first = rows[0]
    return {
        "value": value,
        "reason": reason,
        "source_concept": "+".join(str(row.get("account_id") or row.get("account_nm") or "") for row in rows),
        "provenance": {
            "provider": "OpenDART",
            "filing_id": first.get("rcept_no"),
            "report_code": first.get("reprt_code") or DART_CODE_BY_BUCKET[bucket],
            "business_year": first.get("bsns_year"),
            "source_account_id": first.get("account_id"),
            "source_account_name": first.get("account_nm"),
            "source_field": field,
            "source_value": first.get(field) if field else None,
            "source_currency": currency,
            "source_scale": _json_number(scale),
            "source_unit_label": source_label,
            "aggregation": "reported_total" if len(rows) == 1 else "sum_complete_components",
            "source_facts": [
                {
                    "filing_id": row.get("rcept_no"),
                    "account_id": row.get("account_id"),
                    "account_name": row.get("account_nm"),
                    "source_field": field,
                    "source_value": row.get(field) if field else None,
                }
                for row in rows
            ],
        },
    }


def adapt_dart_filings(
    filings: Mapping[str, Any],
    *,
    account_specs: Mapping[str, Mapping[str, Any]],
    fiscal_year_end: str | date,
    entity_id: str | None = None,
    fs_div: str = "CFS",
    currency: str = "KRW",
    scale: int | float | str | Decimal = 1,
    source_unit_label: str | None = "원",
    report_periods: Mapping[str, Mapping[str, Any]] | None = None,
    absolute_tolerance: float = 0.0,
    relative_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Adapt four DART business/interim filings into canonical fact series.

    ``filings`` keys may be DART report codes (11013/11012/11014/11011) or
    Q1/H1/Q3/FY.  ``scale`` is the multiplier from the declared source unit to
    absolute units.  No CFS→OFS fallback is performed.
    """
    scope = str(fs_div).upper()
    if scope not in {"CFS", "OFS"}:
        raise CanonicalFactError(f"invalid_fs_div:{fs_div}")
    canonical_currency = _normalise_currency(currency)
    if not canonical_currency:
        raise CanonicalFactError("missing_currency")
    source_scale = _amount(scale)
    if source_scale is None or source_scale <= 0:
        raise CanonicalFactError("invalid_scale")
    specs = _normalise_specs(account_specs)
    rows_by_report = _dart_report_rows(filings)
    layout = _normalise_report_periods(fiscal_year_end, report_periods)
    fiscal_year = int(layout["metadata"]["fiscal_year"])
    report_descriptors = {
        bucket: {
            "report_code": DART_CODE_BY_BUCKET[bucket],
            "report_type": DART_REPORTS[DART_CODE_BY_BUCKET[bucket]]["report_type"],
        }
        for bucket in REPORT_ORDER
    }

    series: dict[str, Any] = {}
    for account_id, spec in specs.items():
        source_points: dict[str, dict[str, Any]] = {}
        for bucket in REPORT_ORDER:
            selected_rows, missing_reason = _pick_dart_rows(
                rows_by_report.get(bucket, []), spec, fs_div=scope
            )
            source_points[bucket] = _dart_source_point(
                selected_rows,
                bucket=bucket,
                spec=spec,
                currency=canonical_currency,
                scale=source_scale,
                source_label=source_unit_label,
                fiscal_year=fiscal_year,
                missing_reason=missing_reason,
            )
        series[account_id] = _assemble_series(
            source="DART",
            account_id=account_id,
            spec=spec,
            source_points=source_points,
            period_layout=layout,
            fiscal_year=fiscal_year,
            fs_div=scope,
            unit=_unit(
                unit_kind=spec["unit_kind"],
                currency=canonical_currency,
                source_scale=source_scale,
                source_label=source_unit_label,
            ),
            report_descriptors=report_descriptors,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "DART",
        "entity_id": entity_id,
        "fiscal_year": fiscal_year,
        "fiscal_year_start": layout["fiscal_year_start"],
        "fiscal_year_end": layout["metadata"]["fiscal_year_end"],
        "fs_div": scope,
        "currency": canonical_currency,
        "series": series,
    }


def default_sec_account_specs() -> dict[str, dict[str, Any]]:
    """Return the existing SEC concept catalogue in canonical-spec form."""
    from .sec_xbrl import SJ, US_GAAP_TAGS

    return {
        account_id: {
            "nature": "balance" if SJ.get(account_id) == "BS" else "flow",
            "statement": SJ.get(account_id, "IS"),
            "sec_concepts": list(concepts),
            "unit_kind": "currency",
        }
        for account_id, concepts in US_GAAP_TAGS.items()
    }


def default_dart_account_specs(
    accounts_map: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build canonical DART specs from the engine's reviewed account map."""
    source = accounts_map or load_accounts_map()
    out: dict[str, dict[str, Any]] = {}
    for account_id, raw in (source.get("accounts") or {}).items():
        statement = str(raw.get("sj") or "").upper()
        source_ids = [str(item) for item in (raw.get("ids") or []) if not str(item).startswith("us-gaap_")]
        source_names = [str(item) for item in (raw.get("names") or [])]
        if statement not in _STATEMENT_NAMES or not (source_ids or source_names):
            continue
        out[str(account_id)] = {
            "nature": "balance" if statement in {"BS", "SCE"} else "flow",
            "statement": statement,
            "source_ids": source_ids,
            "source_names": source_names,
            "unit_kind": "currency",
            "aggregation": deepcopy(raw.get("aggregation") or {}),
        }
    return out


def _select_sec_point(
    facts: Mapping[str, Any],
    *,
    account_id: str,
    spec: Mapping[str, Any],
    bucket: str,
    expected_start: str,
    expected_end: str,
    currency: str,
) -> dict[str, Any]:
    concepts = [str(value) for value in (spec.get("sec_concepts") or [])]
    if not concepts:
        raise CanonicalFactError("sec_spec_requires_concepts")
    gaap = ((facts.get("facts") or {}).get("us-gaap") or {})
    descriptor = SEC_REPORTS[bucket]
    for concept_name in concepts:
        # A standard SEC current lease-liability concept is a maturity bucket,
        # not a total liability.  This defensive check protects callers that
        # bring their own account specs as well as the default tag catalogue.
        if account_id == "LEASE_LIABILITIES" and concept_name.lower().endswith("current"):
            continue
        concept = gaap.get(concept_name)
        if not isinstance(concept, Mapping):
            continue
        units = concept.get("units") or {}
        requested_unit = str(spec.get("sec_unit") or currency)
        points = units.get(requested_unit) or []
        candidates: list[dict[str, Any]] = []
        for raw in points:
            if not isinstance(raw, Mapping) or _amount(raw.get("val")) is None:
                continue
            form = str(raw.get("form") or "").upper()
            if form not in {descriptor["report_code"], descriptor["report_code"] + "/A"}:
                continue
            fp = str(raw.get("fp") or "").upper()
            if fp and fp != descriptor["fp"]:
                continue
            if str(raw.get("end") or "") != expected_end:
                continue
            if spec["nature"] == "flow" and str(raw.get("start") or "") != expected_start:
                continue
            candidates.append(dict(raw))
        if not candidates:
            continue
        candidates.sort(key=lambda row: (str(row.get("filed") or ""), str(row.get("accn") or "")))
        chosen = candidates[-1]
        value = _json_number(_amount(chosen["val"]))
        return {
            "value": value,
            "reason": None,
            "source_concept": f"us-gaap:{concept_name}",
            "provenance": {
                "provider": "SEC companyfacts",
                "filing_id": chosen.get("accn"),
                "filed_at": chosen.get("filed"),
                "form": chosen.get("form"),
                "fiscal_period": chosen.get("fp"),
                "source_concept": f"us-gaap:{concept_name}",
                "source_value": chosen.get("val"),
                "source_unit": requested_unit,
                "source_start": chosen.get("start"),
                "source_end": chosen.get("end"),
                "frame": chosen.get("frame"),
            },
        }
    return {
        "value": None,
        "reason": f"missing:sec_exact_period_fact_{bucket}",
        "provenance": {
            "provider": "SEC companyfacts",
            "required_start": expected_start if spec["nature"] == "flow" else None,
            "required_end": expected_end,
            "required_form": descriptor["report_code"],
            "concepts_tried": concepts,
        },
    }


def adapt_sec_companyfacts(
    facts: Mapping[str, Any],
    *,
    fiscal_year_end: str | date,
    account_specs: Mapping[str, Mapping[str, Any]] | None = None,
    entity_id: str | None = None,
    fs_div: str = "CFS",
    currency: str = "USD",
    report_periods: Mapping[str, Mapping[str, Any]] | None = None,
    absolute_tolerance: float = 0.0,
    relative_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Adapt SEC companyfacts to the same canonical schema as DART.

    Duration facts must exactly match the fiscal YTD bounds.  A quarterly SEC
    fact with only a three-month duration is therefore never mislabeled as H1
    or Q3 YTD.
    """
    scope = str(fs_div).upper()
    if scope != "CFS":
        raise CanonicalFactError("sec_companyfacts_requires_cfs")
    canonical_currency = _normalise_currency(currency)
    if not canonical_currency:
        raise CanonicalFactError("missing_currency")
    specs = _normalise_specs(account_specs or default_sec_account_specs())
    layout = _normalise_report_periods(fiscal_year_end, report_periods)
    fiscal_year = int(layout["metadata"]["fiscal_year"])
    report_descriptors = {
        bucket: {
            "report_code": SEC_REPORTS[bucket]["report_code"],
            "report_type": SEC_REPORTS[bucket]["report_type"],
        }
        for bucket in REPORT_ORDER
    }
    series: dict[str, Any] = {}
    for account_id, spec in specs.items():
        source_points: dict[str, dict[str, Any]] = {}
        for bucket in REPORT_ORDER:
            period = layout["reports"][bucket]
            source_points[bucket] = _select_sec_point(
                facts,
                account_id=account_id,
                spec=spec,
                bucket=bucket,
                expected_start=period["source_start"],
                expected_end=period["source_end"],
                currency=canonical_currency,
            )
        series[account_id] = _assemble_series(
            source="SEC",
            account_id=account_id,
            spec=spec,
            source_points=source_points,
            period_layout=layout,
            fiscal_year=fiscal_year,
            fs_div=scope,
            unit=_unit(
                unit_kind=spec["unit_kind"],
                currency=canonical_currency,
                source_scale=Decimal(1),
                source_label=canonical_currency,
            ),
            report_descriptors=report_descriptors,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "SEC",
        "entity_id": entity_id,
        "entity_name": facts.get("entityName"),
        "fiscal_year": fiscal_year,
        "fiscal_year_start": layout["fiscal_year_start"],
        "fiscal_year_end": layout["metadata"]["fiscal_year_end"],
        "fs_div": scope,
        "currency": canonical_currency,
        "series": series,
    }


def make_labeled_proxy(
    unavailable_fact: Mapping[str, Any],
    *,
    value: int | float,
    metric_id: str,
    entity_class: str,
    estimate_policy_id: str,
    method: str,
    reason: str,
    confidence: str,
    source_references: Sequence[Mapping[str, Any]],
    visibility: str = "expert",
) -> dict[str, Any]:
    """Turn an unavailable cell into a clearly labelled external proxy.

    Adapters never call this automatically.  A later domain-specific layer may
    use it only when it can supply auditable inputs.  ``high`` confidence is
    deliberately rejected because a proxy is not a reported or exactly
    derived filing fact.
    """
    if unavailable_fact.get("availability") != "unavailable":
        raise CanonicalFactError("proxy_requires_unavailable_fact")
    policy = PROXY_POLICIES.get(str(estimate_policy_id))
    if policy is None:
        raise CanonicalFactError("proxy_requires_approved_estimate_policy")
    metric = str(metric_id).strip().lower()
    entity = str(entity_class).strip().lower()
    view = str(visibility).strip().lower()
    if metric not in policy["metrics"]:
        raise CanonicalFactError("proxy_metric_not_allowed_by_policy")
    if entity not in policy["entity_classes"]:
        raise CanonicalFactError("proxy_entity_class_not_allowed_by_policy")
    if view not in policy["visibility"]:
        raise CanonicalFactError("proxy_visibility_not_allowed_by_policy")
    if not str(method).strip():
        raise CanonicalFactError("proxy_requires_method")
    if not str(reason).strip():
        raise CanonicalFactError("proxy_requires_reason")
    if confidence not in _CONFIDENCE - {"high"}:
        raise CanonicalFactError("proxy_confidence_must_be_low_or_medium")
    if not source_references:
        raise CanonicalFactError("proxy_requires_source_references")
    proxy_value = _amount(value)
    if proxy_value is None:
        raise CanonicalFactError("proxy_requires_numeric_value")
    out = deepcopy(dict(unavailable_fact))
    out.update(
        {
            "value": _json_number(proxy_value),
            "availability": "available",
            "quality": "proxy",
            "confidence": confidence,
            "reason": reason,
            "metric_id": metric,
            "entity_class": entity,
            "estimate_policy_id": estimate_policy_id,
            "visibility": view,
            "provenance": {
                "derivation": method,
                "source_facts": [dict(ref) for ref in source_references],
                "proxy": True,
                "estimate_policy_id": estimate_policy_id,
            },
        }
    )
    return out
