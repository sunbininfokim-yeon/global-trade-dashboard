"""Build elections_contest_v1 for deu-2026-berlin-ag.

SMD: Amtsblatt für Berlin Nr. 36 (2026-08-27) Wahlkreisvorschläge, 78 districts.
Current seats: Abgeordnetenhaus factions page (19th WP, 159 members).
PR list heads: Amtsblatt Landeslisten #1 + Spitzenkandidaten for CDU/SPD/LINKE Bezirkslisten.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw" / "deu"
RAW_TXT = RAW_DIR / "abl_smd.txt"
RAW_PDF = RAW_DIR / "abl_2026_36.pdf"
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "deu-2026-berlin-ag"

ABL = (
    "https://www.berlin.de/wahlen/wahlen/berliner-wahlen-2026/"
    "allgemeine-informationen/abl_2026_36_2273_2644_98.pdf"
)
FACTIONS = "https://www.parlament-berlin.de/das-parlament/fraktionen"
LISTS_PM = "https://www.berlin.de/wahlen/pressemitteilungen/2026/pressemitteilung.1697177.php"
WIKI_DE = "https://de.wikipedia.org/wiki/Wahl_zum_Abgeordnetenhaus_von_Berlin_2026"
WIKI_EN = "https://en.wikipedia.org/wiki/2026_Berlin_state_election"
KING = "https://www.parlament-berlin.de/Abgeordnete/alexander-king"
BROUSEK = "https://www.parlament-berlin.de/Abgeordnete/antonin-brousek-1"
WAHLEN = "https://www.berlin.de/wahlen/wahlen/berliner-wahlen-2026/allgemeine-informationen/artikel.1578239.php"

BEZIRK_META = [
    ("Mitte", "미테", "01", 7),
    ("Friedrichshain-Kreuzberg", "프리드리히샤인-크로이츠베르크", "02", 5),
    ("Pankow", "판코", "03", 9),
    ("Charlottenburg-Wilmersdorf", "샤를로텐부르크-빌머스도르프", "04", 7),
    ("Spandau", "슈판다우", "05", 5),
    ("Steglitz-Zehlendorf", "슈테글리츠-첼렌도르프", "06", 7),
    ("Tempelhof-Schöneberg", "템펠호프-쇠네베르크", "07", 7),
    ("Neukölln", "노이쾰른", "08", 6),
    ("Treptow-Köpenick", "트레프토-쾨페니크", "09", 7),
    ("Marzahn-Hellersdorf", "마르찬-헬러스도르프", "10", 6),
    ("Lichtenberg", "리히텐베르크", "11", 6),
    ("Reinickendorf", "라이니켄도르프", "12", 6),
]
BEZIRK_KO = {ru: ko for ru, ko, _, _ in BEZIRK_META}
BEZIRK_CODE = {ru: code for ru, _, code, _ in BEZIRK_META}

PARTY_META: Dict[str, Dict[str, str]] = {
    "CDU": {
        "name_de": "Christlich Demokratische Union Deutschlands",
        "name_ko": "기민련",
        "name_en": "Christian Democratic Union",
        "leader_ko": "슈테판 에버스",
        "note_ko": "투표용지 1번. 12개 구 명부. 슈피첸은 에버스(베그너 시장은 7월에 사퇴).",
    },
    "SPD": {
        "name_de": "Sozialdemokratische Partei Deutschlands",
        "name_ko": "사민당",
        "name_en": "Social Democratic Party",
        "leader_ko": "슈테펜 크라흐",
        "note_ko": "투표용지 2번. 12개 구 명부.",
    },
    "GRÜNE": {
        "name_de": "Bündnis 90/Die Grünen",
        "name_ko": "동맹90/녹색당",
        "name_en": "Alliance 90/The Greens",
        "leader_ko": "베르너 그라프·베티나 야라슈",
        "note_ko": "투표용지 3번. 주명부 1번 야라슈, 2번 그라프(시장 후보).",
    },
    "LINKE": {
        "name_de": "Die Linke",
        "name_ko": "좌파당",
        "name_en": "The Left",
        "leader_ko": "엘리프 에랄프",
        "note_ko": "투표용지 4번. 12개 구 명부.",
    },
    "AfD": {
        "name_de": "Alternative für Deutschland",
        "name_ko": "독일을 위한 대안",
        "name_en": "Alternative for Germany",
        "leader_ko": "크리스틴 브링커",
        "note_ko": "투표용지 5번. 주명부.",
    },
    "FDP": {
        "name_de": "Freie Demokratische Partei",
        "name_ko": "자민당",
        "name_en": "Free Democratic Party",
        "leader_ko": "크리스토프 마이어",
        "note_ko": "투표용지 6번. 주명부.",
    },
    "Tierschutz": {
        "name_de": "PARTEI MENSCH KLIMA TIERSCHUTZ",
        "name_ko": "동물보호당",
        "name_en": "Human Environment Animal Protection",
        "leader_ko": "니코 포신스키",
        "note_ko": "투표용지 7번. 주명부.",
    },
    "PARTEI": {
        "name_de": "Die PARTEI",
        "name_ko": "디 파르타이",
        "name_en": "Die PARTEI",
        "leader_ko": "알무트 부흐발트",
        "note_ko": "투표용지 8번. 주명부.",
    },
    "Volt": {
        "name_de": "Volt Deutschland",
        "name_ko": "볼트",
        "name_en": "Volt Germany",
        "leader_ko": "안나 아우어바흐",
        "note_ko": "투표용지 9번. 주명부. 공동 슈피첸 파울 뢰퍼.",
    },
    "Urbane": {
        "name_de": "Die Urbane. Eine HipHop Partei",
        "name_ko": "디 우르바네",
        "name_en": "The Urban. A HipHop Party",
        "leader_ko": "니콜 드라코스",
        "note_ko": "투표용지 12번. 주명부.",
    },
    "DKP": {
        "name_de": "Deutsche Kommunistische Partei",
        "name_ko": "독일공산당",
        "name_en": "German Communist Party",
        "leader_ko": "아르놀트 숄첼",
        "note_ko": "투표용지 13번. 주명부.",
    },
    "ÖDP": {
        "name_de": "Ökologisch-Demokratische Partei",
        "name_ko": "생태민주당",
        "name_en": "Ecological Democratic Party",
        "leader_ko": "토마스 쿤",
        "note_ko": "투표용지 14번. 주명부.",
    },
    "HEIMAT": {
        "name_de": "Die Heimat",
        "name_ko": "디 하이마트",
        "name_en": "Die Heimat",
        "note_ko": "투표용지 15번. 일부 구 명부만. 구 NPD.",
    },
    "Berg": {
        "name_de": "bergpartei, die überpartei",
        "name_ko": "베르크파르타이",
        "name_en": "bergpartei, die überpartei",
        "note_ko": "투표용지 16번. 일부 구 명부만.",
    },
    "SGP": {
        "name_de": "Sozialistische Gleichheitspartei",
        "name_ko": "사회주의평등당",
        "name_en": "Socialist Equality Party",
        "leader_ko": "크리스토프 반드라이어",
        "note_ko": "투표용지 17번. 주명부.",
    },
    "BSW": {
        "name_de": "Bündnis Sahra Wagenknecht",
        "name_ko": "사라 바겐크네히트 연합",
        "name_en": "Sahra Wagenknecht Alliance",
        "leader_ko": "알렉산더 킹·미하엘 뤼더스",
        "note_ko": "투표용지 24번. 주명부 1번 킹. 킹은 제19기 무회파(좌파당에서 이적).",
    },
    "PdF": {
        "name_de": "Partei des Fortschritts",
        "name_ko": "진보당",
        "name_en": "Party of Progress",
        "leader_ko": "에메 퀸",
        "note_ko": "투표용지 27번. 주명부.",
    },
    "MERA25": {
        "name_de": "MERA25",
        "name_ko": "메라25",
        "name_en": "MERA25",
        "note_ko": "투표용지 26번. 소선거구만 확인된 후보지.",
    },
    "FRAUEN": {
        "name_de": "Feministische Partei DIE FRAUEN",
        "name_ko": "여성당",
        "name_en": "Feminist Party DIE FRAUEN",
        "note_ko": "투표용지 30번. 소선거구 소수.",
    },
    "DL": {
        "name_de": "Demokratische Linke",
        "name_ko": "민주좌파",
        "name_en": "Democratic Left",
        "note_ko": "투표용지 29번. 소선거구 소수.",
    },
    "MIETER": {
        "name_de": "Mieterpartei",
        "name_ko": "임차인당",
        "name_en": "Tenants' Party",
        "note_ko": "투표용지 11번. 소선거구 소수.",
    },
    "IND": {
        "name_de": "Einzelbewerber",
        "name_ko": "무소속",
        "name_en": "Independent",
        "note_ko": "어느 정당·연립에도 합산하지 않는다. 제19기 무회파 브로우섹(아펠 명부로 당선 후 회파 이탈)도 여기.",
    },
}

CURRENT_BY_PARTY = {
    "CDU": 52,
    "SPD": 36,
    "GRÜNE": 33,
    "LINKE": 20,
    "AfD": 16,
    "BSW": 1,
    "IND": 1,
}
CURRENT_TOTAL = 159
CURRENT_NOTE = (
    "제19기 베를린 주의회 전체 159석(법정 130 + 초과의석). "
    "parlament-berlin.de 회파: CDU 52, SPD 36, GRÜNE 33, LINKE 20, AfD 16, 무회파 2. "
    "무회파 2는 킹(BSW, 좌파당 이적)과 브로우섹(아펠 명부 당선, 회파 없음)이라 "
    "BSW 1·IND 1로 나눈다. 52+36+33+20+16+1+1=159. "
    "소선거구·명부로 나눈 공시전 의석은 출처에 없어 두 열에 같은 전체 숫자를 둔다."
)

PR_HEADS = [
    {"party_abbr": "CDU", "name": "Evers, Stefan", "note_ko": "슈피첸. 구 명부(주명부 없음)."},
    {"party_abbr": "SPD", "name": "Krach, Steffen", "note_ko": "슈피첸. 구 명부(주명부 없음)."},
    {"party_abbr": "GRÜNE", "name": "Jarasch, Bettina", "note_ko": "주명부 1번. 2번은 Graf, Werner(시장 후보)."},
    {"party_abbr": "LINKE", "name": "Eralp, Elif", "note_ko": "슈피첸. 구 명부(주명부 없음)."},
    {"party_abbr": "AfD", "name": "Brinker, Kristin", "note_ko": "주명부 1번."},
    {"party_abbr": "FDP", "name": "Meyer, Christoph", "note_ko": "주명부 1번."},
    {"party_abbr": "Tierschutz", "name": "Poschinski, Nico", "note_ko": "주명부 1번."},
    {"party_abbr": "PARTEI", "name": "Buchwald, Almut", "note_ko": "주명부 1번."},
    {"party_abbr": "Volt", "name": "Auerbach, Anna", "note_ko": "주명부 1번."},
    {"party_abbr": "Urbane", "name": "Drakos, Nicole", "note_ko": "주명부 1번."},
    {"party_abbr": "DKP", "name": "Schölzel, Arnold", "note_ko": "주명부 1번."},
    {"party_abbr": "ÖDP", "name": "Kuhn, Thomas", "note_ko": "주명부 1번."},
    {"party_abbr": "SGP", "name": "Vandreier, Christoph", "note_ko": "주명부 1번."},
    {"party_abbr": "BSW", "name": "King, Alexander", "note_ko": "주명부 1번. 공동 슈피첸 뤼더스."},
    {"party_abbr": "PdF", "name": "Kühn, Aimée", "note_ko": "주명부 1번."},
]


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def load_smd_text() -> str:
    if RAW_TXT.exists():
        return RAW_TXT.read_text(encoding="utf-8")
    if not RAW_PDF.exists():
        raise SystemExit(f"missing {RAW_TXT} and {RAW_PDF}")
    from pypdf import PdfReader

    r = PdfReader(str(RAW_PDF))
    parts = []
    for i in range(3, 83):
        parts.append(r.pages[i].extract_text() or "")
    return "\n".join(parts)


def party_from_block(block: str) -> str:
    b = block
    if "Anderer Kreiswahlvorschlag" in b or "Einzelbewerber" in b:
        return "IND"
    if "Wagenknecht" in b or re.search(r"\bBSW\b", b):
        return "BSW"
    if "MERA25" in b or "Gemeinsam für Frieden" in b:
        return "MERA25"
    if "MENSCH KLIMA" in b or "PARTEI MENSCH" in b:
        return "Tierschutz"
    if "basisdemokratische Initiative" in b or "Elitenförderung" in b:
        return "PARTEI"
    if "Christlich Demokratische" in b or re.search(r"\bCDU\b", b):
        return "CDU"
    if "Sozialdemokratische" in b or re.search(r"\bSPD\b", b):
        return "SPD"
    if "BÜNDNIS 90" in b or "DIE GRÜNEN" in b or re.search(r"\bGRÜNE\b", b):
        return "GRÜNE"
    if "Die Linke" in b:
        return "LINKE"
    if "Alternative für Deutschland" in b or re.search(r"\bAfD\b", b):
        return "AfD"
    if "Freie Demokratische" in b or re.search(r"\bFDP\b", b):
        return "FDP"
    if "Volt" in b:
        return "Volt"
    if "Deutsche Kommunistische" in b:
        return "DKP"
    if "Ökologisch-Demokratische" in b:
        return "ÖDP"
    if "Sozialistische Gleichheitspartei" in b:
        return "SGP"
    if "Die Heimat" in b or "HEIMAT" in b:
        return "HEIMAT"
    if "bergpartei" in b or "überpartei" in b or "B*" in b:
        return "Berg"
    if "Partei des Fortschritts" in b:
        return "PdF"
    if "FREIE WÄHLER" in b:
        return "FW"
    if "Die Urbane" in b:
        return "Urbane"
    if "Mieterpartei" in b or "MIETERPARTEI" in b:
        return "MIETER"
    if "Demokratische Linke" in b:
        return "DL"
    if "DIE FRAUEN" in b or "Feministische" in b:
        return "FRAUEN"
    if "Losdemokratie" in b:
        return "Losdem"
    raise SystemExit(f"unmapped party block: {block[:180]!r}")


def clean_name(raw: str) -> str:
    name = re.sub(r"\s+,", ",", raw).strip().rstrip(",").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def parse_smd(text: str) -> List[Dict[str, Any]]:
    pat = re.compile(r"Wahlkreisverband:\s*(.+?)\s*\nWahlkreis\s+(\d+)", re.S)
    marks = list(pat.finditer(text))
    if len(marks) != 78:
        raise SystemExit(f"expected 78 districts, got {len(marks)}")
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = text[m.start() : end]
        bez = re.sub(r"\s+", " ", m.group(1)).strip()
        wk = int(m.group(2))
        if bez not in BEZIRK_KO:
            raise SystemExit(f"unmapped bezirk {bez!r}")
        cands: List[Dict[str, Any]] = []
        work = block
        if "Hilmer-Benedict" in block:
            cands.append(
                {
                    "party_abbr": "GRÜNE",
                    "name": "Hilmer-Benedict, Christina",
                    "status": "nominated",
                    "source": ABL,
                    "note_ko": "Landeswahlleiter 2026-08-28 정정 공고.",
                }
            )
            work = block.replace(
                "Nr. 3  \nName:\nGeboren:\nErlernter Beruf:\nAusgeübter Beruf:\n"
                "BÜNDNIS 90/DIE GRÜNEN \nGRÜNE\nHilmer-Benedict, Christina \n"
                "1979, Anklam \nKulturwissenschaftlerin \nKulturarbeiterin",
                "",
            )
        for cm in re.finditer(
            r"Nr\. (\d+)\s+([\s\S]*?)\nName:\s*(.+)\nGeboren:([\s\S]*?)(?=\nNr\. |\nWahlkreisverband:|\Z)",
            work,
        ):
            name = clean_name(cm.group(3))
            if not name or name == "Geboren:":
                continue
            party = party_from_block(cm.group(2))
            rest = cm.group(4)
            cand: Dict[str, Any] = {
                "party_abbr": party,
                "name": name,
                "status": "nominated",
                "source": ABL,
            }
            if "Mitglied des Abgeordnetenhauses von Berlin" in rest:
                cand["incumbent"] = True
            cands.append(cand)
        if not cands:
            raise SystemExit(f"{bez} {wk}: no candidates")
        code = BEZIRK_CODE[bez]
        out.append(
            {
                "id": f"{code}-{wk:02d}",
                "name_ko": f"{BEZIRK_KO[bez]} {wk}구",
                "name_de": f"{bez} {wk}",
                "group_ko": BEZIRK_KO[bez],
                "seats": 1,
                "status": "nominated",
                "candidates": cands,
            }
        )
    out.sort(key=lambda d: d["id"])
    n = sum(len(d["candidates"]) for d in out)
    if n != 670:
        raise SystemExit(f"expected 670 SMD candidates, got {n}")
    return out


def pr_district() -> Dict[str, Any]:
    cands = []
    for row in PR_HEADS:
        cands.append(
            {
                "party_abbr": row["party_abbr"],
                "name": row["name"],
                "status": "nominated",
                "source": ABL if row["party_abbr"] not in {"CDU", "SPD", "LINKE"} else WIKI_DE,
                "note_ko": row["note_ko"],
            }
        )
    return {
        "id": "pr-berlin",
        "name_ko": "주·구 명부",
        "name_de": "Landes- und Bezirkslisten",
        "group_ko": "비례",
        "seats": 52,
        "status": "nominated",
        "note_ko": (
            "명부 전원은 넣지 않고 주명부 1번(CDU·SPD·LINKE는 슈피첸)만 적는다. "
            "HEIMAT와 베르크파르타이는 일부 구 명부만이라 이 열에 넣지 않았다. "
            "실제 명부 의석 수는 초과의석·보정의석으로 52보다 커질 수 있다."
        ),
        "candidates": cands,
    }


def parties_block(used: set) -> List[Dict[str, Any]]:
    out = []
    for abbr, meta in PARTY_META.items():
        if abbr not in used:
            continue
        row = {"abbr": abbr}
        for k in ("name_de", "name_ko", "name_en", "leader_ko", "note_ko"):
            if meta.get(k):
                row[k] = meta[k]
        out.append(row)
    return out


def current_block() -> Dict[str, Any]:
    return {
        "by_party": dict(CURRENT_BY_PARTY),
        "total": CURRENT_TOTAL,
        "as_of": "2026-09-19",
        "note_ko": CURRENT_NOTE,
        "vacancies": 0,
    }


def build() -> Dict[str, Any]:
    smd = parse_smd(load_smd_text())
    pr = [pr_district()]
    used = set(CURRENT_BY_PARTY)
    by_party = Counter()
    for d in smd:
        for c in d["candidates"]:
            used.add(c["party_abbr"])
            by_party[c["party_abbr"]] += 1
    used.update(r["party_abbr"] for r in PR_HEADS)
    used.add("HEIMAT")  # 일부 구 명부만. 소선거구 후보는 Amtsblatt A절에 없음.
    print("SMD by party:", dict(by_party), "sum", sum(by_party.values()))

    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "DEU",
        "date": "2026-09-20",
        "system_id": "deu-landtag-berlin",
        "as_of": AS_OF,
        "sources": [ABL, FACTIONS, LISTS_PM, WIKI_DE, WIKI_EN, KING, BROUSEK, WAHLEN],
        "parties": parties_block(used),
        "columns": [
            {
                "key": "smd",
                "label_ko": "소선거구",
                "current": current_block(),
                "contested_ko": "78개 지역구 전원. 투표 2026-09-20, 집계 전.",
                "seat_note_ko": "연동형. 지역구 당선은 명부 몫에서 뺀다. 후보는 Amtsblatt Nr. 36 (2026-08-27) 등록자 670명.",
                "districts": smd,
            },
            {
                "key": "pr",
                "label_ko": "비례대표",
                "current": current_block(),
                "contested_ko": "법정 최소 52석 명부. 초과의석·보정의석으로 늘어날 수 있다.",
                "seat_note_ko": "연동형. 5% 또는 직접의석. Hare/Niemeyer.",
                "districts": pr,
            },
        ],
    }
    return compact(doc)


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
        "iso3": "DEU",
        "date": "2026-09-20",
        "path": f"elections_contests/{EVENT_ID}.json",
        "status": "complete",
        "as_of": AS_OF,
    }
    events = [e for e in idx.get("events", []) if e.get("event_id") != EVENT_ID]
    events.append(row)
    events.sort(key=lambda e: (e.get("date") or "", e.get("event_id") or ""))
    idx["events"] = events
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    smd = doc["columns"][0].pop("districts")
    smd_rel = f"elections_contests/{EVENT_ID}.smd.districts.json"
    payload = json.dumps(
        {"schema": "elections_contest_districts_v1", "districts": smd},
        ensure_ascii=False,
        indent=2,
    )
    # 1MB rule — split if the combined file would exceed it.
    inline = json.dumps({**doc, "columns": [{**doc["columns"][0], "districts": smd}, doc["columns"][1]]}, ensure_ascii=False)
    if len(inline.encode("utf-8")) > 1_000_000:
        (PUBLIC / smd_rel).write_text(payload + "\n", encoding="utf-8")
        doc["columns"][0]["districts_path"] = smd_rel
        out_districts = smd
    else:
        doc["columns"][0]["districts"] = smd
        out_districts = smd
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    pr = doc["columns"][1]["districts"]
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"SMD {len(out_districts)} / {sum(len(d['candidates']) for d in out_districts)}; "
        f"PR {len(pr)} / {sum(len(d['candidates']) for d in pr)}"
    )


if __name__ == "__main__":
    main()
