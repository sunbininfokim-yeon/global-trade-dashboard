"""Build elections_contest_v1 for fra-2026-rn-congres-19.

Party congress (not a public election). President: official RN protocol + Le Parisien
quoting congress organiser Yoann Gillet (also named on the RN page). National
council: 100 elected seats; named list not published — district stays scheduled.
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
EVENT_ID = "fra-2026-rn-congres-19"

RN_CONGRES = "https://rassemblementnational.fr/congres2026"
WIKI = "https://fr.wikipedia.org/wiki/XIXe_congr%C3%A8s_du_Rassemblement_national"
PARISIEN = (
    "https://www.leparisien.fr/politique/rassemblement-national-jordan-bardella-"
    "seul-candidat-a-sa-reelection-a-la-presidence-du-parti-10-08-2026-"
    "AWDGYDAMBBF4VFRFHN4JVNN2J4.php"
)


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def upsert_index() -> None:
    path = PUBLIC / "elections_contests_index_v1.json"
    if path.exists():
        idx = json.loads(path.read_text(encoding="utf-8"))
    else:
        idx = {
            "schema": "elections_contests_index_v1",
            "null_policy": {"없음": "해당 없음", "불명": "미확정"},
            "events": [],
        }
    idx["as_of"] = AS_OF
    idx.setdefault("null_policy", {"없음": "해당 없음", "불명": "미확정"})
    row = {
        "event_id": EVENT_ID,
        "iso3": "FRA",
        "date": "2026-10-24",
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
    parties: List[Dict[str, str]] = [
        {
            "abbr": "RN",
            "name_fr": "Rassemblement national",
            "name_ko": "국민연합",
            "name_en": "National Rally",
            "leader_ko": "조르당 바르델라",
            "note_ko": "당내 전당대회. 일반 유권자 선거가 아니다. 유권자는 2026-09-20까지 당비 납부 당원.",
        }
    ]
    president = {
        "id": "president",
        "name_ko": "당수",
        "group_ko": "전국",
        "seats": 1,
        "status": "nominated",
        "candidates": [
            {
                "party_abbr": "RN",
                "name": "Jordan Bardella",
                "incumbent": True,
                "status": "nominated",
                "source": PARISIEN,
                "note_ko": (
                    "현직(2022–). 전당대회 조직 담당 요안 질레(AFP/르파리지앙 2026-08-10)가 "
                    "유일한 당수 후보라고 밝혔다. 확대 전국평의회 20% 추천. 위키 후보자 칸에도 이 이름만 있다. "
                    "전자투표는 열려 있어 무투표(uncontested)로 두지 않았다."
                ),
            }
        ],
    }
    conseil = {
        "id": "conseil-national",
        "name_ko": "전국평의회",
        "group_ko": "전국",
        "seats": 100,
        "status": "scheduled",
        "candidates": [],
        "note_ko": (
            "당원 직선 100석. 당수가 20명을 추가로 지명(위키)하나 투표용지가 아니라 이 열에 넣지 않았다. "
            "르파리지앙: 등록 421명(남 307·여 114). 명단은 RN 사이트에 없어 이름을 넣지 않았다. "
            "바르델라·르펜은 이 투표에 입후보하지 않음(당수는 직권 위원, 20명 지명 가능)."
        ),
    }
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "FRA",
        "date": "2026-10-24",
        "as_of": AS_OF,
        "sources": [RN_CONGRES, WIKI, PARISIEN],
        "parties": parties,
        "columns": [
            {
                "key": "president",
                "label_ko": "당수",
                "current": {
                    "by_party": {"RN": 1},
                    "total": 1,
                    "as_of": AS_OF,
                    "note_ko": "현직 당수 조르당 바르델라(2022년 전당대회 당선). 당내 1인 자리.",
                },
                "contested_ko": "당수 1인. 전자투표 2026-09-21–10-22, 결과 10-24 오를레앙 발표.",
                "seat_note_ko": (
                    "확대 전국평의회 20% 추천이 필요(RN 규약·위키). "
                    "일요일(10-25) 대선 출정식은 이 열이 아니다."
                ),
                "districts": [president],
            },
            {
                "key": "conseil_national",
                "label_ko": "전국평의회",
                "current": {
                    "by_party": {"RN": 100},
                    "total": 100,
                    "as_of": AS_OF,
                    "note_ko": (
                        "당원 직선분 100석. 전원 RN 당내 기구라 정당 키는 RN 하나. "
                        "현직 명단은 출처에 없어 사람 이름을 넣지 않았다. 지명 20석은 total에 넣지 않았다."
                    ),
                },
                "contested_ko": "전국평의회 직선 100석. 전자투표 같은 기간. 상위 100명.",
                "seat_note_ko": "2년 이상 당원만 입후보(2024-07-10 이전 가입). 당비·재정 의무 충족.",
                "districts": [conseil],
            },
        ],
        "note_ko": (
            "당권 행사. 유권자는 2026-09-20까지 당비 납부 당원(RN 공지). "
            "규약 개정 임시총회는 대진이 아니라 넣지 않았다. 결과 발표 전."
        ),
    }
    return compact(doc)


def main() -> None:
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"president {len(doc['columns'][0]['districts'][0]['candidates'])}; "
        f"conseil scheduled"
    )


if __name__ == "__main__":
    main()
