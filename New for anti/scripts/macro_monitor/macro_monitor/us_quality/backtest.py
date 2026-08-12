"""Leakage audit and preregistered lag-evidence gate."""

from __future__ import annotations

from typing import Any, Iterable

from .contracts import available_as_of, validate_release_envelope


def audit_point_in_time(rows: Iterable[dict[str, Any]], prediction_at: str) -> dict[str, Any]:
    """Audit that every feature release existed at prediction time."""
    invalid = []
    leaked = []
    checked = 0
    for row in rows:
        checked += 1
        errors = validate_release_envelope(row)
        if errors:
            invalid.append({"release_id": row.get("release_id"), "errors": errors})
        elif not available_as_of(row, prediction_at):
            leaked.append(
                {
                    "release_id": row.get("release_id"),
                    "published_at": row.get("published_at"),
                    "prediction_at": prediction_at,
                }
            )
    return {
        "passed": not invalid and not leaked,
        "checked": checked,
        "invalid": invalid,
        "leaked": leaked,
    }


def assess_lag_evidence(
    result: dict[str, Any],
    *,
    minimum_oos: int = 36,
    minimum_adjacent_lags: int = 2,
    minimum_sign_stability: float = 0.67,
    minimum_oos_improvement_pct: float = 5.0,
) -> dict[str, Any]:
    """Map preregistered backtest evidence to a non-causal status.

    The function consumes already-computed statistics; it cannot search lags or
    tune thresholds after seeing results.
    """
    if not result.get("leakage_audit_passed"):
        status = "invalid_leakage"
    elif int(result.get("oos_n") or 0) < minimum_oos:
        status = "inconclusive"
    elif not result.get("expected_direction_holds"):
        status = "rejected" if result.get("repeated_opposite_direction") else "unstable"
    else:
        adjacent = int(result.get("adjacent_lags_supported") or 0)
        stability = float(result.get("rolling_sign_stability") or 0.0)
        improvement = float(result.get("oos_improvement_vs_best_baseline_pct") or 0.0)
        uncertainty_ok = bool(result.get("uncertainty_passed"))
        regime_ok = bool(result.get("regime_stable"))
        if (
            adjacent >= minimum_adjacent_lags
            and stability >= minimum_sign_stability
            and improvement >= minimum_oos_improvement_pct
            and uncertainty_ok
            and regime_ok
        ):
            status = "historically_supported"
        elif improvement > 0 and uncertainty_ok and (adjacent >= 1 or stability >= 0.5):
            status = "conditional"
        else:
            status = "unstable"

    return {
        "status": status,
        "thresholds": {
            "minimum_oos": minimum_oos,
            "minimum_adjacent_lags": minimum_adjacent_lags,
            "minimum_sign_stability": minimum_sign_stability,
            "minimum_oos_improvement_pct": minimum_oos_improvement_pct,
        },
        "evidence": dict(result),
        "interpretation": "historical_predictive_evidence_not_causal_finding",
    }
