"""Build DEU/FRA/BRA legislature extracts (curated from official/aggregators) + scaffold wave countries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "extracted"
OUT.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(name: str, doc: Dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def deu_bundestag() -> Dict[str, Any]:
    # Final 2025 Bundestag result (21st Bundestag) — still current in 2026; no federal election 2026.
    parties = [
        {"abbr": "CDU", "name_en": "CDU", "seats": 164},
        {"abbr": "AfD", "name_en": "AfD", "seats": 152},
        {"abbr": "SPD", "name_en": "SPD", "seats": 120},
        {"abbr": "Grüne", "name_en": "Alliance 90/The Greens", "seats": 85},
        {"abbr": "Linke", "name_en": "The Left", "seats": 64},
        {"abbr": "CSU", "name_en": "CSU", "seats": 44},
        {"abbr": "SSW", "name_en": "SSW", "seats": 1},
    ]
    by = {p["abbr"]: p["seats"] for p in parties}
    by["CDU/CSU"] = by["CDU"] + by["CSU"]
    return {
        "as_of": now_iso(),
        "source": {
            "id": "bundeswahlleiterin_2025_final",
            "url": "https://www.bundeswahlleiterin.de/en/info/presse/mitteilungen/bundestagswahl-2025/29_25_endgueltiges-ergebnis.html",
            "org": "Die Bundeswahlleiterin",
            "grade": "official",
            "note": "21st Bundestag final seat matrix after 2025 snap election; 2026 no federal general.",
        },
        "summary": {
            "chamber": "bundestag",
            "seats_total": 630,
            "by_party_abbr": by,
            "union_faction_cdu_csu": by["CDU/CSU"],
            "election_basis": "2025-02",
        },
        "parties": parties,
        "floor_leadership": [
            {
                "office": "chancellor",
                "name": "Friedrich Merz",
                "party_abbr": "CDU",
                "source": "https://www.bundeskanzler.de/",
            },
            {
                "office": "largest_opposition_group",
                "name": "불명",
                "party_abbr": "AfD",
                "note": "AfD 2nd-largest Fraktion by seats; parliamentary floor roles separate from chancellor.",
            },
        ],
    }


def fra_assemblee() -> Dict[str, Any]:
    # Parliamentary groups as of 2026-05-28 (Wikipedia model table for 17th legislature)
    groups = [
        {"abbr": "RN", "name_en": "Rassemblement national", "seats": 122, "position": "opposition"},
        {"abbr": "EPR", "name_en": "Ensemble pour la République", "seats": 91, "position": "presidential_group"},
        {"abbr": "LFI-NFP", "name_en": "La France insoumise – NFP", "seats": 71, "position": "opposition"},
        {"abbr": "SOC", "name_en": "Socialistes et apparentés", "seats": 68, "position": "opposition"},
        {"abbr": "DR", "name_en": "Droite républicaine", "seats": 48, "position": "minority"},
        {"abbr": "EcoS", "name_en": "Écologiste et social", "seats": 38, "position": "opposition"},
        {"abbr": "Dem", "name_en": "Les Démocrates", "seats": 37, "position": "allied_center"},
        {"abbr": "HOR", "name_en": "Horizons & Indépendants", "seats": 34, "position": "allied_center"},
        {"abbr": "LIOT", "name_en": "LIOT", "seats": 23, "position": "opposition"},
        {"abbr": "GDR", "name_en": "Gauche démocrate et républicaine", "seats": 17, "position": "opposition"},
        {"abbr": "UDR", "name_en": "Union des droites pour la République", "seats": 17, "position": "opposition"},
        {"abbr": "NI", "name_en": "Non-inscrits", "seats": 11, "position": "other"},
    ]
    by = {g["abbr"]: g["seats"] for g in groups}
    # Rough presidential-lean bloc: EPR + Dem + HOR
    bloc = by["EPR"] + by["Dem"] + by["HOR"]
    return {
        "as_of": now_iso(),
        "source": {
            "id": "wiki_an_groupes_17_2026-05-28",
            "url": "https://fr.wikipedia.org/wiki/Mod%C3%A8le:Groupes_parlementaires_de_l'Assembl%C3%A9e_nationale_fran%C3%A7aise_(Cinqui%C3%A8me_R%C3%A9publique),_17",
            "grade": "aggregator_wikipedia",
            "as_of_table": "2026-05-28",
            "cross_check": "https://www.assemblee-nationale.fr/",
            "note": "Group seats drift; refresh against AN composition page periodically.",
        },
        "summary": {
            "chamber": "assemblee_nationale",
            "legislature": 17,
            "seats_total": 577,
            "by_group_abbr": by,
            "presidential_center_bloc_EPR_Dem_HOR": bloc,
            "seats_sum": sum(by.values()),
        },
        "parties": groups,
        "floor_leadership": [
            {
                "office": "president_of_republic",
                "name": "Emmanuel Macron",
                "party_abbr": "EPR",
                "note": "Head of state; Assembly is hung/no single majority.",
            },
            {
                "office": "prime_minister",
                "name": "불명",
                "note": "Matignon turnover frequent after 2024 hung parliament — fill from JORF when next extract.",
            },
        ],
    }


def bra_congress() -> Dict[str, Any]:
    chamber = [
        {"abbr": "PL", "seats": 97},
        {"abbr": "PT", "seats": 64},
        {"abbr": "UNIÃO", "seats": 52},
        {"abbr": "PSD", "seats": 48},
        {"abbr": "PP", "seats": 46},
        {"abbr": "Republicanos", "seats": 42},
        {"abbr": "MDB", "seats": 38},
        {"abbr": "Podemos", "seats": 27},
        {"abbr": "PSDB", "seats": 18},
        {"abbr": "PSB", "seats": 17},
        {"abbr": "PSOL", "seats": 13},
        {"abbr": "PCdoB", "seats": 11},
        {"abbr": "PDT", "seats": 9},
        {"abbr": "PV", "seats": 6},
        {"abbr": "Avante", "seats": 5},
        {"abbr": "Novo", "seats": 5},
        {"abbr": "Solidariedade", "seats": 4},
        {"abbr": "Rede", "seats": 3},
        {"abbr": "PRD", "seats": 3},
        {"abbr": "Cidadania", "seats": 2},
        {"abbr": "Missão", "seats": 1},
        {"abbr": "DC", "seats": 1},
    ]
    senate = [
        {"abbr": "PL", "seats": 16},
        {"abbr": "PSD", "seats": 14},
        {"abbr": "MDB", "seats": 9},
        {"abbr": "PT", "seats": 9},
        {"abbr": "PP", "seats": 7},
        {"abbr": "PSB", "seats": 7},
        {"abbr": "Republicanos", "seats": 6},
        {"abbr": "Podemos", "seats": 3},
        {"abbr": "PSDB", "seats": 3},
        {"abbr": "UNIÃO", "seats": 3},
        {"abbr": "PDT", "seats": 2},
        {"abbr": "Novo", "seats": 1},
        {"abbr": "Avante", "seats": 1},
    ]
    return {
        "as_of": now_iso(),
        "source": {
            "id": "forte_congress_2026-07-30",
            "url": "https://www.forte.jor.br/2026/07/30/congresso-nacional-chega-as-eleicoes-de-2026-com-poder-pulverizado-entre-22-partidos/",
            "grade": "media_cross_check",
            "note": "Pre-election 2026 midyear bank counts; TSE open data supersedes when wired.",
            "tse": "https://dadosabertos.tse.jus.br/",
        },
        "summary": {
            "chamber_deputies_nominal": 513,
            "chamber_seats_listed": sum(p["seats"] for p in chamber),
            "senate_total": 81,
            "senate_seats_listed": sum(p["seats"] for p in senate),
            "chamber_by_abbr": {p["abbr"]: p["seats"] for p in chamber},
            "senate_by_abbr": {p["abbr"]: p["seats"] for p in senate},
            "largest_chamber": "PL",
            "ruling_party_pt_chamber": 64,
        },
        "chamber_of_deputies": chamber,
        "senate": senate,
        "floor_leadership": [
            {
                "office": "president",
                "name": "Luiz Inácio Lula da Silva",
                "party_abbr": "PT",
            },
            {
                "office": "president_chamber",
                "name": "Hugo Motta",
                "party_abbr": "Republicanos",
                "confidence": "medium",
                "note": "Named on National Congress page cross-check 2025–26 session — verify after 2026 election.",
            },
            {
                "office": "president_senate",
                "name": "Davi Alcolumbre",
                "party_abbr": "UNIÃO",
                "confidence": "medium",
            },
        ],
    }


def rus_duma_light() -> Dict[str, Any]:
    # Pre-Sept 2026 Duma 8th convocation approximate current seats (wiki earlier extract); full CIKRF later
    parties = [
        {"abbr": "UR", "name_en": "United Russia", "seats": 310},
        {"abbr": "CPRF", "name_en": "CPRF", "seats": 56},
        {"abbr": "SR", "name_en": "A Just Russia", "seats": 27},
        {"abbr": "LDPR", "name_en": "LDPR", "seats": 22},
        {"abbr": "NL", "name_en": "New People", "seats": 15},
    ]
    return {
        "as_of": now_iso(),
        "source": {
            "id": "wiki_duma_pre_2026",
            "grade": "aggregator_approximate",
            "note": "8th Duma seat snapshot before 2026-09 election; replace with CIKRF after vote.",
            "url": "https://en.wikipedia.org/wiki/2026_Russian_legislative_election",
        },
        "summary": {
            "chamber": "state_duma",
            "convocation": 8,
            "seats_total_nominal": 450,
            "by_party_abbr": {p["abbr"]: p["seats"] for p in parties},
            "seats_listed": sum(p["seats"] for p in parties),
            "note": "listed < 450 — independents/others 불명 in this light pass",
        },
        "parties": parties,
        "floor_leadership": [
            {"office": "president", "name": "Vladimir Putin", "party_abbr": "UR"},
            {
                "office": "state_duma_chair",
                "name": "Vyacheslav Volodin",
                "party_abbr": "UR",
                "confidence": "medium",
            },
        ],
    }


def merge_polls() -> Dict[str, Any]:
    path = OUT / "governance_polls.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"series": []}
    # drop prior DEU/FRA/BRA to re-append clean
    series = [s for s in doc.get("series") or [] if s.get("iso3") not in {"DEU", "FRA", "BRA", "KOR"}]
    # keep existing KOR if any and re-add updated
    series = [s for s in series if s.get("iso3") != "KOR"]
    series.extend(
        [
            {
                "iso3": "KOR",
                "kind": "presidential_job_approval",
                "subject": "Lee Jae Myung",
                "pollster": "Gallup Korea (via Yonhap / prior series)",
                "approve_pct": 54,
                "field_note": "Earlier 2026 snapshot; Carnegie notes mid-2026 dip below 50% after local elections — refresh soon.",
                "sources": [
                    {
                        "url": "https://en.yna.co.kr/view/AEN20260703004600315",
                        "label": "Yonhap/Gallup Korea ~54%",
                    }
                ],
                "confidence": "medium",
            },
            {
                "iso3": "DEU",
                "kind": "chancellor_approval",
                "subject": "Friedrich Merz",
                "pollster": "불명",
                "approve_pct": None,
                "field_note": "Series slot reserved; no single canonical series wired yet.",
                "sources": [],
                "confidence": "low",
                "status": "todo",
            },
            {
                "iso3": "FRA",
                "kind": "presidential_job_approval",
                "subject": "Emmanuel Macron",
                "pollster": "불명",
                "approve_pct": None,
                "status": "todo",
                "field_note": "Hung assembly era — wire Ifop/Elabe later.",
                "confidence": "low",
            },
            {
                "iso3": "BRA",
                "kind": "presidential_job_approval",
                "subject": "Lula",
                "pollster": "불명",
                "approve_pct": None,
                "status": "todo",
                "field_note": "Datafolha/Quaest series wire later; horserace rejected.",
                "confidence": "low",
            },
        ]
    )
    return {
        "as_of": now_iso(),
        "policy": {
            "admit": [
                "presidential_job_approval",
                "cabinet_approval",
                "pm_approval",
                "pm_preferred",
                "chancellor_approval",
            ],
            "reject": ["national_horserace_headline"],
        },
        "series": series,
    }


def main() -> int:
    deu = deu_bundestag()
    fra = fra_assemblee()
    bra = bra_congress()
    rus = rus_duma_light()
    polls = merge_polls()
    write("deu_bundestag.json", deu)
    write("fra_assemblee.json", fra)
    write("bra_congress.json", bra)
    write("rus_duma.json", rus)
    write("governance_polls.json", polls)

    summary_path = OUT / "summary.json"
    summary: Dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["generated_at"] = now_iso()
    summary["deu"] = {
        "bundestag_by_abbr": deu["summary"]["by_party_abbr"],
        "seats_total": deu["summary"]["seats_total"],
    }
    summary["fra"] = {
        "assemblee_by_group": fra["summary"]["by_group_abbr"],
        "presidential_bloc": fra["summary"]["presidential_center_bloc_EPR_Dem_HOR"],
    }
    summary["bra"] = {
        "chamber_by_abbr_top": dict(list(bra["summary"]["chamber_by_abbr"].items())[:8]),
        "senate_by_abbr_top": dict(list(bra["summary"]["senate_by_abbr"].items())[:6]),
    }
    summary["rus"] = rus["summary"]
    summary["polls"] = {
        "series": [
            {
                "iso3": s["iso3"],
                "kind": s["kind"],
                "approve_pct": s.get("approve_pct"),
                "status": s.get("status"),
            }
            for s in polls["series"]
        ]
    }
    write("summary.json", summary)
    print(
        json.dumps(
            {
                "deu_total": deu["summary"]["seats_total"],
                "fra_sum": fra["summary"]["seats_sum"],
                "bra_chamber": bra["summary"]["chamber_seats_listed"],
                "rus_listed": rus["summary"]["seats_listed"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
