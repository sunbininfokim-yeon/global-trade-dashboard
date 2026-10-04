"""Country ↔ world linking algorithm.

Opinion implemented: the two layers must be *connected*, not only displayed side by side.

Link types
----------
1. identity
   Country series *is* that reporter's export-to-world total
   (e.g. USA ERS World total == USA node).

2. contributor
   Country volume is a component of a world (or multi-country) aggregate.
   share = country_norm / world_norm when same month & compatible units.

3. partial_sum_proxy
   No official world row: sum of available countries (normalized) is stored as
   *proxy only*, with reporters[] and never labeled official_world.

4. incomparable
   Units/metrics cannot be aligned — edge exists for navigation, no numeric share.

Normalization to kg (mass only). Value series (AUD, USD) stay incomparable to mass.
"""

from __future__ import annotations

from typing import Any

# unit → multiply to kg
TO_KG = {
    "kg": 1.0,
    "metric_tons": 1000.0,
    "t": 1000.0,
    "tonnes": 1000.0,
    "kMT_cu_content": 1_000_000.0,  # thousand metric tons → kg
    "KTONS": 1_000_000.0,
}


def world_rollup_policy() -> dict[str, Any]:
    return {
        "algorithm": "link_country_world_v1",
        "modes": {
            "reporter_export_to_world": {
                "meaning_ko": "한 보고국의 대세계 수출 총량",
                "is_global_supply": False,
                "ui_label_ko": "해당국→세계 수출",
            },
            "partial_country_set": {
                "meaning_ko": "확보 국가만. 합산 시 partial_sum_proxy",
                "is_global_supply": False,
                "ui_label_ko": "부분 국가 세트",
            },
            "official_world": {
                "meaning_ko": "원천 World 행 (PSD World 등)",
                "is_global_supply": True,
                "ui_label_ko": "공식 세계 집계",
            },
        },
        "link_types": ["identity", "contributor", "partial_sum_proxy", "incomparable"],
        "forbidden_ko": [
            "단위 변환 없이 합산",
            "partial_sum_proxy를 official_world로 표기",
            "금액 시리즈와 물량 시리즈 합산",
        ],
        "ui_join_ko": (
            "국가 클릭 ↔ 세계/부분합 노드로 왕복. "
            "share_of_world는 같은 달·kg 환산 가능할 때만. "
            "identity면 국가=그 나라의 대세계 수출."
        ),
    }


def to_kg(value: float, unit: str | None) -> float | None:
    if value is None or not unit:
        return None
    u = unit.strip()
    if u in TO_KG:
        return float(value) * TO_KG[u]
    # already described as kg-like
    if u.lower() in TO_KG:
        return float(value) * TO_KG[u.lower()]
    return None


def _index_by_month(points: list[dict]) -> dict[str, dict]:
    return {p["month"]: p for p in points if p.get("month")}


def merge_reporters(
    commodity_id: str,
    country_blocks: dict[str, list],
    *,
    units: dict[str, str],
) -> dict[str, Any]:
    unit_set = set(v for v in units.values() if v)
    reporters = sorted(country_blocks.keys())
    compatible = len(unit_set) <= 1
    return {
        "commodity_id": commodity_id,
        "reporters": reporters,
        "units_present": sorted(unit_set),
        "sum_allowed": False,
        "rollup_mode": "partial_country_set",
        "note_ko": (
            "단위 통일·공식 World 없으면 합산을 official로 쓰지 않음."
            if not compatible
            else "동일 단위여도 커버 불완전이면 partial."
        ),
    }


def link_country_world(
    commodity_id: str,
    countries: dict[str, dict],
    *,
    usa_is_export_to_world: bool = False,
) -> dict[str, Any]:
    """Build explicit edges between country nodes and a world/proxy node.

    `countries`: iso3 → {points, latest_available_month, ...}
    """
    edges: list[dict[str, Any]] = []
    nodes: dict[str, Any] = {}

    # --- country nodes ---
    month_union: set[str] = set()
    for iso, block in countries.items():
        pts = block.get("points") or []
        by_m = _index_by_month(pts)
        month_union |= set(by_m.keys())
        unit = pts[-1]["unit"] if pts else None
        nodes[iso] = {
            "type": "country",
            "iso3": iso,
            "unit_native": unit,
            "point_count": len(pts),
            "latest": block.get("latest_available_month"),
            "mass_convertible": unit in TO_KG if unit else False,
        }
        if iso == "USA" and usa_is_export_to_world:
            # identity: USA series == reporter export-to-world
            edges.append(
                {
                    "from": "USA",
                    "to": "WORLD_USA_EXPORT",
                    "link_type": "identity",
                    "note_ko": "미국 시리즈 = 미국→세계 수출 총량 (ERS World total)",
                }
            )
            nodes["WORLD_USA_EXPORT"] = {
                "type": "reporter_export_to_world",
                "reporter": "USA",
                "is_global_supply": False,
                "mirrors": "USA",
            }

    # --- partial sum proxy for mass-convertible countries ---
    mass_isos = [iso for iso, n in nodes.items() if n.get("type") == "country" and n.get("mass_convertible")]
    proxy_series: list[dict] = []
    if len(mass_isos) >= 1:
        for month in sorted(month_union):
            parts = {}
            total = 0.0
            ok = True
            for iso in mass_isos:
                pts = countries[iso].get("points") or []
                by_m = _index_by_month(pts)
                if month not in by_m:
                    ok = False
                    break
                kg = to_kg(by_m[month]["value"], by_m[month].get("unit"))
                if kg is None:
                    ok = False
                    break
                parts[iso] = kg
                total += kg
            if not ok or total <= 0:
                continue
            shares = {iso: parts[iso] / total for iso in parts}
            proxy_series.append(
                {
                    "month": month,
                    "value_kg": total,
                    "unit": "kg",
                    "contributors": parts,
                    "shares": shares,
                }
            )
            for iso, sh in shares.items():
                edges.append(
                    {
                        "from": iso,
                        "to": "PARTIAL_SUM",
                        "link_type": "contributor",
                        "month": month,
                        "share": round(sh, 6),
                        "country_kg": parts[iso],
                        "partial_sum_kg": total,
                    }
                )

        if proxy_series:
            nodes["PARTIAL_SUM"] = {
                "type": "partial_sum_proxy",
                "is_global_supply": False,
                "reporters": mass_isos,
                "latest": proxy_series[-1]["month"],
                "point_count": len(proxy_series),
                "note_ko": "kg 환산 가능한 확보국만 합산. 세계 공급 아님.",
            }

    # --- incomparable edges (navigation only) ---
    for iso, n in list(nodes.items()):
        if n.get("type") != "country":
            continue
        if not n.get("mass_convertible"):
            edges.append(
                {
                    "from": iso,
                    "to": "PARTIAL_SUM" if "PARTIAL_SUM" in nodes else "WORLD_VIEW",
                    "link_type": "incomparable",
                    "note_ko": f"단위 {n.get('unit_native')} → kg 환산 불가, 숫자 연동 없음",
                }
            )

    # latest shares snapshot
    latest_shares = proxy_series[-1]["shares"] if proxy_series else {}

    return {
        "commodity_id": commodity_id,
        "algorithm": "link_country_world_v1",
        "nodes": nodes,
        "edges": edges,
        "partial_sum_series": proxy_series[-12:] if proxy_series else [],
        "latest_contributor_shares": latest_shares,
        "has_numeric_link": bool(proxy_series) or any(e["link_type"] == "identity" for e in edges),
        "note_ko": (
            "국가↔세계(또는 부분합) 엣지. identity=대세계 수출 동일, "
            "contributor=부분합 기여도, incomparable=단위 불일치."
        ),
    }
