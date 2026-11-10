"""Reviewed shipbuilding contract roll-forwards, separate from generic backlog."""
from datetime import date
from functools import lru_cache
import json
from pathlib import Path

from .reviewed_periodic import REPORT_WINDOWS, reviewed_periodic_source


REGISTRY = Path(__file__).resolve().parents[1] / "config/shipbuilding_orderbook_registry.json"
PERIOD_FOR_FORM = {"11011": "annual", "11013": "Q1", "11012": "Q2", "11014": "Q3"}
KEYS = ("opening", "contract_movement", "recognized", "closing")


@lru_cache(maxsize=1)
def _registry():
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if doc.get("schema_version") != "kfa-shipbuilding-orderbook-registry/1":
        raise ValueError("invalid:shipbuilding_orderbook_registry")
    return doc


def _validate_rows(packet):
    scale = packet["scale"]
    if type(scale) is not int or scale not in {1, 1000, 1000000, 100000000}:
        raise ValueError("invalid:shipbuilding_orderbook_scale")
    rows = {}
    for row in packet["rows"]:
        key, label = row["id"], row["label"]
        if key in rows or not isinstance(key, str) or not key or not isinstance(label, str) or not label.strip():
            raise ValueError("invalid:shipbuilding_orderbook_row")
        values = {}
        for field in KEYS:
            raw = row[field]
            if type(raw) is not int or abs(raw) * scale > 10**20 or (field in {"opening", "closing"} and raw < 0):
                raise ValueError("invalid:shipbuilding_orderbook_amount")
            values[field] = raw * scale
        if values["opening"] + values["contract_movement"] - values["recognized"] != values["closing"]:
            raise ValueError("conflict:shipbuilding_orderbook_rollforward")
        rows[key] = {"id": key, "label_ko": label, "included_in": None if key == "total" else "total", **values}
    total = rows.get("total")
    segments = [row for key, row in rows.items() if key != "total"]
    if not total or (segments and any(sum(row[k] for row in segments) != total[k] for k in KEYS)):
        raise ValueError("conflict:shipbuilding_orderbook_segments")
    return list(rows.values()), total


def _schedule(packet, total, window):
    years = packet.get("revenue_schedule")
    if years is None:
        return []
    if not isinstance(years, list) or not isinstance(packet.get("schedule_table"), str) or not packet["schedule_table"].strip():
        raise ValueError("invalid:shipbuilding_orderbook_recognition_schedule")
    next_year = date.fromisoformat(packet["period_end"]).year + (window == "annual")
    schedule = []
    for index, bucket in enumerate(years):
        first, last, amount = bucket["from_year"], bucket["through_year"], bucket["amount"]
        if (type(first) is not int or first != next_year or (last is None and index != len(years) - 1)
                or (last is not None and (type(last) is not int or last < first))
                or type(amount) is not int or amount < 0 or amount * packet["scale"] > 10**20):
            raise ValueError("invalid:shipbuilding_orderbook_recognition_schedule")
        schedule.append({"from_year": first, "through_year": last, "amount": amount * packet["scale"],
                         "remaining_in_current_year": first == date.fromisoformat(packet["period_end"]).year})
        next_year = last + 1 if last is not None else None
    if not schedule or sum(row["amount"] for row in schedule) != total["closing"]:
        raise ValueError("conflict:shipbuilding_orderbook_recognition_schedule")
    return schedule


def build_shipbuilding_orderbook(canonical, industry, period, end, *, publication_cutoff=None):
    if industry == "financial":
        return None
    doc = _registry()
    issuer = [p for p in doc["packets"] if p["financial_provider"] == canonical.get("source")
              and p["entity_id"] == canonical.get("entity_id")]
    if not issuer and industry != "shipbuilding":
        return None
    result = {"schema_version": "kfa-shipbuilding-orderbook/1", "as_of": end,
              "status": "unavailable", "reason": "missing:reviewed_orderbook_for_period_and_scope",
              "rows": [], "expected_revenue_recognition": [], "schedule_reason": "missing:reviewed_recognition_schedule", "closing_vessels": None,
              "vessel_count_reason": "missing:verified_orderbook_vessel_count"}
    matched = [p for p in issuer if p["period_end"] == end and p["period_start"] == canonical.get("fiscal_year_start")
               and p["fs_div"] == canonical.get("fs_div") and p["currency"] == canonical.get("currency")
               and PERIOD_FOR_FORM[doc["reports"][p["report_id"]]["form"]] == period]
    if not matched:
        return result
    if len(matched) != 1:
        raise ValueError("conflict:shipbuilding_orderbook_packets")
    packet = matched[0]
    source = reviewed_periodic_source(doc["reports"][packet["report_id"]], end)
    if source["filing_id"] != packet["report_id"]:
        raise ValueError("incompatible:shipbuilding_orderbook_filing_id")
    if publication_cutoff and date.fromisoformat(source["filed"]) > date.fromisoformat(publication_cutoff):
        return {**result, "reason": "unavailable:filing_after_publication_cutoff"}
    rows, total = _validate_rows(packet)
    window = REPORT_WINDOWS[source["form"]]
    schedule = _schedule(packet, total, window)
    return {**result, "status": "reported", "reason": None, "rows": rows,
            "period_start": packet["period_start"], "period_end": end, "source_window": window,
            "currency": packet["currency"], "fs_div": packet["fs_div"],
            "basis": "reported_contract_rollforward_including_contract_and_fx_changes",
            "evidence": {**source, "table": packet["table"], "source_scale": packet["scale"]},
            "expected_revenue_recognition": schedule,
            "schedule_reason": None if schedule else result["schedule_reason"],
            "schedule_evidence": {**source, "table": packet["schedule_table"], "source_scale": packet["scale"]} if schedule else None}
