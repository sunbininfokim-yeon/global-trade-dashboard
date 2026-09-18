#!/usr/bin/env python3
"""Add party-group/committee secretaries to the 26 State Council departments.

Do not assume minister == party secretary. Confirmed splits: MFA, MEE, MNR.
MOD has no civilian party group. Remaining concurrent rows need a ministry
or Xinhua/gov.cn title, not Wikipedia.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "config" / "china_leadership_extracted.json"

COMMITTEE = "party_committee"  # 党委
GROUP = "party_group"  # 党组


def secretary(
    *,
    same_as_minister: bool,
    organ: str,
    name_en=None,
    name_zh=None,
    name_ko=None,
    since=None,
    status="incumbent",
    confidence="high",
    note_ko=None,
    source=None,
):
    title_zh = {"party_committee": "党委书记", "party_group": "党组书记"}.get(organ)
    title_ko = {"party_committee": "당위서기", "party_group": "당조서기"}.get(organ)
    row = {
        "same_as_minister": same_as_minister,
        "organ": organ,
        "status": status,
        "confidence": confidence,
    }
    if title_zh:
        row["title_zh"] = title_zh
        row["title_ko"] = title_ko
    if name_en:
        row["name_en"] = name_en
        row["name_zh"] = name_zh
        row["name_ko"] = name_ko
    if since:
        row["since"] = since
    if note_ko:
        row["note_ko"] = note_ko
    if source:
        row["source"] = source
    return row


def concurrent(dept: dict, organ: str, source: str, confidence="high") -> dict:
    minister = dept["minister"]
    return secretary(
        same_as_minister=True,
        organ=organ,
        name_en=minister["name_en"],
        name_zh=minister.get("name_zh"),
        name_ko=minister["name_ko"],
        status=minister.get("status", "incumbent"),
        confidence=confidence,
        source=source,
    )


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    data["version"] = 7
    data["merge_note"] = (
        "2026-09-12 Cursor patch v7: party group/committee secretary on all 26 "
        "constituent departments. Splits: MFA Qi Yu, MEE Sun Jinlong, MNR Liu "
        "Guohong with minister vacant (presidential order 79). MOD not applicable. "
        "Wikipedia not used."
    )

    depts = {row["id"]: row for row in data["party_state"]["state_council"]["constituent_departments"]}

    # --- splits / vacant ---
    depts["mfa"]["party_group_secretary"] = secretary(
        same_as_minister=False,
        organ=COMMITTEE,
        name_en="Qi Yu",
        name_zh="齐玉",
        name_ko="제위",
        confidence="high",
        note_ko="부장 왕이와 분리. 외교부는 당위.",
        source="https://www.fmprc.gov.cn/wjb_673085/zygy_673101/qy/",
    )
    depts["mfa"]["minister"]["note_ko"] = "당위 서기는 제위 齐玉. 부장≠당서기"

    depts["mod"]["party_group_secretary"] = secretary(
        same_as_minister=False,
        organ="not_applicable",
        status="not_applicable",
        confidence="high",
        note_ko="국방부는 국무원 구성부문이지만 민간 당조가 없다. PLA·중앙군사위 계통.",
    )

    depts["mee"]["party_group_secretary"] = secretary(
        same_as_minister=False,
        organ=GROUP,
        name_en="Sun Jinlong",
        name_zh="孙金龙",
        name_ko="쑨진룽",
        since="2020-04",
        confidence="high",
        note_ko="부부장 겸. 부장 황룬추는 구삼학사(비당원).",
        source="https://www.mee.gov.cn/zjhb/ldzc/",
    )
    depts["mee"]["minister"]["note_ko"] = "구삼학사. 당조 서기는 쑨진룽. 부장≠당서기"

    depts["mnr"]["minister"] = {
        "name_en": "vacant_mnr_minister",
        "name_ko": "공석",
        "status": "vacant",
        "since": "2026-06-26",
        "confidence": "high",
        "title_ko": "자연자원부",
        "note_ko": "관즈어우 면. 주석령 79호. 후임 부장은 인대 미임명.",
    }
    depts["mnr"]["predecessor"] = {
        "name_en": "Guan Zhi'ou",
        "name_zh": "关志鸥",
        "name_ko": "관즈어우",
        "status": "removed",
        "since": "2024-12-25",
        "until": "2026-06-26",
        "next_post": "중공 후베이성위 서기",
        "next_post_since": "2026-05-30",
        "confidence": "high",
    }
    depts["mnr"]["party_group_secretary"] = secretary(
        same_as_minister=False,
        organ=GROUP,
        name_en="Liu Guohong",
        name_zh="刘国洪",
        name_ko="류궈훙",
        since="2026-07-30",
        confidence="high",
        note_ko="중조부 발표. 부장 인대 임명은 아직 없다.",
        source="https://www.news.cn/politics/20260730/dd7f1f8bd6ad4386b771e0d1af63ebe8/c.html",
    )

    concurrent_sources = {
        "ndrc": (GROUP, "https://www.ndrc.gov.cn/fzggw/wld/zsj/", "high"),
        "moe": (GROUP, "http://www.moe.gov.cn/jyb_zzjg/moe_187/huaijinpeng/", "high"),
        "most": (GROUP, "https://most.gov.cn/zzjg/bld/", "high"),
        "miit": (GROUP, "https://www.miit.gov.cn/bld/index.html", "high"),
        "seac": (GROUP, "https://www.neac.gov.cn/seac/mwjs/", "high"),
        "mps": (COMMITTEE, "https://www.gov.cn/guoqing/2023-03/12/content_5746384.htm", "high"),
        "mss": (COMMITTEE, "http://chinapeace.gov.cn/chinapeace/c100007/2026-09/09/content_12855649.shtml", "high"),
        "mca": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "moj": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mof": (GROUP, "http://www.mof.gov.cn/znjg/buzhangzhichuang/czblfa/grjjlfa/", "high"),
        "mohrss": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mohurd": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mot": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mwr": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mara": (GROUP, "https://dangwei.moa.gov.cn/zjxxjy/202606/t20260623_6485209.htm", "high"),
        "mofcom": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mct": (GROUP, "https://www.mct.gov.cn/gywhb/bld/", "high"),
        "nhc": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mva": (GROUP, "https://liuyan.people.com.cn/pro-dfbbs-front/home", "medium-high"),
        "mem": (COMMITTEE, "https://www.mem.gov.cn/jg/ldxx/zhchzh/index.shtml", "high"),
        "pbc": (COMMITTEE, "https://www.pbc.gov.cn/hanglingdao/128697/128734/index.html", "high"),
        "nao": (GROUP, "https://www.audit.gov.cn/n10/n15/c140218/content.html", "high"),
    }
    for dept_id, (organ, source, confidence) in concurrent_sources.items():
        depts[dept_id]["party_group_secretary"] = concurrent(depts[dept_id], organ, source, confidence)

    sc = data["party_state"]["state_council"]
    extra_sources = [
        "http://www.npc.gov.cn/npc/c2/c30834/202606/t20260626_455822.html",
        "https://www.12371.cn/2026/06/26/ARTI1782481321320800.shtml",
        "https://www.news.cn/politics/20260730/dd7f1f8bd6ad4386b771e0d1af63ebe8/c.html",
        "https://www.news.cn/politics/20260530/328c3d70ff984ed38a5e0fc89427ce43/c.html",
        "https://www.fmprc.gov.cn/wjb_673085/zygy_673101/qy/",
        "https://www.mee.gov.cn/zjhb/ldzc/",
    ]
    sc["sources"] = list(dict.fromkeys((sc.get("sources") or []) + extra_sources))
    sc["note_ko"] = (
        "공식 구성부문 26곳. cabinet_23=false는 국방·인행·감사. "
        "당조/당위 서기는 party_group_secretary. 분리: 외교·생태환경·자연자원. "
        "국방부는 민간 당조 없음. 자연자원부 부장은 2026-06-26 이후 공석."
    )

    missing = [row["id"] for row in sc["constituent_departments"] if "party_group_secretary" not in row]
    if missing:
        raise SystemExit(f"missing party_group_secretary: {missing}")

    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    splits = [
        row["id"]
        for row in sc["constituent_departments"]
        if not row["party_group_secretary"].get("same_as_minister")
        and row["party_group_secretary"].get("organ") != "not_applicable"
    ]
    print("patched", PATH)
    print("splits", splits)
    print("mnr minister", depts["mnr"]["minister"]["status"], "pgs", depts["mnr"]["party_group_secretary"]["name_zh"])


if __name__ == "__main__":
    main()
