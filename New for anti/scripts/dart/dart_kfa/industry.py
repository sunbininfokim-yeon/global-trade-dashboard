"""Industry kit resolution and flag evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_industry_kits(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "industry_kits.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def load_universe_seed(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "universe_seed.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def load_export_bok_coverage(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "export_bok_coverage.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_kit_id(
    corp: dict[str, Any] | None,
    kits_doc: dict[str, Any] | None = None,
) -> str:
    doc = kits_doc or load_industry_kits()
    kits = doc.get("kits") or {}
    try:
        aliases = load_export_bok_coverage().get("aliases") or {}
    except OSError:
        aliases = {"electronics": "electronics_components"}

    if corp and corp.get("industry_kit"):
        raw = str(corp["industry_kit"])
        kid = aliases.get(raw, raw)
        return kid if kid in kits else "general"

    industry = str((corp or {}).get("industry") or "")
    # Longest KSIC prefix wins (C261 before C26 before C)
    best_id = "general"
    best_len = -1
    for kid, kit in kits.items():
        if kid == "general":
            continue
        for prefix in kit.get("ksic_prefixes") or []:
            p = str(prefix)
            if industry.startswith(p) and len(p) > best_len:
                best_id = kid
                best_len = len(p)
    return best_id


def get_kit(kit_id: str, kits_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = kits_doc or load_industry_kits()
    kits = doc.get("kits") or {}
    try:
        aliases = load_export_bok_coverage().get("aliases") or {}
    except OSError:
        aliases = {}
    kid = aliases.get(kit_id, kit_id)
    return kits.get(kid) or kits.get(kit_id) or kits["general"]


def _metric_value(metrics: dict[str, Any], mid: str) -> float | None:
    cell = metrics.get(mid) or {}
    v = cell.get("value")
    return float(v) if v is not None else None


def evaluate_flags(
    kit: dict[str, Any],
    *,
    metrics: dict[str, Any],
    amounts: dict[str, float | None],
) -> list[dict[str, Any]]:
    """Rule flags — deterministic, no ML."""
    out: list[dict[str, Any]] = []
    fcf = _metric_value(metrics, "fcf")
    eq = _metric_value(metrics, "earnings_quality")
    om = _metric_value(metrics, "operating_margin")
    debt = _metric_value(metrics, "debt_ratio")
    inv_t = metrics.get("inventory_turnover") or {}
    trend = inv_t.get("trend_3y") or []
    lease = amounts.get("LEASE_LIABILITIES")
    contract = amounts.get("CONTRACT_LIABILITIES")
    total_liab = amounts.get("TOTAL_LIABILITIES")
    capex = amounts.get("CAPEX")

    for flag in kit.get("flags") or []:
        when = flag.get("when")
        hit = False
        if when == "fcf_negative_and_capex_large":
            hit = fcf is not None and fcf < 0 and capex is not None and abs(capex) > 0
        elif when == "inventory_turnover_falling":
            nums = [x for x in trend if isinstance(x, (int, float))]
            hit = len(nums) >= 2 and nums[-1] < nums[0]
        elif when == "contract_liabilities_high":
            hit = (
                contract is not None
                and total_liab not in (None, 0)
                and contract / abs(total_liab) >= 0.15
            )
        elif when == "earnings_quality_low":
            hit = eq is not None and eq < 0.8
        elif when == "lease_liabilities_present_or_high_debt":
            hit = (lease is not None and lease > 0) or (debt is not None and debt >= 150)
        elif when == "operating_margin_very_high":
            hit = om is not None and om >= 25
        if hit:
            out.append(
                {
                    "id": flag.get("id"),
                    "severity_ko": flag.get("severity_ko"),
                    "when": when,
                }
            )
    return out


from .peers import (
    background_for_kit,
    compare_to_peers,
    load_bok_peers,
    resolve_peer_row,
)


def apply_industry_layer(
    *,
    corp: dict[str, Any] | None,
    metrics: dict[str, Any],
    amounts: dict[str, float | None],
    entity_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (entity_policy or {}).get("is_financial_entity"):
        entity_class = entity_policy.get("entity_class") or "financial_suspected"
        label = {"bank": "은행·금융지주", "insurance": "보험", "financial_other": "기타 금융", "financial_suspected": "금융업 의심"}.get(entity_class, "금융업")
        return {
            "industry_kit": entity_class,
            "label_ko": label,
            "notes_ko": ["금융업은 산업기업 현금흐름·순차입·유동성·DCF 지표를 적용하지 않습니다."],
            "watch_notes": [],
            "ma_focus": [],
            "priority_metrics": ["roe", "roa"],
            "mti_export_items": [],
            "flags": [],
            "adjusted_metrics": {},
            "models_hint_ko": [],
            "sources": [entity_policy.get("evidence")],
            "background": {},
            "bok_peer": {"asof": None, "source_ko": None, "row": None, "vs": {"available": False, "metrics": {}}},
        }
    kits_doc = load_industry_kits()
    kit_id = resolve_kit_id(corp, kits_doc)
    try:
        aliases = load_export_bok_coverage().get("aliases") or {}
        kit_id = aliases.get(kit_id, kit_id)
    except OSError:
        pass
    kit = get_kit(kit_id, kits_doc)
    priority = kit.get("priority_metrics") or []
    prioritized = {mid: metrics[mid] for mid in priority if mid in metrics}
    for mid, cell in metrics.items():
        if mid not in prioritized:
            prioritized[mid] = cell

    lease = amounts.get("LEASE_LIABILITIES")
    contract = amounts.get("CONTRACT_LIABILITIES")
    equity = amounts.get("EQUITY")
    total_liab = amounts.get("TOTAL_LIABILITIES")
    adjustments: dict[str, Any] = {}
    if lease is not None and total_liab is not None and equity not in (None, 0):
        adj_liab = total_liab - lease
        adjustments["debt_ratio_ex_lease"] = {
            "value": round(100.0 * adj_liab / equity, 4),
            "unit": "pct",
            "label": "부채비율(리스제외)",
            "reason": None,
        }
    if contract is not None and total_liab is not None and equity not in (None, 0):
        adj_liab = total_liab - contract
        adjustments["debt_ratio_ex_contract_liab"] = {
            "value": round(100.0 * adj_liab / equity, 4),
            "unit": "pct",
            "label": "부채비율(계약부채·선수금 제외)",
            "reason": None,
        }

    peers_doc = load_bok_peers()
    peer_row = resolve_peer_row(kit=kit, corp=corp, peers_doc=peers_doc)
    peer_vs = compare_to_peers(metrics, peer_row)
    bg = background_for_kit(kit_id)

    return {
        "industry_kit": kit_id,
        "label_ko": kit.get("label_ko"),
        "notes_ko": kit.get("notes_ko") or [],
        "watch_notes": kit.get("watch_notes") or [],
        "ma_focus": kit.get("ma_focus") or [],
        "priority_metrics": priority,
        "mti_export_items": kit.get("mti_export_items") or [],
        "flags": evaluate_flags(kit, metrics=metrics, amounts=amounts),
        "adjusted_metrics": adjustments,
        "models_hint_ko": kit.get("adjusted_views") or [],
        "sources": kit.get("sources") or [],
        "background": bg,
        "bok_peer": {
            "asof": peers_doc.get("asof"),
            "source_ko": peers_doc.get("source_ko"),
            "row": {
                "ksic": (peer_row or {}).get("matched_ksic") or (peer_row or {}).get("ksic"),
                "label_ko": (peer_row or {}).get("label_ko"),
                "current_ratio": (peer_row or {}).get("current_ratio"),
                "debt_ratio": (peer_row or {}).get("debt_ratio"),
                "net_margin": (peer_row or {}).get("net_margin"),
                "equity_ratio": (peer_row or {}).get("equity_ratio"),
                "asset_turnover": (peer_row or {}).get("asset_turnover"),
            }
            if peer_row
            else None,
            "vs": peer_vs,
        },
    }
