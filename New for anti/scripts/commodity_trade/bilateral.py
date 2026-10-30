"""Transport-independent bilateral partitions; no fetching or implicit imputation.

One partition is one source/reporter/HS revision/period/statistical scope. Never
merge exporter and importer reports, different HS headings, or monthly/annual
fallbacks. Unknown coverage is deliberately the default.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
import re
from typing import Any


METRICS = ("net_weight_kg", "trade_value_usd", "quantity_bbl")
UNITS = dict(zip(METRICS, ("kg", "USD", "bbl")))


class ContractError(ValueError):
    """Invalid or ambiguous data must not replace a published partition."""


def period_key(period: str, frequency: str) -> str:
    if not isinstance(period, str):
        raise ContractError("period must be a string")
    if frequency == "M" and re.fullmatch(r"\d{6}", period):
        try:
            date(int(period[:4]), int(period[4:]), 1)
        except ValueError as exc:
            raise ContractError("invalid monthly period") from exc
    elif frequency == "A" and re.fullmatch(r"\d{4}", period):
        if int(period) < 1:
            raise ContractError("invalid annual period")
    else:
        raise ContractError("frequency/period mismatch")
    return period


def partner_code(value: Any) -> str:
    # Source Comtrade codes, not an inferred ISO country list. Includes World=0.
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,3}", str(value)):
        raise ContractError("invalid source partner code")
    return str(int(value))


def number(value: Any) -> float | None:
    if value is None or value in ("", "NA", "N/A", "..", "-"):
        return None
    if isinstance(value, bool):
        raise ContractError("boolean is not a measurement")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("invalid measurement") from exc
    if not math.isfinite(result) or result < 0:
        raise ContractError("measurement must be finite and nonnegative")
    return result


def validate_meta(meta: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(meta)
    for key in ("source", "scope_id", "hs_version", "value_basis"):
        if not isinstance(out.get(key), str) or not out[key].strip():
            raise ContractError(f"missing {key}; explicitly use unknown if unavailable")
    out["reporter"] = partner_code(out.get("reporter"))
    if out["reporter"] == "0":
        raise ContractError("World cannot be the reporter")
    if not isinstance(out.get("hs"), str) or not re.fullmatch(r"\d{4}|\d{6}", out["hs"]):
        raise ContractError("exact HS4/HS6 required")
    period_key(out.get("period"), out.get("frequency"))
    for key in ("all_partners_verified", "partners_disjoint"):
        if key in out and not isinstance(out[key], bool):
            raise ContractError(f"{key} must be boolean")
        out.setdefault(key, False)
    # Identity is based on actual code, never a conflicting legacy display slug.
    out["commodity_id"] = f"HS:{out['hs_version']}:{out['hs']}"
    return out


def build_partition(meta: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build X and M separately from adapter-normalized rows.

    Rows: partner, flow, period, metrics (explicit kg/USD/bbl), optional quality.
    World rows are denominators only. Conflicting duplicate cells fail closed;
    adapters must resolve customs/transport/HS aggregation before calling us.
    """
    meta = validate_meta(meta)
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("flow") not in {"X", "M"}:
            raise ContractError("flow must be X or M")
        if row.get("period") != meta["period"]:
            raise ContractError("row period differs from partition")
        partner = partner_code(row.get("partner"))
        metrics = row.get("metrics", {})
        if not isinstance(metrics, dict) or set(metrics) - set(METRICS):
            raise ContractError("unknown metric or unit")
        cell = {
            "partner": partner,
            "flow": row["flow"],
            "metrics": {key: number(metrics.get(key)) for key in METRICS},
            "quality": deepcopy(row.get("quality", {})),
        }
        key = row["flow"], partner
        if key in cells and cells[key] != cell:
            raise ContractError("conflicting duplicate partner/flow; aggregation required upstream")
        cells[key] = cell

    flows = {}
    for flow in ("X", "M"):
        world = cells.get((flow, "0"))
        partners = [deepcopy(v) for (f, p), v in sorted(cells.items()) if f == flow and p != "0"]
        analysis = {}
        for metric in METRICS:
            known = [p for p in partners if p["metrics"][metric] is not None]
            denom = world["metrics"][metric] if world else None
            comparable = meta["scope_id"] != "unknown" and meta["hs_version"] != "unknown"
            if metric == "trade_value_usd" and meta["value_basis"] == "unknown":
                comparable = False
            reason = None
            if not comparable:
                reason = "unknown_comparison_scope"
            elif denom is None:
                reason = "world_total_missing"
            elif denom == 0:
                reason = "world_total_zero"
            elif any(p["metrics"][metric] > denom for p in known):
                reason = "partner_exceeds_world"
            coverage = None
            if meta["partners_disjoint"] and known and denom and reason is None:
                # Sum ratios rather than enormous source values. Never clip >100%.
                fraction = math.fsum(p["metrics"][metric] / denom for p in known)
                if fraction > 1.000001:
                    reason = "observed_sum_exceeds_world"
                else:
                    coverage = round(fraction * 100, 8)
            ranks = {}
            for i, value in enumerate(sorted((p["metrics"][metric] for p in known), reverse=True), 1):
                ranks.setdefault(value, i)  # competition ranks: 1,1,3
            rank_scope = "observed_partner_codes"
            if meta["all_partners_verified"] and meta["partners_disjoint"] and len(known) == len(partners):
                rank_scope = "all_reported_partner_codes"
            for p in partners:
                value = p["metrics"][metric]
                p.setdefault("analysis", {})[metric] = {
                    "share_pct": round(value / denom * 100, 8) if value is not None and reason is None else None,
                    "share_reason": "measurement_missing" if value is None else reason,
                    "rank": ranks.get(value) if value is not None else None,
                    "rank_scope": rank_scope,
                }
            analysis[metric] = {
                "unit": UNITS[metric], "world_total": denom,
                "share_reason": reason, "known_partner_count": len(known),
                "observed_coverage_pct": coverage,
                "world_quality": deepcopy(world["quality"]) if world else None,
            }
        for p in partners:
            p["exporter"] = meta["reporter"] if flow == "X" else p["partner"]
            p["importer"] = p["partner"] if flow == "X" else meta["reporter"]
        flows[flow] = {"rows": partners, "metrics": analysis, "status": "observed" if partners else "no_partner_observations"}
    return {"schema": "bilateral-partition-v1", "meta": meta, "flows": flows}


def country_view(partition: dict[str, Any], focus: str) -> list[dict[str, Any]]:
    """Mirror a *direction*, never the importing country's World denominator."""
    focus = partner_code(focus)
    result = []
    reporter = partition["meta"]["reporter"]
    for flow, block in partition["flows"].items():
        for original in block["rows"]:
            if focus not in {original["exporter"], original["importer"]}:
                continue
            row = deepcopy(original)
            row["reporter"] = reporter
            row["source_flow"] = flow
            row["focus_flow"] = flow if focus == reporter else ("M" if flow == "X" else "X")
            row["counterparty"] = row["partner"] if focus == reporter else reporter
            row["reporting_basis"] = "direct_report" if focus == reporter else "partner_report_mirror"
            if focus != reporter:
                for metric in METRICS:
                    row["analysis"][metric] = {
                        "share_pct": None, "share_reason": "mirror_denominator_not_comparable",
                        "rank": None, "rank_scope": "not_ranked",
                    }
            result.append(row)
    return result
