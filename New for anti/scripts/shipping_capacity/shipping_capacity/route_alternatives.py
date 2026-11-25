"""Same-service detour arithmetic and a separately scoped Arctic benchmark."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def service_detour_comparison(
    profile: dict[str, Any], baseline: dict[str, Any], traffic_input_status: str,
) -> dict[str, Any]:
    """Compare one detour at a time, not a closure-duration simulation.

    At fixed cargo and loading, fleet requirement is proportional to cycle
    length. Non-exposed cargo retains its normal cycle. This uses the existing
    baseline, including its direction driver, without adding reserve twice.
    """
    normal = profile["normal"]
    baseline_dwt = baseline["baseline_required_dwt"]
    basis_available = bool(traffic_input_status) and not traffic_input_status.startswith("scenario_seed")
    unavoidable_gates = [
        row["chokepoint_id"] for row in profile["chokepoint_alternatives"] if not row["reroute_available"]
    ]
    options: dict[tuple, dict[str, Any]] = {}
    for row in profile["chokepoint_alternatives"]:
        gate = row["chokepoint_id"]
        receiver = row["reroute_receiver_id"]
        evidence = row["distance_evidence"] or {}
        available = row["reroute_available"]
        extra_nm = row["reroute_extra_nm_one_way"]
        exposed_share = row["exposure_share"]
        # Identical Cape detours are shared by Suez and Bab el-Mandeb;
        # a closure affecting either gate cannot create two copies of it.
        key = ("cape", extra_nm, exposed_share) if available and receiver == "cape_good_hope" else (gate,)
        if key in options:
            options[key]["bypassed_chokepoint_ids"].append(gate)
            continue
        extra_days = row["reroute_extra_cycle_days"]
        increase = exposure_adjusted_dwt = None
        if available and basis_available:
            increase = exposed_share * extra_days / normal["cycle_days_round_trip"]
            exposure_adjusted_dwt = baseline_dwt * increase
        if not available:
            status = "no_same_port_sea_detour"
            label = "동일 출발·도착항의 해상 우회 없음"
            warning = "대체 선적·송유관·운송 보류는 별도입니다. 우회거리·추가 DWT를 0으로 보지 않습니다."
        elif receiver == "cape_good_hope":
            status = "representative_sea_detour"
            label = "희망봉 우회"
            warning = "일반 운항 속도와 동일한 항만 체류 가정입니다. 운항표나 추가 대기 예측이 아닙니다."
        else:
            status = "conditional_geometry_only"
            label = (
                "순다 경유 가정" if gate == "malacca" and "sunda" in evidence.get("reroute_traversed_passages", [])
                else "대표 우회거리 가정"
            )
            warning = (
                "통과 가능한 선박이라는 조건에서만 성립합니다. 선종·흘수별 통과 적격성이나 우회로 처리능력은 검증하지 않았습니다."
                if gate == "malacca" else
                "대표 우회거리로 계산한 민감도입니다. 실제 우회 경로·흘수·항만 조건은 정해지지 않았습니다."
            )
        options[key] = {
            "id": receiver if key[0] == "cape" else gate,
            "label_ko": label,
            "status": status,
            "bypassed_chokepoint_ids": [gate] if available else [],
            "blocking_chokepoint_id": None if available else gate,
            "requires_open_chokepoint_ids": unavoidable_gates if available else [],
            "distance_basis": row["input_status"],
            "distance_evidence_id": evidence.get("id"),
            "distance_nm_one_way": row["rerouted_distance_nm_one_way"],
            "additional_nm_one_way": extra_nm,
            "additional_sailing_days_one_way": row["reroute_extra_days_one_way"],
            "additional_cycle_days_round_trip": extra_days,
            "cycle_days_round_trip": row["rerouted_cycle_days"],
            "exposed_flow_share": exposed_share,
            "required_dwt_with_detour": round(baseline_dwt + exposure_adjusted_dwt, 6) if exposure_adjusted_dwt is not None else None,
            "additional_required_dwt": round(exposure_adjusted_dwt, 6) if exposure_adjusted_dwt is not None else None,
            "additional_required_dwt_pct": round(increase * 100, 4) if increase is not None and baseline_dwt > 0 else None,
            "warning_ko": warning,
        }
        if not available and gate == "hormuz":
            options[key]["warning_ko"] += " 페르시아만 안쪽 항에서 출발하는 선박은 희망봉으로 돌아 호르무즈를 피할 수 없습니다."
    # Keep IDs distinct even if a future config uses two different Cape assumptions.
    id_counts = {}
    for option in options.values():
        key = option["id"]
        id_counts[key] = id_counts.get(key, 0) + 1
    for option in options.values():
        if id_counts[option["id"]] > 1:
            option["id"] += ":" + "+".join(option["bypassed_chokepoint_ids"])
    return {
        "method_id": "fixed_service_flow_exposure_weighted_cycle_v1",
        "traffic_input_status": traffic_input_status,
        "baseline_required_dwt": baseline_dwt if basis_available else None,
        "options": list(options.values()),
        "warning_ko": (
            "영향받는 비중만 양방향으로 우회하고, 연간 화물·적재율·일반 속도·항만 체류일은 같다고 가정합니다. "
            "DWT는 운송 수요를 유지하는 데 필요한 모형상 배치량이며 실제 통항량·여유 선대가 아닙니다. "
            "서로 다른 대안의 수치를 합하지 않습니다. 컨테이너 TEU·LNG 화물창 m³로 임의 환산하지 않습니다."
        ),
    }


def _positive(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def load_arctic_route_reference(path: Path) -> dict[str, Any]:
    """Reuse the published ice-model port-pair comparison, not its forecasts."""
    source = {
        "source_path": "sea_route_v1.json",
        "source_field": "route_line.compare",
        "status": "unavailable",
        "routes": [],
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        line = payload["route_line"]
        comparison = line["compare"]
        if (comparison["from_ko"], comparison["to_ko"]) != ("부산", "로테르담"):
            return source
        rows = comparison["routes"]
        by_id = {row["id"]: row for row in rows}
        speed = comparison["speed_kn"]
        note = comparison["note_ko"]
        if (len(rows) != 3 or set(by_id) != {"suez", "cape", "nsr"}
                or not _positive(speed) or not isinstance(note, str) or not note
                or not all(_positive(row["nm"]) and _positive(row["days"]) for row in rows)):
            return source
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return source
    base = by_id["suez"]
    return {
        **source,
        "status": "conditional_port_pair_reference",
        "origin_ko": comparison["from_ko"],
        "destination_ko": comparison["to_ko"],
        "open_water_speed_knots": speed,
        "baseline_id": "suez",
        "source_note_ko": note,
        "routes": [
            {
                "id": key,
                "distance_nm_one_way": row["nm"],
                "transit_days_one_way": row["days"],
                "difference_nm_one_way": round(row["nm"] - base["nm"], 2),
                "difference_days_one_way": round(row["days"] - base["days"], 2),
                "difference_days_round_trip_transit": round(2 * (row["days"] - base["days"]), 2),
                "additional_required_dwt": None,
            }
            for key in ("suez", "cape", "nsr") for row in (by_id[key],)
        ],
        "warning_ko": (
            "부산–로테르담 대표 항구쌍의 모형 비교입니다. 왕복 차이는 양방향 통과시간이 같다는 가정이며 항만 체류를 제외합니다. "
            "북극항로는 해빙·선박 적격성·허가에 따라 이용 가능성이 달라집니다. "
            "동아시아–북유럽 전체 물동량이나 동일 선급 배치를 적용할 근거가 없어 추가 DWT는 산출하지 않습니다."
        ),
    }
