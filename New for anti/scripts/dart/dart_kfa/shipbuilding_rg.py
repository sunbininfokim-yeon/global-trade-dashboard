"""Received refund-guarantee facilities, never debt, cash, or backlog."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


REGISTRY = Path(__file__).resolve().parents[1] / "config/shipbuilding_rg_registry.json"
BASIS = {
    "rg_only": "선수금환급보증(RG) 단독",
    "rg_and_other_performance": "선수금환급보증(RG) 등 이행성보증",
}


@lru_cache(maxsize=1)
def _packets():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("schema_version") != "kfa-shipbuilding-rg-registry/1" or not isinstance(data.get("packets"), list):
        raise ValueError("invalid:shipbuilding_rg_registry")
    return data["packets"]


def _money(raw, scale):
    if raw is None:
        return None
    if type(raw) not in {str, int}:
        raise ValueError("invalid:shipbuilding_rg_amount")
    try:
        result = Decimal(raw) * scale
    except InvalidOperation as exc:
        raise ValueError("invalid:shipbuilding_rg_amount") from exc
    if not result.is_finite() or not 0 <= result <= 10**20 or result != result.to_integral_value():
        raise ValueError("invalid:shipbuilding_rg_amount")
    return int(result)


def _source(packet):
    source = packet["source"]
    url = urlsplit(source["url"])
    filing, form, filed = source["filing_id"], source["form"], source["filed"]
    filed_date = date.fromisoformat(filed)
    if (source["provider"] != "KRX_KIND" or url.scheme != "https" or url.netloc != "kind.krx.co.kr"
            or url.query or url.fragment or filed_date < date.fromisoformat(packet["as_of"])
            or not re.fullmatch(r"[0-9]{14}", filing) or not filing.startswith(filed_date.strftime("%Y%m%d"))
            or form not in {"11011", "11012", "11013", "11014"}
            or not re.fullmatch(rf"/external/{filed.replace('-', '/')}/[0-9]{{6}}/{filing}/{form}\.htm", url.path)):
        raise ValueError("invalid:shipbuilding_rg_filing")
    return dict(source)


def build_shipbuilding_rg(canonical, industry, end, *, publication_cutoff=None):
    if industry == "financial":
        return None
    identity = (canonical.get("source"), canonical.get("entity_id"))
    eligible = [p for p in _packets() if (p["financial_provider"], p["entity_id"]) == identity]
    if not eligible and industry != "shipbuilding":
        return None
    result = {"schema_version": "kfa-shipbuilding-rg/1", "as_of": end, "fs_div": canonical.get("fs_div"),
              "status": "unavailable", "reason": "missing:reviewed_rg_disclosure_for_period_and_scope",
              "rg_only_available": False, "portfolios": []}
    seen_portfolios = set()
    for packet in eligible:
        if packet["as_of"] != end or packet["fs_div"] != canonical.get("fs_div"):
            continue
        source = _source(packet)
        if publication_cutoff and date.fromisoformat(source["filed"]) > date.fromisoformat(publication_cutoff):
            result["reason"] = "unavailable:filing_after_publication_cutoff"
            continue
        basis, table = packet["basis"], packet["table"]
        if basis not in BASIS or basis in seen_portfolios or not isinstance(table, str) or not table.strip() or not packet["rows"]:
            raise ValueError("invalid:shipbuilding_rg_portfolio")
        seen_portfolios.add(basis)
        rows, seen = [], set()
        for row in packet["rows"]:
            guarantor, currency, scale = row["guarantor"], row["currency"], row["scale"]
            currency_basis = row.get("currency_basis", "as_disclosed")
            if (not isinstance(guarantor, str) or not guarantor.strip() or not re.fullmatch(r"[A-Z]{3}", currency)
                    or type(scale) is not int or scale not in {1, 1000, 1000000, 100000000}
                    or currency_basis not in {"as_disclosed", "issuer_translated_period_end"} or (guarantor, currency) in seen):
                raise ValueError("invalid:shipbuilding_rg_row_or_duplicate")
            seen.add((guarantor, currency))
            limit, outstanding = _money(row.get("limit"), scale), _money(row.get("outstanding"), scale)
            if limit is None and outstanding is None:
                raise ValueError("invalid:empty_shipbuilding_rg_row")
            headroom, utilization = None, None
            if limit is None or outstanding is None:
                reason = "missing:comparable_limit_or_outstanding"
            elif outstanding > limit:
                reason = "conflict:outstanding_exceeds_limit"
            elif not limit:
                headroom, reason = 0, "nonpositive:limit_for_utilization"
            else:
                headroom, utilization, reason = limit - outstanding, outstanding / limit, None
            rows.append({"guarantor": guarantor, "currency": currency, "currency_basis": currency_basis,
                         "limit": limit, "outstanding": outstanding, "limit_less_outstanding": headroom,
                         "utilization": utilization, "calculation_reason": reason,
                         "source_scale": scale, "source_limit": row.get("limit"), "source_outstanding": row.get("outstanding")})
        result["portfolios"].append({"basis": basis, "label_ko": BASIS[basis], "rows": rows,
                                     "evidence": {**source, "table": table}})
    if result["portfolios"]:
        rg_only = "rg_only" in seen_portfolios
        result.update(status="reported" if rg_only else "partial", rg_only_available=rg_only,
                      reason=None if rg_only else "missing:rg_only_breakdown")
    return result
