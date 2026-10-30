"""Conservative entity policy for financial issuers.

Industrial cash-flow, leverage and enterprise-value formulas do not describe a
bank or insurer.  Classification therefore fails closed: an explicit match,
KSIC financial code, or financial name hint disables those formulas.
"""

from __future__ import annotations

from typing import Any


POLICY_VERSION = "financial-entity-policy-1.0.0"

# These are identity overrides, not a fuzzy name matcher.  Keep additions
# reviewable and keyed to the primary reporting identifier where possible.
ENTITY_OVERRIDES: tuple[dict[str, str], ...] = (
    {"source": "dart", "corp_code": "00688996", "entity_class": "bank", "label": "KB Financial Group"},
    {"source": "dart", "corp_code": "00382199", "entity_class": "bank", "label": "Shinhan Financial Group"},
    {"source": "dart", "corp_code": "00547583", "entity_class": "bank", "label": "Hana Financial Group"},
    {"source": "dart", "corp_code": "01350869", "entity_class": "bank", "label": "Woori Financial Group"},
    {"source": "dart", "corp_code": "00126256", "entity_class": "insurance", "label": "Samsung Life Insurance"},
    {"source": "sec", "corp_code": "0000019617", "entity_class": "bank", "label": "JPMorgan Chase"},
)

# Intentionally broad only after the policy has already elected to fail closed.
FINANCIAL_NAME_HINTS = ("은행", "금융", "보험", "생명", "화재", "bank", "financial", "insurance")

# These calculations are built on industrial working-capital, debt and cash-flow
# assumptions and must never be interpreted for deposit-taking or insurance
# balance sheets.
INDUSTRIAL_BASE_METRICS = frozenset({
    "current_ratio", "quick_ratio", "cash_ratio", "debt_ratio",
    "operating_margin", "net_margin", "asset_turnover", "inventory_turnover",
    "receivables_turnover", "earnings_quality", "fcf", "roic", "ccc_days",
    "interest_coverage",
})


def _norm(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def _source(corp: dict[str, Any] | None) -> str:
    raw = _norm((corp or {}).get("source"))
    return "sec" if raw in {"sec", "sec_companyfacts"} else "dart"


def _policy(entity_class: str, *, status: str, source: str, evidence: str) -> dict[str, Any]:
    financial = entity_class in {"bank", "insurance", "financial_other", "financial_suspected"}
    return {
        "version": POLICY_VERSION,
        "entity_class": entity_class,
        "classification_status": status,
        "source": source,
        "evidence": evidence,
        "is_financial_entity": financial,
        "industrial_metrics_allowed": not financial,
        "safe_output_policy": {
            "allowed": ["reported_operating_income", "net_income", "equity", "total_assets", "roe", "roa"],
            "not_applicable": sorted(INDUSTRIAL_BASE_METRICS | {"ebitda", "net_debt", "valuation", "ma_metrics"}),
            "reason": "not_applicable:financial_entity_industrial_metric",
        },
    }


def classify_entity(corp: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a deterministic financial-entity policy from supplied metadata."""
    corp = corp or {}
    source = _source(corp)
    if corp.get("corp_code"):
        width = 10 if source == "sec" else 8
        corp_code = str(corp.get("corp_code") or "").strip().zfill(width)
    else:
        corp_code = ""

    explicit = _norm(corp.get("entity_class") or corp.get("entity_policy"))
    if explicit in {"bank", "insurance", "financial_other"}:
        return _policy(explicit, status="complete", source=source, evidence="explicit:corp.entity_class")

    for override in ENTITY_OVERRIDES:
        if override["source"] == source and override["corp_code"] == corp_code:
            return _policy(override["entity_class"], status="complete", source=source, evidence=f"override:{override['label']}")

    industry = _norm(corp.get("industry"))
    if industry.startswith("k65") or industry.startswith("65"):
        return _policy("insurance", status="complete", source=source, evidence=f"ksic:{corp.get('industry')}")
    if industry.startswith("k64") or industry.startswith("64"):
        return _policy("bank", status="complete", source=source, evidence=f"ksic:{corp.get('industry')}")
    if industry.startswith("k66") or industry.startswith("66"):
        return _policy("financial_other", status="complete", source=source, evidence=f"ksic:{corp.get('industry')}")

    name = _norm(corp.get("name") or corp.get("entity") or corp.get("code"))
    if any(hint in name for hint in FINANCIAL_NAME_HINTS):
        return _policy("financial_suspected", status="partial", source=source, evidence="name_hint:fail_closed")
    return _policy("industrial_or_unknown", status="unavailable", source=source, evidence="no_financial_evidence")


def is_financial(policy: dict[str, Any] | None) -> bool:
    return bool((policy or {}).get("is_financial_entity"))


def not_applicable_cell(cell: dict[str, Any], reason: str = "not_applicable:financial_entity_industrial_metric") -> dict[str, Any]:
    """Preserve metadata while making a calculated industrial metric unavailable."""
    out = dict(cell)
    out["value"] = None
    out["reason"] = reason
    out["policy_status"] = "not_applicable"
    return out
