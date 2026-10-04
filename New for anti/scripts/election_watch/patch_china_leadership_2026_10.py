#!/usr/bin/env python3
"""Monthly check 2026-10-01: changes since the 2026-09-12 patch.

Only slots that already exist are touched. No NPCSC session met in September
(the 24th closed 2026-08-28), so no minister was formally appointed or removed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "config" / "china_leadership_extracted.json"

EXPULSION_SRC = "https://paper.people.com.cn/rmrb/pc/content/202609/22/content_30182384.html"
EXPULSION_NOTE = "2026-09-21 정치국 회의 당적 제명 승인. 군적은 앞서 제명. 군사검찰 이송."


def expel(row: dict) -> None:
    row["status"] = "expelled_2026-09"
    row["fallen"] = True
    row["display"] = "strikethrough"
    row["note_ko"] = EXPULSION_NOTE
    row["source"] = EXPULSION_SRC


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    data["version"] = 8
    data["as_of"] = "2026-10-01"
    data["extracted_at"] = "2026-10-01"
    data["next_full_review"] = "2026-11-01"
    data["merge_note"] = (
        "2026-10-01 Cursor monthly check: MIIT Li Lecheng to Anhui party secretary "
        "(2026-09-23, minister removal pending NPCSC); Zhang Youxia and Liu Zhenli "
        "expelled from the party (2026-09-21); Wang Xiangxi expelled (2026-09-08). "
        "No NPCSC session in September. Wikipedia not used."
    )

    depts = {row["id"]: row for row in data["party_state"]["state_council"]["constituent_departments"]}

    miit = depts["miit"]
    miit["minister"]["note_ko"] = (
        "2026-09-23 중앙 결정으로 안후이성위 서기 전출. 부장직은 인대 상무위 면직 전까지 "
        "법적으로 남는다. 후임 미발표."
    )
    miit["minister"]["transfer"] = {
        "to_ko": "중공 안후이성위 서기",
        "to_zh": "中共安徽省委书记",
        "date": "2026-09-23",
        "npc_removal": "pending",
        "source": "https://www.news.cn/politics/20260923/c0696467dcc44eb99211b61aab57ba22/c.html",
    }
    miit["party_group_secretary"] = {
        "same_as_minister": False,
        "organ": "party_group",
        "title_zh": "党组书记",
        "title_ko": "당조서기",
        "status": "unknown",
        "confidence": "medium",
        "note_ko": "리러청 2026-09-23 안후이 전출. 후임 당조서기 미발표.",
        "predecessor": {
            "name_en": "Li Lecheng",
            "name_zh": "李乐成",
            "name_ko": "리러청",
            "until": "2026-09-23",
        },
    }

    mem_prev = depts["mem"]["predecessor"]
    mem_prev["status"] = "expelled_2026-09"
    mem_prev["note_ko"] = "2026-02 부장 면직 후 2026-09-08 당적·공직 박탈(쌍개). 검찰 이송."
    mem_prev["source"] = "https://www.chinanews.com.cn/gn/2026/09-08/10692684.shtml"

    mnr_pgs = depts["mnr"]["party_group_secretary"]
    mnr_pgs["note_ko"] = (
        "중조부 발표. 2026-09-22 국신판 회견 직함은 '당조서기·국가자연자원총독찰'. "
        "부장 인대 임명은 아직 없다."
    )

    touched = 0
    for row in data["party_state"]["politburo"].get("fallen", []):
        if row.get("name_en") in ("Zhang Youxia", "Liu Zhenli"):
            expel(row)
            touched += 1
    for row in data["cmc"].get("fallen", []):
        if row.get("name_en") in ("Zhang Youxia", "Liu Zhenli"):
            expel(row)
            touched += 1
    if touched < 3:
        raise SystemExit(f"expected Zhang Youxia x2 + Liu Zhenli x1, touched {touched}")

    sc = data["party_state"]["state_council"]
    sc["as_of"] = "2026-10-01"
    sc["sources"] = list(dict.fromkeys((sc.get("sources") or []) + [
        "https://www.news.cn/politics/20260923/c0696467dcc44eb99211b61aab57ba22/c.html",
        "https://www.chinanews.com.cn/gn/2026/09-08/10692684.shtml",
        "https://www.forestry.gov.cn/lyj/1/lcdt/20260922/689301.html",
    ]))

    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("patched", PATH, "version", data["version"])


if __name__ == "__main__":
    main()
