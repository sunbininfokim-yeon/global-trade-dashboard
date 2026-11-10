"""Exact adapters for saved OpenDART share counts and funding schedules."""
from datetime import date
import re


BOND_BUCKETS = (
    ("yy1_below", 0, 12), ("yy1_excess_yy2_below", 12, 24),
    ("yy2_excess_yy3_below", 24, 36), ("yy3_excess_yy4_below", 36, 48),
    ("yy4_excess_yy5_below", 48, 60), ("yy5_excess_yy10_below", 60, 120), ("yy10_excess", 120, None),
)
SHORT_BUCKETS = (
    ("de10_below", "10일 이하", "10d"),
    ("de10_excess_de30_below", "10일 초과~30일 이하", "30d"),
    ("de30_excess_de90_below", "30일 초과~90일 이하", "90d"),
    ("de90_excess_de180_below", "90일 초과~180일 이하", "180d"),
    ("de180_excess_yy1_below", "180일 초과~1년 이하", "1y"),
)
CP_TAIL = (
    ("yy1_excess_yy2_below", "1년 초과~2년 이하", "2y"),
    ("yy2_excess_yy3_below", "2년 초과~3년 이하", "3y"),
    ("yy3_excess", "3년 초과", None),
)
INSTRUMENTS = {
    "corporate_bond": ("cprndNrdmpBlce", "회사채", tuple(
        (field, f"{low // 12}년 초과~{high // 12}년 이하" if low and high else "1년 이하" if high else "10년 초과",
         f"{high // 12}y" if high else None) for field, low, high in BOND_BUCKETS)),
    "commercial_paper": ("entrprsBilScritsNrdmpBlce", "기업어음(CP)", SHORT_BUCKETS + CP_TAIL),
    "short_term_bond": ("srtpdPsndbtNrdmpBlce", "단기사채", SHORT_BUCKETS),
}
SUMMARY_KEYS = ("10d", "30d", "90d", "180d", "1y")


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


def _instrument_schedule(packet, canonical, end, instrument, endpoint, label, specs):
    if not isinstance(packet, dict) or packet.get("endpoint") != endpoint:
        raise ValueError("incompatible:dart_instrument_endpoint")
    if (packet.get("as_of") != end or not end or packet.get("currency") != canonical.get("currency")
            or packet.get("scope") not in {"issuer_only", "CFS", "OFS"}
            or (packet["scope"] != "issuer_only" and packet["scope"] != canonical.get("fs_div"))):
        raise ValueError("incompatible:dart_instrument_scope_currency_or_date")
    response = packet.get("response")
    if isinstance(response, dict) and response.get("status") == "013" and not response.get("list"):
        return {"status": "unavailable", "reason": "missing:opendart_no_data"}
    rows, url = _report_rows(packet, canonical)
    receipt = packet["receipt"]
    if date.fromisoformat(f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}") < date.fromisoformat(end):
        raise ValueError("incompatible:dart_instrument_filed_before_as_of")
    scale = packet.get("scale")
    selector = packet.get("row_selector", {"remndr_exprtn1": "미상환 잔액", "remndr_exprtn2": "합계"})
    evidence = packet.get("scope_evidence")
    if (type(scale) is not int or scale not in {1, 1000, 1000000, 100000000}
            or not isinstance(evidence, str) or not evidence.strip()
            or not isinstance(selector, dict) or set(selector) != {"remndr_exprtn1", "remndr_exprtn2"}
            or not all(isinstance(v, str) and v.strip() for v in selector.values())):
        raise ValueError("invalid:dart_instrument_row_scope_or_unit")
    matches = [row for row in rows if all(str(row.get(k, "")).strip() == v.strip() for k, v in selector.items())]
    if len(matches) != 1:
        raise ValueError("missing_or_conflict:dart_instrument_exact_scope_row")
    row = matches[0]
    fields = {field for field, _, _ in specs}
    known = {field for _, _, layout in INSTRUMENTS.values() for field, _, _ in layout}
    if (known.intersection(row) != fields
            or ("isu_lmt" in row, "remndr_lmt" in row) != ((True, True) if instrument == "short_term_bond" else (False, False))):
        raise ValueError("incompatible:dart_instrument_bucket_layout")
    def number(record, key):
        return _unsigned(record.get(key), dash_zero=packet.get("dash_means_zero") is True) * scale

    if selector["remndr_exprtn2"].strip() == "합계":
        placements = {name: [entry for entry in rows
                             if str(entry.get("remndr_exprtn1", "")).strip() == selector["remndr_exprtn1"].strip()
                             and str(entry.get("remndr_exprtn2", "")).strip() == name]
                      for name in ("공모", "사모")}
        if all(placements.values()):
            if any(len(entries) != 1 for entries in placements.values()):
                raise ValueError("conflict:dart_instrument_placement_rows")
            public, private = (entries[0] for entries in placements.values())
            if any(number(public, k) + number(private, k) != number(row, k) for k in fields | {"sm"}):
                raise ValueError("conflict:dart_instrument_placement_total")
    buckets, total = [], number(row, "sm")
    running, summary = 0, {key: None for key in SUMMARY_KEYS}
    for field, name, boundary in specs:
        amount = number(row, field)
        running += amount
        if boundary in summary:
            summary[boundary] = running
        buckets.append({"field": field, "label_ko": name, "upper_boundary": boundary, "amount": amount})
    if running != total:
        raise ValueError("conflict:dart_instrument_bucket_total")
    return {"status": "reported", "reason": None, "scope": packet["scope"], "currency": packet["currency"],
            "measure": "reported_outstanding_balance", "outstanding": total, "buckets": buckets,
            "cumulative": {k: {"value": v, "reason": "missing:exact_reported_boundary" if v is None else None}
                           for k, v in summary.items()},
            "source": {"filing_id": packet["receipt"], "table": evidence, "url": url, "endpoint": endpoint,
                       "source_scale": scale, "row_selector": selector}}


def dart_instrument_profile(packets, canonical, end):
    if packets is not None and (canonical.get("source") != "DART" or not isinstance(packets, dict)
                                or set(packets) - INSTRUMENTS.keys()):
        raise ValueError("invalid:dart_instrument_packets")
    result = []
    for instrument, (endpoint, label, specs) in INSTRUMENTS.items():
        packet = (packets or {}).get(instrument)
        if packet is None:
            row = {"status": "unavailable", "reason": "missing:dart_instrument_packet"}
        else:
            try:
                row = _instrument_schedule(packet, canonical, end, instrument, endpoint, label, specs)
            except ValueError as exc:
                # An unavailable instrument does not erase other validated products.
                row = {"status": "unavailable", "reason": str(exc)}
        result.append({"instrument": instrument, "label_ko": label, "outstanding": None, "buckets": [], "cumulative": {}, **row})
    return result
