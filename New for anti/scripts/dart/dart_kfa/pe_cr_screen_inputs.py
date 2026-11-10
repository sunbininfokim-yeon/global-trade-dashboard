"""Optional inputs for the CR/PE screen; public facts and scenarios stay separate."""
from datetime import date, timedelta
import math
import re
from urllib.parse import urlsplit


def _num(value):
    return type(value) in (int, float) and abs(value) <= 10**20 and math.isfinite(value)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _source(raw):
    if not isinstance(raw, dict) or not all(_text(raw.get(k)) for k in ("filing_id", "url", "locator")):
        raise ValueError("missing:screen_source_locator")
    url = urlsplit(raw["url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("invalid:screen_source_url")
    return {k: raw[k] for k in ("filing_id", "url", "locator")}


def cash_plan_13w(packet, canonical):
    if packet is None:
        return {"classification": "scenario", "weeks": [], "reason": "requires:opening_cash_and_13_week_management_plan"}
    if (not isinstance(packet, dict) or packet.get("schema_version") != "kfa-cash-plan/1"
            or any(not packet.get(k) or packet[k] != canonical.get(k) for k in ("entity_id", "fs_div", "currency"))
            or type(packet.get("scale")) is not int or packet["scale"] != 1):
        raise ValueError("incompatible:cash_plan_identity_scope_currency_or_unit")
    balance, floor = packet.get("opening_unrestricted_cash"), packet.get("minimum_cash")
    if not _num(balance) or balance < 0 or not _num(floor) or floor < 0 or not _text(packet.get("scenario_label")):
        raise ValueError("invalid:cash_plan_opening_cash_minimum_or_label")
    expected = date.fromisoformat(packet["as_of"]) + timedelta(days=1)
    weeks = packet.get("weeks")
    if not isinstance(weeks, list) or len(weeks) != 13:
        raise ValueError("requires:exactly_13_cash_plan_weeks")
    inflows = ("operating_receipts", "committed_financing_draws")
    outflows = ("operating_payments", "cash_taxes", "cash_capex", "principal_payments", "cash_interest")
    rows = []
    for i, week in enumerate(weeks, 1):
        if not isinstance(week, dict) or set(week) != set(inflows + outflows + ("week_start",)) or week.get("week_start") != expected.isoformat():
            raise ValueError("invalid:cash_plan_week_calendar_or_fields")
        if any(not _num(week[k]) or week[k] < 0 for k in inflows + outflows):
            raise ValueError("invalid:cash_plan_amounts")
        incoming, outgoing = sum(week[k] for k in inflows), sum(week[k] for k in outflows)
        closing = balance + incoming - outgoing
        rows.append({**week, "week": i, "week_end": (expected + timedelta(days=6)).isoformat(), "opening_cash": balance,
                     "inflows": incoming, "outflows": outgoing, "closing_cash": closing,
                     "minimum_cash_shortfall": max(0, floor - closing)})
        balance = closing
        expected += timedelta(days=7)
    breached = next((row["week"] for row in rows if row["minimum_cash_shortfall"] > 0), None)
    return {"classification": "scenario", "basis": "explicit_weekly_inputs_not_annual_extrapolation", "reason": None,
            "as_of": packet["as_of"], "scenario_label": packet["scenario_label"], "currency": packet["currency"], "minimum_cash": floor,
            "first_week_below_minimum": breached, "lowest_closing_cash": min(row["closing_cash"] for row in rows), "weeks": rows}


def _scoped(packet, canonical, end, schema):
    if (not isinstance(packet, dict) or packet.get("schema_version") != schema or not end or packet.get("as_of") != end
            or any(not packet.get(k) or packet[k] != canonical.get(k) for k in ("entity_id", "fs_div", "currency"))):
        raise ValueError("incompatible:screen_disclosure_identity_scope_currency_or_period")


def industry_metrics(packet, canonical, start, end):
    if packet is None:
        return {"rows": [], "reason": "missing:reviewed_industry_observations"}
    _scoped(packet, canonical, end, "kfa-screen-industry/1")
    if type(packet.get("scale")) is not int or packet["scale"] != 1:
        raise ValueError("invalid:industry_observation_scale")
    rows, seen = [], set()
    for row in packet.get("rows", []):
        key, scope, unit = row.get("metric"), row.get("scope"), row.get("unit")
        if key not in {"capacity_utilization", "market_share", "order_backlog"} or not _text(scope) or not _text(unit) or (key, scope) in seen:
            raise ValueError("invalid:industry_observation_identity")
        seen.add((key, scope))
        if not start or row.get("period_start") != (None if key == "order_backlog" else start) or row.get("period_end") != end:
            raise ValueError("incompatible:industry_observation_period")
        a, b = row.get("numerator"), row.get("denominator")
        if not _num(a) or a < 0 or (key == "order_backlog" and (b is not None or unit != canonical.get("currency"))) or (
                key != "order_backlog" and (not _num(b) or b <= 0 or (key == "market_share" and a > b))):
            raise ValueError("invalid:industry_observation_quantity")
        rows.append({"metric": key, "scope": scope, "unit": unit, "value": a if key == "order_backlog" else a / b,
                     "numerator": a, "denominator": b, "source": _source(row.get("source")),
                     "period_start": row.get("period_start"), "period_end": end})
    return {"rows": rows, "reason": None if rows else "missing:reviewed_industry_observations"}


AUDIT_LABELS = {"적정": "unmodified", "적정의견": "unmodified", "한정": "qualified", "한정의견": "qualified",
                "부적정": "adverse", "부적정의견": "adverse", "의견거절": "disclaimer"}


def _dart_rows(packet, canonical, end, endpoint):
    if (canonical.get("source") != "DART" or not isinstance(packet, dict) or packet.get("endpoint") != endpoint
            or not end or packet.get("as_of") != end):
        raise ValueError("incompatible:dart_governance_request")
    response = packet.get("response") or {}
    if not isinstance(response, dict):
        raise ValueError("invalid:dart_governance_response")
    if response.get("status") == "013":
        if response.get("list"):
            raise ValueError("invalid:dart_governance_no_data_response")
        return [], None
    receipt, rows = packet.get("receipt"), response.get("list")
    if not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt) or response.get("status") != "000" or not isinstance(rows, list) or not rows:
        raise ValueError("invalid:dart_governance_response")
    if any(not isinstance(row, dict) or row.get("rcept_no") != receipt or row.get("corp_code") != canonical.get("entity_id") for row in rows):
        raise ValueError("incompatible:dart_governance_receipt_or_entity")
    return [row for row in rows if row.get("stlm_dt") == end], {
        "filing_id": receipt, "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}", "locator": endpoint}


def governance_profile(packet, canonical, start, end, *, period, dart_audit=None, dart_ownership=None):
    audit, ownership, related = None, [], []
    if packet is not None:
        _scoped(packet, canonical, end, "kfa-screen-governance/1")
        if packet.get("period_start") != start or not start or type(packet.get("scale")) is not int or packet["scale"] != 1:
            raise ValueError("incompatible:governance_period_or_unit")
        raw_audit = packet.get("audit")
        if raw_audit is not None and period == "annual":
            if raw_audit.get("opinion") not in {"unmodified", "qualified", "adverse", "disclaimer"} or not _text(raw_audit.get("auditor")):
                raise ValueError("invalid:reviewed_audit_opinion")
            audit = {"opinion": raw_audit["opinion"], "auditor": raw_audit["auditor"], "source": _source(raw_audit.get("source"))}
        for row in packet.get("related_party_transactions", []):
            if not _text(row.get("category")) or not _text(row.get("counterparty")) or not _num(row.get("amount")) or row["amount"] < 0:
                raise ValueError("invalid:related_party_observation")
            if row.get("basis") not in {"period_transaction", "closing_balance"}:
                raise ValueError("invalid:related_party_basis")
            related.append({**{k: row[k] for k in ("category", "counterparty", "amount", "basis")},
                            "currency": canonical.get("currency"), "source": _source(row.get("source"))})
        for row in packet.get("ownership_events", []):
            changed = date.fromisoformat(row["date"])
            if not date.fromisoformat(start) <= changed <= date.fromisoformat(end) or not _text(row.get("holder")):
                raise ValueError("invalid:reviewed_ownership_event")
            ownership.append({"date": changed.isoformat(), "holder": row["holder"], "source": _source(row.get("source"))})
    if dart_audit is not None and period == "annual":
        rows, source = _dart_rows(dart_audit, canonical, end, "accnutAdtorNmNdAdtOpinion")
        if dart_audit.get("reprt_code") != "11011" or dart_audit.get("fs_div") != canonical.get("fs_div") or not _text(dart_audit.get("scope_evidence")):
            raise ValueError("requires:dart_annual_audit_scope_evidence")
        if len(rows) > 1:
            raise ValueError("conflict:dart_current_audit_rows")
        if rows:
            row = rows[0]
            label, auditor = row.get("adt_opinion"), row.get("adtor")
            if _text(label) and _text(auditor):
                classification = AUDIT_LABELS.get("".join(label.split()))
                if audit is not None and (classification != audit["opinion"] or auditor != audit["auditor"]):
                    raise ValueError("conflict:reviewed_and_dart_audit_opinion")
                audit = {"opinion": classification, "reported_label": label, "auditor": auditor, "source": source,
                         "scope_evidence": dart_audit["scope_evidence"]}
    if dart_ownership is not None:
        rows, source = _dart_rows(dart_ownership, canonical, end, "hyslrChgSttus")
        for row in rows:
            if not _text(row.get("mxmm_shrholdr_nm")) or row["mxmm_shrholdr_nm"].strip() == "-":
                continue
            changed = date.fromisoformat(str(row.get("change_on") or "").replace(".", "-").strip("-"))
            if start and date.fromisoformat(start) <= changed <= date.fromisoformat(end) and _text(row.get("mxmm_shrholdr_nm")):
                ownership.append({"date": changed.isoformat(), "holder": row["mxmm_shrholdr_nm"], "source": source})
    ownership = sorted({(r["date"], r["holder"]): r for r in ownership}.values(), key=lambda row: row["date"])
    return {"audit": audit, "audit_reason": None if audit and audit["opinion"] else "missing_or_unclassified:annual_audit_opinion",
            "ownership_events": ownership, "ownership_reason": None if ownership else "missing:reviewed_ownership_events_not_evidence_of_no_change",
            "related_party_transactions": related, "related_party_reason": None if related else "missing:reviewed_related_party_observations"}
