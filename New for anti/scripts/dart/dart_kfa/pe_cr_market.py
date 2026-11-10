"""Explicit point-in-time market inputs and like-for-like peer summaries."""
from datetime import date
import math
from statistics import median


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _class_observations(classes, raw, as_of):
    if not isinstance(classes, list) or not classes:
        return None, "missing:share_classes"
    seen, parts = set(), []
    for row in classes:
        if not isinstance(row, dict):
            return None, "invalid:share_class"
        key = row.get("id")
        shares = row.get("shares_out")
        if not isinstance(key, str) or not key or key in seen or not positive(row.get("price")) or type(shares) is not int or not positive(shares):
            return None, "invalid:share_class_price_or_shares"
        if row.get("price_date") != raw["as_of"] or row.get("currency") != raw["currency"] or row.get("share_basis") != "outstanding_excluding_treasury":
            return None, "incompatible:share_class_currency_date_or_basis"
        try:
            age = (as_of - date.fromisoformat(row["shares_date"])).days
        except (ValueError, TypeError, KeyError):
            return None, "invalid:shares_date"
        if not 0 <= age <= 120 or not all(isinstance(row.get(k), str) and row[k].strip() for k in ("price_source", "shares_source")):
            return None, "requires:dated_share_count_and_source"
        if age and row.get("corporate_actions_checked") is not True:
            return None, "requires:share_count_corporate_actions_check"
        seen.add(key)
        parts.append({**{k: row[k] for k in ("id", "shares_out", "price", "price_date", "shares_date", "price_source", "shares_source", "share_basis", "currency")},
                      "corporate_actions_checked": row.get("corporate_actions_checked") is True})
    return parts, None


def _dated_value(item, raw, *, allow_zero=False):
    if not isinstance(item, dict):
        return False
    v = item.get("value")
    return ((positive(v) or (allow_zero and type(v) in (int, float) and v == 0))
            and item.get("as_of") == raw["as_of"] and item.get("currency") == raw["currency"]
            and isinstance(item.get("source"), str) and bool(item["source"].strip()))


def _preferred(raw, as_of, ordinary_classes):
    pref = raw.get("preferred_equity")
    if raw.get("preferred_classes") is not None:
        if pref is not None:
            return None, "conflict:choose_preferred_classes_or_preferred_value"
        if raw.get("preferred_coverage") != "all_preferred_share_classes":
            return None, "requires:all_preferred_share_classes"
        parts, problem = _class_observations(raw["preferred_classes"], raw, as_of)
        if problem:
            return None, problem
        if {p["id"] for p in parts} & {p["id"] for p in ordinary_classes}:
            return None, "conflict:ordinary_and_preferred_class_identity"
        value = sum(p["price"] * p["shares_out"] for p in parts)
        if not positive(value):
            return None, "invalid:preferred_equity_value"
        return {"value": value, "as_of": raw["as_of"], "currency": raw["currency"],
                "basis": "quoted_preferred_class_prices_times_shares", "classes": parts}, None
    if _dated_value(pref, raw, allow_zero=True):
        if pref["value"] == 0 and pref.get("basis") != "verified_no_preferred_outstanding":
            return None, "requires:verified_absence_of_preferred_equity"
        return {**{k: pref[k] for k in ("value", "as_of", "currency", "source")},
                "basis": pref.get("basis") or "documented_preferred_value"}, None
    return None, "missing:dated_preferred_equity_value_or_explicit_zero"


def market_observation(raw, canonical):
    if raw is None:
        return None, "missing:market_observation"
    if not isinstance(raw, dict) or raw.get("is_listed") is not True:
        return None, "not_applicable:not_listed_or_unconfirmed"
    if not raw.get("entity_id") or raw["entity_id"] != canonical.get("entity_id") or raw.get("currency") != canonical.get("currency"):
        return None, "incompatible:market_entity_or_currency"
    try:
        as_of = date.fromisoformat(raw["as_of"])
    except (ValueError, TypeError, KeyError):
        return None, "invalid:market_date"
    supplied = raw.get("reported_market_cap")
    observed, parts = None, []
    if supplied is not None:
        if raw.get("classes"):
            return None, "conflict:choose_reported_or_class_based_market_cap"
        if (not _dated_value(supplied, raw) or supplied.get("scope") not in {"all_ordinary", "all_ordinary_and_preferred"}
                or type(supplied.get("scale")) is not int or supplied["scale"] != 1
                or supplied.get("share_basis") != "outstanding_excluding_treasury"
                or not isinstance(supplied.get("scope_evidence"), str) or not supplied["scope_evidence"].strip()):
            return None, "requires:documented_market_cap_scope_share_basis_and_date"
        observed = {k: supplied[k] for k in ("value", "as_of", "currency", "source", "scope", "share_basis", "scope_evidence", "scale")}
    else:
        if raw.get("coverage") != "all_ordinary_share_classes":
            return None, "requires:all_ordinary_share_classes"
        parts, problem = _class_observations(raw.get("classes"), raw, as_of)
        if problem:
            return None, problem
    preferred, preferred_reason = _preferred(raw, as_of, parts)
    pref_value = preferred["value"] if preferred else None
    ordinary_reason, total_reason = None, None
    if observed and observed["scope"] == "all_ordinary_and_preferred":
        total = observed["value"]
        ordinary = total - pref_value if pref_value is not None else None
        if pref_value is None:
            ordinary_reason = "requires:preferred_split_for_ordinary_market_cap"
        elif not positive(ordinary):
            return None, "conflict:preferred_value_exceeds_or_equals_reported_total_equity"
        method = "reported_total_equity_preferred_already_included"
    else:
        ordinary = observed["value"] if observed else sum(p["price"] * p["shares_out"] for p in parts)
        if not positive(ordinary):
            return None, "invalid:market_cap"
        total = ordinary + pref_value if pref_value is not None else None
        if total is not None and not positive(total):
            return None, "invalid:total_equity_market_value"
        total_reason = preferred_reason
        method = "ordinary_equity_plus_separate_preferred"
    return {"as_of": raw["as_of"], "currency": raw["currency"], "market_cap": ordinary,
            "market_cap_reason": ordinary_reason, "equity_market_value_total": total, "equity_market_value_total_reason": total_reason,
            "equity_market_value_method": method, "reported_market_cap": observed, "preferred_equity": preferred, "preferred_reason": preferred_reason,
            "classes": parts, "fundamentals_available_date": raw.get("fundamentals_available_date")}, None


COMPS = ("per", "pbr", "ev_to_ebitda", "ev_to_ebit", "ev_to_sales", "roe", "roa", "ccc_days")
MARKET_COMPS = frozenset(COMPS[:5])
PEER_COLUMNS = (
    ("per", "PER", "multiple"), ("pbr", "PBR", "multiple"), ("ev_to_ebitda", "EV/EBITDA", "multiple"),
    ("ev_to_ebit", "EV/EBIT", "multiple"), ("ev_to_sales", "EV/매출", "multiple"),
    ("roe", "ROE", "percent"), ("roa", "ROA", "percent"), ("ccc_days", "CCC", "days"),
)


def _peer_cells(snapshot, *, market_date_matches=True):
    cards = snapshot.get("cards") or {}
    result = {}
    for key in COMPS:
        cell = cards.get(key) or {}
        value = cell.get("value")
        if key in MARKET_COMPS and not market_date_matches:
            result[key] = {"value": None, "reason": "incompatible:peer_market_date"}
        elif cell.get("status") == "computed" and type(value) in (int, float) and math.isfinite(value):
            result[key] = {"value": value, "reason": None}
        else:
            result[key] = {"value": None, "reason": cell.get("reason") or "missing:metric"}
    return result


def compare_peers(target, peers, *, peer_ids=None):
    """Compare explicit peer snapshots, not rankings or investment signals."""
    context = target["comparison_context"]
    if peer_ids is not None:
        if (not isinstance(peer_ids, (list, tuple)) or len(peer_ids) > 8
                or any(not isinstance(i, str) or not i.strip() or i != i.strip() for i in peer_ids)
                or len(set(peer_ids)) != len(peer_ids)):
            raise ValueError("invalid:peer_selection_requires_up_to_eight_distinct_resolved_ids")
        snapshots = {}
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            identity = (peer.get("comparison_context") or {}).get("entity_id")
            if identity in peer_ids:
                if identity in snapshots:
                    raise ValueError("conflict:duplicate_resolved_peer_snapshot")
                snapshots[identity] = peer
        peers = [snapshots.get(i, {"comparison_context": {"entity_id": i}, "selection_missing": True}) for i in peer_ids]
    rows, excluded, seen = [], [], {context.get("entity_id")}
    for peer in peers:
        if not isinstance(peer, dict):
            excluded.append({"entity_id": None, "reason": "invalid_peer_snapshot"})
            continue
        other = peer.get("comparison_context") or {}
        eid = other.get("entity_id")
        reason = None
        if peer.get("selection_missing") is True:
            reason = "missing:resolved_peer_snapshot"
        elif peer.get("schema_version") != "kfa-pe-cr/1" or not eid or eid in seen:
            reason = "invalid_or_duplicate_peer_identity"
        elif not context.get("accounting_basis") or not other.get("accounting_basis"):
            reason = "requires_confirmed_accounting_basis"
        elif not context.get("peer_group") or any(other.get(k) != context.get(k) for k in
                 ("peer_group", "industry", "source", "accounting_basis", "fs_div", "period_start", "period_end")):
            reason = "incompatible_peer_group_or_basis"
        elif context.get("period") != "annual" or other.get("period") != "annual" or context.get("fs_div") != "CFS":
            reason = "requires_consolidated_annual_basis"
        if reason:
            excluded.append({"entity_id": eid, "reason": reason})
            continue
        seen.add(eid)
        cells = _peer_cells(peer, market_date_matches=bool(context.get("market_date")) and other.get("market_date") == context["market_date"])
        rows.append({"entity_id": eid, "label": other.get("entity_label"), "market_date": other.get("market_date"),
                     "metrics": {k: v["value"] for k, v in cells.items()}, "cells": cells})
    statistics = {}
    for key in COMPS:
        values = [row["metrics"][key] for row in rows
                  if type(row["metrics"][key]) in (int, float) and math.isfinite(row["metrics"][key])]
        statistics[key] = {"count": len(values), "median": median(values) if len(values) >= 2 else None,
                           "reason": None if len(values) >= 2 else "requires:two_comparable_observations"}
    return {"peer_group": context.get("peer_group"), "included": rows, "excluded": excluded, "summary": statistics,
            "columns": [{"id": k, "label": label, "display": unit} for k, label, unit in PEER_COLUMNS],
            "target": {"entity_id": context.get("entity_id"), "label": context.get("entity_label"), "cells": _peer_cells(target)},
            "selection": {"peer_ids": list(peer_ids) if peer_ids is not None else None, "max_selected": 8},
            "target_excluded_from_median": True}
