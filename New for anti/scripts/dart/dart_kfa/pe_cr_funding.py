"""Verified note schedules, bond duration and segments; no inferred instruments."""
from datetime import date
from math import isfinite
from urllib.parse import urlsplit


def _numeric(value):
    return type(value) in (float, int) and isfinite(value) and abs(value) <= 10**20


def _amount(value):
    return _numeric(value) and value >= 0


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _source(row):
    source = row.get("source") or {}
    if not isinstance(source, dict) or not all(_text(source.get(k)) for k in ("filing_id", "table", "url")):
        raise ValueError("missing:disclosure_source")
    u = urlsplit(source["url"])
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("invalid:disclosure_source_url")
    return {k: source[k] for k in ("filing_id", "table", "url")}


def _packet(packet, schema, canonical, end):
    if not isinstance(packet, dict) or packet.get("schema_version") != schema:
        raise ValueError("invalid:disclosure_profile_schema")
    if not end or packet.get("as_of") != end or any(not packet.get(k) or packet[k] != canonical.get(k) for k in ("entity_id", "fs_div", "currency")):
        raise ValueError("incompatible:disclosure_entity_scope_currency_or_date")
    if type(packet.get("scale")) is not int or packet["scale"] != 1:
        raise ValueError("requires:absolute_disclosure_currency_units")


def _maturity_table(table):
    if table.get("side") not in {"asset", "liability"} or table.get("measure") not in {"principal", "undiscounted_contractual_cash_flow", "reported_corporate_bond_outstanding"}:
        raise ValueError("invalid:maturity_side_or_measure")
    if not _text(table.get("id")) or not _text(table.get("group")):
        raise ValueError("missing:maturity_group")
    source = _source(table)
    buckets = table.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        raise ValueError("missing:maturity_buckets")
    after, paid, within = 0, 0, None
    selected = []
    for row in buckets:
        low, high, value = (row.get(k) for k in ("from_month", "to_month", "amount"))
        if after is None or type(low) is not int or low != after or (high is not None and (type(high) is not int or high <= low)) or not _amount(value):
            raise ValueError("invalid:maturity_bucket_order_or_amount")
        selected.append({"from_month": low, "to_month": high, "amount": value})
        paid += value
        if high == 12:
            within = paid
        after = high
    return {"id": table["id"], "group": table["group"], "side": table["side"], "measure": table["measure"],
            "buckets": selected, "reported_covered_total": paid, "within_12_months": within,
            "within_12_months_reason": "missing:exact_12_month_bucket_boundary" if within is None else None,
            "covers_open_ended_tail": after is None, "source": source}


def _bond_duration(bond, as_of):
    if not _text(bond.get("id")) or bond.get("side") not in {"asset", "liability"}:
        raise ValueError("invalid:bond_identity_or_side")
    result = {"id": bond["id"], "side": bond["side"], "macaulay_years": None, "modified_years": None, "reason": None}
    if bond.get("fixed_non_callable") is not True or bond.get("complete_schedule") is not True:
        return {**result, "reason": "requires:complete_fixed_non_callable_cashflows"}
    source = _source(bond)
    ytm, face = bond.get("annual_effective_ytm"), bond.get("remaining_principal")
    if not _numeric(ytm) or ytm <= -1 or bond.get("yield_as_of") != as_of or not _text(bond.get("yield_source")):
        return {**result, "reason": "requires:dated_annual_effective_ytm", "source": source}
    flows = bond.get("cashflows")
    if not isinstance(flows, list) or not flows or not _amount(face) or face <= 0:
        return {**result, "reason": "missing:bond_cashflows_or_principal", "source": source}
    principal, pv_total, weighted = 0, 0, 0
    prev = anchor = date.fromisoformat(as_of)
    for cf in flows:
        due = date.fromisoformat(cf["date"])
        coupon, repayment = cf.get("coupon"), cf.get("principal")
        if due <= prev or not _amount(coupon) or not _amount(repayment) or coupon + repayment <= 0:
            raise ValueError("invalid:bond_cashflow_order_or_amount")
        t = (due - anchor).days / 365
        try:
            pv = (coupon + repayment) / (1 + ytm)**t
        except (OverflowError, ZeroDivisionError):
            return {**result, "reason": "nonfinite:discounted_cashflows", "source": source}
        principal += repayment
        pv_total += pv
        weighted += t * pv
        prev = due
    if principal != face or flows[-1]["principal"] <= 0:
        return {**result, "reason": "conflict:principal_schedule_does_not_reconcile", "source": source}
    if not isfinite(pv_total) or not isfinite(weighted) or pv_total <= 0:
        return {**result, "reason": "nonfinite:discounted_cashflows", "source": source}
    d = weighted / pv_total
    modified = d / (1 + ytm)
    if not isfinite(modified):
        return {**result, "reason": "nonfinite:modified_duration", "source": source}
    return {**result, "macaulay_years": d, "modified_years": modified, "annual_effective_ytm": ytm,
            "yield_source": bond["yield_source"], "source": source, "basis": "ACT/365F, annual effective YTM"}


def _segments(segments, start):
    if segments.get("period_start") != start:
        raise ValueError("incompatible:segment_period_start")
    seen, rows = set(), []
    for row in segments.get("rows", []):
        key = row.get("id")
        if not _text(key) or key in seen or not _text(row.get("name")) or row.get("kind") not in {"operating_segment", "portfolio_category"}:
            raise ValueError("invalid:segment_identity")
        seen.add(key)
        metrics = {}
        for field in ("revenue", "profit", "assets"):
            if field not in row:
                continue
            observation = row[field]
            if (not isinstance(observation, dict) or not _numeric(observation.get("value"))
                    or not _text(observation.get("basis")) or (field == "assets" and observation["value"] < 0)):
                raise ValueError("invalid:segment_observation_" + field)
            metrics[field] = {"value": observation["value"], "basis": observation["basis"], "source": _source(observation)}
        if not metrics:
            raise ValueError("missing:segment_observations")
        rows.append({"id": key, "name": row["name"], "kind": row["kind"], "metrics": metrics})
    return rows


def _principal_profile(tables, selected):
    empty = {"value": None, "reason": "missing:verified_complete_financing_principal_schedule"}
    if selected is None:
        return empty
    if not isinstance(selected, dict) or selected.get("coverage") != "complete_financing_principal_including_leases":
        raise ValueError("invalid:principal_schedule_coverage")
    source = _source(selected)
    table = tables.get(selected.get("table_id"))
    if not table or table["side"] != "liability" or table["measure"] != "principal" or not table["covers_open_ended_tail"]:
        return {**empty, "reason": "incompatible:principal_schedule_requires_liability_principal_with_full_tail"}
    if table["within_12_months"] is None:
        return {**empty, "reason": table["within_12_months_reason"]}
    return {"value": table["within_12_months"], "total_principal": table["reported_covered_total"],
            "table_id": table["id"], "reason": None, "source": source, "table_source": table["source"]}


def _matched_gap(tables, selected):
    if selected is None:
        return {"rows": [], "reason": "missing:matched_asset_liability_scope"}
    if not isinstance(selected, dict) or selected.get("coverage") != "comparable_contractual_funding_cashflows":
        raise ValueError("invalid:funding_gap_coverage")
    source = _source(selected)
    asset, debt = tables.get(selected.get("asset_table_id")), tables.get(selected.get("liability_table_id"))
    if (not asset or not debt or asset["side"] != "asset" or debt["side"] != "liability"
            or asset["measure"] != debt["measure"] or asset["measure"] not in {"principal", "undiscounted_contractual_cash_flow"}):
        return {"rows": [], "reason": "incompatible:asset_liability_measure_or_side"}
    boundaries = lambda table: [(r["from_month"], r["to_month"]) for r in table["buckets"]]
    if boundaries(asset) != boundaries(debt):
        return {"rows": [], "reason": "incompatible:asset_liability_bucket_boundaries"}
    cumulative, rows = 0, []
    for left, right in zip(asset["buckets"], debt["buckets"]):
        gap = left["amount"] - right["amount"]
        cumulative += gap
        rows.append({"from_month": left["from_month"], "to_month": left["to_month"], "contractual_inflows": left["amount"],
                     "contractual_outflows": right["amount"], "gap": gap, "cumulative_gap": cumulative})
    return {"rows": rows, "reason": None, "measure": asset["measure"], "asset_table_id": asset["id"],
            "liability_table_id": debt["id"], "source": source, "policy": "excludes_opening_cash_expected_recoveries_and_refinancing"}


def build_disclosure_profile(canonical, *, start, end, funding=None, segments=None, dart_bonds=None, issuer_policy=None):
    tables, bonds, rows = [], [], []
    if funding is not None:
        _packet(funding, "kfa-funding-disclosure/1", canonical, end)
        tables = [_maturity_table(table) for table in funding.get("tables", [])]
        bonds = [_bond_duration(bond, end) for bond in funding.get("bonds", [])]
    if dart_bonds is not None:
        from .pe_cr_dart_schedules import dart_bond_table
        tables.append(_maturity_table(dart_bond_table(dart_bonds, canonical, end)))
    for group in (tables, bonds):
        if len({row["id"] for row in group}) != len(group):
            raise ValueError("conflict:duplicate_funding_table_or_bond")
    if segments is not None:
        _packet(segments, "kfa-segment-disclosure/1", canonical, end)
        rows = _segments(segments, start)
    by_id = {table["id"]: table for table in tables}
    result = {"as_of": end, "period_start": start, "currency": canonical.get("currency"), "fs_div": canonical.get("fs_div"),
            "maturity": {"tables": tables, "reason": None if tables else "missing:reviewed_contractual_maturity_tables"},
            "principal_profile": _principal_profile(by_id, (funding or {}).get("principal_profile")),
            "contractual_funding_gap": _matched_gap(by_id, (funding or {}).get("matched_gap")),
            "duration": {"bonds": bonds, "reason": None if bonds else "missing:fixed_bond_cashflows_and_dated_yields"},
            "segments": {"rows": rows, "reason": None if rows else "missing:reviewed_segment_rows"},
            "aggregation_policy": "no_implicit_sum_across_tables_segments_or_assets_and_liabilities"}
    policy = issuer_policy or {}
    issuer_class = policy.get("entity_class")
    labels = {"specialized_credit_finance": "여신전문금융", "npl_asset_management": "NPL 투자·관리"}
    instruments = (funding or {}).get("dart_instruments")
    if instruments is not None or issuer_class in labels:
        from .pe_cr_dart_schedules import dart_instrument_profile
        result["instrument_maturity"] = {
            "schema_version": "kfa-funding-instruments/1",
            "issuer_type": {"id": issuer_class if issuer_class in labels else "unclassified",
                            "label_ko": labels.get(issuer_class), "evidence": policy.get("evidence") if issuer_class in labels else None},
            "rows": dart_instrument_profile(instruments, canonical, end),
            "aggregation_policy": "do_not_sum_with_legacy_bond_table_or_complete_financing_principal",
        }
    return result
