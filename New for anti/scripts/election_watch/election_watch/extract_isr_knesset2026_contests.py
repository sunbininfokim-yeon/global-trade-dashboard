"""Build elections_contest_v1 for isr-2026-knesset.

Current seats: Knesset OData KNS_PersonToPosition (PositionID 54, Knesset 25, IsCurrent).
Running lists: Wikipedia party-lists page (38 submitted heads). Do not invent districts.
isr-2026-candidate-lists is a calendar deadline, not a contest file.
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"
RAW = ROOT / "raw" / "isr"

AS_OF = date.today().isoformat()
EVENT_ID = "isr-2026-knesset"

KNESSET_ODATA = "https://knesset.gov.il/Odata/ParliamentInfo.svc/KNS_PersonToPosition"
WIKI_LISTS = "https://en.wikipedia.org/wiki/Party_lists_for_the_2026_Israeli_legislative_election"
WIKI_ELECTION = "https://en.wikipedia.org/wiki/2026_Israeli_legislative_election"
TOI_38 = (
    "https://www.timesofisrael.com/"
    "israels-election-takes-shape-as-38-parties-submit-slates-from-likud-to-joint-list/"
)
CEC = "https://www.bechirot.gov.il/"
IDI = "https://en.idi.org.il/israeli-elections-and-parties/elections/2026/"

UA = "global-trade-dashboard election_watch/isr-knesset (+research)"

# Knesset OData FactionName → sitting abbr.
FACTION_ABBR = {
    'הליכוד': "Likud",
    "יש עתיד": "YA",
    'התאחדות הספרדים שומרי תורה תנועתו של מרן הרב עובדיה יוסף זצ"ל': "Shas",
    "כחול לבן - המחנה הממלכתי": "BW",
    "הציונות הדתית בראשות בצלאל סמוטריץ'": "RZP",
    "יהדות התורה": "UTJ",
    "עוצמה יהודית בראשות איתמר בן גביר": "Otzma",
    "ישראל ביתנו": "YB",
    'רע"ם': "Raam",
    'חד"ש-תע"ל': "HadashTaal",
    "הימין הממלכתי": "NewHope",
    "העבודה": "Labor",
    "נעם - בראשות אבי מעוז": "Noam",
}

SKIP_HEADINGS = {
    "notes",
    "references",
    "see also",
    "external links",
    "additional parties",
    "party lists for the 2026 israeli legislative election",
}

# Wikipedia heading → contest party. aliases are lowercase.
LIST_META: List[Dict[str, Any]] = [
    {
        "abbr": "Amcha",
        "aliases": ["amcha yisrael", "amcha israel"],
        "name_en": "Amcha Yisrael",
        "name_ko": "암하 이스라엘",
        "name_he": "עמך ישראל",
    },
    {
        "abbr": "BW",
        "aliases": ["blue and white"],
        "name_en": "Blue and White",
        "name_ko": "청백",
        "name_he": "כחול לבן",
        "note_ko": "현직 회파 청백-국가통합. 가자 방위장관 간츠가 명부 1번.",
    },
    {
        "abbr": "Democrats",
        "aliases": ["the democrats"],
        "name_en": "The Democrats",
        "name_ko": "민주당",
        "name_he": "הדמוקרטים",
        "note_ko": "노동당·메레츠 연합 명부. 원내 회파는 노동당 4석으로 남아 있다.",
    },
    {
        "abbr": "HarediPublic",
        "aliases": ["haredi public", "the haredi public"],
        "name_en": "Haredi Public",
        "name_ko": "하레디 공공",
        "name_he": "הציבור החרדי",
    },
    {
        "abbr": "IsraelFirst",
        "aliases": ["israel first"],
        "name_en": "Israel First",
        "name_ko": "이스라엘 퍼스트",
        "name_he": "ישראל תחילה",
        "note_ko": "신희망 의원 샤렌 하스켈이 이끈다. 신희망 회파와 별도 명부.",
    },
    {
        "abbr": "JointList",
        "aliases": ["joint list", "the joint list"],
        "name_en": "Joint List",
        "name_ko": "공동명부",
        "name_he": "הרשימה המשותפת",
        "note_ko": "하다시·타알·발라드. 원내 회파는 하다시-타알 5석(발라드는 문턱 미달로 원외).",
    },
    {
        "abbr": "Likud",
        "aliases": ["likud"],
        "name_en": "Likud",
        "name_ko": "리쿠드",
        "name_he": "הליכוד",
        "note_ko": "기드온 사아르(신희망)가 리쿠드 명부 7번. 원내 신희망 회파는 그대로 4석.",
    },
    {
        "abbr": "Noam",
        "aliases": ["noam"],
        "name_en": "Noam",
        "name_ko": "노암",
        "name_he": "נעם",
    },
    {
        "abbr": "Otzma",
        "aliases": ["otzma yehudit"],
        "name_en": "Otzma Yehudit",
        "name_ko": "오츠마 예후딧",
        "name_he": "עוצמה יהודית",
    },
    {
        "abbr": "RZP",
        "aliases": ["religious zionist party-zehut", "religious zionist party"],
        "name_en": "Religious Zionist Party–Zehut",
        "name_ko": "종교시온주의-제후트",
        "name_he": "הציונות הדתית – זהות",
        "note_ko": "원내 회파는 종교시온주의 7석. 2026 명부는 제후트(페이글린)와 공동.",
    },
    {
        "abbr": "Reservists",
        "aliases": ["the reservists and the economic party", "the reservists"],
        "name_en": "The Reservists and the Economic Party",
        "name_ko": "예비군-경제당",
        "name_he": "המילואימניקים והכלכלית",
    },
    {
        "abbr": "Shas",
        "aliases": ["shas"],
        "name_en": "Shas",
        "name_ko": "샤스",
        "name_he": 'ש"ס',
    },
    {
        "abbr": "Together",
        "aliases": ["together"],
        "name_en": "Together",
        "name_ko": "비야하드",
        "name_he": "ביחד",
        "note_ko": "베넷 2026 + 예시 아티드. 원내 회파는 예시 아티드 24석.",
    },
    {
        "abbr": "Raam",
        "aliases": ["united arab list"],
        "name_en": "United Arab List (Ra'am)",
        "name_ko": "라암",
        "name_he": 'רע"ם',
    },
    {
        "abbr": "UTJ",
        "aliases": ["united torah judaism"],
        "name_en": "United Torah Judaism",
        "name_ko": "연합토라유대교",
        "name_he": "יהדות התורה",
        "note_ko": "2026 명부 1번은 야코프 아셰르(데겔 하토라). 골드크노프는 2번.",
    },
    {
        "abbr": "Yashar",
        "aliases": ["yashar"],
        "name_en": "Yashar",
        "name_ko": "야샤르",
        "name_he": "ישר!",
    },
    {
        "abbr": "YB",
        "aliases": ["yisrael beiteinu"],
        "name_en": "Yisrael Beiteinu",
        "name_ko": "이스라엘 베이테이누",
        "name_he": "ישראל ביתנו",
    },
    {
        "abbr": "Sharshar",
        "aliases": ["sharshar"],
        "name_en": "Sharshar",
        "name_ko": "샤르샤르",
        "name_he": "שרשר",
    },
    {
        "abbr": "Partnership",
        "aliases": ["ihud bnei habrit", "partnership for all", "partnership for everyone"],
        "name_en": "Partnership for All (Ihud Bnei HaBrit)",
        "name_ko": "모두를 위한 동반",
        "name_he": "השותפות לכולם",
    },
    {
        "abbr": "Pirates",
        "aliases": ["pirate party", "the pirates"],
        "name_en": "Pirate Party",
        "name_ko": "해적당",
        "name_he": "הפיראטים",
    },
    {
        "abbr": "GanEden",
        "aliases": ["paradise", "garden of eden"],
        "name_en": "Garden of Eden",
        "name_ko": "간 에덴",
        "name_he": "גן עדן",
    },
    {
        "abbr": "WomensVoice",
        "aliases": ["women's voice", "womens voice"],
        "name_en": "Women's Voice",
        "name_ko": "여성의 목소리",
        "name_he": "קול הנשים",
    },
    {
        "abbr": "BeyachadNatzliach",
        "aliases": ["beyachad natzliach", "together we will succeed"],
        "name_en": "Together We Will Succeed",
        "name_ko": "함께 해내자",
        "name_he": "ביחד נצליח",
    },
    {
        "abbr": "MishpatTzedek",
        "aliases": ["mishpat tzedek", "just law"],
        "name_en": "Mishpat Tzedek",
        "name_ko": "미슈파트 체데크",
        "name_he": "משפט צדק",
    },
    {
        "abbr": "Shma",
        "aliases": ["shma"],
        "name_en": "Shma",
        "name_ko": "셰마",
        "name_he": "שמע",
        "note_ko": "위키 명부 페이지: 나프탈리 골드만 1인 명부.",
    },
    {
        "abbr": "SederChadash",
        "aliases": ["new order"],
        "name_en": "New Order",
        "name_ko": "세데르 하다시",
        "name_he": "סדר חדש",
    },
    {
        "abbr": "AniVeAta",
        "aliases": ["you and i", "ani veata", "ani ve'ata"],
        "name_en": "Ani VeAta",
        "name_ko": "아니 베아타",
        "name_he": "אני ואתה",
    },
    {
        "abbr": "BritOlam",
        "aliases": ["brit olam", "eternal covenant"],
        "name_en": "Brit Olam",
        "name_ko": "브리트 올람",
        "name_he": "ברית עולם",
    },
    {
        "abbr": "HaTikun",
        "aliases": ["hatikun", "fixing the electoral and governing system"],
        "name_en": "HaTikun",
        "name_ko": "하티쿤",
        "name_he": "התיקון",
        "note_ko": "선거·통치제도 개정 명부.",
    },
    {
        "abbr": "BibleBloc",
        "aliases": ["bible bloc", "the biblical bloc"],
        "name_en": "Biblical Bloc",
        "name_ko": "성서 블록",
        "name_he": 'גה"ת-גוש התנ"כי',
    },
    {
        "abbr": "Betach",
        "aliases": ["betach"],
        "name_en": "Betach",
        "name_ko": "베타흐",
        "name_he": "בטח",
        "note_ko": "위키 제출 목록의 Social Security와 IDI Betach가 같은 줄로 잡힌다.",
    },
    {
        "abbr": "OrotHaShahar",
        "aliases": ["orot hashahar", "dawn's light, a party for everyone", "dawn’s light, a party for everyone"],
        "name_en": "Lights of Dawn",
        "name_ko": "오로트 하샤하르",
        "name_he": "אורות השחר",
    },
    {
        "abbr": "PersonalSafety",
        "aliases": ["democtatorship", "personal safety", "personal security"],
        "name_en": "Personal Safety",
        "name_ko": "개인 안전",
        "name_he": "ביטחון אישי",
    },
    {
        "abbr": "ColorBlack",
        "aliases": ["the color black"],
        "name_en": "The Color Black",
        "name_ko": "색 검정",
        "name_he": "צבע שחור",
    },
    {
        "abbr": "Ahi",
        "aliases": ["ahi", "ahi movement"],
        "name_en": "Ahi Movement",
        "name_ko": "아히",
        "name_he": "תנועת אחי",
    },
    {
        "abbr": "TzometBeitYisrael",
        "aliases": ["tzomet - beit yisrael", "tzomet – beit yisrael", "the house of israel junction"],
        "name_en": "Tzomet–Beit Yisrael",
        "name_ko": "초메트-베이트 이스라엘",
        "name_he": "צומת בית ישראל",
    },
    {
        "abbr": "Tkuma",
        "aliases": ["tkuma", "redemption"],
        "name_en": "Tkuma",
        "name_ko": "트쿠마",
        "name_he": "התקומה",
        "note_ko": "역사적 트쿠마당과 다른 2026 명부. 위키 제출 목록은 Redemption.",
    },
    {
        "abbr": "Hakahal",
        "aliases": ["hakahal", "hakahal party", "the hakhel party"],
        "name_en": "Hakahal",
        "name_ko": "하카할",
        "name_he": "הקהל",
    },
]

SITTING_ONLY = [
    {
        "abbr": "YA",
        "name_en": "Yesh Atid",
        "name_ko": "예시 아티드",
        "name_he": "יש עתיד",
        "note_ko": "원내 24석. 2026 명부는 베넷과 비야하드(Together).",
    },
    {
        "abbr": "Labor",
        "name_en": "Labor",
        "name_ko": "노동당",
        "name_he": "העבודה",
        "note_ko": "원내 회파명. 2026 명부는 민주당(The Democrats).",
    },
    {
        "abbr": "HadashTaal",
        "name_en": "Hadash–Ta'al",
        "name_ko": "하다시-타알",
        "name_he": 'חד"ש-תע"ל',
        "note_ko": "원내 5석. 2026 명부는 발라드와 공동명부.",
    },
    {
        "abbr": "NewHope",
        "name_en": "New Hope",
        "name_ko": "신희망",
        "name_he": "הימין הממלכתי",
        "note_ko": "원내 회파 히민 하맘라크티 4석. 사아르는 리쿠드 명부. 하스켈은 이스라엘 퍼스트.",
    },
]


def strip_tags(html: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = unescape(t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fetch(url: str, dest: Optional[Path] = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if "charset=" in ctype.lower():
        enc = ctype.split("charset=", 1)[1].split(";")[0].strip()
    else:
        enc = "utf-8"
    text = data.decode(enc, errors="replace")
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return text


def odata_rows(filt: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    skip = 0
    while True:
        url = (
            f"{KNESSET_ODATA}?$format=json&$filter={filt}"
            f"&$top=100&$skip={skip}"
        )
        payload = json.loads(fetch(url))
        chunk = payload.get("value") or []
        rows.extend(chunk)
        if len(chunk) < 100:
            break
        skip += 100
        if skip > 5000:
            raise SystemExit("OData pagination overflow")
    return rows


def current_seats() -> Tuple[Dict[str, int], str]:
    filt = "KnessetNum%20eq%2025%20and%20PositionID%20eq%2054%20and%20IsCurrent%20eq%20true"
    rows = odata_rows(filt)
    people: Dict[int, str] = {}
    for row in rows:
        pid = row.get("PersonID")
        raw = (row.get("FactionName") or "").strip()
        if pid is None:
            continue
        people[int(pid)] = raw
    if len(people) != 120:
        raise SystemExit(f"Knesset current MKs {len(people)} ≠ 120 (rows {len(rows)})")
    counts: Counter[str] = Counter()
    unknown = []
    for name in people.values():
        abbr = FACTION_ABBR.get(name)
        if not abbr:
            unknown.append(name)
            continue
        counts[abbr] += 1
    if unknown:
        raise SystemExit(f"unmapped Knesset factions: {sorted(set(unknown))}")
    if sum(counts.values()) != 120:
        raise SystemExit(f"mapped seats {sum(counts.values())}")
    note = (
        "크네세트 OData KNS_PersonToPosition PositionID 54(회파 소속) "
        f"KnessetNum=25 IsCurrent, {AS_OF}. "
        "리쿠드 32 예시아티드 24 샤스 11 청백 8 종교시온주의 7 연합토라 7 "
        "오츠마 6 베이테이누 6 라암 5 하다시-타알 5 신희망 4 노동당 4 노암 1 = 120. "
        "영문 위키 2026 해산표는 오츠마 7·종교시온주의 6으로 뒤바뀌어 있어 원문을 쓴다."
    )
    return dict(counts), note


def meta_for_heading(heading: str) -> Optional[Dict[str, Any]]:
    key = heading.strip().lower()
    key = key.replace("–", "-").replace("—", "-")
    key = key.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    for meta in LIST_META:
        for alias in meta["aliases"]:
            if key == alias or key.startswith(alias + " "):
                return meta
    return None


def parse_wiki_lists(html: str) -> List[Dict[str, str]]:
    # Parsoid / desktop both: h2/h3 then first numbered item.
    chunks = re.split(r"<h[23]\b", html, flags=re.I)
    found: List[Dict[str, str]] = []
    used_abbr = set()
    for chunk in chunks:
        hm = re.search(r">([^<]+)</h[23]>", chunk[:800], flags=re.I)
        if not hm:
            hm = re.search(
                r'class="mw-headline"[^>]*>\s*([^<]+)',
                chunk[:800],
                flags=re.I,
            )
        if not hm:
            continue
        heading = strip_tags(hm.group(1))
        if heading.lower() in SKIP_HEADINGS:
            continue
        meta = meta_for_heading(heading)
        if meta is None:
            continue
        if meta["abbr"] in used_abbr:
            continue
        # first list item after heading
        name = ""
        ol = re.search(r"<ol\b[^>]*>(.*?)</ol>", chunk, flags=re.I | re.S)
        if ol:
            li = re.search(r"<li\b[^>]*>(.*?)</li>", ol.group(1), flags=re.I | re.S)
            if li:
                name = strip_tags(li.group(1))
        if not name:
            m = re.search(
                r"(?:is headed by|is led by|list is headed by|list, headed by)\s+([^\[<\.,]+)",
                strip_tags(chunk[:1500]),
                flags=re.I,
            )
            if m:
                name = m.group(1).strip()
        # drop party-letter suffix like "H" after Hadash
        name = re.sub(r"\s+[HTBRNZDAye]+\s*$", "", name).strip()
        name = re.sub(r"\s+\[[a-z]\]\s*$", "", name, flags=re.I).strip()
        if not name:
            raise SystemExit(f"no list head for {heading}")
        used_abbr.add(meta["abbr"])
        found.append(
            {
                "abbr": meta["abbr"],
                "heading": heading,
                "name": name,
            }
        )
    if len(found) != 38:
        have = [x["heading"] for x in found]
        raise SystemExit(f"parsed {len(found)} lists, need 38: {have}")
    return found


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def parties_block(running: List[Dict[str, str]], current: Dict[str, int]) -> List[Dict[str, Any]]:
    by_abbr = {m["abbr"]: m for m in LIST_META}
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in running:
        meta = by_abbr[row["abbr"]]
        item: Dict[str, Any] = {
            "abbr": meta["abbr"],
            "name_ko": meta["name_ko"],
            "name_en": meta["name_en"],
            "name_he": meta["name_he"],
        }
        if meta.get("note_ko"):
            item["note_ko"] = meta["note_ko"]
        out.append(item)
        seen.add(meta["abbr"])
    for extra in SITTING_ONLY:
        if extra["abbr"] in seen:
            continue
        if extra["abbr"] not in current:
            continue
        out.append(dict(extra))
        seen.add(extra["abbr"])
    missing = set(current) - seen
    if missing:
        raise SystemExit(f"parties missing current keys {missing}")
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
        "iso3": "ISR",
        "date": "2026-10-27",
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
    current, current_note = current_seats()
    html = fetch(WIKI_LISTS, RAW / "party_lists_2026.html")
    running = parse_wiki_lists(html)
    elect = fetch(WIKI_ELECTION, RAW / "election_2026.html")
    if "38 parties submitted" not in elect and "38 parties" not in elect:
        raise SystemExit("2026 election page missing 38-list confirmation")
    candidates = []
    for i, row in enumerate(running, start=1):
        candidates.append(
            {
                "party_abbr": row["abbr"],
                "name": row["name"],
                "status": "nominated",
                "source": WIKI_LISTS,
                "note_ko": f"전국 명부 {i}번째 제목 «{row['heading']}»의 1번. CEC 최종 승인 2026-09-27 예정.",
            }
        )
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "ISR",
        "date": "2026-10-27",
        "system_id": "isr-knesset",
        "as_of": AS_OF,
        "sources": [KNESSET_ODATA, WIKI_LISTS, WIKI_ELECTION, TOI_38, IDI, CEC],
        "parties": parties_block(running, current),
        "columns": [
            {
                "key": "knesset",
                "label_ko": "크네세트",
                "current": {
                    "by_party": current,
                    "total": 120,
                    "as_of": AS_OF,
                    "note_ko": current_note,
                    "vacancies": 0,
                },
                "contested_ko": "120석 전원 개선. 전국 1구 폐쇄명부 비례, 봉쇄선 3.25%.",
                "seat_note_ko": (
                    "선거구를 짓지 않았다. 후보는 제출된 38개 명부의 1번만. "
                    "전체 명단은 위키 Party lists / CEC 공식 공고(예정 2026-10-18). "
                    "isr-2026-candidate-lists는 제출 기한이지 대진 파일이 아니다."
                ),
                "districts": [
                    {
                        "id": "IL",
                        "name_ko": "전국 명부",
                        "group_ko": "크네세트",
                        "seats": 120,
                        "status": "nominated",
                        "candidates": candidates,
                        "note_ko": (
                            "2026-09-08 CEC 제출 38개 명부. 최종 승인 2026-09-27, "
                            "공식 공고 2026-10-18. 투표일 2026-10-27."
                        ),
                    }
                ],
            }
        ],
        "note_ko": (
            "작업 A의 isr-knesset 제도 행은 origin/main 시스템에 아직 없다. "
            "system_id는 원 이름에 맞춰 두었다. 여론조사·승률은 넣지 않았다."
        ),
    }
    return compact(doc)


def main() -> None:
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    n = len(doc["columns"][0]["districts"][0]["candidates"])
    print(f"wrote {out} ({out.stat().st_size} bytes); lists {n}; current {doc['columns'][0]['current']['by_party']}")


if __name__ == "__main__":
    main()
