"""Exact adapters for saved OpenDART share-count and corporate-bond responses."""
from datetime import date
import re


BOND_BUCKETS = (
    ("yy1_below", 0, 12), ("yy1_excess_yy2_below", 12, 24),
    ("yy2_excess_yy3_below", 24, 36), ("yy3_excess_yy4_below", 36, 48),
    ("yy4_excess_yy5_below", 48, 60), ("yy5_excess_yy10_below", 60, 120), ("yy10_excess", 120, None),
)


def _unsigned(raw, *, dash_zero=False):
    s = str(raw).strip()
    if s == "-" and dash_zero:
        return 0
    if not re.fullmatch(r"(?:[0-9]{1,20}|[0-9]{1,3}(?:,[0-9]{3}){1,6})", s):
        raise ValueError("missing_or_invalid:dart_reported_number")
    return int(s.replace(",", ""))


def _report_rows(packet, canonical):
    if canonical.get("source") != "DART" or not isinstance(packet, dict):
        raise ValueError("requires:dart_source_packet")
    response = packet.get("response") or {}
    if not isinstance(response, dict) or response.get("status") != "000" or not isinstance(response.get("list"), list):
        raise ValueError("unavailable:dart_schedule_response")
    receipt, as_of = packet.get("receipt"), packet.get("as_of")
    if not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt) or not isinstance(as_of, str):
        raise ValueError("invalid:dart_schedule_identity")
    date.fromisoformat(as_of)
    rows = response["list"]
    if not rows or any(not isinstance(row, dict) or row.get("corp_code") != canonical.get("entity_id")
                       or row.get("rcept_no") != receipt or row.get("stlm_dt") != as_of for row in rows):
        raise ValueError("incompatible:dart_schedule_entity_receipt_or_date")
    return rows, f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"


def attach_dart_shares(market, packet, canonical):
    rows, url = _report_rows(packet, canonical)
    if not isinstance(market, dict):
        raise ValueError("missing:market_class_prices_for_dart_shares")
    groups = [k for k in ("classes", "preferred_classes") if market.get(k) is not None]
    if not groups or any(not isinstance(market[k], list) or not market[k] for k in groups):
        raise ValueError("missing:market_class_prices_for_dart_shares")
    try:
        report_available = date.fromisoformat(f'{packet["receipt"][:4]}-{packet["receipt"][4:6]}-{packet["receipt"][6:8]}')
        quote_date = date.fromisoformat(market["as_of"])
    except (ValueError, TypeError, KeyError):
        raise ValueError("invalid:dart_shares_or_market_date") from None
    if report_available > quote_date:
        raise ValueError("incompatible:shares_filing_not_public_at_market_date")
    out, used = dict(market), set()
    for key in groups:
        classes = []
        for item in market[key]:
            label = item.get("dart_security_type") if isinstance(item, dict) else None
            if not isinstance(label, str) or not label or label in {"합계", "총계", "계", "비고"} or label in used:
                raise ValueError("invalid:dart_security_class_selector")
            matches = [row for row in rows if row.get("se") == label]
            if len(matches) != 1:
                raise ValueError("missing_or_conflict:dart_security_class")
            row = matches[0]
            issued = _unsigned(row.get("istc_totqy"))
            treasury = _unsigned(row.get("tesstk_co"), dash_zero=packet.get("dash_means_zero") is True)
            dist = _unsigned(row.get("distb_stock_co"))
            if dist != issued - treasury or (item.get("shares_out") is not None and item["shares_out"] != dist):
                raise ValueError("conflict:dart_outstanding_share_reconciliation")
            classes.append({**item, "shares_out": dist, "shares_date": packet["as_of"], "shares_source": url,
                            "share_basis": "outstanding_excluding_treasury"})
            used.add(label)
        out[key] = classes
    return out


def dart_bond_table(packet, canonical, end):
    rows, url = _report_rows(packet, canonical)
    if packet["as_of"] != end or packet.get("fs_div") != canonical.get("fs_div") or packet.get("currency") != canonical.get("currency"):
        raise ValueError("incompatible:dart_bond_scope_currency_or_period")
    scope_evidence = packet.get("scope_evidence")
    if not isinstance(scope_evidence, str) or not scope_evidence.strip():
        raise ValueError("requires:original_bond_table_scope_evidence")
    scale, selector = packet.get("scale"), packet.get("row_selector")
    if (type(scale) is not int or scale not in (1, 1000, 1000000, 100000000) or not isinstance(selector, dict)
            or set(selector) != {"remndr_exprtn1", "remndr_exprtn2"} or not all(isinstance(v, str) for v in selector.values())):
        raise ValueError("invalid:dart_bond_row_selector_or_unit")
    matches = [row for row in rows if all(row.get(k) == v for k, v in selector.items())]
    if len(matches) != 1:
        raise ValueError("missing_or_conflict:dart_bond_exact_scope_row")
    row = matches[0]
    buckets = [{"from_month": low, "to_month": high, "amount": _unsigned(row.get(k), dash_zero=packet.get("dash_means_zero") is True) * scale}
               for k, low, high in BOND_BUCKETS]
    if sum(b["amount"] for b in buckets) != _unsigned(row.get("sm")) * scale:
        raise ValueError("conflict:dart_bond_bucket_total")
    return {"id": "dart_corporate_bonds", "side": "liability", "group": "회사채 미상환 잔액", "measure": "reported_corporate_bond_outstanding",
            "buckets": buckets, "source": {"filing_id": packet["receipt"], "table": scope_evidence, "url": url}}
