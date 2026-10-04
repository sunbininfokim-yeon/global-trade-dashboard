"""Build elections_contest_v1 for bra-2026-general-r1.

TSE DivulgaCand/CDN returns 403 from this environment. Candidate rows come from
G1 auto-reports that TSE feeds (governors 2026-08-31, senate 2026-09-01; both
updated 2026-09-19). Chamber lists are too large for those pages — 27 UFs stay
scheduled. Presidential tickets: Wikipedia EN confirmed table + TSE/CNN/G1
notes on the PRTB Marçal → Avalanche swap.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "bra"
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "bra-2026-general-r1"

G1_GOV = (
    "https://g1.globo.com/politica/eleicoes/2026/noticia/2026/08/31/"
    "eleicoes-2026-veja-os-candidatos-aos-governos-de-todos-os-estados-e-do-df.ghtml"
)
G1_SEN = (
    "https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/01/"
    "eleicoes-2026-veja-os-candidatos-ao-senado-de-todos-os-estados-e-do-df.ghtml"
)
G1_PRES = (
    "https://g1.globo.com/politica/eleicoes/2026/noticia/2026/08/17/"
    "quem-sao-candidatos-a-presidencia-registro-tse.ghtml"
)
G1_PRES_TOOL = "https://g1.globo.com/politica/eleicoes/2026/quem-sao-os-candidatos/presidente.ghtml"
WIKI_EN = "https://en.wikipedia.org/wiki/2026_Brazilian_general_election"
WIKI_GOV = "https://en.wikipedia.org/wiki/List_of_current_state_governors_in_Brazil"
WIKI_CHAMBER = "https://en.wikipedia.org/wiki/Chamber_of_Deputies_(Brazil)"
WIKI_SENATE = "https://en.wikipedia.org/wiki/Federal_Senate_(Brazil)"
CNN_MARCAL = "https://www.cnnbrasil.com.br/"
G1_AVALANCHE = (
    "https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/15/"
    "apos-tse-barrar-pablo-marcal-prtb-quer-leonardo-avalanche-como-candidato"
    "-a-presidencia-troca-tem-voto-favoravel-de-relatora.ghtml"
)
TSE = "https://www.tse.jus.br/"

UA = "Mozilla/5.0 (compatible; global-trade-dashboard election_watch/bra-2026-r1)"

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
UF_BY_PT = {pt: (code, ko) for code, pt, ko in UFS}

CHAMBER_SEATS = {
    "AC": 8, "AL": 9, "AP": 8, "AM": 8, "BA": 39, "CE": 22, "DF": 8,
    "ES": 10, "GO": 17, "MA": 18, "MT": 8, "MS": 8, "MG": 53, "PA": 17,
    "PB": 12, "PR": 30, "PE": 25, "PI": 10, "RJ": 46, "RN": 8, "RS": 31,
    "RO": 8, "RR": 8, "SC": 16, "SP": 70, "SE": 8, "TO": 8,
}

PARTY_CANON = {
    "UNIÃO": "UNIAO",
    "MISSÃO": "MISSAO",
}

PARTY_META: Dict[str, Dict[str, str]] = {
    "PT": {
        "name_pt": "Partido dos Trabalhadores",
        "name_ko": "노동자당",
        "name_en": "Workers' Party",
        "note_ko": "여당. 연맹 Brasil da Esperança(PT·PCdoB·PV). 숫자는 정당별이며 연맹 합계를 만들지 않았다.",
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
        "note_ko": "연맹 União Progressista(UNIÃO·PP). 숫자는 정당별.",
    },
    "PP": {
        "name_pt": "Progressistas",
        "name_ko": "진보당",
        "name_en": "Progressistas",
        "note_ko": "연맹 União Progressista(UNIÃO·PP). 숫자는 정당별.",
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
    "PODE": {
        "name_pt": "Podemos",
        "name_ko": "포데모스",
        "name_en": "Podemos",
    },
    "PDT": {
        "name_pt": "Partido Democrático Trabalhista",
        "name_ko": "민주노동당",
        "name_en": "Democratic Labour Party",
    },
    "PSB": {
        "name_pt": "Partido Socialista Brasileiro",
        "name_ko": "브라질사회당",
        "name_en": "Brazilian Socialist Party",
    },
    "PSDB": {
        "name_pt": "Partido da Social Democracia Brasileira",
        "name_ko": "브라질사회민주당",
        "name_en": "Brazilian Social Democracy Party",
        "note_ko": "연맹 Always Forward(PSDB·Cidadania). 숫자는 정당별.",
    },
    "CIDADANIA": {
        "name_pt": "Cidadania",
        "name_ko": "시타다니아",
        "name_en": "Cidadania",
        "note_ko": "연맹 Always Forward(PSDB·Cidadania). 숫자는 정당별.",
    },
    "PSOL": {
        "name_pt": "Partido Socialismo e Liberdade",
        "name_ko": "사회주의자유당",
        "name_en": "Socialism and Liberty Party",
        "note_ko": "연맹 PSOL-REDE. 숫자는 정당별.",
    },
    "REDE": {
        "name_pt": "Rede Sustentabilidade",
        "name_ko": "지속가능네트워크",
        "name_en": "Sustainability Network",
        "note_ko": "연맹 PSOL-REDE. 숫자는 정당별.",
    },
    "AVANTE": {
        "name_pt": "Avante",
        "name_ko": "아반치",
        "name_en": "Avante",
    },
    "SOLIDARIEDADE": {
        "name_pt": "Solidariedade",
        "name_ko": "연대",
        "name_en": "Solidarity",
        "note_ko": "연맹 Renovação Solidária(Solidariedade·PRD). 숫자는 정당별.",
    },
    "PRD": {
        "name_pt": "Partido Renovação Democrática",
        "name_ko": "민주개혁당",
        "name_en": "Democratic Renewal Party",
        "note_ko": "연맹 Renovação Solidária(Solidariedade·PRD). 숫자는 정당별.",
    },
    "PCdoB": {
        "name_pt": "Partido Comunista do Brasil",
        "name_ko": "브라질공산당",
        "name_en": "Communist Party of Brazil",
        "note_ko": "연맹 Brasil da Esperança(PT·PCdoB·PV). 숫자는 정당별. PCB와 다른 당.",
    },
    "PV": {
        "name_pt": "Partido Verde",
        "name_ko": "녹색당",
        "name_en": "Green Party",
        "note_ko": "연맹 Brasil da Esperança(PT·PCdoB·PV). 숫자는 정당별.",
    },
    "NOVO": {
        "name_pt": "Partido Novo",
        "name_ko": "신당",
        "name_en": "New Party",
    },
    "MISSAO": {
        "name_pt": "Missão",
        "name_ko": "미상당",
        "name_en": "Mission Party",
    },
    "UP": {
        "name_pt": "Unidade Popular",
        "name_ko": "민중통합",
        "name_en": "Popular Unity",
    },
    "PSTU": {
        "name_pt": "Partido Socialista dos Trabalhadores Unificado",
        "name_ko": "통일사회주의노동당",
        "name_en": "United Socialist Workers' Party",
    },
    "PCB": {
        "name_pt": "Partido Comunista Brasileiro",
        "name_ko": "브라질공산당(PCB)",
        "name_en": "Brazilian Communist Party",
        "note_ko": "PCdoB와 다른 당.",
    },
    "PCO": {
        "name_pt": "Partido da Causa Operária",
        "name_ko": "노동자원인당",
        "name_en": "Workers' Cause Party",
    },
    "DC": {
        "name_pt": "Democracia Cristã",
        "name_ko": "기독민주당",
        "name_en": "Christian Democracy",
    },
    "DEMOCRATA": {
        "name_pt": "Democrata",
        "name_ko": "민주당(Democrata)",
        "name_en": "Democrata",
    },
    "PRTB": {
        "name_pt": "Partido Renovador Trabalhista Brasileiro",
        "name_ko": "브라질노동쇄신당",
        "name_en": "Brazilian Labour Renewal Party",
        "note_ko": "대선: TSE가 2026-09-11 Marçal 등록을 기각. G1 2026-09-15는 Avalanche 교체. 영문 위키 확정표는 Marçal을 남겨 둔 스냅샷이 있다.",
    },
    "AGIR": {
        "name_pt": "Agir",
        "name_ko": "아지르",
        "name_en": "Agir",
    },
    "MOBILIZA": {
        "name_pt": "Mobilização Nacional",
        "name_ko": "모빌리자",
        "name_en": "National Mobilization",
    },
    "IND": {
        "name_pt": "Independente",
        "name_ko": "무소속",
        "name_en": "Independent",
        "note_ko": "현직 주지사 열에만. 무소속을 어느 당에도 더하지 않는다.",
    },
}

# Wikipedia 2026 general election Congress "Incumbent 2026" party-level table.
CHAMBER_CURRENT = {
    "PL": 98, "PT": 64, "UNIAO": 52, "PP": 46, "PSD": 48, "MDB": 38,
    "REPUBLICANOS": 42, "PODE": 27, "PDT": 10, "PSB": 17, "PSDB": 18,
    "PSOL": 13, "AVANTE": 5, "SOLIDARIEDADE": 4, "PCdoB": 11, "PV": 6,
    "PRD": 3, "CIDADANIA": 2, "NOVO": 5, "REDE": 3, "MISSAO": 1,
}
SENATE_CURRENT = {
    "PL": 16, "PSD": 14, "MDB": 9, "PT": 9, "PP": 7, "PSB": 7,
    "REPUBLICANOS": 6, "PSDB": 4, "PODE": 3, "UNIAO": 3, "PDT": 2, "AVANTE": 1,
}
# Wikipedia list of current state governors.
GOV_CURRENT = {
    "PP": 4, "MDB": 2, "SOLIDARIEDADE": 1, "UNIAO": 3, "PT": 4,
    "PSB": 2, "PSD": 6, "IND": 2, "REPUBLICANOS": 2, "PL": 1,
}

GOV_HOLDERS = {
    "AC": ["gladson cameli"],
    "AL": ["paulo dantas"],
    "AP": ["clecio"],
    "AM": ["wilson lima"],
    "BA": ["jeronimo rodrigues"],
    "CE": ["elmano"],
    "DF": ["celina"],
    "ES": ["casagrande"],
    "GO": ["caiado"],
    "MA": ["brandao"],
    "MT": ["mauro mendes"],
    "MS": ["riedel"],
    "MG": ["mateus simoes"],
    "PA": ["helder barbalho"],
    "PB": ["joao azevedo"],
    "PR": ["ratinho"],
    "PE": ["raquel lyra"],
    "PI": ["rafael fonteles"],
    "RJ": ["ricardo couto"],
    "RN": ["fatima bezerra"],
    "RS": ["eduardo leite"],
    "RO": ["marcos rocha"],
    "RR": ["denarium"],
    "SP": ["tarcisio"],
    "SC": ["jorginho mello"],
    "SE": ["mitidieri"],
    "TO": ["wanderlei barbosa"],
}

# Outgoing senators (Wikipedia 2026 election table). Tokens matched against G1 urna names.
SENATE_OUTGOING = {
    "AC": ["bittar", "petecao"],
    "AL": ["eudocia", "renan"],
    "AP": ["lucas barreto", "randolfe"],
    "AM": ["eduardo braga", "plinio"],
    "BA": ["angelo coronel", "jaques wagner"],
    "CE": ["cid gomes", "reginauro"],
    "DF": ["leila", "izalci"],
    "ES": ["contarato", "marcos do val"],
    "GO": ["vanderlan", "kajuru"],
    "MA": ["eliziane", "weverton"],
    "MT": ["jayme", "favaro"],
    "MS": ["soraya", "nelsinho"],
    "MG": ["pacheco", "carlos viana"],
    "PA": ["jader", "zequinha"],
    "PB": ["veneziano", "daniella"],
    "PR": ["arns", "oriovisto"],
    "PE": ["humberto costa", "dueire"],
    "PI": ["marcelo castro", "ciro nogueira"],
    "RJ": ["portinho"],
    "RN": ["zenaide", "styvenson"],
    "RS": ["heinze", "paim"],
    "RO": ["marcos rogerio", "confucio"],
    "RR": ["roberta acioly", "chico rodrigues"],
    "SC": ["esperidiao amin", "ivete"],
    "SP": ["gabrilli", "giordano"],
    "SE": ["rogerio carvalho", "alessandro vieira"],
    "TO": ["iraja", "eduardo gomes"],
}

LI_RE = re.compile(
    r"<li>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*\(([^)]+)\)\s*-\s*(\d+)\s*-\s*"
    r"(Concorrendo|Inapto)\s*-\s*([^<]+)</li>",
    re.I,
)


def fold(text: str) -> str:
    nfd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfd if not unicodedata.combining(ch)).lower()


def strip_tags(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def canon_party(raw: str) -> str:
    raw = unescape(raw).strip()
    return PARTY_CANON.get(raw, raw)


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def fetch(url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return data.decode("utf-8", errors="replace")


def load_html(url: str, filename: str) -> str:
    dest = RAW / filename
    try:
        html = fetch(url, dest)
        print(f"fetched {url} -> {dest} ({len(html)} bytes)")
        return html
    except Exception as exc:
        if dest.exists():
            print(f"fetch failed ({exc}); using cache {dest}")
            return dest.read_text(encoding="utf-8", errors="replace")
        raise SystemExit(f"cannot fetch {url}: {exc}") from exc


def parse_g1(html: str) -> Dict[str, List[Dict[str, str]]]:
    parts = re.split(r"<h2[^>]*>", html, flags=re.I)
    out: Dict[str, List[Dict[str, str]]] = {}
    for part in parts[1:]:
        m = re.match(r"(.*?)</h2>(.*)", part, re.I | re.S)
        if not m:
            continue
        title = strip_tags(m.group(1))
        if title not in UF_BY_PT:
            continue
        code, _ko = UF_BY_PT[title]
        body = m.group(2)
        rows: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        for href, name_html, party, number, situacao, tse in LI_RE.findall(body):
            name = strip_tags(name_html)
            party_c = canon_party(party)
            tse_s = unescape(tse).strip()
            key = (name, party_c, number)
            row = {
                "name": name,
                "party": party_c,
                "number": number,
                "situacao": situacao,
                "tse": tse_s,
                "href": unescape(href),
            }
            prev = rows.get(key)
            if prev is None or (prev["situacao"] != "Concorrendo" and situacao == "Concorrendo"):
                rows[key] = row
        out[code] = list(rows.values())
    missing = [code for code, _pt, _ko in UFS if code not in out]
    if missing:
        raise SystemExit(f"G1 missing UFs: {missing}")
    return out


def name_hit(name: str, tokens: Iterable[str]) -> bool:
    n = fold(name)
    for tok in tokens:
        t = fold(tok)
        if len(t) < 5:
            continue
        if t in n:
            return True
    return False


def is_gov_incumbent(code: str, name: str) -> bool:
    return name_hit(name, GOV_HOLDERS.get(code, []))


def is_sen_incumbent(code: str, name: str) -> bool:
    return name_hit(name, SENATE_OUTGOING.get(code, []))


def cand_from_g1(row: Dict[str, str], incumbent: bool) -> Optional[Dict[str, Any]]:
    if row["situacao"] != "Concorrendo":
        return None
    notes = [f"기호 {row['number']}"]
    if row["tse"] != "Deferido":
        notes.append(f"TSE {row['tse']}")
    item: Dict[str, Any] = {
        "party_abbr": row["party"],
        "name": row["name"],
        "status": "nominated",
        "source": row["href"] or G1_GOV,
        "note_ko": ". ".join(notes) + ".",
    }
    if incumbent:
        item["incumbent"] = True
    return item


def president_district() -> Dict[str, Any]:
    wiki = WIKI_EN
    tickets = [
        ("PT", "Luiz Inácio Lula da Silva", "13", "Geraldo Alckmin (PSB)", True, wiki,
         "현직 대통령. 연맹 Brasil da Esperança + PSOL-REDE + PSB + PDT."),
        ("MISSAO", "Renan Santos", "14", "Aroldo Medina (MISSÃO)", False, wiki, None),
        ("PSTU", "Hertz Dias", "16", "Vanessa Portugal (PSTU)", False, wiki, None),
        ("PCB", "Edmilson Costa", "21", "Cleusa Santos (PCB)", False, wiki,
         "영문 위키는 Edmilson Costa. G1 2026-08-17 등록 기사는 Edmilson Dias로 적힌 곳이 있다."),
        ("PL", "Flávio Bolsonaro", "22", "Alfredo Gaspar (PL)", False, wiki, None),
        ("DC", "Clariana Barão", "27", "Fabiana Torquato (DC)", False, wiki, None),
        ("PRTB", "Leonardo Avalanche", "28", "Silvia Hellen da Silva Pereira (PRTB)", False, G1_AVALANCHE,
         "TSE 2026-09-11 Marçal 기각 뒤 PRTB 교체(G1 2026-09-15 보고·위키 각주). G1 Quem são(2026-08-19)와 위키 확정표 일부 스냅샷은 아직 Marçal."),
        ("PCO", "Rui Costa Pimenta", "29", "Antônio Carlos (PCO)", False, wiki, None),
        ("NOVO", "Romeu Zema", "30", "Eduardo Girão (NOVO)", False, wiki, None),
        ("DEMOCRATA", "Wilson Grassi", "35", "Suêd Haidar (DEMOCRATA)", False, wiki, None),
        ("PSD", "Ronaldo Caiado", "55", "Gilberto Kassab (PSD)", False, wiki, None),
        ("AVANTE", "Augusto Cury", "70", "Júlio Delgado (AVANTE)", False, wiki, None),
        ("UP", "Samara Martins", "80", "Raquel Brício (UP)", False, wiki, None),
    ]
    cands: List[Dict[str, Any]] = []
    for party, name, number, vice, inc, src, extra in tickets:
        notes = [f"기호 {number}", f"부통령 후보 {vice}"]
        if extra:
            notes.append(extra)
        row: Dict[str, Any] = {
            "party_abbr": party,
            "name": name,
            "status": "nominated",
            "source": src,
            "note_ko": ". ".join(notes) + ".",
        }
        if inc:
            row["incumbent"] = True
        cands.append(row)
    cands.append({
        "party_abbr": "PRTB",
        "name": "Pablo Marçal",
        "status": "withdrawn",
        "source": "https://www.cnnbrasil.com.br/politica/tse-rejeita-por-unanimidade-candidatura-de-pablo-marcal-a-presidencia/",
        "note_ko": "기호 28로 등록됐으나 TSE 2026-09-11 만장일치 기각(CNN). 입당 기한·이전 유죄. PRTB는 Avalanche로 교체.",
    })
    return {
        "id": "BR",
        "name_ko": "대통령",
        "group_ko": "전국",
        "seats": 1,
        "status": "nominated",
        "candidates": cands,
    }


def districts_from_g1(
    parsed: Dict[str, List[Dict[str, str]]],
    seats: int,
    incumbent_fn,
    source: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for code, pt, ko in UFS:
        cands: List[Dict[str, Any]] = []
        for row in parsed[code]:
            item = cand_from_g1(row, incumbent_fn(code, row["name"]))
            if item:
                if not item.get("source"):
                    item["source"] = source
                cands.append(item)
        out.append({
            "id": code,
            "name_ko": ko,
            "group_ko": pt,
            "seats": seats,
            "status": "nominated" if cands else "scheduled",
            "candidates": cands,
        })
    return out


def chamber_districts() -> List[Dict[str, Any]]:
    if sum(CHAMBER_SEATS.values()) != 513:
        raise SystemExit(f"chamber seats {sum(CHAMBER_SEATS.values())} != 513")
    out: List[Dict[str, Any]] = []
    for code, pt, ko in UFS:
        out.append({
            "id": code,
            "name_ko": ko,
            "group_ko": pt,
            "seats": CHAMBER_SEATS[code],
            "status": "scheduled",
            "candidates": [],
            "note_ko": (
                f"개방명부 비례 {CHAMBER_SEATS[code]}석. G1 전수 명단·TSE CSV는 이 환경에서 "
                "받지 못해 후보를 넣지 않았다(TSE CDN 403)."
            ),
        })
    return out


def parties_block(used: Iterable[str]) -> List[Dict[str, Any]]:
    used_set = set(used)
    out: List[Dict[str, Any]] = []
    for abbr, meta in PARTY_META.items():
        if abbr not in used_set:
            continue
        row: Dict[str, Any] = {"abbr": abbr}
        for k in ("name_pt", "name_ko", "name_en", "leader_ko", "note_ko"):
            if meta.get(k):
                row[k] = meta[k]
        out.append(row)
    missing = used_set - {p["abbr"] for p in out}
    if missing:
        raise SystemExit(f"PARTY_META missing {missing}")
    return out


def collect_abbrs(columns: List[Dict[str, Any]]) -> List[str]:
    used = []
    for col in columns:
        used.extend(col["current"]["by_party"])
        for dist in col["districts"]:
            for c in dist["candidates"]:
                used.append(c["party_abbr"])
    # stable unique, PARTY_META order
    seen = []
    for abbr in PARTY_META:
        if abbr in used and abbr not in seen:
            seen.append(abbr)
    extra = [a for a in used if a not in seen]
    if extra:
        raise SystemExit(f"unknown party abbr {sorted(set(extra))}")
    return seen


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
        "date": "2026-10-04",
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
    gov_html = load_html(G1_GOV, "g1_governors_2026-09-19.html")
    sen_html = load_html(G1_SEN, "g1_senate_2026-09-19.html")
    gov_parsed = parse_g1(gov_html)
    sen_parsed = parse_g1(sen_html)
    gov_d = districts_from_g1(gov_parsed, 1, is_gov_incumbent, G1_GOV)
    sen_d = districts_from_g1(sen_parsed, 2, is_sen_incumbent, G1_SEN)
    ch_d = chamber_districts()
    pres_d = [president_district()]

    n_gov = sum(len(d["candidates"]) for d in gov_d)
    n_sen = sum(len(d["candidates"]) for d in sen_d)
    if n_gov < 150:
        raise SystemExit(f"too few governor candidates: {n_gov}")
    if n_sen < 250:
        raise SystemExit(f"too few senate candidates: {n_sen}")

    columns = [
        {
            "key": "president",
            "label_ko": "대통령",
            "current": {
                "by_party": {"PT": 1},
                "total": 1,
                "as_of": AS_OF,
                "note_ko": "현직 루이스 이나시우 룰라 다 시우바(PT). 1차 과반 아니면 2026-10-25 결선.",
            },
            "contested_ko": "대통령 1인(부통령 동반). 1차 2026-10-04, 결선은 과반 미달 시 10-25.",
            "seat_note_ko": (
                "등록 13장. PRTB는 Marçal 기각 후 Avalanche. "
                "G1 Quem são(08-19)는 아직 Marçal. 하원·주지사와 같은 날 1차."
            ),
            "districts": pres_d,
        },
        {
            "key": "chamber",
            "label_ko": "연방하원",
            "current": {
                "by_party": dict(CHAMBER_CURRENT),
                "total": 513,
                "as_of": "2026-09-19",
                "note_ko": (
                    "영문 위키 2026 총선 페이지 Incumbent 2026 정당별 표. 합 513. "
                    "같은 페이지 회파 표는 UPB/FE Brasil 등 연맹 합계. "
                    f"하원 페이지 Present composition은 회파 합 514"
                    f"(UPB 100=UNIÃO 54+PP 46, PL 97)로 어긋난다. 연맹 합계는 만들지 않았다."
                ),
            },
            "contested_ko": "513석 전원. 27개 주·연방구 개방명부 비례. 결선 없음.",
            "seat_note_ko": (
                "정수: SP70 MG53 RJ46 BA39 RS31 PR30 PE25 CE22 MA18 GO17 PA17 SC16 "
                "PB12 PI10 ES10 AL9, 나머지 11개 UF 각 8 = 513. "
                "후보는 TSE 403·G1 전수 미수록이라 scheduled."
            ),
            "districts": ch_d,
        },
        {
            "key": "senate",
            "label_ko": "연방상원",
            "current": {
                "by_party": dict(SENATE_CURRENT),
                "total": 81,
                "as_of": "2026-09-19",
                "note_ko": (
                    "영문 위키 2026 총선 페이지 Incumbent 2026. 합 81. "
                    "상원 페이지 Composition은 PSD 12·PT 10·PODE 4·PSDB 3·NOVO 1 등으로 어긋난다. "
                    "같은 출처의 총선 표를 썼다."
                ),
            },
            "contested_ko": "81석 중 54석(주당 2인). 결선 없음. 유권자는 두 이름.",
            "seat_note_ko": (
                f"G1 2026-09-01(갱신 2026-09-19 08h) TSE 제공. Concorrendo {n_sen}명. "
                "Inapto·Renúncia는 빼다. Deferido com recurso·Pendente·Indeferido em prazo recursal은 넣었다."
            ),
            "districts": sen_d,
        },
        {
            "key": "governor",
            "label_ko": "주지사",
            "current": {
                "by_party": dict(GOV_CURRENT),
                "total": 27,
                "as_of": "2026-09-19",
                "note_ko": (
                    "영문 위키 List of current state governors. "
                    "PP 4(AC·DF·MS·RR) MDB 2(AL·PA) SOLIDARIEDADE 1(AP) UNIAO 3(AM·MT·RO) "
                    "PT 4(BA·CE·PI·RN) PSB 2(ES·PB) PSD 6(GO·MG·PR·PE·RS·SE) "
                    "IND 2(MA Carlos Brandão, RJ 권한대행 Ricardo Couto) "
                    "REPUBLICANOS 2(SP·TO) PL 1(SC). 4+2+1+3+4+2+6+2+2+1=27. "
                    "GO 현직 Caiado는 대선, MG Mateus Simões는 권한대행에서 당선 후보이기도 하다."
                ),
            },
            "contested_ko": "27개 주·연방구 수장. 1차 과반 아니면 2026-10-25 결선.",
            "seat_note_ko": (
                f"G1 2026-08-31(갱신 2026-09-19 08h) TSE 제공. Concorrendo {n_gov}명. "
                "Inapto는 빼다. 부주지사는 이 열에 넣지 않았다."
            ),
            "districts": gov_d,
        },
    ]
    used = collect_abbrs(columns)
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "BRA",
        "date": "2026-10-04",
        "system_id": "bra-president",
        "as_of": AS_OF,
        "sources": [
            G1_GOV,
            G1_SEN,
            G1_PRES,
            G1_PRES_TOOL,
            WIKI_EN,
            WIKI_GOV,
            WIKI_CHAMBER,
            WIKI_SENATE,
            G1_AVALANCHE,
            TSE,
        ],
        "parties": parties_block(used),
        "columns": columns,
        "note_ko": (
            "TSE dadosabertos/DivulgaCand 는 이 환경에서 HTTP 403. "
            "주지사·상원은 G1(TSE 제공) Concorrendo만. 하원 수천 명은 비움(partial). "
            "결선 이벤트 bra-2026-general-r2 는 만들지 않았다."
        ),
    }
    return compact(doc)


def main() -> None:
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    cols = {c["key"]: c for c in doc["columns"]}
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"president {len(cols['president']['districts'][0]['candidates'])}; "
        f"chamber {len(cols['chamber']['districts'])} scheduled; "
        f"senate {sum(len(d['candidates']) for d in cols['senate']['districts'])}; "
        f"governor {sum(len(d['candidates']) for d in cols['governor']['districts'])}"
    )


if __name__ == "__main__":
    main()
