"""Build elections_contest_v1 for jpn-2026-fukushima-governor.

Official filing list, 2026-10-08. Vote is 2026-10-25, so there is no result.
The assembly by-election on the same notice is a different event and is not here.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "jpn-2026-fukushima-governor"
PDF = "https://www.pref.fukushima.lg.jp/uploaded/attachment/766449.pdf"
PAGE = "https://www.pref.fukushima.lg.jp/sec/62010a/23-chiji.html"

# Filing order on the prefectural election commission list (届出受理番号).
CANDIDATES: List[Dict[str, Any]] = [
    {
        "party_abbr": "IND",
        "name": "金山 屯",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 1번. 만 86세. 무소속. 직업은 自然塾 白河乗馬学校 대표.",
    },
    {
        "party_abbr": "IND",
        "name": "内堀 雅雄",
        "status": "nominated",
        "incumbent": True,
        "source": PDF,
        "note_ko": "접수 2번. 만 62세. 무소속. 현직 지사. 통칭 内堀 まさお. 직업은 후쿠시마현 지사.",
    },
    {
        "party_abbr": "JCP",
        "name": "小山田 友子",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 3번. 만 33세. 당파 日本共産党. 통칭 小山田 ともこ. 직업은 정당 임원.",
    },
    {
        "party_abbr": "IND",
        "name": "塚越 栄光",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 4번. 만 51세. 무소속. 통칭 つかこし 栄光. 직업은 조원업.",
    },
    {
        "party_abbr": "IND",
        "name": "遠藤 雄大",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 5번. 만 41세. 무소속. 통칭 えんどう 雄大. 직업은 회사 경영.",
    },
    {
        "party_abbr": "IND",
        "name": "藤本 昭一",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 6번. 만 61세. 무소속. 직업란은 무직.",
    },
    {
        "party_abbr": "IND",
        "name": "長谷沼 邦彦",
        "status": "nominated",
        "source": PDF,
        "note_ko": "접수 7번. 만 59세. 무소속. 통칭 はせぬま くにひこ. 주소는 사이타마현 가스카베시. 직업은 회사 경영.",
    },
]


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def upsert_index() -> None:
    path = PUBLIC / "elections_contests_index_v1.json"
    idx = json.loads(path.read_text(encoding="utf-8"))
    idx["as_of"] = AS_OF
    row = {
        "event_id": EVENT_ID,
        "iso3": "JPN",
        "date": "2026-10-25",
        "path": f"elections_contests/{EVENT_ID}.json",
        "status": "partial",
        "as_of": AS_OF,
    }
    events = [e for e in idx.get("events", []) if e.get("event_id") != EVENT_ID]
    events.append(row)
    events.sort(key=lambda e: (e.get("date") or "", e.get("event_id") or ""))
    idx["events"] = events
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> Dict[str, Any]:
    if len(CANDIDATES) != 7:
        raise SystemExit(f"candidate count {len(CANDIDATES)}")
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "JPN",
        "date": "2026-10-25",
        "system_id": "jpn-prefecture-governor",
        "as_of": AS_OF,
        "sources": [PDF, PAGE],
        "parties": [
            {
                "abbr": "IND",
                "name_ko": "무소속",
                "name_en": "Independent",
                "name_ja": "無所属",
                "note_ko": "접수표의 당파가 無所属인 사람. 추천 정당이 있어도 여기 합산하지 않는다.",
            },
            {
                "abbr": "JCP",
                "name_ko": "일본공산당",
                "name_en": "Japanese Communist Party",
                "name_ja": "日本共産党",
            },
        ],
        "columns": [
            {
                "key": "governor",
                "label_ko": "현지사",
                "current": {
                    "by_party": {"IND": 1},
                    "total": 1,
                    "as_of": "2026-10-08",
                    "note_ko": "선거 전 현직 内堀 雅雄(무소속). 1=1.",
                    "vacancies": 0,
                },
                "contested_ko": "도도부현 지사 1인",
                "seat_note_ko": (
                    "제23회 후쿠시마현 지사 선거. 고시 2026-10-08, 투개표 2026-10-25. "
                    "같은 고시의 현의회 보궐은 이 파일이 아니다. 개표 전이므로 득표·당선은 없다."
                ),
                "districts": [
                    {
                        "id": "fukushima",
                        "name_ko": "후쿠시마현",
                        "name_ja": "福島県",
                        "seats": 1,
                        "status": "nominated",
                        "note_ko": "현 선거관리위원회 입후보 신고 상황(확정). 접수번호 순.",
                        "candidates": CANDIDATES,
                    }
                ],
            }
        ],
        "note_ko": "임기 만료 지사 선거다. 보궐이 아니다.",
    }
    return compact(doc)


def main() -> None:
    doc = build()
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    n = len(doc["columns"][0]["districts"][0]["candidates"])
    print(f"wrote {out} ({out.stat().st_size} bytes); candidates {n}")


if __name__ == "__main__":
    main()
