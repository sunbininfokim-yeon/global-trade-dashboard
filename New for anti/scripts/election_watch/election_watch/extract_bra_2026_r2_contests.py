"""Build elections_contest_v1 for bra-2026-general-r2.

Runoff for president and governors only, 2026-10-25. First round is 2026-10-04
and has not been held — candidates stay empty (scheduled). Chamber/senate have
no runoff and are not in this file.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "bra-2026-general-r2"

TSE = "https://www.tse.jus.br/"
WIKI = "https://en.wikipedia.org/wiki/2026_Brazilian_general_election"
WIKI_GOV = "https://en.wikipedia.org/wiki/List_of_current_state_governors_in_Brazil"
CONST = "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"

UFS: List[Tuple[str, str, str]] = [
    ("AC", "Acre", "아크리"),
    ("AL", "Alagoas", "알라고아스"),
    ("AP", "Amapá", "아마파"),
    ("AM", "Amazonas", "아마조나스"),
    ("BA", "Bahia", "바이아"),
    ("CE", "Ceará", "세아라"),
    ("DF", "Distrito Federal", "연방구"),
    ("ES", "Espírito Santo", "이스피리투산투"),
    ("GO", "Goiás", "고이아스"),
    ("MA", "Maranhão", "마라냥"),
    ("MT", "Mato Grosso", "마투그로수"),
    ("MS", "Mato Grosso do Sul", "마투그로수두술"),
    ("MG", "Minas Gerais", "미나스제라이스"),
    ("PA", "Pará", "파라"),
    ("PB", "Paraíba", "파라이바"),
    ("PR", "Paraná", "파라나"),
    ("PE", "Pernambuco", "페르남부쿠"),
    ("PI", "Piauí", "피아우이"),
    ("RJ", "Rio de Janeiro", "리우데자네이루"),
    ("RN", "Rio Grande do Norte", "히우그란지두노르치"),
    ("RS", "Rio Grande do Sul", "히우그란지두술"),
    ("RO", "Rondônia", "혼도니아"),
    ("RR", "Roraima", "호라이마"),
    ("SC", "Santa Catarina", "산타카타리나"),
    ("SP", "São Paulo", "상파울루"),
    ("SE", "Sergipe", "세르지피"),
    ("TO", "Tocantins", "토칸칭스"),
]

# Wikipedia list of current state governors (as of 2026-09-19 fetch).
GOV_CURRENT = {
    "PP": 4, "MDB": 2, "SOLIDARIEDADE": 1, "UNIAO": 3, "PT": 4,
    "PSB": 2, "PSD": 6, "IND": 2, "REPUBLICANOS": 2, "PL": 1,
}

PARTY_META: Dict[str, Dict[str, str]] = {
    "PT": {
        "name_pt": "Partido dos Trabalhadores",
        "name_ko": "노동자당",
        "name_en": "Workers' Party",
        "note_ko": "현직 대통령. 결선 진출 여부는 1차(2026-10-04) 이후.",
    },
    "PL": {
        "name_pt": "Partido Liberal",
        "name_ko": "자유당",
        "name_en": "Liberal Party",
    },
    "UNIAO": {
        "name_pt": "União Brasil",
        "name_ko": "브라질연합",
        "name_en": "Brazil Union",
    },
    "PP": {
        "name_pt": "Progressistas",
        "name_ko": "진보당",
        "name_en": "Progressistas",
    },
    "PSD": {
        "name_pt": "Partido Social Democrático",
        "name_ko": "사회민주당",
        "name_en": "Social Democratic Party",
    },
    "MDB": {
        "name_pt": "Movimento Democrático Brasileiro",
        "name_ko": "브라질민주운동",
        "name_en": "Brazilian Democratic Movement",
    },
    "REPUBLICANOS": {
        "name_pt": "Republicanos",
        "name_ko": "공화당",
        "name_en": "Republicans",
    },
    "PSB": {
        "name_pt": "Partido Socialista Brasileiro",
        "name_ko": "브라질사회당",
        "name_en": "Brazilian Socialist Party",
    },
    "SOLIDARIEDADE": {
        "name_pt": "Solidariedade",
        "name_ko": "연대",
        "name_en": "Solidarity",
    },
    "IND": {
        "name_pt": "Independente",
        "name_ko": "무소속",
        "name_en": "Independent",
        "note_ko": "현직 주지사 열. 무소속을 어느 당에도 더하지 않는다.",
    },
}


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def scheduled(code: str, name_ko: str, group_ko: str, seats: int) -> Dict[str, Any]:
    return {
        "id": code,
        "name_ko": name_ko,
        "group_ko": group_ko,
        "seats": seats,
        "status": "scheduled",
        "candidates": [],
        "note_ko": "1차 결과에 따라 결선 여부. 1차 전이라 후보를 넣지 않았다.",
    }


def parties_block(used: List[str]) -> List[Dict[str, Any]]:
    out = []
    for abbr in PARTY_META:
        if abbr not in used:
            continue
        meta = PARTY_META[abbr]
        row: Dict[str, Any] = {"abbr": abbr}
        for k in ("name_pt", "name_ko", "name_en", "note_ko"):
            if meta.get(k):
                row[k] = meta[k]
        out.append(row)
    missing = set(used) - {p["abbr"] for p in out}
    if missing:
        raise SystemExit(f"PARTY_META missing {missing}")
    return out


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
        "iso3": "BRA",
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
    if len(UFS) != 27:
        raise SystemExit(f"UF count {len(UFS)}")
    if sum(GOV_CURRENT.values()) != 27:
        raise SystemExit(f"gov current {sum(GOV_CURRENT.values())}")
    gov_d = [scheduled(code, ko, pt, 1) for code, pt, ko in UFS]
    pres_d = [scheduled("BR", "대통령", "전국", 1)]
    used = ["PT"] + list(GOV_CURRENT)
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "BRA",
        "date": "2026-10-25",
        "system_id": "bra-president",
        "as_of": AS_OF,
        "sources": [WIKI, WIKI_GOV, TSE, CONST],
        "parties": parties_block(used),
        "columns": [
            {
                "key": "president",
                "label_ko": "대통령 결선",
                "current": {
                    "by_party": {"PT": 1},
                    "total": 1,
                    "as_of": AS_OF,
                    "note_ko": "현직 룰라(PT). 결선 진출 두 이름은 1차 유효표 과반 미달일 때만 생긴다.",
                },
                "contested_ko": "대통령 1인(부통령 동반). 1차 과반이면 이 열은 열리지 않는다.",
                "seat_note_ko": (
                    "헌법 77조·TSE: 1차 2026-10-04, 결선은 10월 마지막 일요일(2026-10-25). "
                    "하원·상원은 결선이 없어 이 파일에 넣지 않았다."
                ),
                "districts": pres_d,
            },
            {
                "key": "governor",
                "label_ko": "주지사 결선",
                "current": {
                    "by_party": dict(GOV_CURRENT),
                    "total": 27,
                    "as_of": "2026-09-19",
                    "note_ko": (
                        "영문 위키 List of current state governors. "
                        "PP 4 MDB 2 SOLIDARIEDADE 1 UNIAO 3 PT 4 PSB 2 PSD 6 IND 2 "
                        "REPUBLICANOS 2 PL 1 = 27. 주마다 결선 여부가 다르다."
                    ),
                },
                "contested_ko": "27개 주·연방구 수장 중 1차 과반 미달인 곳만. 지금은 전 자리를 scheduled.",
                "seat_note_ko": "1차 전에 어느 주가 결선인지를 지어내지 않았다. 의회 총선은 1차 파일.",
                "districts": gov_d,
            },
        ],
        "note_ko": (
            "1차(bra-2026-general-r1, 2026-10-04)와 다른 파일. "
            "달력 status는 tentative(1차 과반 미달 시). 후보는 1차 후 채운다."
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
        f"president scheduled; governor {len(doc['columns'][1]['districts'])} scheduled"
    )


if __name__ == "__main__":
    main()
