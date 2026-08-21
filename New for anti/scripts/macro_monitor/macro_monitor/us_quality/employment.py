"""Composition-first interpretation of U.S. payroll releases."""

from __future__ import annotations

from typing import Any


EMPLOYMENT_STATES = {
    "private_broadening",
    "private_narrowing",
    "government_supported",
    "defensive_services_led",
    "mixed",
    "insufficient_data",
}


def _num(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _share(part: float, total: float) -> float | None:
    # Negative/near-zero payroll changes do not have an economically useful
    # "share" denominator.  Preserve the components and leave the ratio null.
    return round(part / total * 100.0, 2) if total > 0 else None


def classify_employment_quality(
    release: dict[str, Any],
    *,
    government_support_share_pct: float = 35.0,
    defensive_lead_share_pct: float = 50.0,
    breadth_floor_pct: float = 50.0,
    hours_drop_floor: float = -0.1,
) -> dict[str, Any]:
    """Classify the breadth of a BLS CES release without producing a score.

    ADP values may be attached as context but never enter the BLS bucket sums.
    """
    keys = (
        "total_nfp_k",
        "private_k",
        "government_k",
        "private_cyclical_k",
        "private_defensive_k",
    )
    values = {key: _num(release, key) for key in keys}
    missing = [key for key, value in values.items() if value is None]
    if missing:
        return {
            "state": "insufficient_data",
            "missing": missing,
            "evidence": [],
            "warnings": ["BLS CES 산업 버킷이 완전하지 않아 구성 판정을 보류합니다."],
        }

    total = values["total_nfp_k"] or 0.0
    private = values["private_k"] or 0.0
    government = values["government_k"] or 0.0
    cyclical = values["private_cyclical_k"] or 0.0
    defensive = values["private_defensive_k"] or 0.0
    diffusion = _num(release, "three_month_diffusion_pct")
    hours_change = _num(release, "avg_weekly_hours_change_3m")
    government_share = _share(government, total)
    defensive_share = _share(defensive, private)

    evidence = [
        {"metric": "total_nfp_k", "value": total},
        {"metric": "private_k", "value": private},
        {"metric": "government_k", "value": government},
        {"metric": "private_cyclical_k", "value": cyclical},
        {"metric": "private_defensive_k", "value": defensive},
    ]
    if diffusion is not None:
        evidence.append({"metric": "three_month_diffusion_pct", "value": diffusion})
    if hours_change is not None:
        evidence.append({"metric": "avg_weekly_hours_change_3m", "value": hours_change})

    if private <= 0 or total <= 0:
        state = "private_narrowing" if private <= 0 else "mixed"
    elif government_share is not None and government_share >= government_support_share_pct:
        state = "government_supported"
    elif defensive_share is not None and defensive_share >= defensive_lead_share_pct and cyclical <= 0:
        state = "defensive_services_led"
    elif (
        cyclical > 0
        and defensive > 0
        and diffusion is not None
        and diffusion >= breadth_floor_pct
        and (hours_change is None or hours_change >= hours_drop_floor)
    ):
        state = "private_broadening"
    elif cyclical <= 0 or (diffusion is not None and diffusion < breadth_floor_pct):
        state = "private_narrowing"
    else:
        state = "mixed"

    warnings: list[str] = []
    if release.get("adp_private_k") is not None:
        warnings.append("ADP는 별도 민간고용 표본이며 BLS CES와 합산하지 않습니다.")
    if diffusion is None:
        warnings.append("산업 확산지수가 없어 broadening 판정을 보수적으로 제한했습니다.")
    return {
        "state": state,
        "government_share_pct": government_share,
        "defensive_private_share_pct": defensive_share,
        "evidence": evidence,
        "warnings": warnings,
        "interpretation": "composition_label_not_forecast",
    }
