"""Reviewed maritime rule references, shared by the local APIs and scenarios."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("regulatory_snapshot.json")


def regulatory_review():
    raw = SNAPSHOT.read_bytes()
    return {**json.loads(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def ets_context(emissions_year, applied_phase):
    review = regulatory_review()
    context = {
        "review_as_of": review["as_of"],
        "review_sha256": review["sha256"],
        "status": "outside_reviewed_schedule",
        "warnings_ko": [],
    }
    try:
        year_number = Decimal(str(emissions_year))
        if not year_number.is_finite() or year_number != year_number.to_integral_value():
            raise ValueError("invalid emissions year")
        year = int(year_number)
    except (InvalidOperation, TypeError, ValueError):
        context["warnings_ko"].append("배출연도를 확인해야 규정 기준을 비교할 수 있습니다.")
        return context

    row = next((r for r in review["ets_schedule"]
                if r["emissions_year_from"] <= year <= r["emissions_year_to"]), None)
    if row is None:
        context["warnings_ko"].append("해당 배출연도는 이번 규정 일정 검토 범위 밖입니다.")
        return context

    expected = Decimal(row["surrender_fraction"])
    matches = Decimal(str(applied_phase)) == expected
    context.update({
        "status": "matches_reviewed_schedule" if matches else "phase_assumption_differs",
        "emissions_year": year,
        "surrender_year": year + 1,
        "surrender_deadline": f"{year + 1}-{review['ets_surrender_month_day']}",
        "statutory_phase_factor": row["surrender_fraction"],
        "applied_phase_factor": str(applied_phase),
        "gases": row["gases"],
        "source_url": review["sources"]["ets_directive"]["url"],
    })
    if not matches:
        context["warnings_ko"].append(
            f"{year}년 배출분의 현행 제출비율은 {expected * 100:g}%입니다. "
            f"입력한 {Decimal(str(applied_phase)) * 100:g}%를 시나리오 가정으로 계산했습니다.")
    return context
