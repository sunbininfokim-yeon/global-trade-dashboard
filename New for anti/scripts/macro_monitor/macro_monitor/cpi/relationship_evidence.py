"""Turn CPI relationship diagnostics into a small, UI-safe evidence contract.

The output deliberately separates three questions:

* what BLS methodology says is mechanically linked;
* whether a candidate added out-of-sample predictive value; and
* whether the latest observed components make a structural path worth watching.

A watch phase is not a forecast.  It is only emitted for directional market
hypotheses and is always accompanied by the observations that produced it.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median
from typing import Any, Mapping, Sequence


PRACTICAL_POLICY = {
    "statistically_validated": {
        "minimum_full_grid_rmse_improvement_pct": 5.0,
        "maximum_full_grid_dm_pvalue": 0.10,
        "maximum_fdr_qvalue": 0.10,
    },
    "watch_candidate": {
        "minimum_best_lag_rmse_improvement_pct": 3.0,
        "maximum_best_lag_dm_pvalue": 0.15,
    },
}

PHASE_LABELS_KO = {
    "starting": "관찰 시작",
    "transmitting": "전이 관찰",
    "fading": "촉발 요인 둔화",
    "inactive": "현재 비활성",
    "not_applicable": "단계 판정 안 함",
    "insufficient_data": "자료 부족",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _month_shift(month: str, amount: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    serial = year * 12 + number - 1 + amount
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def _robust_score(values: Sequence[float], latest: float) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    if len(clean) < 24:
        return None
    center = median(clean)
    mad = median(abs(value - center) for value in clean)
    scale = 1.4826 * mad
    if scale <= 1e-9:
        mean = sum(clean) / len(clean)
        variance = sum((value - mean) ** 2 for value in clean) / len(clean)
        scale = math.sqrt(variance)
        center = mean
    return (latest - center) / scale if scale > 1e-9 else 0.0


def component_state(history: Mapping[str, float], reference_month: str) -> dict[str, Any]:
    """Describe one latest MoM print against its preceding 60-month history."""
    latest = _finite(history.get(reference_month))
    prior_months = [month for month in sorted(history) if month < reference_month][-60:]
    prior = [_finite(history[month]) for month in prior_months]
    score = _robust_score([value for value in prior if value is not None], latest) if latest is not None else None
    active = bool(latest is not None and latest > 0 and score is not None and score >= 0.75)
    return {
        "reference_month": reference_month,
        "mom_pct": latest,
        "robust_score": None if score is None else round(score, 3),
        "positive_impulse": active,
        "rule": "latest SA MoM > 0 and robust score versus preceding 60 months >= 0.75",
    }


def _latest_common_month(item_ids: Sequence[str], series: Mapping[str, Mapping[str, float]]) -> str | None:
    months = [max(series[item_id]) for item_id in item_ids if item_id in series and series[item_id]]
    return min(months) if months else None


def _last_active_month(history: Mapping[str, float], reference_month: str, lookback: int) -> str | None:
    for offset in range(0, lookback + 1):
        month = _month_shift(reference_month, -offset)
        if component_state(history, month)["positive_impulse"]:
            return month
    return None


def assess_watch_phase(
    relation: Mapping[str, Any],
    *,
    series: Mapping[str, Mapping[str, float]],
    item_labels: Mapping[str, str],
) -> dict[str, Any]:
    """Classify a structural watch state without creating a forecast signal."""
    if relation.get("type") != "market_hypothesis":
        return {
            "phase": "not_applicable",
            "label_ko": PHASE_LABELS_KO["not_applicable"],
            "interpretation": "method_or_context_only_not_an_inflation_phase",
        }
    source_ids = [item_id for item_id in relation.get("source_ids", []) if item_id in series]
    target_ids = [item_id for item_id in relation.get("target_ids", []) if item_id in series]
    reference_month = _latest_common_month([*source_ids, *target_ids], series)
    if not reference_month or not source_ids or not target_ids:
        return {
            "phase": "insufficient_data",
            "label_ko": PHASE_LABELS_KO["insufficient_data"],
            "interpretation": "relationship_watch_only_not_forecast",
        }

    source_states = {item_id: component_state(series[item_id], reference_month) for item_id in source_ids}
    target_states = {item_id: component_state(series[item_id], reference_month) for item_id in target_ids}
    source_active = [item_id for item_id, state in source_states.items() if state["positive_impulse"]]
    target_active = [item_id for item_id, state in target_states.items() if state["positive_impulse"]]
    lag_values = [int(value) for value in relation.get("lag_months") or [] if _finite(value) is not None]
    maximum_lag = max(lag_values) if lag_values else 3
    recent_sources = {
        item_id: _last_active_month(series[item_id], reference_month, maximum_lag)
        for item_id in source_ids
    }
    recent_sources = {item_id: month for item_id, month in recent_sources.items() if month}

    if source_active and target_active:
        phase = "transmitting"
        sentence = "출발 항목과 연결 항목이 함께 강해 전이 여부를 관찰합니다."
    elif source_active:
        phase = "starting"
        sentence = "출발 항목은 강해졌지만 연결 항목의 반응은 아직 뚜렷하지 않습니다."
    elif recent_sources and target_active:
        phase = "transmitting"
        sentence = "출발 항목의 최근 상승 뒤 연결 항목이 강해졌지만 인과로 해석하지 않습니다."
    elif recent_sources:
        phase = "fading"
        sentence = "출발 항목의 상승 강도가 낮아졌고 연결 항목도 최근 60개월의 평소 범위를 뚜렷하게 벗어나지 않았습니다."
    else:
        phase = "inactive"
        sentence = "사전 정의한 시차 창 안에서 현재 관찰할 양(+)의 촉발 요인이 없습니다."

    def labels(ids: Sequence[str]) -> list[str]:
        return [item_labels.get(item_id, item_id) for item_id in ids]

    return {
        "phase": phase,
        "label_ko": PHASE_LABELS_KO[phase],
        "reference_month": reference_month,
        "watch_window_months": [min(lag_values), maximum_lag] if lag_values else None,
        "source_active_ids": source_active,
        "target_active_ids": target_active,
        "recent_source_impulses": recent_sources,
        "component_states": {"sources": source_states, "targets": target_states},
        "summary_ko": sentence,
        "basis_ko": (
            f"{reference_month} SA MoM 기준 · 출발 {', '.join(labels(source_active)) or '없음'} · "
            f"연결 {', '.join(labels(target_active)) or '없음'}"
        ),
        "interpretation": "relationship_watch_only_not_causal_finding_or_forecast",
    }


def classify_backtest(row: Mapping[str, Any]) -> dict[str, Any]:
    """Apply a practical screening tier while retaining the stricter result."""
    full = row.get("out_of_sample") or {}
    full_improvement = _finite(full.get("rmse_improvement_pct"))
    full_pvalue = _finite((full.get("diebold_mariano") or {}).get("pvalue"))
    qvalue = _finite((row.get("conditional_predictive_test") or {}).get("fdr_qvalue"))
    best = row.get("best_lag_out_of_sample_exploratory") or {}
    best_improvement = _finite(best.get("rmse_improvement_pct"))
    best_pvalue = _finite((best.get("diebold_mariano") or {}).get("pvalue"))

    strict = PRACTICAL_POLICY["statistically_validated"]
    if (
        full_improvement is not None and full_improvement >= strict["minimum_full_grid_rmse_improvement_pct"]
        and full_pvalue is not None and full_pvalue <= strict["maximum_full_grid_dm_pvalue"]
        and qvalue is not None and qvalue <= strict["maximum_fdr_qvalue"]
    ):
        status = "statistically_validated"
        label = "통계 검증됨"
    else:
        watch = PRACTICAL_POLICY["watch_candidate"]
        if (
            best_improvement is not None and best_improvement >= watch["minimum_best_lag_rmse_improvement_pct"]
            and best_pvalue is not None and best_pvalue <= watch["maximum_best_lag_dm_pvalue"]
        ):
            status = "weak_watch_candidate"
            label = "약한 관찰 후보"
        else:
            status = "tested_no_predictive_power"
            label = "예측력 미확인"
    return {
        "test_id": row.get("id"),
        "relationship_map_id": row.get("relationship_map_id"),
        "status": status,
        "label_ko": label,
        "best_lag_months": best.get("lag_months"),
        "best_lag_rmse_improvement_pct": best_improvement,
        "best_lag_dm_pvalue": best_pvalue,
        "full_grid_rmse_improvement_pct": full_improvement,
        "full_grid_dm_pvalue": full_pvalue,
        "fdr_qvalue": qvalue,
        "coverage": row.get("coverage"),
        "interpretation": "out_of_sample_screen_not_causality",
    }


def build_evidence_snapshot(
    mapping: Mapping[str, Any],
    *,
    backtest_rows: Sequence[Mapping[str, Any]],
    series: Mapping[str, Mapping[str, float]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    labels = {
        item["id"]: item.get("label_ko", item["id"])
        for item in [*mapping.get("driver_frontier", []), *mapping.get("items", [])]
    }
    tests_by_relation: dict[str, list[dict[str, Any]]] = {}
    for row in backtest_rows:
        relation_id = row.get("relationship_map_id")
        if relation_id:
            tests_by_relation.setdefault(str(relation_id), []).append(classify_backtest(row))

    relationships = []
    reference_months = []
    for relation in mapping.get("relationships", []):
        tests = tests_by_relation.get(relation["id"], [])
        phase = assess_watch_phase(relation, series=series, item_labels=labels)
        if phase.get("reference_month"):
            reference_months.append(phase["reference_month"])
        if relation.get("type") == "measurement_link":
            tier, label = "official_methodology", "공식 산식·이연"
        elif any(test["status"] == "statistically_validated" for test in tests):
            tier, label = "statistically_validated", "통계 검증됨"
        else:
            tier, label = "relationship_candidate", "관계 후보"
        relationships.append({
            "relationship_id": relation["id"],
            "evidence_tier": tier,
            "evidence_label_ko": label,
            "phase": phase,
            "tests": tests,
            "display_policy": (
                "show_metrics_and_phase" if tier == "statistically_validated"
                else "show_method_only" if tier == "official_methodology"
                else "show_watch_language_without_forecast"
            ),
        })

    return {
        "schema_version": "us-cpi-relationship-evidence-v1",
        "country": "USA",
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reference_period": min(reference_months) if reference_months else None,
        "data_status": "official_observed_current_vintage",
        "policy": {
            "practical_screen": PRACTICAL_POLICY,
            "phase_rule": "robust latest SA MoM watch state; never a causal finding, directional signal, or numeric forecast",
            "rejected_test_rule": "a rejected sub-path is retained in details but cannot be promoted to a signal",
        },
        "relationships": relationships,
    }
