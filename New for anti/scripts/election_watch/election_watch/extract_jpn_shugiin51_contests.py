"""Build elections_contest_v1 for jpn-2026-shugiin-51.

SMD matchups: Jiji 2026syu prefecture pages (all nominated candidates).
PR seat-takers: House roster in config/extracted/jpn_shugiin.json (（比）blocks).
公示前 seats: Wikipedia 第51回衆議院議員総選挙 (cross-check Nikkei).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "jpn" / "jiji_2026syu"
PUBLIC = ROOT.parents[1] / "public" / "data"
EXTRACTED = ROOT / "config" / "extracted"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "jpn-2026-shugiin-51"
JIJI_INDEX = "https://www.jiji.com/jc/2026syu"
MIC_RESULTS = "https://www.soumu.go.jp/senkyo/senkyo_s/data/shugiin51/index.html"
WIKI_51 = "https://ja.wikipedia.org/wiki/第51回衆議院議員総選挙"
HOUSE_ROSTER = "https://www.shugiin.go.jp/Internet/itdb_annai.nsf/html/statics/syu/1giin.htm"

UA = "global-trade-dashboard election_watch/jpn-shugiin51 (+research)"

PREFS: List[Tuple[str, str, str, int]] = [
    ("01", "北海道", "홋카이도", 12),
    ("02", "青森県", "아오모리현", 3),
    ("03", "岩手県", "이와테현", 3),
    ("04", "宮城県", "미야기현", 5),
    ("05", "秋田県", "아키타현", 3),
    ("06", "山形県", "야마가타현", 3),
    ("07", "福島県", "후쿠시마현", 4),
    ("08", "茨城県", "이바라키현", 7),
    ("09", "栃木県", "도치기현", 5),
    ("10", "群馬県", "군마현", 5),
    ("11", "埼玉県", "사이타마현", 16),
    ("12", "千葉県", "지바현", 14),
    ("13", "東京都", "도쿄도", 30),
    ("14", "神奈川県", "가나가와현", 20),
    ("15", "新潟県", "니가타현", 5),
    ("16", "富山県", "도야마현", 3),
    ("17", "石川県", "이시카와현", 3),
    ("18", "福井県", "후쿠이현", 2),
    ("19", "山梨県", "야마나시현", 2),
    ("20", "長野県", "나가노현", 5),
    ("21", "岐阜県", "기후현", 5),
    ("22", "静岡県", "시즈오카현", 8),
    ("23", "愛知県", "아이치현", 16),
    ("24", "三重県", "미에현", 4),
    ("25", "滋賀県", "시가현", 3),
    ("26", "京都府", "교토부", 6),
    ("27", "大阪府", "오사카부", 19),
    ("28", "兵庫県", "효고현", 12),
    ("29", "奈良県", "나라현", 3),
    ("30", "和歌山県", "와카야마현", 2),
    ("31", "鳥取県", "돗토리현", 2),
    ("32", "島根県", "시마네현", 2),
    ("33", "岡山県", "오카야마현", 4),
    ("34", "広島県", "히로시마현", 6),
    ("35", "山口県", "야마구치현", 3),
    ("36", "徳島県", "도쿠시마현", 2),
    ("37", "香川県", "가가와현", 3),
    ("38", "愛媛県", "에히메현", 3),
    ("39", "高知県", "고치현", 2),
    ("40", "福岡県", "후쿠오카현", 11),
    ("41", "佐賀県", "사가현", 2),
    ("42", "長崎県", "나가사키현", 3),
    ("43", "熊本県", "구마모토현", 4),
    ("44", "大分県", "오이타현", 3),
    ("45", "宮崎県", "미야자키현", 3),
    ("46", "鹿児島県", "가고시마현", 4),
    ("47", "沖縄県", "오키나와현", 4),
]

PR_BLOCKS = [
    ("hokkaido", "北海道", "홋카이도", 8),
    ("tohoku", "東北", "도호쿠", 12),
    ("kita-kanto", "北関東", "기타칸토", 19),
    ("minami-kanto", "南関東", "미나미칸토", 23),
    ("tokyo", "東京", "도쿄", 19),
    ("hokuriku-shinetsu", "北陸信越", "호쿠리쿠신에쓰", 11),
    ("tokai", "東海", "도카이", 21),
    ("kinki", "近畿", "긴키", 24),
    ("chugoku", "中国", "주고쿠", 10),
    ("shikoku", "四国", "시코쿠", 6),
    ("kyushu", "九州", "규슈", 23),
]

PARTY_META: Dict[str, Dict[str, str]] = {
    "LDP": {
        "name_ja": "自由民主党",
        "name_ko": "자유민주당",
        "name_en": "Liberal Democratic Party",
        "leader_ko": "다카이치 사나에",
        "note_ko": "여당. 일본유신회와 연립(자유 연립).",
    },
    "Chudo": {
        "name_ja": "中道改革連合",
        "name_ko": "중도개혁연합",
        "name_en": "Centrist Reform Alliance",
        "leader_ko": "노다 요시히코·사이토 데쓰오",
        "note_ko": "2026-01-16 입헌민주당·공명당 합류로 발족. 공동 대표 체제.",
    },
    "Ishin": {
        "name_ja": "日本維新の会",
        "name_ko": "일본유신회",
        "name_en": "Nippon Ishin no Kai",
        "leader_ko": "요시무라 히로후미",
        "note_ko": "여당. 자민당과 연립.",
    },
    "DPP": {
        "name_ja": "国民民主党",
        "name_ko": "국민민주당",
        "name_en": "Democratic Party For the People",
        "leader_ko": "다마키 유이치로",
    },
    "Sanseito": {
        "name_ja": "参政党",
        "name_ko": "참정당",
        "name_en": "Sanseito",
        "leader_ko": "가미야 소헤이",
    },
    "Mirai": {
        "name_ja": "チームみらい",
        "name_ko": "팀 미라이",
        "name_en": "Team Mirai",
        "leader_ko": "안노 다카히로",
    },
    "JCP": {
        "name_ja": "日本共産党",
        "name_ko": "일본공산당",
        "name_en": "Japanese Communist Party",
        "leader_ko": "다무라 도모코",
    },
    "Genzei": {
        "name_ja": "減税日本・ゆうこく連合",
        "name_ko": "감세일본·유코쿠연합",
        "name_en": "Genzei Nippon / Yukoku Union",
        "leader_ko": "하라구치 가즈히로·가와무라 다카시",
        "note_ko": "2026-01-24 합류. 공동 대표.",
    },
    "Reiwa": {
        "name_ja": "れいわ新選組",
        "name_ko": "레이와 신센구미",
        "name_en": "Reiwa Shinsengumi",
        "leader_ko": "야마모토 다로",
    },
    "Hoshu": {
        "name_ja": "日本保守党",
        "name_ko": "일본보수당",
        "name_en": "Conservative Party of Japan",
        "leader_ko": "햐쿠타 나오키",
    },
    "SDP": {
        "name_ja": "社会民主党",
        "name_ko": "사회민주당",
        "name_en": "Social Democratic Party",
        "leader_ko": "후쿠시마 미즈호",
    },
    "IND": {
        "name_ja": "無所属",
        "name_ko": "무소속",
        "name_en": "Independent",
        "note_ko": "어느 정당·연립에도 합산하지 않는다.",
    },
}

PARTY_FROM_JA = {
    "自由民主党": "LDP",
    "自民": "LDP",
    "中道改革連合": "Chudo",
    "中道": "Chudo",
    "日本維新の会": "Ishin",
    "維新": "Ishin",
    "国民民主党": "DPP",
    "国民": "DPP",
    "参政党": "Sanseito",
    "参政": "Sanseito",
    "チームみらい": "Mirai",
    "みらい": "Mirai",
    "日本共産党": "JCP",
    "共産": "JCP",
    "減税日本・ゆうこく連合": "Genzei",
    "減税ゆうこく": "Genzei",
    "減税日本": "Genzei",
    "ゆうこく連合": "Genzei",
    "減ゆ": "Genzei",
    "れいわ新選組": "Reiwa",
    "れいわ": "Reiwa",
    "れ新": "Reiwa",
    "日本保守党": "Hoshu",
    "保守": "Hoshu",
    "社会民主党": "SDP",
    "社民": "SDP",
    "無所属": "IND",
    "無所": "IND",
}

# 公示前勢力 — Wikipedia 第51回 + Nikkei 公示前. 0석 정당은 넣지 않는다.
CURRENT_BY_PARTY = {
    "LDP": 198,
    "Chudo": 167,
    "Ishin": 34,
    "DPP": 27,
    "Sanseito": 2,
    "JCP": 8,
    "Genzei": 5,
    "Reiwa": 8,
    "Hoshu": 1,
    "IND": 15,
}
CURRENT_TOTAL = 465
CURRENT_AS_OF = "2026-01-27"
CURRENT_NOTE = (
    "공시전 세력(중의원 전체 465석). 소선거구·비례로 나눈 공시전 의석은 출처에 없어 "
    "열마다 같은 전체 숫자를 둔다. 198+167+34+27+2+8+5+8+1+15=465."
)

SMD_RESULT_NOTE = "소선거구 당선 집계. 정당별 합이 total과 같아야 한다."
PR_RESULT_NOTE = (
    "중의원 의원 명부 회파 기준 당선자. 명부 전체(915명)는 총무성 결과조에 있다. "
    "위키/닛케이 선거 당선 당파와 어긋남: 중도 42·레이와 1 vs 회파 중도 41·무소속 2·레이와 0. "
    "숫자는 맞추지 않고 둘 다 남긴다."
)
PR_IND_NOTES = {
    "石井啓一": "중의원 회파 무소속. 위키 비례 북칸토 당선 명단에는 중도개혁연합.",
    "山本ジョージ": "중의원 회파 무소속. 선거 당선 당파 표기와 다를 수 있음.",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def ensure_jiji_pages(sleep_s: float = 0.25) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for code, _ja, _ko, _n in PREFS:
        dest = RAW / f"senkyoku_{code}.html"
        if dest.exists() and dest.stat().st_size > 10000:
            continue
        url = f"{JIJI_INDEX}?l=senkyoku_{code}"
        print(f"fetch {url}")
        dest.write_bytes(fetch(url))
        time.sleep(sleep_s)


def strip_tags(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return unescape(re.sub(r"\s+", " ", t)).strip()


def party_abbr(raw: str) -> Tuple[str, Optional[str]]:
    text = raw.replace("\u3000", " ").strip()
    rec = None
    m = re.search(r"[（(]([^）)]+)[）)]", text)
    if m:
        rec = m.group(1).strip()
        text = (text[: m.start()] + text[m.end() :]).strip()
    text = text.split("\n")[0].strip()
    if text in PARTY_FROM_JA:
        return PARTY_FROM_JA[text], rec
    for ja, abbr in sorted(PARTY_FROM_JA.items(), key=lambda x: -len(x[0])):
        if text.startswith(ja) or ja in text:
            return abbr, rec
    if not text or text in {"諸派", "その他"}:
        return "IND", rec or text or None
    slug = re.sub(r"[^A-Za-z0-9]+", "", text)[:12] or "OTHER"
    return f"OTH-{slug}", rec


def parse_votes(cell: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", cell)
    return int(digits) if digits else None


def parse_pref_html(code: str, html: str) -> List[Dict[str, Any]]:
    pref = next(p for p in PREFS if p[0] == code)
    districts: List[Dict[str, Any]] = []
    blocks = re.findall(
        r'<div class="Senkyo_ku" id="(\d+)">\s*<h4>(.*?)</h4>(.*?)</table>',
        html,
        flags=re.S,
    )
    for dist_id, h4, table in blocks:
        title = strip_tags(re.sub(r"<span.*?</span>", "", h4, flags=re.S))
        title = re.sub(r"（.*?）", "", title).strip()
        mnum = re.search(r"(\d+)\s*区", title)
        n = int(mnum.group(1)) if mnum else int(dist_id)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)
        cands: List[Dict[str, Any]] = []
        for row in rows[1:]:
            if "<th" in row:
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
            if len(tds) < 3:
                continue
            vote_html, name_html, party_html = tds[0], tds[1], tds[2]
            status_html = tds[3] if len(tds) > 3 else ""
            elected_smd = "tousenS" in vote_html and "当" in vote_html
            elected_pr = "tousenH" in vote_html or 'class="hirei"' in row
            votes = parse_votes(vote_html)
            name_plain = strip_tags(re.sub(r"<p>.*?</p>", "", name_html, flags=re.S))
            name = re.sub(r"\s+", " ", name_plain.replace("\u3000", " ")).strip()
            party_text = strip_tags(party_html)
            abbr, rec = party_abbr(party_text)
            dual = "Juhuku" in status_html or ">重<" in status_html
            incumbent = bool(re.search(r">前<", status_html))
            cand: Dict[str, Any] = {
                "party_abbr": abbr,
                "name": name,
                "status": "nominated",
                "elected": elected_smd,
                "source": f"{JIJI_INDEX}?l=senkyoku_{code}#{dist_id}",
            }
            if votes is not None:
                cand["votes"] = votes
            if dual:
                cand["dual_listed"] = True
            if incumbent:
                cand["incumbent"] = True
            notes = []
            if elected_pr:
                notes.append("비례 부활 당선(소선거구는 낙선)")
            if rec:
                notes.append(f"추천: {rec}")
            if notes:
                cand["note_ko"] = " · ".join(notes)
            href = re.search(r'href="(\./2026syu\?d=\d+)"', name_html)
            if href:
                cand["source"] = "https://www.jiji.com/jc/" + href.group(1).lstrip("./")
            cands.append(cand)
        districts.append(
            {
                "id": f"{code}-{n:02d}",
                "name_ko": f"{pref[2]} {n}구",
                "name_ja": f"{pref[1].replace('県','').replace('府','').replace('都','')}{n}区"
                if pref[1] != "北海道"
                else f"北海道{n}区",
                "group_ko": pref[2],
                "seats": 1,
                "status": "completed",
                "candidates": cands,
            }
        )
    return districts


def load_pr_from_roster() -> List[Dict[str, Any]]:
    roster = json.loads((EXTRACTED / "jpn_shugiin.json").read_text(encoding="utf-8"))
    by_block: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in roster.get("members") or []:
        dist = m.get("district") or ""
        if not dist.startswith("（比）"):
            continue
        block_ja = dist.replace("（比）", "").strip()
        abbr = m.get("abbr") or PARTY_FROM_JA.get(m.get("kaiha") or "", "IND")
        name = (m.get("name") or "").replace(" ", "")
        row: Dict[str, Any] = {
            "party_abbr": abbr,
            "name": name,
            "status": "nominated",
            "elected": True,
            "source": HOUSE_ROSTER,
        }
        extra = PR_IND_NOTES.get(name)
        if extra:
            row["note_ko"] = extra
        by_block[block_ja].append(row)
    districts = []
    for key, ja, ko, seats in PR_BLOCKS:
        cands = by_block.get(ja) or []
        dist: Dict[str, Any] = {
            "id": key,
            "name_ko": f"{ko} 블록",
            "name_ja": f"{ja}ブロック",
            "group_ko": "비례대표",
            "seats": seats,
            "status": "completed",
            "candidates": cands,
        }
        if len(cands) != seats:
            dist["note_ko"] = (
                f"법정 정수 {seats}석, 중의원 명부 （比）{ja} 표기 {len(cands)}명. "
                "맞추지 않음."
            )
        districts.append(dist)
    return districts


def parties_used(abbrs: Counter) -> List[Dict[str, Any]]:
    out = []
    for abbr in list(PARTY_META) + [a for a in abbrs if a not in PARTY_META]:
        if abbr not in abbrs and abbr not in CURRENT_BY_PARTY:
            continue
        meta = PARTY_META.get(abbr) or {
            "name_ja": abbr,
            "name_ko": abbr,
            "name_en": abbr,
        }
        row: Dict[str, Any] = {"abbr": abbr, **{k: v for k, v in meta.items() if v}}
        out.append(row)
    # Keep running parties even if they had 0 current seats (Mirai, SDP).
    seen = {p["abbr"] for p in out}
    for abbr in abbrs:
        if abbr not in seen:
            out.append({"abbr": abbr, "name_ko": abbr, "name_en": abbr})
    return out


def count_elected(districts: List[Dict[str, Any]], smd: bool) -> Counter:
    c: Counter = Counter()
    for d in districts:
        for cand in d["candidates"]:
            if smd:
                if cand.get("elected") is True:
                    c[cand["party_abbr"]] += 1
            else:
                if cand.get("elected") is True:
                    c[cand["party_abbr"]] += 1
    return c


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: compact(v)
            for k, v in obj.items()
            if v is not None and v != ""
        }
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def build() -> Dict[str, Any]:
    ensure_jiji_pages()
    smd_districts: List[Dict[str, Any]] = []
    for code, ja, ko, n_expect in PREFS:
        html = (RAW / f"senkyoku_{code}.html").read_text(encoding="utf-8", errors="replace")
        got = parse_pref_html(code, html)
        if len(got) != n_expect:
            raise SystemExit(f"{ja}: expected {n_expect} districts, got {len(got)}")
        smd_districts.extend(got)
    if len(smd_districts) != 289:
        raise SystemExit(f"SMD count {len(smd_districts)} != 289")

    pr_districts = load_pr_from_roster()
    smd_result = count_elected(smd_districts, smd=True)
    pr_result = count_elected(pr_districts, smd=False)
    running = Counter()
    for d in smd_districts + pr_districts:
        for c in d["candidates"]:
            running[c["party_abbr"]] += 1

    used_parties = set(running) | set(CURRENT_BY_PARTY)
    parties = parties_used(Counter({a: 1 for a in used_parties}))

    current = {
        "by_party": dict(CURRENT_BY_PARTY),
        "total": CURRENT_TOTAL,
        "as_of": CURRENT_AS_OF,
        "note_ko": CURRENT_NOTE,
        "vacancies": 0,
    }

    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "JPN",
        "date": "2026-02-08",
        "system_id": "jpn-shugiin",
        "as_of": AS_OF,
        "sources": [
            JIJI_INDEX,
            MIC_RESULTS,
            WIKI_51,
            HOUSE_ROSTER,
            "https://www.nikkei.com/special/election",
        ],
        "parties": parties,
        "columns": [
            {
                "key": "smd",
                "label_ko": "소선거구",
                "current": current,
                "result": {
                    "by_party": dict(smd_result),
                    "total": 289,
                    "as_of": "2026-02-08",
                    "note_ko": SMD_RESULT_NOTE,
                },
                "contested_ko": "289석 전원 개선",
                "seat_note_ko": "병립형. 이 열과 비례대표 열은 연동되지 않는다.",
                "districts": smd_districts,
            },
            {
                "key": "pr",
                "label_ko": "비례대표",
                "current": current,
                "result": {
                    "by_party": dict(pr_result),
                    "total": 176,
                    "as_of": "2026-02-08",
                    "note_ko": PR_RESULT_NOTE,
                },
                "contested_ko": "176석 11개 권역",
                "seat_note_ko": "권역 정당명부. 중복입후보자는 소선거구 열에 dual_listed.",
                "districts": pr_districts,
            },
        ],
    }
    return compact(doc)


def write_outputs(doc: Dict[str, Any]) -> None:
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTESTS_DIR / f"{EVENT_ID}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index = {
        "schema": "elections_contests_index_v1",
        "as_of": AS_OF,
        "null_policy": {"없음": "해당 없음", "불명": "미확정"},
        "events": [
            {
                "event_id": EVENT_ID,
                "iso3": "JPN",
                "date": "2026-02-08",
                "path": f"elections_contests/{EVENT_ID}.json",
                "status": "complete",
                "as_of": AS_OF,
            }
        ],
    }
    (PUBLIC / "elections_contests_index_v1.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    smd_n = len(doc["columns"][0]["districts"])
    smd_c = sum(len(d["candidates"]) for d in doc["columns"][0]["districts"])
    pr_n = len(doc["columns"][1]["districts"])
    pr_c = sum(len(d["candidates"]) for d in doc["columns"][1]["districts"])
    print(f"wrote {path} SMD {smd_n} districts / {smd_c} candidates; PR {pr_n} / {pr_c}")
    print("smd elected", doc["columns"][0]["result"]["by_party"], "sum", sum(doc["columns"][0]["result"]["by_party"].values()))
    print("pr elected", doc["columns"][1]["result"]["by_party"], "sum", sum(doc["columns"][1]["result"]["by_party"].values()))


def main() -> None:
    doc = build()
    write_outputs(doc)


if __name__ == "__main__":
    main()
