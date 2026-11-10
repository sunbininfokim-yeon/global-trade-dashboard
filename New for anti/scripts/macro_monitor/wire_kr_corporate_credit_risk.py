#!/usr/bin/env python3
"""Update the Korea growth card from the FSS annual regular evaluation releases."""

from __future__ import annotations

import json
from pathlib import Path

from macro_monitor import us_public_series as ups
from macro_monitor import world_public_series as wps

PACK = Path(__file__).resolve().parents[2] / "public" / "data" / "macro_monitor_v1.json"
CARD_ID = "kr_corporate_credit_risk"
# Evaluation year, KDI archive date, KDI release ID, C, D, large, SME.
# The 2022 breakdown is also reported as the prior-year comparison in the 2023 release.
RELEASES = (
    (2022, "2022-12-20", 233532, 84, 101, 2, 183),
    (2023, "2023-12-18", 246103, 118, 113, 9, 222),
    (2024, "2024-12-24", 261497, 100, 130, 11, 219),
    (2025, "2025-12-18", 274908, 104, 117, 17, 204),
)


def main() -> None:
    pack_text = PACK.read_text(encoding="utf-8")
    pack = json.loads(pack_text)
    korea = next(country for country in pack["countries"] if country["iso3"] == "KOR")
    years = [str(row[0]) for row in RELEASES]
    points = []
    for year, _, _, grade_c, grade_d, large, sme in RELEASES:
        total = grade_c + grade_d
        if total != large + sme:
            raise ValueError(f"{year}: grade and company-size totals differ")
        points.append((f"{year}-12-31", total))

    spec = ups.Spec(
        CARD_ID, "annual", "개사", wps.money("", 0, signed=False, suffix="개사"),
        "채권은행의 연간 정기 신용위험평가에서 C·D등급을 받은 부실징후기업 수입니다. 수시평가 결과는 별도입니다.",
        "금융감독원",
        tuple(f"https://eiec.kdi.re.kr/policy/materialView.do?num={row[2]}" for row in reversed(RELEASES)),
        "annual", label_ko="기업 신용위험평가", chart_type="bar",
    )
    patch = ups.build_patch(spec, points, retrieved_at=ups.now_iso(), asof=RELEASES[-1][1])
    patch["panels"] = [
        {
            "id": panel_id, "label": label, "type": "stack", "unit": spec.unit, "dates": years,
            "series": [{"label": name, "values": [row[index] for row in RELEASES]} for name, index in columns],
            "note_ko": note,
        }
        for panel_id, label, columns, note in (
            ("grade", "등급별", (("C등급", 3), ("D등급", 4)),
             "C등급은 경영정상화 가능성이 있는 기업, D등급은 경영정상화 가능성이 낮은 기업입니다."),
            ("size", "기업 규모별", (("대기업", 5), ("중소기업", 6)),
             "이 평가에서는 금융권 신용공여 500억원 이상을 대기업으로 분류합니다."),
        )
    ]
    ups.ensure_card(korea, CARD_ID, "growth", spec)
    indicators = {indicator["id"]: indicator for indicator in korea["indicators"]}
    ups.apply_patch(indicators[CARD_ID], patch)
    ups.sync_chips(korea, indicators, {CARD_ID})
    ups.refresh_status_summary(korea)
    updated = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if updated != pack_text:
        PACK.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
