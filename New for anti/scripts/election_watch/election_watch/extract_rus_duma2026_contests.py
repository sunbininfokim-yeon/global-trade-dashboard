"""Build elections_contest_v1 for rus-2026-duma.

SMD matchups: Russian Wikipedia constituency tables (registered candidates
as of 2026-09-14; votes empty because counting is still open).
Current seats: State Duma English factions page (8th convocation).
PR lists: CEC-registered federal lists (Yabloko list disqualified).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "rus" / "wiki_smd_2026.md"
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "rus-2026-duma"

WIKI_SMD = (
    "https://ru.wikipedia.org/wiki/"
    "%D0%92%D1%8B%D0%B1%D0%BE%D1%80%D1%8B_%D0%B2_%D0%93%D0%BE%D1%81%D1%83%D0%B4%D0%B0%D1%80%D1%81%D1%82%D0%B2%D0%B5%D0%BD%D0%BD%D1%83%D1%8E_%D0%B4%D1%83%D0%BC%D1%83_(2026):_%D1%80%D0%B5%D0%B7%D1%83%D0%BB%D1%8C%D1%82%D0%B0%D1%82%D1%8B_%D0%BF%D0%BE_%D0%BE%D0%B4%D0%BD%D0%BE%D0%BC%D0%B0%D0%BD%D0%B4%D0%B0%D1%82%D0%BD%D1%8B%D0%BC_%D0%BE%D0%BA%D1%80%D1%83%D0%B3%D0%B0%D0%BC"
)
WIKI_EN = "https://en.wikipedia.org/wiki/2026_Russian_legislative_election"
WIKI_RU = (
    "https://ru.wikipedia.org/wiki/"
    "%D0%92%D1%8B%D0%B1%D0%BE%D1%80%D1%8B_%D0%B2_%D0%93%D0%BE%D1%81%D1%83%D0%B4%D0%B0%D1%80%D1%81%D1%82%D0%B2%D0%B5%D0%BD%D0%BD%D1%83%D1%8E_%D0%B4%D1%83%D0%BC%D1%83_(2026)"
)
DUMA_FACTIONS = "http://duma.gov.ru/en/duma/factions/"
CIKRF = "http://www.cikrf.ru/"
IZVESTIA_11 = (
    "https://en.iz.ru/en/2140986/2026-07-30/cec-has-registered-11-parties-state-duma-elections"
)
RG_11 = (
    "https://rg.ru/2026/07/30/cik-zaregistriroval-spiski-vseh-11-partij-vydvinuvshih-kandidatov-v-gosdumu.html"
)
KREMLIN = "http://en.kremlin.ru/acts/news/80036"
MID = "https://mid.ru/ru/useful_information/vote_2026/"

SKIP_ROWS = ("Недействительных бюллетеней", "Явка по округу")

PARTY_FROM_RU = {
    "Единая Россия": "UR",
    "КПРФ": "CPRF",
    "ЛДПР": "LDPR",
    "Новые люди": "NL",
    "Справедливая Россия": "SR",
    "Яблоко": "Yabloko",
    "Родина": "Rodina",
    "Зелёные": "Greens",
    "Коммунисты России": "CR",
    "Партия пенсионеров": "RPPSS",
    "Партия прямой демократии": "PPD",
    "Самовыдвижение": "IND",
    "Самовыдвиженцы": "IND",
}

# Ballot order 2026-08-05 (Interfax / EN Wikipedia). Yabloko list later struck.
PARTY_META: Dict[str, Dict[str, Any]] = {
    "UR": {
        "name_ru": "Единая Россия",
        "name_ko": "통합러시아",
        "name_en": "United Russia",
        "leader_ko": "드미트리 메드베데프",
        "note_ko": "여당. 투표용지 1번. 연방명부 1번은 세르게이 라브로프. 당대표 메드베데프는 명부에 없음.",
        "ballot": 1,
    },
    "Yabloko": {
        "name_ru": "Яблоко",
        "name_ko": "야블로코",
        "name_en": "Yabloko",
        "leader_ko": "니콜라이 리바코프",
        "note_ko": "투표용지 2번으로 등록됐으나 2026-08-10 대법원이 연방명부를 실격, 8-17 항소 기각. 소선거구 후보는 남음. 당대표는 출마 제한.",
        "ballot": 2,
    },
    "LDPR": {
        "name_ru": "ЛДПР",
        "name_ko": "자유민주당",
        "name_en": "Liberal Democratic Party of Russia",
        "leader_ko": "레오니드 슬루츠키",
        "note_ko": "투표용지 3번.",
        "ballot": 3,
    },
    "PPD": {
        "name_ru": "Партия прямой демократии",
        "name_ko": "직접민주당",
        "name_en": "Party of Direct Democracy",
        "leader_ko": "타티야나 콜나우스",
        "note_ko": "투표용지 4번. 연방 상위 명부 없이 지역집단만 구성.",
        "ballot": 4,
    },
    "Greens": {
        "name_ru": "Российская экологическая партия «Зелёные»",
        "name_ko": "녹색당",
        "name_en": "The Greens",
        "leader_ko": "콘스탄틴 아타얀",
        "note_ko": "투표용지 5번. 연방명부 1번은 마리나 시시키나.",
        "ballot": 5,
    },
    "SR": {
        "name_ru": "Справедливая Россия",
        "name_ko": "정의러시아",
        "name_en": "A Just Russia",
        "leader_ko": "세르게이 미로노프",
        "note_ko": "투표용지 6번. 2025-10 당명을 정의러시아—진실을 위하여에서 되돌림.",
        "ballot": 6,
    },
    "Rodina": {
        "name_ru": "Родина",
        "name_ko": "조국당",
        "name_en": "Rodina",
        "leader_ko": "알렉세이 주라블료프",
        "note_ko": "투표용지 7번. 야블로코 명부 실격 소송을 냄.",
        "ballot": 7,
    },
    "CPRF": {
        "name_ru": "КПРФ",
        "name_ko": "러시아연방공산당",
        "name_en": "Communist Party of the Russian Federation",
        "leader_ko": "겐나디 주가노프",
        "note_ko": "투표용지 8번.",
        "ballot": 8,
    },
    "RPPSS": {
        "name_ru": "Российская партия пенсионеров за социальную справедливость",
        "name_ko": "연금생활자당",
        "name_en": "Russian Party of Pensioners for Social Justice",
        "leader_ko": "에릭 프라즈드니코프",
        "note_ko": "투표용지 9번.",
        "ballot": 9,
    },
    "CR": {
        "name_ru": "Коммунисты России",
        "name_ko": "러시아공산주의자들",
        "name_en": "Communists of Russia",
        "leader_ko": "세르게이 말린코비치",
        "note_ko": "투표용지 10번.",
        "ballot": 10,
    },
    "NL": {
        "name_ru": "Новые люди",
        "name_ko": "새로운 사람들",
        "name_en": "New People",
        "leader_ko": "알렉세이 네차예프",
        "note_ko": "투표용지 11번. 두마 영문 회파 표기는 NP.",
        "ballot": 11,
    },
    "IND": {
        "name_ru": "Самовыдвижение",
        "name_ko": "무소속",
        "name_en": "Independent",
        "note_ko": "어느 정당·연립에도 합산하지 않는다.",
    },
}

# 8th Duma factions, duma.gov.ru English page retrieved 2026-09-19.
CURRENT_BY_PARTY = {
    "UR": 310,
    "CPRF": 56,
    "SR": 27,
    "LDPR": 22,
    "NL": 15,
    "IND": 4,
}
CURRENT_TOTAL = 450
CURRENT_VACANCIES = 16
CURRENT_NOTE = (
    "제8기 국가두마 전체(소·비 구분 숫자는 출처에 없어 두 열에 같은 전체 숫자를 둔다). "
    "duma.gov.ru 회파: UR 310, CPRF 56, JR(정의러시아) 27, LDPR 22, NEW PEOPLE 15, "
    "무회파 4(드미트리예바·리시친·마르첸코·닐로프), 공석 16. "
    "310+56+27+22+15+4=434, 공석 16을 더하면 450. "
    "위키백과 2026 총선 표의 current seats도 같은 다섯 회파 숫자다."
)

# Federal-list #1 and registered list size (ruwiki participants table).
PR_LISTS = [
    {
        "party_abbr": "UR",
        "name": "Сергей Лавров",
        "list_n": 390,
        "note_ko": "연방 상위: 라브로프, 소뱌닌, 포드두브니, 리보바-벨로바, 골로빈.",
    },
    {
        "party_abbr": "LDPR",
        "name": "Леонид Слуцкий",
        "list_n": 246,
        "note_ko": "연방 상위 10명. 명부 1번=당대표.",
    },
    {
        "party_abbr": "PPD",
        "name": "Татьяна Колнауз",
        "list_n": 240,
        "note_ko": "연방 상위 명부 없음. 당대표. 지역집단 40개만.",
    },
    {
        "party_abbr": "Greens",
        "name": "Марина Шишкина",
        "list_n": 263,
        "note_ko": "연방명부 1번. 당대표는 콘스탄틴 아타얀.",
    },
    {
        "party_abbr": "SR",
        "name": "Сергей Миронов",
        "list_n": 263,
        "note_ko": "연방 상위: 미로노프, 바바코프, 킴, 체르니쇼프.",
    },
    {
        "party_abbr": "Rodina",
        "name": "Алексей Журавлёв",
        "list_n": 289,
        "note_ko": "연방명부 1번=당대표.",
    },
    {
        "party_abbr": "CPRF",
        "name": "Геннадий Зюганов",
        "list_n": 333,
        "note_ko": "연방 상위 15명(법정 상한). 명부 1번=당대표.",
    },
    {
        "party_abbr": "RPPSS",
        "name": "Эрик Праздников",
        "list_n": 268,
        "note_ko": "연방명부 1번=당대표.",
    },
    {
        "party_abbr": "CR",
        "name": "Сергей Малинкович",
        "list_n": 270,
        "note_ko": "연방명부 1번=당대표.",
    },
    {
        "party_abbr": "NL",
        "name": "Алексей Нечаев",
        "list_n": 298,
        "note_ko": "연방 상위: 네차예프, 다반코프, 아브크센티예바.",
    },
]

SUBJECT_KO = {
    "Республика Адыгея": "아디게야 공화국",
    "Республика Алтай": "알타이 공화국",
    "Республика Башкортостан": "바시키르 공화국",
    "Республика Бурятия": "부랴티야 공화국",
    "Республика Дагестан": "다게스탄 공화국",
    "ДНР*": "도네츠크",
    "Республика Ингушетия": "잉구시 공화국",
    "Кабардино-Балкарская Республика": "카바르디노-발카르 공화국",
    "Республика Калмыкия": "칼미키야 공화국",
    "Карачаево-Черкесская Республика": "카라차예보-체르케스 공화국",
    "Республика Карелия": "카렐리야 공화국",
    "Республика Коми": "코미 공화국",
    "Республика Крым*": "크림",
    "Республика Марий Эл": "마리엘 공화국",
    "Республика Мордовия": "모르도바 공화국",
    "Республика Саха (Якутия)": "사하 공화국",
    "Республика Северная Осетия – Алания": "북오세티야 공화국",
    "Республика Татарстан": "타타르스탄 공화국",
    "Республика Тыва": "투바 공화국",
    "Удмуртская Республика": "우드무르트 공화국",
    "Республика Хакасия": "하카시야 공화국",
    "Чеченская Республика": "체첸 공화국",
    "Чувашская Республика": "추바시 공화국",
    "Алтайский край": "알타이 지방",
    "Забайкальский край": "자바이칼 지방",
    "Камчатский край": "캄차카 지방",
    "Краснодарский край": "크라스노다르 지방",
    "Красноярский край": "크라스노야르스크 지방",
    "Пермский край": "페름 지방",
    "Приморский край": "연해주",
    "Ставропольский край": "스타브로폴 지방",
    "Хабаровский край": "하바롭스크 지방",
    "Амурская область": "아무르주",
    "Архангельская область": "아르한겔스크주",
    "Астраханская область": "아스트라한주",
    "Белгородская область": "벨고로드주",
    "Брянская область": "브랸스크주",
    "Владимирская область": "블라디미르주",
    "Волгоградская область": "볼고그라드주",
    "Вологодская область": "볼로그다주",
    "Воронежская область": "보로네시주",
    "Ивановская область": "이바노보주",
    "Иркутская область": "이르쿠츠크주",
    "Калининградская область": "칼리닌그라드주",
    "Калужская область": "칼루가주",
    "Кемеровская область": "케메로보주",
    "Кировская область": "키로프주",
    "Костромская область": "코스트로마주",
    "Курганская область": "쿠르간주",
    "Курская область": "쿠르스크주",
    "Ленинградская область": "레닌그라드주",
    "Липецкая область": "리페츠크주",
    "Магаданская область": "마가단주",
    "Московская область": "모스크바주",
    "Мурманская область": "무르만스크주",
    "Нижегородская область": "니즈니노브고로드주",
    "Новгородская область": "노브고로드주",
    "Новосибирская область": "노보시비르스크주",
    "Омская область": "옴스크주",
    "Оренбургская область": "오렌부르크주",
    "Орловская область": "오룔주",
    "Пензенская область": "펜자주",
    "Псковская область": "프스코프주",
    "Ростовская область": "로스토프주",
    "Рязанская область": "랴잔주",
    "Самарская область": "사마라주",
    "Саратовская область": "사라토프주",
    "Сахалинская область": "사할린주",
    "Свердловская область": "스베르들롭스크주",
    "Смоленская область": "스몰렌스크주",
    "Тамбовская область": "탐보프주",
    "Тверская область": "트베리주",
    "Томская область": "톰스크주",
    "Тульская область": "툴라주",
    "Тюменская область": "튜멘주",
    "Ульяновская область": "울리야놉스크주",
    "Челябинская область": "첼랴빈스크주",
    "Ярославская область": "야로슬라블주",
    "Москва": "모스크바",
    "Санкт-Петербург": "상트페테르부르크",
    "Севастополь*": "세바스토폴",
    "Еврейская автономная область": "유대인 자치주",
    "Ненецкий автономный округ": "네네츠 자치구",
    "Ханты-Мансийский автономный округ": "한티만시 자치구",
    "Чукотский автономный округ": "추코트 자치구",
    "Ямало-Ненецкий автономный округ": "야말로네네츠 자치구",
    "ЛНР*": "루한스크",
    "Запорожская область*": "자포리자주",
    "Херсонская область*": "헤르손주",
}

OCCUPIED = {
    "ДНР*",
    "ЛНР*",
    "Запорожская область*",
    "Херсонская область*",
    "Республика Крым*",
    "Севастополь*",
}

DISTRICT_RE = re.compile(
    r"^(.+?) — Округ № (\d+) \((.+?)\)$", re.M
)
CAND_RE = re.compile(
    r"^\| \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|",
    re.M,
)
FOOT_RE = re.compile(r"\[([bcd])\]", re.I)
TAG_RE = re.compile(r"\[[^\]]+\]")


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def clean_name(raw: str) -> Tuple[str, Optional[str], Optional[str]]:
    text = raw.strip()
    foot = None
    m = FOOT_RE.search(text)
    if m:
        foot = m.group(1).lower()
    text = TAG_RE.sub("", text)
    text = text.replace("отказ в регистрации", "")
    text = re.sub(r"\s*,\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text, foot, None


def status_from(cell: str) -> Optional[str]:
    s = cell.strip()
    if s.startswith("зарегистрирован"):
        return "nominated"
    if "выбывший" in s:
        return "withdrawn"
    return None


def parse_smd(text: str) -> List[Dict[str, Any]]:
    matches = list(DISTRICT_RE.finditer(text))
    if len(matches) != 225:
        raise SystemExit(f"expected 225 district headers, got {len(matches)}")
    districts: List[Dict[str, Any]] = []
    for i, m in enumerate(matches):
        subject = m.group(1).strip()
        num = int(m.group(2))
        nick = m.group(3).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else text.find("## Комментарии")
        block = text[start:end]
        cands: List[Dict[str, Any]] = []
        for row in CAND_RE.finditer(block):
            party_ru = row.group(1).strip()
            if party_ru in SKIP_ROWS:
                continue
            abbr = PARTY_FROM_RU.get(party_ru)
            if not abbr:
                raise SystemExit(f"unknown party {party_ru!r} in district {num}")
            name, foot, _ = clean_name(row.group(2))
            st = status_from(row.group(3))
            if st != "nominated":
                continue
            if not name:
                raise SystemExit(f"empty name district {num} party {party_ru}")
            cand: Dict[str, Any] = {
                "party_abbr": abbr,
                "name": name,
                "status": "nominated",
                "source": WIKI_SMD,
            }
            if foot == "b":
                cand["incumbent"] = True
                cand["note_ko"] = "이 구 현직"
            elif foot == "c":
                cand["incumbent"] = True
                cand["note_ko"] = "현직(비례 명부)"
            elif foot == "d":
                cand["incumbent"] = True
                cand["note_ko"] = "현직(다른 구)"
            cands.append(cand)
        if not cands:
            raise SystemExit(f"district {num} has no registered candidates")
        group = SUBJECT_KO.get(subject)
        if not group:
            raise SystemExit(f"unmapped subject {subject!r}")
        dist: Dict[str, Any] = {
            "id": f"{num:03d}",
            "name_ko": f"{group} {num}구",
            "name_ru": nick,
            "group_ko": group,
            "seats": 1,
            "status": "nominated",
            "candidates": cands,
        }
        if subject in OCCUPIED:
            dist["note_ko"] = (
                "러시아 관할 선거구(점령지·병합 주장). "
                "우크라이나 외무부는 점령지 투표를 무효라고 밝혔다."
            )
        districts.append(dist)
    districts.sort(key=lambda d: int(d["id"]))
    ids = [int(d["id"]) for d in districts]
    if ids != list(range(1, 226)):
        raise SystemExit(f"district id gap: {ids[:5]}…")
    return districts


def pr_district() -> Dict[str, Any]:
    cands = []
    for row in PR_LISTS:
        cands.append(
            {
                "party_abbr": row["party_abbr"],
                "name": row["name"],
                "status": "nominated",
                "source": WIKI_RU,
                "note_ko": f"연방명부 {row['list_n']}명. {row['note_ko']}",
            }
        )
    return {
        "id": "pr-federal",
        "name_ko": "연방명부",
        "name_ru": "Федеральный округ",
        "group_ko": "비례",
        "seats": 225,
        "status": "nominated",
        "note_ko": (
            "야블로코 연방명부는 2026-08-10 대법원이 실격(8-17 항소 기각). "
            "투표용지에는 나머지 10개 정당. 명부 전원(등록 3,133명)은 넣지 않고 "
            "연방 상위 1번만 적는다. PPD는 연방 상위가 없어 당대표를 적었다."
        ),
        "candidates": cands,
    }


def parties_block(used: set) -> List[Dict[str, Any]]:
    out = []
    for abbr, meta in PARTY_META.items():
        if abbr not in used and abbr != "IND":
            continue
        row = {"abbr": abbr}
        for k in ("name_ru", "name_ko", "name_en", "leader_ko", "note_ko"):
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
        "vacancies": CURRENT_VACANCIES,
    }


def build() -> Dict[str, Any]:
    text = RAW.read_text(encoding="utf-8")
    smd = parse_smd(text)
    pr = [pr_district()]
    used = set(CURRENT_BY_PARTY)
    by_party = Counter()
    for d in smd:
        for c in d["candidates"]:
            used.add(c["party_abbr"])
            by_party[c["party_abbr"]] += 1
    used.update(r["party_abbr"] for r in PR_LISTS)
    used.add("Yabloko")

    print("SMD registered by party:", dict(by_party), "sum", sum(by_party.values()))
    wiki_expect = {
        "UR": 219,
        "Greens": 119,
        "CR": 85,
        "CPRF": 220,
        "LDPR": 219,
        "NL": 210,
        "RPPSS": 98,
        "PPD": 18,
        "Rodina": 62,
        "IND": 4,
        "SR": 223,
        "Yabloko": 115,
    }
    for abbr, n in wiki_expect.items():
        got = by_party[abbr]
        if got != n:
            print(f"  count mismatch {abbr}: parsed {got} wiki-table {n}")

    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "RUS",
        "date": "2026-09-20",
        "system_id": "rus-duma",
        "as_of": AS_OF,
        "sources": [
            DUMA_FACTIONS,
            CIKRF,
            IZVESTIA_11,
            RG_11,
            WIKI_EN,
            WIKI_RU,
            WIKI_SMD,
            KREMLIN,
            MID,
        ],
        "parties": parties_block(used),
        "columns": [
            {
                "key": "smd",
                "label_ko": "소선거구",
                "current": current_block(),
                "contested_ko": "225석 전원 개선. 투표 2026-09-18–20, 집계 전.",
                "seat_note_ko": "병립형. 이 열과 비례대표 열은 연동되지 않는다. 후보는 2026-09-14 위키 표(ЦИК 기준) 등록자만.",
                "districts": smd,
            },
            {
                "key": "pr",
                "label_ko": "비례대표",
                "current": current_block(),
                "contested_ko": "225석 연방명부, 봉쇄 5%.",
                "seat_note_ko": "병립형. 소선거구 당선과 연동하지 않는다.",
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
        "iso3": "RUS",
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
    smd_path = PUBLIC / smd_rel
    smd_path.write_text(
        json.dumps(
            {"schema": "elections_contest_districts_v1", "districts": smd},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    doc["columns"][0]["districts_path"] = smd_rel
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    pr = doc["columns"][1]["districts"]
    print(
        f"wrote {out} ({out.stat().st_size} bytes) and {smd_path} ({smd_path.stat().st_size} bytes); "
        f"SMD {len(smd)} / {sum(len(d['candidates']) for d in smd)}; "
        f"PR {len(pr)} / {sum(len(d['candidates']) for d in pr)}"
    )


if __name__ == "__main__":
    main()
