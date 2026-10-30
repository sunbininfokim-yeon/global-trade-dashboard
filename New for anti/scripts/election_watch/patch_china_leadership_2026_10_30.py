#!/usr/bin/env python3
"""Apply the 20th Central Committee Fifth Plenum communique to existing slots.

Source: https://www.gov.cn/yaowen/liebiao/202610/content_7084479.htm
Does not add seats for people who were not already in this file.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRACT = ROOT / "config" / "china_leadership_extracted.json"
SRC = "https://www.gov.cn/yaowen/liebiao/202610/content_7084479.htm"
CONFIRM = "2026-10-29 20기 5중전회 공보가 정치국의 당적 제명을 확인."


def confirm(person: dict, extra: str = "") -> None:
    sentence = CONFIRM if not extra else f"{CONFIRM} {extra}"
    note = person.get("note_ko") or ""
    if CONFIRM not in note:
        person["note_ko"] = f"{note} {sentence}".strip()
    person.setdefault("source", SRC)


def strike(person: dict) -> None:
    person["status"] = "expelled_2026-10"
    person["fallen"] = True
    person["display"] = "strikethrough"
    person["confidence"] = "high"
    person["note_ko"] = f"{CONFIRM} 후임 미발표."
    person["source"] = SRC


def main() -> None:
    data = json.loads(EXTRACT.read_text(encoding="utf-8"))
    data["version"] = 10
    data["as_of"] = "2026-10-30"
    data["extracted_at"] = "2026-10-30"
    data["next_full_review"] = "2026-11-30"
    data["merge_note"] = (
        "2026-10-30 Fifth Plenum communique (gov.cn 2026-10-29): "
        "confirmed expulsions for people already on this roster; "
        "Zhang Shengmin added to the Politburo; no new CMC seat and no new ministry."
    )

    pb = data["party_state"]["politburo"]
    pb["active_n_approx"] = 22
    pb["note_ko"] = (
        "20차 정치국 원래 24명. 허웨이둥·장유샤·마싱루이 제명은 2026-10-29 5중전회가 확인. "
        "장성민을 정치국 위원으로 증선해 현원은 약 22명."
    )
    if not any(row.get("name_en") == "Zhang Shengmin" for row in pb["active"]):
        pb["active"].append(
            {
                "name_en": "Zhang Shengmin",
                "name_zh": "张升民",
                "name_ko": "장성민",
                "role_ko": "정치국 위원·군위부주석",
                "title_ko": "군위부주석",
                "since": "2026-10-29",
                "status": "incumbent",
                "note_ko": "2026-10-29 5중전회 증선. 군위부주석은 2025-10-23부터.",
                "source": SRC,
            }
        )
    for row in pb["fallen"]:
        if row.get("name_en") in ("Zhang Youxia", "Ma Xingrui"):
            confirm(row)

    for row in data["cmc"]["fallen"]:
        if row.get("name_en") in ("Zhang Youxia", "Liu Zhenli"):
            confirm(row)
    for row in data["cmc"]["active_core"]:
        if row.get("name_en") == "Zhang Shengmin":
            confirm_note = "2026-10-29 중앙정치국 위원으로 증선."
            note = row.get("note") or ""
            if confirm_note not in note:
                row["note"] = f"{note} {confirm_note}".strip()

    depts = {row["id"]: row for row in data["party_state"]["state_council"]["constituent_departments"]}
    confirm(depts["mem"]["predecessor"])
    jin = depts["miit"]["predecessor"]
    jin["status"] = "expelled_2026-10"
    jin["fallen"] = True
    jin["display"] = "strikethrough"
    confirm(jin)
    miit_note = depts["miit"]["minister"].get("note_ko") or ""
    jin_clause = "전임 진좡룽은 2026-10-29 5중전회가 제명을 확인."
    if jin_clause not in miit_note:
        depts["miit"]["minister"]["note_ko"] = f"{miit_note} {jin_clause}".strip()

    director = data["party_state"]["central_departments"]["mcf_office"]["director"]
    lei = "전 상무부주임 레이판페이(雷凡培)는 2026-10-29 제명 확인. 주임 자리는 공석."
    if lei not in (director.get("note_ko") or ""):
        director["note_ko"] = f"{director.get('note_ko') or ''} {lei}".strip()

    army = data["service_branches"]["army"]["commander"]
    army["note"] = "리차오밍(李桥铭)은 2026-10-29 5중전회가 제명을 확인. 정식 사령 미발표."
    army["source"] = SRC

    seats = {
        ("eastern", "political_commissar"): "Liu Qingsong",
        ("western", "commander"): "Wang Haijiang",
        ("northern", "commander"): "Huang Ming",
    }
    for theater in data["theater_commands"]:
        for field, expected in seats.items():
            if theater.get("id") != field[0]:
                continue
            person = theater[field[1]]
            if person.get("name_en") != expected:
                raise SystemExit(f"unexpected {theater['id']} {field[1]}: {person.get('name_en')}")
            strike(person)

    EXTRACT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {EXTRACT} version {data['version']}")


if __name__ == "__main__":
    main()
