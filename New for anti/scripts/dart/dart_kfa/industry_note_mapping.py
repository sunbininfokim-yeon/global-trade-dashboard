"""Issuer/period-qualified industry facts from reviewed public filing tables."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


CONFIG = Path(__file__).resolve().parents[1] / "config"
PRODUCTS = {"dram_revenue", "nand_revenue", "other_product_revenue"}
HBM = "hbm_revenue"
BACKLOG_PARTS = {"funded_order_backlog", "unfunded_order_backlog"}
SCALES = {1, 1000, 1000000, 100000000, 1000000000}
CROSS_IDS = {("DART", "00164779", "SEC", "0002120882")}
PERIODS = {"annual", "Q1", "Q2", "Q3", "Q4"}


@lru_cache(maxsize=1)
def _catalog():
    definitions = json.loads((CONFIG / "industry_note_metrics.json").read_text(encoding="utf-8"))
    registry = json.loads((CONFIG / "industry_note_registry.json").read_text(encoding="utf-8"))
    if (definitions.get("schema_version") != "kfa-industry-note-metrics/1"
            or registry.get("schema_version") != "kfa-industry-note-registry/1"):
        raise ValueError("invalid:industry_note_catalog")
    return definitions, registry["packets"]


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _date(value):
    return date.fromisoformat(value)


def _amount(value, scale, *, integer=True):
    if type(scale) is not int or scale not in SCALES or type(value) not in {str, int}:
        raise ValueError("invalid:industry_note_amount_or_scale")
    try:
        amount = Decimal(value) * scale
    except InvalidOperation as exc:
        raise ValueError("invalid:industry_note_amount_or_scale") from exc
    if not amount.is_finite() or abs(amount) > 10**20 or (integer and amount != amount.to_integral_value()):
        raise ValueError("invalid:industry_note_amount_or_scale")
    return amount


def _source(packet):
    source = packet["source"]
    if not all(_string(source.get(k)) for k in ("provider", "entity_id", "filing_id", "filed", "form", "url")):
        raise ValueError("invalid:industry_note_source")
    provider, entity = source["provider"], source["entity_id"]
    identity = (packet["financial_provider"], packet["entity_id"], provider, entity)
    if (identity[0] != provider or identity[1] != entity) and identity not in CROSS_IDS:
        raise ValueError("incompatible:industry_note_source_identity")
    url = urlsplit(source["url"])
    if url.scheme != "https" or url.username or url.password or _date(source["filed"]) < _date(packet["period_end"]):
        raise ValueError("invalid:industry_note_source")
    if provider == "SEC":
        filing = source["filing_id"]
        if (url.netloc != "www.sec.gov" or url.query or not re.fullmatch(r"[0-9]{10}", entity)
                or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", filing)
                or not url.path.startswith(f"/Archives/edgar/data/{int(entity)}/{filing.replace('-', '')}/")
                or source["form"] not in {"10-K", "10-Q", "20-F", "6-K", "F-1"}):
            raise ValueError("invalid:industry_note_sec_filing")
    elif provider == "DART":
        if (url.netloc != "dart.fss.or.kr" or url.path != "/dsaf001/main.do"
                or not re.fullmatch(r"[0-9]{8}", entity) or not re.fullmatch(r"[0-9]{14}", source["filing_id"])
                or parse_qs(url.query) != {"rcpNo": [source["filing_id"]]}
                or source["form"] not in {"11011", "11012", "11013", "11014"}):
            raise ValueError("invalid:industry_note_dart_filing")
    else:
        raise ValueError("invalid:industry_note_provider")
    return dict(source)


def _point(canonical, account, period):
    series = (canonical.get("series") or {}).get(account) or {}
    return (series.get("annual") if period == "annual" else (series.get("quarters") or {}).get(period)) or {}


def _bounds(canonical, period):
    if period == "annual":
        return canonical.get("fiscal_year_start"), canonical.get("fiscal_year_end")
    for account in ("PECR_revenue", "PECR_op", "REVENUE", "OPERATING_INCOME"):
        fact = _point(canonical, account, period)
        if fact.get("period_kind") == "flow_discrete_quarter" and fact.get("period_start") and fact.get("period_end"):
            return fact["period_start"], fact["period_end"]
    return None, None


def _build_rows(packet, definitions, canonical, period):
    source = _source(packet)
    start, end, scope, currency = (packet[k] for k in ("period_start", "period_end", "fs_div", "currency"))
    rows = {}
    for raw in packet["rows"]:
        key = raw["metric"]
        if key not in definitions["kits"][packet["industry"]] or key in rows:
            raise ValueError("invalid:industry_note_metric_or_duplicate")
        label, unit_kind, nature, basis = definitions["metrics"][key]
        if (raw.get("basis") != basis or raw.get("unit") != (currency if unit_kind == "money" else unit_kind)
                or not all(_string(raw.get(k)) for k in ("scope", "table", "row"))
                or (key in PRODUCTS | {HBM} and raw["scope"] != "consolidated_group")):
            raise ValueError("incompatible:industry_note_metric_basis")
        scale = raw["scale"]
        value = _amount(raw["amount"], scale, integer=unit_kind != "percent")
        if (unit_kind != "money" and scale != 1) or (value < 0 and not (key.startswith("same_store_sales_growth") and value >= -100)):
            raise ValueError("invalid:industry_note_unit_or_sign")
        parent = "dram_revenue" if key == HBM else "firm_order_backlog" if key in BACKLOG_PARTS else None
        rows[key] = {"id": key, "label_ko": label, "value": float(value / 100) if unit_kind == "percent" else int(value),
                     "unit": "ratio" if unit_kind == "percent" else raw["unit"], "basis": basis, "scope": raw["scope"],
                     "period_start": start if nature == "flow" else None, "period_end": end, "fs_div": scope, "status": "reported",
                     "reason": None, "included_in": parent, "methodology_ko": raw.get("methodology_ko"),
                     "evidence": {**source, "table": raw["table"], "row": raw["row"], "source_scale": scale,
                                  "source_amount": raw["amount"], "source_unit": raw["unit"]}}
    if BACKLOG_PARTS & rows.keys():
        group = BACKLOG_PARTS | {"firm_order_backlog"}
        if (not group <= rows.keys() or len({(rows[k]["scope"], rows[k]["evidence"]["table"]) for k in group}) != 1
                or sum(rows[k]["value"] for k in BACKLOG_PARTS) != rows["firm_order_backlog"]["value"]):
            raise ValueError("conflict:industry_note_backlog_partition")
    product_ids = set(rows) & (PRODUCTS | {HBM})
    if product_ids:
        control = packet.get("product_revenue_control") or {}
        target = _amount(control.get("amount"), control.get("scale"))
        if (target <= 0 or not _string(control.get("table")) or not PRODUCTS <= rows.keys()
                or any(rows[k]["evidence"]["table"] != control["table"] for k in PRODUCTS)
                or sum(rows[k]["value"] for k in PRODUCTS) != target
                or (HBM in rows and rows[HBM]["value"] > rows["dram_revenue"]["value"])):
            raise ValueError("conflict:industry_note_product_partition")
        cell = _point(canonical, "PECR_revenue", period)
        unit = cell.get("unit") or {}
        total = cell.get("value")
        total = Decimal(str(total)) if type(total) in {int, float} else Decimal("NaN")
        if (scope != "CFS" or cell.get("source") != packet["financial_provider"] or cell.get("fs_div") != scope
                or cell.get("period_start") != start or cell.get("period_end") != end
                or cell.get("nature") != "flow" or cell.get("period_kind") != ("flow_annual" if period == "annual" else "flow_discrete_quarter")
                or cell.get("availability") != "available" or cell.get("quality") not in {"reported", "deterministic_derived"}
                or unit.get("kind") != "currency" or unit.get("currency") != currency or unit.get("scale") != 1
                or not cell.get("provenance") or not total.is_finite()
                or abs(total - target) >= control["scale"]):
            return {}, "conflict_or_missing:canonical_consolidated_revenue_control"
        for key in product_ids:
            rows[key]["share_of_consolidated_revenue"] = float(rows[key]["value"] / target)
    return rows, None


def build_industry_note_profile(canonical, industry, period, *, publication_cutoff=None):
    """Exact-match committed evidence. No caller/API text can promote a row."""
    if period not in PERIODS:
        raise ValueError("invalid:industry_note_period")
    definitions, registry = _catalog()
    start, end = _bounds(canonical, period)
    identity = (canonical.get("source"), canonical.get("entity_id"))
    matches = [p for p in registry if (p["financial_provider"], p["entity_id"]) == identity
               and p["period"] == period and p["period_start"] == start and p["period_end"] == end
               and p["fs_div"] == canonical.get("fs_div") and p["currency"] == canonical.get("currency")]
    if industry in {"general", "manufacturing"} and len({p["industry"] for p in matches}) == 1:
        industry = matches[0]["industry"]
    expected = definitions["kits"].get(industry, [])
    matches = [p for p in matches if p["industry"] == industry]
    if len(matches) > 1:
        raise ValueError("conflict:industry_note_packets")
    reason = "missing:reviewed_issuer_period_mapping" if expected else "not_applicable:no_industry_note_metrics"
    rows, mapping_id = {}, None
    if matches:
        packet = matches[0]
        if publication_cutoff is not None and _date(packet["source"]["filed"]) > _date(publication_cutoff):
            reason = "unavailable:filing_after_publication_cutoff"
        else:
            rows, reason = _build_rows(packet, definitions, canonical, period)
            mapping_id = packet["id"] if rows else None
    return {"schema_version": "kfa-industry-note-profile/1", "industry": industry, "mapping_id": mapping_id,
            "period": period, "period_start": start, "period_end": end, "reason": reason,
            "rows": [rows[key] if key in rows else {"id": key, "label_ko": definitions["metrics"][key][0], "value": None,
                                                    "status": "unavailable", "reason": reason or "missing:verified_disclosure_row"}
                     for key in expected]}
