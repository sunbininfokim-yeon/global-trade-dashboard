"""Build elections_contest_v1 for can-2026-quebec.

Dissolution seats: Assemblée nationale, 43rd legislature through 2026-08-27 (125).
2026 result: Wikipedia detailed results (127 ridings). Riding vote cells are filled
only where the page has a number; winners still come from the sortant/élu table.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"
RAW = ROOT / "raw" / "can"

AS_OF = date.today().isoformat()
EVENT_ID = "can-2026-quebec"

WIKI_RESULTS = (
    "https://fr.wikipedia.org/wiki/"
    "Résultats_détaillés_des_élections_générales_québécoises_de_2026"
)
WIKI_LEG = "https://fr.wikipedia.org/wiki/43e_législature_du_Québec"
ASSNAT = (
    "https://www.assnat.qc.ca/fr/actualites-salle-presse/nouvelle/actualite-67333.html"
)
DGEQ = (
    "https://www.electionsquebec.qc.ca/resultats-et-statistiques/"
    "resultats-generales/2026-10-05/"
)
UA = "global-trade-dashboard election_watch/can-quebec2026 (+research)"

# 43e législature, row « Du 22 avril au 27 août 2026 ». Sum 125.
# CAQ 79, PLQ 18, QS 11, PQ 7, PCQ 1, IND 9. Vacant column is « - ».
CURRENT = {"CAQ": 79, "PLQ": 18, "QS": 11, "PQ": 7, "PCQ": 1, "IND": 9}
CURRENT_TOTAL = 125
RESULT_TOTAL = 127

LABEL_ABBR = {
    "parti québécois": "PQ",
    "pq": "PQ",
    "conservateur": "PCQ",
    "pcq": "PCQ",
    "libéral": "PLQ",
    "plq": "PLQ",
    "caq": "CAQ",
    "québec solidaire": "QS",
    "qs": "QS",
    "indépendant": "IND",
    "indépendants": "IND",
    "ind": "IND",
    "climat québec": "CQ",
    "vert": "PVQ",
    "parti vert du québec": "PVQ",
    "nul": "PN",
    "parti nul": "PN",
    "parti canadien du québec": "PCaQ",
    "marxiste-léniniste": "PMLQ",
    "communiste": "COMM",
    "équipe autonomiste": "EA",
    "bloc pot": "BP",
    "culinaire": "PCuQ",
    "démocratie directe": "DD",
    "accès propriété et équité": "PAPE",
    "présence": "Presence",
    "osons québec": "OQ",
}

PARTY_META: Dict[str, Dict[str, str]] = {
    "PQ": {"name_ko": "퀘벡당", "name_en": "Parti Québécois", "name_fr": "Parti québécois"},
    "PLQ": {"name_ko": "퀘벡자유당", "name_en": "Quebec Liberal Party", "name_fr": "Parti libéral du Québec"},
    "PCQ": {"name_ko": "퀘벡보수당", "name_en": "Conservative Party of Quebec", "name_fr": "Parti conservateur du Québec"},
    "CAQ": {
        "name_ko": "미래를위한연합",
        "name_en": "Coalition Avenir Québec",
        "name_fr": "Coalition avenir Québec",
        "note_ko": "해산 시 여당 79석. 2026 총선에서 의석 0.",
    },
    "QS": {"name_ko": "연대퀘벡", "name_en": "Québec solidaire", "name_fr": "Québec solidaire"},
    "IND": {"name_ko": "무소속", "name_en": "Independent", "name_fr": "Indépendant"},
    "CQ": {"name_ko": "기후퀘벡", "name_en": "Climat Québec", "name_fr": "Climat Québec"},
    "PVQ": {"name_ko": "퀘벡녹색당", "name_en": "Green Party of Quebec", "name_fr": "Parti vert du Québec"},
    "PN": {"name_ko": "널당", "name_en": "Parti nul", "name_fr": "Parti nul"},
    "PCaQ": {"name_ko": "퀘벡캐나다당", "name_en": "Canadian Party of Quebec", "name_fr": "Parti canadien du Québec"},
    "PMLQ": {"name_ko": "퀘벡마르크스레닌주의당", "name_en": "Marxist-Leninist Party of Quebec", "name_fr": "Parti marxiste-léniniste du Québec"},
    "COMM": {"name_ko": "퀘벡공산당", "name_en": "Communist Party of Quebec", "name_fr": "Parti communiste du Québec"},
    "EA": {"name_ko": "자치주의팀", "name_en": "Équipe autonomiste", "name_fr": "Équipe autonomiste"},
    "BP": {"name_ko": "블록팟", "name_en": "Bloc Pot", "name_fr": "Bloc pot"},
    "PCuQ": {"name_ko": "퀘벡요리당", "name_en": "Parti culinaire du Québec", "name_fr": "Parti culinaire du Québec"},
    "DD": {"name_ko": "직접민주", "name_en": "Démocratie directe", "name_fr": "Démocratie directe"},
    "PAPE": {"name_ko": "재산접근공평당", "name_en": "Parti accès propriété et équité", "name_fr": "Parti accès propriété et équité"},
    "Presence": {"name_ko": "프레장스퀘벡", "name_en": "Présence Québec", "name_fr": "Présence Québec"},
    "OQ": {"name_ko": "오송퀘벡", "name_en": "Osons Québec", "name_fr": "Osons Québec"},
}


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def fold(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    name = name.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", name).strip().casefold()


def slug(name: str) -> str:
    text = fold(name)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "riding"


def abbr_for(label: str) -> str:
    key = fold(re.sub(r"\s*\[[^\]]+\]", "", label))
    key = re.sub(r"\s+", " ", key)
    folded = {fold(k): v for k, v in LABEL_ABBR.items()}
    if key not in folded:
        raise SystemExit(f"unknown party label: {label!r} -> {key!r}")
    return folded[key]


def fetch_wikitext() -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "qc2026_results.wikitext"
    if dest.exists() and dest.stat().st_size > 100_000:
        return dest.read_text(encoding="utf-8")
    title = "Résultats détaillés des élections générales québécoises de 2026"
    query = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
        }
    )
    req = urllib.request.Request(
        "https://fr.wikipedia.org/w/api.php?" + query,
        headers={"User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = payload["parse"]["wikitext"]["*"]
    dest.write_text(text, encoding="utf-8")
    return text


def clean_name(raw: str) -> str:
    name = re.sub(r"<ref[^>]*>.*?</ref>", "", raw)
    name = re.sub(r"<ref[^>]*/>", "", name)
    name = re.sub(r"\{\{[^}]+\}\}", "", name)
    name = name.replace("'''", "").replace("''", "")
    name = re.sub(r"\s+", " ", name).strip(" *")
    if not name or name.startswith("[["):
        raise SystemExit(f"bad candidate name: {raw!r}")
    return name


def parse_winners(wt: str) -> Dict[str, Dict[str, Optional[str]]]:
    start = wt.find("=== Députés sortants et élus par région administrative ===")
    if start < 0:
        raise SystemExit("missing sortant/élu table")
    end = re.search(r"\n==[^=]", wt[start + 20 :])
    if not end:
        raise SystemExit("sortant table has no end")
    table = wt[start : start + 20 + end.start()]
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for block in table.split("\n|-"):
        riding = re.search(r"\[\[#([^|\]]+)\|([^\]]+)\]\]", block)
        if not riding:
            continue
        title = riding.group(2).strip()
        sortnames = re.findall(
            r"\{\{sortname\|([^}|]+)\|([^}|]+)(?:\|[^}]*)?\}\}", block
        )
        party_links = re.findall(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", block)
        folded = {fold(k): v for k, v in LABEL_ABBR.items()}
        parties = []
        for label in party_links:
            key = fold(label)
            if key in folded:
                parties.append(folded[key])
        new_seat = "Nouvelle circonscription" in block
        if new_seat:
            if len(sortnames) != 1 or len(parties) != 1:
                raise SystemExit(f"{title}: new riding parse {sortnames} {party_links}")
            elected = clean_name(f"{sortnames[0][0]} {sortnames[0][1]}")
            out[title] = {
                "elected": elected,
                "elected_party": parties[-1],
                "sortant": None,
                "sortant_party": None,
            }
            continue
        if len(sortnames) < 2 or len(parties) < 2:
            raise SystemExit(f"{title}: row parse {sortnames} {party_links}")
        out[title] = {
            "sortant": clean_name(f"{sortnames[0][0]} {sortnames[0][1]}"),
            "sortant_party": parties[-2],
            "elected": clean_name(f"{sortnames[1][0]} {sortnames[1][1]}"),
            "elected_party": parties[-1],
        }
    if len(out) != RESULT_TOTAL:
        raise SystemExit(f"winners {len(out)} != {RESULT_TOTAL}")
    return out


def parse_riding_tables(wt: str) -> List[Dict[str, Any]]:
    chunks = re.split(r"\n(=+) *([^=\n]+?) *\1\n", wt)
    region = ""
    ridings: List[Dict[str, Any]] = []

    def add_table(title: str, body: str) -> None:
        cands = candidates_from_body(body)
        if not cands:
            raise SystemExit(f"{title}: no candidates")
        ridings.append({"name": title, "region": region, "candidates": cands})

    i = 1
    while i + 2 < len(chunks):
        level, title, body = chunks[i], chunks[i + 1].strip(), chunks[i + 2]
        i += 3
        if level == "==":
            region = re.sub(r"\s*\(\{\{[^}]+\}\}\)\s*$", "", title).strip()
            region = re.sub(r"\s*\([^)]*sièges?\)\s*$", "", region).strip()
            cap = re.search(r"\|\+\s*\[\[([^|\]]+)\]\]", body)
            if cap and "Candidat" in body and "wikitable" in body:
                add_table(cap.group(1).strip(), body)
            continue
        if level != "===" or "Candidat" not in body or "wikitable" not in body:
            continue
        add_table(title, body)
    if len(ridings) != RESULT_TOTAL:
        raise SystemExit(f"riding tables {len(ridings)} != {RESULT_TOTAL}")
    return ridings


def candidates_from_body(body: str) -> List[Dict[str, Any]]:
    cands: List[Dict[str, Any]] = []
    party: Optional[str] = None
    folded = {fold(k): v for k, v in LABEL_ABBR.items()}
    for line in body.splitlines():
        party_m = re.search(r"\|align=left\|\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", line)
        if party_m:
            key = fold(party_m.group(1))
            if key in folded:
                party = folded[key]
                continue
            if party:
                cands.append(
                    {
                        "party_abbr": party,
                        "name": clean_name(party_m.group(1)),
                        "votes": None,
                    }
                )
                party = None
            continue
        name_m = re.search(r"\|align=left\|(?!\[\[)([^\n<]+)", line)
        if name_m and party:
            cands.append(
                {
                    "party_abbr": party,
                    "name": clean_name(name_m.group(1)),
                    "votes": None,
                }
            )
            party = None
            continue
        if cands and cands[-1]["votes"] is None:
            num = re.search(r"formatnum:(\d+)", line)
            if num:
                cands[-1]["votes"] = int(num.group(1))
            elif re.fullmatch(r"\|\d{1,7}", line.strip()):
                cands[-1]["votes"] = int(line.strip()[1:])
    return cands


def build() -> Dict[str, Any]:
    wt = fetch_wikitext()
    winners = parse_winners(wt)
    tables = parse_riding_tables(wt)
    by_name = {fold(r["name"]): r for r in tables}
    if set(by_name) != {fold(n) for n in winners}:
        missing = {fold(n) for n in winners} - set(by_name)
        extra = set(by_name) - {fold(n) for n in winners}
        raise SystemExit(f"riding name mismatch missing={list(missing)[:5]} extra={list(extra)[:5]}")

    seat_counts: Counter = Counter()
    districts = []
    seen_ids = set()
    for title, win in winners.items():
        row = by_name[fold(title)]
        same_party = [c for c in row["candidates"] if c["party_abbr"] == win["elected_party"]]
        exact = [c for c in same_party if fold(c["name"]) == fold(win["elected"])]
        if len(exact) == 1:
            winner_name = exact[0]["name"]
            spelling_note = None
        elif len(same_party) == 1:
            winner_name = same_party[0]["name"]
            spelling_note = (
                f"당선 표는 «{win['elected']}», 선거구 명부는 «{winner_name}»."
            )
        else:
            raise SystemExit(f"{title}: elected {win['elected']} not on the ballot list")
        voted = [c for c in row["candidates"] if isinstance(c["votes"], int)]
        if voted:
            top = max(c["votes"] for c in voted)
            tops = [c for c in voted if c["votes"] == top]
            if len(tops) != 1 or tops[0]["name"] != winner_name:
                raise SystemExit(
                    f"{title}: vote winner {tops} != summary {win['elected']} {win['elected_party']}"
                )
        matched = False
        candidates = []
        for cand in row["candidates"]:
            elected = cand["name"] == winner_name
            if elected:
                matched = True
            item: Dict[str, Any] = {
                "party_abbr": cand["party_abbr"],
                "name": cand["name"],
                "status": "nominated",
                "elected": elected,
                "source": WIKI_RESULTS,
            }
            if win["sortant"] and fold(cand["name"]) == fold(win["sortant"]):
                item["incumbent"] = True
            if isinstance(cand["votes"], int):
                item["votes"] = cand["votes"]
            candidates.append(item)
        if not matched:
            raise SystemExit(f"{title}: elected {win['elected']} not on the ballot list")
        seat_counts[win["elected_party"]] += 1
        dist_id = slug(title)
        if dist_id in seen_ids:
            raise SystemExit(f"duplicate id {dist_id}")
        seen_ids.add(dist_id)
        notes = []
        if not voted:
            notes.append("위키 선거구 표의 득표 칸이 비어 있다. 당선자만 해산의원·당선 표에서 맞췄다.")
        if spelling_note:
            notes.append(spelling_note)
        note = " ".join(notes) if notes else None
        districts.append(
            compact(
                {
                    "id": dist_id,
                    "name_ko": title,
                    "name_fr": title,
                    "group_ko": row["region"],
                    "seats": 1,
                    "status": "completed",
                    "candidates": candidates,
                    "note_ko": note,
                }
            )
        )

    if sum(seat_counts.values()) != RESULT_TOTAL:
        raise SystemExit(f"seat sum {sum(seat_counts.values())}")
    result_by = dict(seat_counts)
    result_by["CAQ"] = 0
    if sum(result_by.values()) != RESULT_TOTAL:
        raise SystemExit(f"result sum {sum(result_by.values())} {result_by}")

    used = set(CURRENT) | set(result_by)
    for dist in districts:
        for cand in dist["candidates"]:
            used.add(cand["party_abbr"])
    parties = []
    for abbr in sorted(used, key=lambda a: (a not in CURRENT, a)):
        meta = PARTY_META[abbr]
        item = {"abbr": abbr, "name_ko": meta["name_ko"], "name_en": meta["name_en"], "name_fr": meta["name_fr"]}
        if meta.get("note_ko"):
            item["note_ko"] = meta["note_ko"]
        parties.append(item)

    return compact(
        {
            "schema": "elections_contest_v1",
            "event_id": EVENT_ID,
            "iso3": "CAN",
            "date": "2026-10-05",
            "system_id": "can-local",
            "as_of": AS_OF,
            "sources": [ASSNAT, WIKI_LEG, WIKI_RESULTS, DGEQ],
            "parties": parties,
            "columns": [
                {
                    "key": "assembly",
                    "label_ko": "퀘벡 주의회",
                    "current": {
                        "by_party": CURRENT,
                        "total": CURRENT_TOTAL,
                        "as_of": "2026-08-27",
                        "note_ko": (
                            "43대 의회 해산일 의석. 주의회 표 «22 avril–27 août 2026»: "
                            "CAQ 79, PLQ 18, QS 11, PQ 7, PCQ 1, 무소속 9. 합 125. 공석 칸은 «-»."
                        ),
                    },
                    "result": {
                        "by_party": result_by,
                        "total": RESULT_TOTAL,
                        "as_of": "2026-10-05",
                        "note_ko": (
                            "위키 해산의원·당선 표 127명. PQ 59, PLQ 40, PCQ 19, QS 9, CAQ 0. "
                            "CAQ 0은 의석이 없다는 결과다. DGEQ 결과 페이지의 표는 정적 HTML에 없다."
                        ),
                    },
                    "contested_ko": "퀘벡 주의회 127석 전원",
                    "districts": districts,
                }
            ],
            "note_ko": (
                "연방 총선이 아니다. 해산 시 125석, 이번 지도는 127석"
                "(벨푀유·마리라코스트제랭라주아 신설). 득표가 있는 선거구만 votes를 넣었다. "
                "여론조사·승률은 넣지 않았다."
            ),
        }
    )


def upsert_index() -> None:
    path = PUBLIC / "elections_contests_index_v1.json"
    idx = json.loads(path.read_text(encoding="utf-8"))
    idx["as_of"] = AS_OF
    row = {
        "event_id": EVENT_ID,
        "iso3": "CAN",
        "date": "2026-10-05",
        "path": f"elections_contests/{EVENT_ID}.json",
        "status": "partial",
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
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    dists = doc["columns"][0]["districts"]
    with_votes = sum(1 for d in dists if any("votes" in c for c in d["candidates"]))
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"districts {len(dists)}; with votes {with_votes}; "
        f"candidates {sum(len(d['candidates']) for d in dists)}"
    )


if __name__ == "__main__":
    main()
