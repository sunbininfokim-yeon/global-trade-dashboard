"""Reviewed IT service operating segments and a separate product revenue mix."""
from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path

from .reviewed_periodic import REPORT_WINDOWS, reviewed_periodic_source


REGISTRY = Path(__file__).resolve().parents[1] / "config/it_service_reporting_registry.json"
FORM_BY_PERIOD = {"annual": "11011", "Q1": "11013", "Q2": "11012"}
FIELDS = {"segments": ("revenue", "operating_income"), "products": ("revenue",)}
ORDER_SCOPE = "open_long_term_sales_and_service_orders_only"
NO_ORDERS = "no_open_long_term_orders_in_disclosed_scope"


@lru_cache(maxsize=1)
def _registry():
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "kfa-it-service-reporting-registry/1":
        raise ValueError("invalid:it_service_reporting_registry")
    return raw["packets"]


def _table(packet, kind):
    raw = packet[kind]
    source = packet["source"]
    locator = {**source, "url": raw.get("url", source["url"])}
    if source["entity_id"] != packet["entity_id"] or source["provider"] != "DART":
        raise ValueError("incompatible:it_service_source_identity")
    evidence = {**reviewed_periodic_source(locator, packet["period_end"]),
                "table": raw["table"], "source_scale": packet["scale"],
                "period_start": packet["period_start"], "period_end": packet["period_end"],
                "source_window": REPORT_WINDOWS[source["form"]]}
    scale = packet["scale"]
    if (type(scale) is not int or scale not in {1, 1000, 1000000}
            or not isinstance(raw["table"], str) or not raw["table"].strip()):
        raise ValueError("invalid:it_service_table")
    locator_key = "reported_column" if kind == "segments" else "reported_row"
    result = {}
    for row in raw["rows"]:
        key = row["id"]
        if key in result or not all(isinstance(row.get(k), str) and row[k].strip() for k in ("id", "label", locator_key)):
            raise ValueError("invalid:it_service_table_row")
        if any(type(row.get(f)) is not int or abs(row[f]) * scale > 10**20 for f in FIELDS[kind]):
            raise ValueError("invalid:it_service_amount_or_scale")
        if key != "eliminations" and row["revenue"] < 0:
            raise ValueError("invalid:it_service_revenue")
        result[key] = {"id": key, "label_ko": row["label"], "source_locations": [row[locator_key]],
                       **{f: row[f] * scale for f in FIELDS[kind]}}
    if ("total" not in result or result["total"]["revenue"] <= 0 or len(result) < 2
            or ("eliminations" in result) != (kind == "segments")
            or any(sum(r[f] for k, r in result.items() if k != "total") != result["total"][f] for f in FIELDS[kind])):
        raise ValueError("conflict:it_service_" + kind + "_reconciliation")
    return result, evidence


def _quarter(packet, prior, kind):
    current, current_evidence = _table(packet, kind)
    previous, previous_evidence = _table(prior, kind)
    if (not packet.get("reporting_basis_id") or packet["reporting_basis_id"] != prior.get("reporting_basis_id")
            or packet["scale"] != prior["scale"] or current.keys() != previous.keys()
            or any(current[key]["label_ko"] != previous[key]["label_ko"] for key in current)):
        raise ValueError("incompatible:it_service_quarter_reporting_basis")
    for key, row in current.items():
        for f in FIELDS[kind]:
            row[f] -= previous[key][f]
        if key != "eliminations" and row["revenue"] < 0:
            raise ValueError("incompatible:it_service_quarter_revenue")
        row["source_locations"] += previous[key]["source_locations"]
    return current, [current_evidence, previous_evidence]


def _receipts(provenance):
    receipt = provenance.get("filing_id")
    if receipt:
        return {receipt}
    return set().union(*(_receipts(p) for p in provenance.get("source_facts") or ()))


def _matches_control(canonical, period, account, value, start, end, packet, prior):
    series = (canonical.get("series") or {}).get(account) or {}
    fact = (series.get("annual") if period == "annual" else (series.get("quarters") or {}).get(period)) or {}
    unit = fact.get("unit") or {}
    provenance = fact.get("provenance") or {}
    primary = {packet["source"]["filing_id"]}
    receipts = set(primary)
    if prior:
        receipts.add(prior["source"]["filing_id"])
    direct = provenance.get("direct_quarter_source")
    same_filing = (_receipts(direct) == primary and _receipts(provenance) <= receipts
                   if direct else _receipts(provenance) == receipts)
    return (fact.get("period_kind") == ("flow_annual" if period == "annual" else "flow_discrete_quarter")
            and fact.get("nature") == "flow" and fact.get("period_start") == start and fact.get("period_end") == end
            and fact.get("fs_div") == canonical["fs_div"] and fact.get("source") == canonical["source"]
            and (unit.get("kind"), unit.get("currency"), unit.get("scale")) == ("currency", canonical["currency"], 1)
            and fact.get("availability") == "available" and fact.get("quality") in {"reported", "deterministic_derived"}
            and same_filing and type(fact.get("value")) in {int, float} and fact["value"] == value)


def build_it_service_reporting(canonical, industry, period, start, end, *, publication_cutoff=None):
    if industry != "it_services" or canonical.get("source") != "DART":
        return None
    issuer = [p for p in _registry() if p["entity_id"] == canonical.get("entity_id")]
    if not issuer:
        return None
    result = {"schema_version": "kfa-it-service-reporting/1", "mapping_id": None, "status": "unavailable",
              "reason": "missing:reviewed_it_service_filing_for_period_and_scope", "period": period,
              "period_start": start, "period_end": end, "fs_div": canonical.get("fs_div"), "currency": canonical.get("currency"),
              "segment_profitability": None, "product_mix": None, "long_term_orders": None}
    fy_start = canonical.get("fiscal_year_start")
    packets = [p for p in issuer if p["fs_div"] == canonical.get("fs_div") and p["currency"] == canonical.get("currency")
               and p["period_start"] == fy_start]

    def match(form, date_end):
        matches = [p for p in packets if p["source"]["form"] == form and p["period_end"] == date_end]
        if len(matches) > 1:
            raise ValueError("conflict:it_service_reporting_packets")
        return matches[0] if matches else None

    packet = match(FORM_BY_PERIOD[period], end) if period in FORM_BY_PERIOD else None
    if not packet or not start or not end or not fy_start or start > end:
        return result
    prior = None
    if period == "Q2":
        prior = match("11013", (date.fromisoformat(start) - timedelta(days=1)).isoformat())
        if not prior:
            return {**result, "reason": "missing:reviewed_q1_for_h1_difference"}
    elif start != fy_start:
        return result
    if publication_cutoff and any(date.fromisoformat(p["source"]["filed"]) > date.fromisoformat(publication_cutoff)
                                  for p in (packet, prior) if p):
        return {**result, "reason": "unavailable:filing_after_publication_cutoff"}
    def selected_table(kind):
        if prior:
            return _quarter(packet, prior, kind)
        rows, evidence = _table(packet, kind)
        return rows, [evidence]

    segments, segment_sources = selected_table("segments")
    products, product_sources = selected_table("products")
    revenue, op = segments["total"]["revenue"], segments["total"]["operating_income"]
    if revenue <= 0 or products["total"]["revenue"] != revenue:
        raise ValueError("conflict:it_service_consolidated_revenue_crosscheck")
    if (not _matches_control(canonical, period, "PECR_revenue", revenue, start, end, packet, prior)
            or not _matches_control(canonical, period, "PECR_op", op, start, end, packet, prior)):
        return {**result, "reason": "conflict_or_missing:canonical_it_service_revenue_or_operating_income"}
    for key, row in segments.items():
        row["row_type"] = "consolidated_total" if key == "total" else "elimination" if key == "eliminations" else "operating_segment"
        row["included_in"] = None if key == "total" else "total"
        row["operating_margin"] = row["operating_income"] / row["revenue"] if key != "eliminations" and row["revenue"] > 0 else None
    for key, row in products.items():
        row["included_in"] = None if key == "total" else "total"
        row["share_of_consolidated_revenue"] = row["revenue"] / revenue
    order = packet.get("orders")
    if order:
        if order["status"] != NO_ORDERS or not isinstance(order["table"], str) or not order["table"].strip():
            raise ValueError("invalid:it_service_order_scope")
        order = {"status": "not_applicable", "value": None, "reason": NO_ORDERS, "as_of": end, "scope": ORDER_SCOPE,
                 "evidence": {**product_sources[0], "table": order["table"]}}
    return {**result, "status": "deterministic_derived" if prior else "reported", "reason": None,
            "mapping_id": packet["id"], "calculation": "half_year_ytd_minus_first_quarter" if prior else "as_reported",
            "segment_profitability": {"basis": "reported_segments_before_intersegment_elimination", "evidence": segment_sources,
                                      "rows": list(segments.values())},
            "product_mix": {"basis": "consolidated_product_service_revenue_no_matching_profit", "evidence": product_sources,
                            "rows": list(products.values())},
            "long_term_orders": order}
