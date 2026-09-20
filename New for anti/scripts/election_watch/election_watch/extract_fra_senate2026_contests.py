"""Build elections_contest_v1 for fra-2026-senate.

Interior ministry CSVs on data.gouv (majority tour 1 + PR lists), seats from
Sénat livret série 2, current groups from senat.fr grp.html (2026-09-12).
Indirect election; calendar date stays 2026-09.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import date
from typing import Any, Dict, Iterable, List, Tuple

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"
RAW = ROOT / "raw" / "fra"

AS_OF = date.today().isoformat()
EVENT_ID = "fra-2026-senate"

CSV_PR = "https://www.data.gouv.fr/fr/datasets/r/67cfd5b8-2728-4c50-98db-9f8462772f22"
CSV_MAJ = "https://www.data.gouv.fr/fr/datasets/r/6428b072-c610-4bc2-9790-8f2ea8978341"
SENAT_GRP = "https://www.senat.fr/senateurs/grp.html"
SENAT_SITE = "https://senatoriales2026.senat.fr/"
LIVRET = "https://senatoriales2026.senat.fr/media/6a468691a692a_Livret_Donnees_essentielles_Scrutin_2026.pdf"
UA = "Mozilla/5.0 (compatible; global-trade-dashboard election_watch/fra-senate2026)"

# Sénat livret série 2, keyed by Interior circ code.
SEATS_PR = {
    "01": 3, "02": 3, "06": 5, "13": 8, "14": 3, "17": 3, "21": 3, "22": 3,
    "25": 3, "26": 3, "27": 3, "28": 3, "29": 4, "30": 3, "31": 5, "33": 6,
    "34": 4, "35": 4, "67": 5, "68": 4, "69": 7, "71": 3, "72": 3, "74": 3,
    "76": 6, "80": 3, "83": 4, "84": 3, "85": 3, "ZZ": 6,
}
SEATS_MAJ = {
    "03": 2, "04": 1, "05": 1, "07": 2, "08": 2, "09": 1, "10": 2, "11": 2,
    "12": 2, "15": 2, "16": 2, "18": 2, "19": 2, "23": 2, "24": 2, "2A": 1,
    "2B": 1, "32": 2, "36": 2, "70": 2, "73": 2, "79": 2, "81": 2, "82": 2,
    "86": 2, "87": 2, "88": 2, "89": 2, "90": 1, "973": 2, "977": 1, "978": 1,
    "986": 1, "987": 2,
}

# senat.fr 그룹 표, 2026-09-12. 합 348.
GROUP_CURRENT = {
    "REP": 131, "SER": 64, "UC": 59, "LI-RT": 20, "RDPI": 19,
    "CRCE-K": 18, "RDSE": 17, "GEST": 16, "RASNAG": 4,
}

PARTY_META: Dict[str, Dict[str, str]] = {
    "REP": {
        "name_fr": "Groupe Les Républicains",
        "name_ko": "공화당 그룹",
        "name_en": "The Republicans group",
        "leader_ko": "마티외 다르노",
        "note_ko": "원내 그룹. 후보 누앙스 LR/LLR과 숫자를 합치지 않는다. senat.fr 2026-09-12: 정회원 101·동조 15·연계 15=131.",
    },
    "SER": {
        "name_fr": "Groupe Socialiste, Écologiste et Républicain",
        "name_ko": "사회당·생태·공화 그룹",
        "name_en": "Socialist, Ecologist and Republican group",
        "leader_ko": "파트리크 카네르",
        "note_ko": "원내 그룹. 상원 리브레는 시리즈2 기준 SER 65석으로 적어 12일 표(64)와 어긋난다.",
    },
    "UC": {
        "name_fr": "Groupe Union Centriste",
        "name_ko": "중도연합 그룹",
        "name_en": "Centrist Union group",
        "leader_ko": "에르베 마르세유",
    },
    "LI-RT": {
        "name_fr": "Groupe Les Indépendants - République et Territoires",
        "name_ko": "무소속-공화와 영토 그룹",
        "name_en": "Independents – Republic and Territories",
        "leader_ko": "클로드 말뤼레",
    },
    "RDPI": {
        "name_fr": "Groupe Rassemblement des démocrates, progressistes et indépendants",
        "name_ko": "민주·진보·무소속 연합",
        "name_en": "RDPI",
    },
    "CRCE-K": {
        "name_fr": "Groupe Communiste Républicain Citoyen et Écologiste - Kanaky",
        "name_ko": "공산·공화·시민·생태-카나키 그룹",
        "name_en": "CRCE-Kanaky",
        "leader_ko": "세실 퀴키에르망",
    },
    "RDSE": {
        "name_fr": "Groupe du Rassemblement Démocratique et Social Européen",
        "name_ko": "민주사회유럽연합 그룹",
        "name_en": "RDSE",
        "leader_ko": "마리즈 카레르",
    },
    "GEST": {
        "name_fr": "Groupe Écologiste - Solidarité et Territoires",
        "name_ko": "생태-연대와 영토 그룹",
        "name_en": "Ecologist group",
        "leader_ko": "기욤 공타르",
    },
    "RASNAG": {
        "name_fr": "Réunion administrative des sénateurs ne figurant sur la liste d'aucun groupe",
        "name_ko": "무소속 행정회합",
        "name_en": "Non-attached (RASNAG)",
    },
}

NUANCE_KO = {
    "LR": "공화당", "LLR": "공화당 명부", "SOC": "사회당", "LSOC": "사회당 명부",
    "RN": "국민연합", "LRN": "국민연합 명부", "FI": "불복하는 프랑스", "LFI": "불복하는 프랑스 명부",
    "COM": "공산당", "LCOM": "공산당 명부", "VEC": "유럽생태-녹색당", "LVEC": "생태 명부",
    "HOR": "오리종", "LHOR": "오리종 명부", "UDI": "독립민주연합", "LUDI": "UDI 명부",
    "REN": "르네상스", "MDM": "민주운동", "LMDM": "민주운동 명부",
    "REC": "르콩케트", "LREC": "르콩케트 명부", "UDR": "공화국 우파연합", "LUDR": "UDR 명부",
    "DVD": "기타 우파", "LDVD": "기타 우파 명부", "DVG": "기타 좌파", "LDVG": "기타 좌파 명부",
    "DVC": "기타 중도", "LDVC": "기타 중도 명부", "DIV": "기타", "LDIV": "기타 명부",
    "EXD": "극우", "LEXD": "극우 명부", "ECO": "생태", "LECO": "생태 명부",
    "REG": "지역주의", "LREG": "지역주의 명부", "RDG": "급진당", "PR": "급진당",
    "GEN": "제네라시옹", "DSV": "주권우파", "LUG": "좌파연합 명부", "LUC": "중도연합 명부",
    "LUD": "우파연합 명부", "LUXD": "극우연합 명부",
}


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def fetch(url: str, dest_name: str) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / dest_name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        print(f"fetched {url} -> {dest} ({len(data)} bytes)")
        return data.decode("utf-8-sig")
    except Exception as exc:
        if dest.exists():
            print(f"fetch failed ({exc}); using cache {dest}")
            return dest.read_text(encoding="utf-8-sig")
        raise SystemExit(f"cannot fetch {url}: {exc}") from exc


def read_csv(text: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def current_block() -> Dict[str, Any]:
    summed = sum(GROUP_CURRENT.values())
    if summed != 348:
        raise SystemExit(f"group seats {summed} != 348")
    return {
        "by_party": dict(GROUP_CURRENT),
        "total": 348,
        "as_of": "2026-09-12",
        "note_ko": (
            "senat.fr 그룹 표(2026-09-12). REP 131(101+15+15) SER 64 UC 59 LI-RT 20 "
            "RDPI 19 CRCE-K 18 RDSE 17 GEST 16 RASNAG 4 = 348. "
            "원내 그룹이지 후보 누앙스(LR·SOC·RN…)가 아니다. 시리즈2/다수결·비례로 나눈 공시전 의석은 출처에 없어 두 열에 같은 348을 둔다. "
            "상원 리브레는 SER 시리즈2 잔여를 65로 적어 64와 병기."
        ),
    }


def cand_row(party: str, name: str, source: str, incumbent: bool, note: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "party_abbr": party,
        "name": name,
        "status": "nominated",
        "source": source,
        "note_ko": note,
    }
    if incumbent:
        row["incumbent"] = True
    return row


def build_maj(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    by: Dict[str, List[Dict[str, str]]] = {}
    names: Dict[str, str] = {}
    used = []
    for r in rows:
        code = r["Code circonscription"].strip()
        by.setdefault(code, []).append(r)
        names[code] = r["Libellé circonscription"].strip()
    districts = []
    for code in sorted(by, key=lambda c: (c.isdigit() is False, c)):
        if code not in SEATS_MAJ:
            raise SystemExit(f"majority circ {code} missing seats")
        cands = []
        for r in by[code]:
            party = (r.get("Code nuance") or "DIV").strip() or "DIV"
            used.append(party)
            prenom = (r.get("Prénom du candidat") or "").strip()
            nom = (r.get("Nom du candidat") or "").strip()
            repl = " ".join(
                x for x in [(r.get("Prénom remplaçant") or "").strip(), (r.get("Nom remplaçant") or "").strip()] if x
            )
            nuance = (r.get("Nuance du candidat") or party).strip()
            notes = [f"누앙스 {nuance}"]
            if repl:
                notes.append(f"보충 {repl}")
            cands.append(cand_row(
                party,
                f"{prenom} {nom}".strip(),
                CSV_MAJ,
                (r.get("Sortant") or "").strip() == "OUI",
                ". ".join(notes) + ".",
            ))
        districts.append({
            "id": code,
            "name_ko": names[code],
            "group_ko": "다수결 2라운드",
            "seats": SEATS_MAJ[code],
            "status": "nominated",
            "candidates": cands,
        })
    if len(districts) != 34:
        raise SystemExit(f"majority districts {len(districts)} != 34")
    if sum(d["seats"] for d in districts) != 59:
        raise SystemExit("majority seats != 59")
    return districts, used


def build_pr(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    by: Dict[str, List[Dict[str, str]]] = {}
    names: Dict[str, str] = {}
    used = []
    for r in rows:
        code = r["Code circonscription"].strip()
        by.setdefault(code, []).append(r)
        names[code] = r["Circonscription"].strip()
    districts = []
    for code in sorted(by, key=lambda c: (c.isdigit() is False, c)):
        if code not in SEATS_PR:
            raise SystemExit(f"PR circ {code} missing seats")
        ordered = sorted(by[code], key=lambda r: (int(r.get("N° dépôt") or 0), int(r.get("Ordre") or 0)))
        cands = []
        for r in ordered:
            party = (r.get("Code nuance de liste") or "LDIV").strip() or "LDIV"
            used.append(party)
            prenom = (r.get("Prénom sur le bulletin de vote") or "").strip()
            nom = (r.get("Nom sur le bulletin de vote") or "").strip()
            liste = (r.get("Libellé de la liste") or "").strip()
            ordre = (r.get("Ordre") or "").strip()
            notes = [f"명부 {liste}", f"순번 {ordre}"]
            if (r.get("Tête de liste") or "").strip() == "OUI":
                notes.append("명부 1번")
            cands.append(cand_row(
                party,
                f"{prenom} {nom}".strip(),
                CSV_PR,
                (r.get("Sortant") or "").strip() == "OUI",
                ". ".join(notes) + ".",
            ))
        districts.append({
            "id": code,
            "name_ko": names[code],
            "group_ko": "비례명부",
            "seats": SEATS_PR[code],
            "status": "nominated",
            "candidates": cands,
        })
    if len(districts) != 30:
        raise SystemExit(f"PR districts {len(districts)} != 30")
    if sum(d["seats"] for d in districts) != 119:
        raise SystemExit("PR seats != 119")
    return districts, used


def parties_block(used: Iterable[str]) -> List[Dict[str, Any]]:
    used_set = set(used) | set(GROUP_CURRENT)
    out: List[Dict[str, Any]] = []
    for abbr in list(PARTY_META) + sorted(used_set - set(PARTY_META)):
        if abbr not in used_set:
            continue
        meta = PARTY_META.get(abbr, {})
        row: Dict[str, Any] = {"abbr": abbr}
        row["name_ko"] = meta.get("name_ko") or NUANCE_KO.get(abbr) or abbr
        if meta.get("name_fr"):
            row["name_fr"] = meta["name_fr"]
        if meta.get("name_en"):
            row["name_en"] = meta["name_en"]
        if meta.get("leader_ko"):
            row["leader_ko"] = meta["leader_ko"]
        if meta.get("note_ko"):
            row["note_ko"] = meta["note_ko"]
        out.append(row)
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
        "iso3": "FRA",
        "date": "2026-09",
        "path": f"elections_contests/{EVENT_ID}.json",
        "status": "complete",
        "as_of": AS_OF,
    }
    events = [e for e in idx.get("events", []) if e.get("event_id") != EVENT_ID]
    events.append(row)
    events.sort(key=lambda e: (e.get("date") or "", e.get("event_id") or ""))
    idx["events"] = events
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> Dict[str, Any]:
    maj_rows = read_csv(fetch(CSV_MAJ, "senat2026_majoritaire.csv"))
    pr_rows = read_csv(fetch(CSV_PR, "senat2026_proportionnel.csv"))
    maj_d, maj_parties = build_maj(maj_rows)
    pr_d, pr_parties = build_pr(pr_rows)
    current = current_block()
    n_maj = sum(len(d["candidates"]) for d in maj_d)
    n_pr = sum(len(d["candidates"]) for d in pr_d)
    columns = [
        {
            "key": "majority",
            "label_ko": "다수결 (1~2석 도)",
            "current": current,
            "contested_ko": "시리즈 2 다수결 34개 선거구 59석. 같은 날 2라운드. 간선.",
            "seat_note_ko": (
                f"내무부 data.gouv 개인 후보 {n_maj}명(1차). 보충후보는 note_ko. "
                "일반 유권자 투표가 아니다. 그랑 엘렉퇴르 약 93 469명(시리즈 2)."
            ),
            "districts": maj_d,
        },
        {
            "key": "pr",
            "label_ko": "비례명부 (3석 이상)",
            "current": current,
            "contested_ko": "시리즈 2 비례 30개 선거구 119석. 최고평균, 교차·선호투표 없음.",
            "seat_note_ko": (
                f"내무부 data.gouv 명부 후보 {n_pr}명. 명부 전체가 투표용지라 전원을 넣었다. "
                "해외 프랑스인 6석은 ZZ."
            ),
            "districts": pr_d,
        },
    ]
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "FRA",
        "date": "2026-09",
        "system_id": "fra-senate",
        "as_of": AS_OF,
        "sources": [CSV_MAJ, CSV_PR, SENAT_GRP, SENAT_SITE, LIVRET],
        "parties": parties_block(maj_parties + pr_parties),
        "columns": columns,
        "note_ko": (
            "달력 date는 2026-09(월 단위, 데크레 공고 전으로 적혀 있음). "
            "상원 공식 일정은 2026-09-27. 시리즈 2 178석(59+119). "
            "현재 의석은 원내 그룹, 후보는 내무부 누앙스. 합치지 않았다."
        ),
    }
    return compact(doc)


def main() -> None:
    if sum(SEATS_PR.values()) != 119 or sum(SEATS_MAJ.values()) != 59:
        raise SystemExit("seat tables do not sum")
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    maj = doc["columns"][0]
    pr = doc["columns"][1]
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"majority {len(maj['districts'])}/{sum(len(d['candidates']) for d in maj['districts'])}; "
        f"pr {len(pr['districts'])}/{sum(len(d['candidates']) for d in pr['districts'])}"
    )


if __name__ == "__main__":
    main()
