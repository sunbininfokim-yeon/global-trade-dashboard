#!/usr/bin/env python3
"""Copy CHN party_state onto the public board and fill the org-chart skeleton.

chn-org.js ministryPool only matches cmc.defense_minister + security_organs,
so constituent_departments never reach the State Council tab unless names are
supplied on elections_cn_party_v1.json (documented override) or the UI is
changed. This script does the data-side half without touching JS.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRACT = ROOT / "config" / "china_leadership_extracted.json"
BOARD = ROOT.parent.parent / "public" / "data" / "elections_board_v1.json"
CHART = ROOT.parent.parent / "public" / "data" / "elections_cn_party_v1.json"

KO_ALIASES = {
    "주택도농건설부": "주택도시농촌건설부",
    "심계서": "감사서",
}


def dumps_block(obj: object, key_indent: int) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    pad = " " * key_indent
    lines = body.splitlines()
    return "\n".join(lines[:1] + [pad + line for line in lines[1:]])


def replace_json_value(text: str, key: str, start: int, new_obj: object, key_indent: int) -> str:
    needle = f'"{key}": '
    idx = text.find(needle, start)
    if idx < 0:
        raise SystemExit(f"missing {key} after offset {start}")
    brace = text.find("{", idx)
    if brace < 0 or brace > idx + len(needle) + 5:
        raise SystemExit(f"{key} is not an object")
    depth = 0
    end = None
    for i, ch in enumerate(text[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"unclosed {key}")
    return text[:brace] + dumps_block(new_obj, key_indent) + text[end:]


def dept_index(departments: list[dict]) -> dict[str, dict]:
    out = {}
    for row in departments:
        out[row["title_ko"]] = row
        out[row.get("title_zh") or ""] = row
        out[row.get("id") or ""] = row
    return {k: v for k, v in out.items() if k}


def fill_chart(chart: dict, departments: list[dict]) -> int:
    by_ko = dept_index(departments)
    filled = 0
    for ministry in chart["state_council_ministries"]:
        key = KO_ALIASES.get(ministry["ko"], ministry["ko"])
        row = by_ko.get(key)
        if not row:
            raise SystemExit(f"no extract match for chart ministry {ministry['ko']}")
        minister = row.get("minister") or {}
        ministry["name_ko"] = minister.get("name_ko")
        ministry["name_en"] = minister.get("name_en")
        if minister.get("name_zh"):
            ministry["name_zh"] = minister["name_zh"]
        ministry["status"] = minister.get("status", "incumbent")
        if minister.get("since"):
            ministry["since"] = minister["since"]
        if minister.get("note_ko"):
            ministry["note_ko"] = minister["note_ko"]
        pgs = row.get("party_group_secretary") or {}
        for stale in ("party_secretary_ko", "party_secretary_en", "party_secretary_zh", "party_secretary_status"):
            ministry.pop(stale, None)
        ministry["same_as_minister"] = bool(pgs.get("same_as_minister"))
        if pgs.get("status") == "unknown":
            ministry["party_secretary_status"] = "unknown"
        if pgs.get("title_ko"):
            ministry["party_title_ko"] = pgs["title_ko"]
        if pgs.get("organ"):
            ministry["party_organ"] = pgs["organ"]
        if pgs.get("name_ko") or pgs.get("status") == "not_applicable":
            ministry["party_secretary_ko"] = pgs.get("name_ko")
            ministry["party_secretary_en"] = pgs.get("name_en")
            if pgs.get("name_zh"):
                ministry["party_secretary_zh"] = pgs["name_zh"]
            ministry["party_secretary_status"] = pgs.get("status")
        filled += 1
    return filled


def main() -> None:
    extract = json.loads(EXTRACT.read_text(encoding="utf-8"))
    party_state = extract["party_state"]
    depts = party_state["state_council"]["constituent_departments"]
    if len(depts) != 26:
        raise SystemExit(f"expected 26 constituent departments, got {len(depts)}")

    board_text = BOARD.read_text(encoding="utf-8")
    chn = board_text.find('"iso3": "CHN"')
    if chn < 0:
        raise SystemExit("CHN missing from board")
    leadership = board_text.find('"leadership": {', chn)
    if leadership < 0:
        raise SystemExit("CHN leadership missing")

    as_of = extract.get("as_of") or "2026-09-12"
    next_review = extract.get("next_full_review") or "2026-10-01"
    lead_as_of = board_text.find('"as_of": "', leadership)
    if lead_as_of < 0 or lead_as_of > leadership + 120:
        raise SystemExit("CHN leadership as_of not found")
    as_of_end = board_text.find('"', lead_as_of + len('"as_of": "'))
    board_text = board_text[:lead_as_of] + f'"as_of": "{as_of}"' + board_text[as_of_end + 1:]
    lead_review = board_text.find('"next_full_review": "', leadership)
    if lead_review < 0 or lead_review > leadership + 280:
        raise SystemExit("CHN next_full_review not found")
    review_end = board_text.find('"', lead_review + len('"next_full_review": "'))
    board_text = (
        board_text[:lead_review]
        + f'"next_full_review": "{next_review}"'
        + board_text[review_end + 1:]
    )
    board_text = replace_json_value(board_text, "party_state", leadership, party_state, 8)
    if "cmc" in party_state:
        raise SystemExit("party_state unexpectedly has a cmc key; cmc splice would hit it")
    board_text = replace_json_value(board_text, "cmc", leadership, extract["cmc"], 8)
    BOARD.write_text(board_text, encoding="utf-8")

    chart = json.loads(CHART.read_text(encoding="utf-8"))
    filled = fill_chart(chart, depts)
    CHART.write_text(json.dumps(chart, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"board party_state copied ({len(depts)} departments)")
    print(f"chart ministries named: {filled}")


if __name__ == "__main__":
    main()
