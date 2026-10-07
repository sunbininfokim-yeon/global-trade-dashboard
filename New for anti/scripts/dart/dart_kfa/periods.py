"""Period-integrity helpers for Korean filing flows and balances.

OpenDART interim statements are cumulative year-to-date (YTD) reports.  This
module is deliberately independent of the HTTP client and metric engine: it
accepts already-normalised numbers and returns explicit period metadata.  A
missing predecessor never falls back to a cumulative number labelled as a
quarter.

The public helpers use the four OpenDART report buckets:

* ``Q1`` — first-quarter YTD (also the standalone first quarter)
* ``H1`` — first-half YTD
* ``Q3`` — first-nine-month YTD
* ``FY`` — full-year

Flows are differenced; balances are point-in-time values and are never
differenced.  This distinction is part of the returned contract rather than
being left to a chart renderer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


REPORT_TO_QUARTER = {"Q1": "Q1", "H1": "Q2", "Q3": "Q3", "FY": "Q4"}
REPORT_ORDER = ("Q1", "H1", "Q3", "FY")
QUARTER_ORDER = ("Q1", "Q2", "Q3", "Q4")
_FLOW_PREDECESSOR = {"Q1": None, "H1": "Q1", "Q3": "H1", "FY": "Q3"}


class PeriodContractError(ValueError):
    """Raised when fiscal-period metadata is malformed or self-contradictory."""


def _iso_day(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PeriodContractError(f"invalid_iso_date:{value}") from exc


def _add_months(value: date, months: int) -> date:
    """Calendar-month shift preserving the day when possible.

    Financial year ends are normally month ends.  Clamping makes the helper
    deterministic for unusual dates such as 30 November without introducing a
    December-year assumption.
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))


def fiscal_period_metadata(
    fiscal_year_end: str | date,
    *,
    report_ends: Mapping[str, str | date] | None = None,
) -> dict[str, Any]:
    """Build the four fiscal-quarter endpoints from the reported FY end.

    ``fiscal_year_end`` is required so callers cannot silently label every
    company as 31 December.  A source adapter may pass actual report ends for
    Q1/H1/Q3/FY; when supplied they are validated for order and FY agreement,
    then retained as source metadata.  Otherwise the quarter endpoints are
    derived by month offset from the FY end.
    """
    fy_end = _iso_day(fiscal_year_end)
    derived = {
        "Q1": _add_months(fy_end, -9),
        "Q2": _add_months(fy_end, -6),
        "Q3": _add_months(fy_end, -3),
        "Q4": fy_end,
    }
    actual: dict[str, date] = {}
    if report_ends:
        unknown = set(report_ends) - set(REPORT_TO_QUARTER)
        if unknown:
            raise PeriodContractError("unknown_report_end:" + ",".join(sorted(unknown)))
        for report, raw_end in report_ends.items():
            actual[REPORT_TO_QUARTER[report]] = _iso_day(raw_end)
        if "Q4" in actual and actual["Q4"] != fy_end:
            raise PeriodContractError("fy_end_mismatch:FY")
        ordered_actual = [actual[q] for q in QUARTER_ORDER if q in actual]
        if any(later <= earlier for earlier, later in zip(ordered_actual, ordered_actual[1:])):
            raise PeriodContractError("report_ends_not_strictly_increasing")

    quarters: dict[str, dict[str, Any]] = {}
    for quarter in QUARTER_ORDER:
        source_report = REPORT_ORDER[QUARTER_ORDER.index(quarter)]
        endpoint = actual.get(quarter, derived[quarter])
        quarters[quarter] = {
            "fiscal_year": fy_end.year,
            "fiscal_quarter": quarter,
            "period_end": endpoint.isoformat(),
            "source_report": source_report,
            "endpoint_origin": "reported" if quarter in actual else "derived_from_fiscal_year_end",
        }
    return {
        "fiscal_year": fy_end.year,
        "fiscal_year_end": fy_end.isoformat(),
        "quarters": quarters,
    }


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _public_number(value: Decimal) -> float:
    """Use floats at the JSON boundary, after exact subtraction internally."""
    return float(value)


def _require_metadata(periods: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not periods or not isinstance(periods.get("quarters"), Mapping):
        raise PeriodContractError("missing_fiscal_period_metadata")
    quarters = periods["quarters"]
    missing = [q for q in QUARTER_ORDER if q not in quarters]
    if missing:
        raise PeriodContractError("missing_quarter_metadata:" + ",".join(missing))
    for quarter in QUARTER_ORDER:
        meta = quarters[quarter]
        if not isinstance(meta, Mapping):
            raise PeriodContractError(f"invalid_quarter_metadata:{quarter}")
        if not isinstance(meta.get("fiscal_year"), int):
            raise PeriodContractError(f"missing_quarter_fiscal_year:{quarter}")
        if "period_end" not in meta:
            raise PeriodContractError(f"missing_quarter_period_end:{quarter}")
        _iso_day(meta["period_end"])
    return quarters


def discrete_quarters_from_ytd(
    ytd_values: Mapping[str, Any],
    *,
    periods: Mapping[str, Any],
    metric_id: str | None = None,
    direct_values: Mapping[str, Any] | None = None,
    absolute_tolerance: float = 0.0,
    relative_tolerance: float = 0.0,
) -> dict[str, dict[str, Any]]:
    """Convert one flow's DART YTD reports into standalone quarters.

    Missing predecessor reports suppress only the affected quarter.  For
    example, a present H1 with absent Q1 does *not* become Q2, while Q3 can
    still be calculated if both Q3 and H1 are present.

    ``direct_values`` is optional and uses ``Q1`` through ``Q4`` keys.  A
    caller may provide one only when the source explicitly identifies the
    amount as a standalone quarter; a generic interim ``thstrm_amount`` is
    not enough evidence.  A valid direct observation takes precedence over a
    YTD subtraction, but when both are present they must reconcile within the
    supplied tolerance.  A disagreement is a filing/adapter conflict, not a
    licence to pick the more convenient figure.
    """
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise PeriodContractError("negative_reconciliation_tolerance")
    quarter_meta = _require_metadata(periods)
    direct_values = direct_values or {}
    out: dict[str, dict[str, Any]] = {}
    for report in REPORT_ORDER:
        quarter = REPORT_TO_QUARTER[report]
        current = _number(ytd_values.get(report))
        predecessor_report = _FLOW_PREDECESSOR[report]
        predecessor = _number(ytd_values.get(predecessor_report)) if predecessor_report else None
        direct = _number(direct_values.get(quarter))
        base = {
            "metric_id": metric_id,
            "period_kind": "flow_discrete_quarter",
            "fiscal_year": quarter_meta[quarter]["fiscal_year"],
            "fiscal_quarter": quarter,
            "period_end": quarter_meta[quarter]["period_end"],
            "source_report": report,
            "source_ytd_reports": [report] if predecessor_report is None else [predecessor_report, report],
        }
        ytd_value: Decimal | None = None
        ytd_reason: str | None = None
        if current is None:
            ytd_reason = f"missing:ytd_{report}"
        elif predecessor_report and predecessor is None:
            ytd_reason = f"missing:predecessor_ytd_{predecessor_report}"
        else:
            ytd_value = current if predecessor is None else current - predecessor

        if direct is not None:
            if ytd_value is not None:
                tolerance = max(
                    Decimal(str(absolute_tolerance)),
                    abs(ytd_value) * Decimal(str(relative_tolerance)),
                )
                if abs(direct - ytd_value) > tolerance:
                    out[quarter] = {
                        **base,
                        "value": None,
                        "reason": "conflict:direct_quarter_vs_ytd_derivation",
                        "direct_value": _public_number(direct),
                        "ytd_derived_value": _public_number(ytd_value),
                        "tolerance": _public_number(tolerance),
                        "direct_source_report": report,
                    }
                    continue
            out[quarter] = {
                **base,
                "value": _public_number(direct),
                "reason": None,
                "derivation": "reported_direct_quarter",
                "direct_source_report": report,
                "direct_value": _public_number(direct),
                "ytd_derived_value": _public_number(ytd_value) if ytd_value is not None else None,
            }
            continue

        if ytd_value is None:
            out[quarter] = {**base, "value": None, "reason": ytd_reason}
            continue
        out[quarter] = {
            **base,
            "value": _public_number(ytd_value),
            "reason": None,
            "derivation": "reported_q1_ytd" if predecessor_report is None else f"{report}_ytd_minus_{predecessor_report}_ytd",
        }
    return out


def point_in_time_quarters(
    balance_values: Mapping[str, Any],
    *,
    periods: Mapping[str, Any],
    metric_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Map balance-sheet reports to quarter endpoints without differencing."""
    quarter_meta = _require_metadata(periods)
    out: dict[str, dict[str, Any]] = {}
    for report in REPORT_ORDER:
        quarter = REPORT_TO_QUARTER[report]
        value = _number(balance_values.get(report))
        base = {
            "metric_id": metric_id,
            "period_kind": "balance_point_in_time",
            "fiscal_year": quarter_meta[quarter]["fiscal_year"],
            "fiscal_quarter": quarter,
            "period_end": quarter_meta[quarter]["period_end"],
            "source_report": report,
            "source_ytd_reports": [report],
            "derivation": "reported_point_in_time_not_differenced",
        }
        out[quarter] = (
            {**base, "value": _public_number(value), "reason": None}
            if value is not None
            else {**base, "value": None, "reason": f"missing:balance_{report}"}
        )
    return out


def annual_fcf(cfo: Any, capex: Any) -> float | None:
    """Return FCF = CFO − |Capex|, retaining the source's Capex sign policy."""
    cfo_value, capex_value = _number(cfo), _number(capex)
    if cfo_value is None or capex_value is None:
        return None
    return _public_number(cfo_value - abs(capex_value))


def quarterly_fcf_from_ytd(
    cfo_ytd: Mapping[str, Any],
    capex_ytd: Mapping[str, Any],
    *,
    periods: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Derive standalone quarterly FCF only from standalone quarterly flows."""
    cfo_quarters = discrete_quarters_from_ytd(cfo_ytd, periods=periods, metric_id="CFO")
    capex_quarters = discrete_quarters_from_ytd(capex_ytd, periods=periods, metric_id="CAPEX")
    out: dict[str, dict[str, Any]] = {}
    for quarter in QUARTER_ORDER:
        cfo_cell, capex_cell = cfo_quarters[quarter], capex_quarters[quarter]
        base = {
            "metric_id": "FCF",
            "period_kind": "flow_discrete_quarter",
            "fiscal_year": cfo_cell["fiscal_year"],
            "fiscal_quarter": quarter,
            "period_end": cfo_cell["period_end"],
            "source_report": cfo_cell["source_report"],
            "definition": "CFO - abs(Capex)",
            "components": {"cfo": cfo_cell["value"], "capex": capex_cell["value"]},
        }
        if cfo_cell["value"] is None or capex_cell["value"] is None:
            missing = []
            if cfo_cell["value"] is None:
                missing.append("cfo:" + str(cfo_cell["reason"]))
            if capex_cell["value"] is None:
                missing.append("capex:" + str(capex_cell["reason"]))
            out[quarter] = {**base, "value": None, "reason": "missing:" + ",".join(missing)}
        else:
            out[quarter] = {
                **base,
                "value": annual_fcf(cfo_cell["value"], capex_cell["value"]),
                "reason": None,
            }
    return out


def reconcile_fcf(
    cfo_ytd: Mapping[str, Any],
    capex_ytd: Mapping[str, Any],
    quarterly_fcf: Mapping[str, Mapping[str, Any]],
    *,
    absolute_tolerance: float = 0.0,
    relative_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Reconcile FY FCF with the sum of discrete quarters.

    A result is ``incomplete`` (not a passing reconciliation) when the annual
    source or any quarter is missing.  ``mismatch`` preserves the delta so a
    company-specific issue, such as the LG Chem case, is observable rather
    than rounded away.
    """
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise PeriodContractError("negative_reconciliation_tolerance")
    annual = annual_fcf(cfo_ytd.get("FY"), capex_ytd.get("FY"))
    quarter_values: list[float] = []
    missing_quarters: list[str] = []
    for quarter in QUARTER_ORDER:
        cell = quarterly_fcf.get(quarter)
        value = _number(cell.get("value")) if cell else None
        if value is None:
            missing_quarters.append(quarter)
        else:
            quarter_values.append(_public_number(value))

    if annual is None or missing_quarters:
        return {
            "status": "incomplete",
            "reconciled": None,
            "annual_fcf": annual,
            "quarter_sum": None if missing_quarters else float(sum(quarter_values)),
            "delta": None,
            "missing_quarters": missing_quarters,
            "reason": "missing:annual_fcf" if annual is None else "missing:discrete_quarters",
        }

    quarter_sum = float(sum(quarter_values))
    delta = quarter_sum - annual
    tolerance = max(float(absolute_tolerance), abs(annual) * float(relative_tolerance))
    reconciled = abs(delta) <= tolerance
    return {
        "status": "ok" if reconciled else "mismatch",
        "reconciled": reconciled,
        "annual_fcf": annual,
        "quarter_sum": quarter_sum,
        "delta": delta,
        "tolerance": tolerance,
        "missing_quarters": [],
        "reason": None if reconciled else "reconciliation:fy_fcf_not_equal_to_sum_discrete_quarters",
    }
