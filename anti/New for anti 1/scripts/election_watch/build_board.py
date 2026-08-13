"""Build elections_board_v1.json from country seed + profiles + news tags + betting."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from election_watch.betting import fetch_us_election_markets  # noqa: E402


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile(iso3: str) -> Optional[Dict[str, Any]]:
    path = ROOT / "config" / "profiles" / f"{iso3.lower()}.json"
    if path.exists():
        return load_json(path)
    return None


def load_extracted(name: str) -> Optional[Dict[str, Any]]:
    path = ROOT / "config" / "extracted" / name
    if path.exists():
        return load_json(path)
    return None


def load_calendar(iso3: str, year: int) -> Optional[Dict[str, Any]]:
    """Authoritative year calendar under config/calendars/{iso3}_{year}.json."""
    path = ROOT / "config" / "calendars" / f"{iso3.lower()}_{year}.json"
    if path.exists():
        return load_json(path)
    return None


def resolve_events(
    *,
    iso3: str,
    year: int,
    profile: Dict[str, Any],
    seed_country: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Prefer calendars/*.json, then profile.elections, then country_seed."""
    cal = load_calendar(iso3, year)
    if cal and isinstance(cal.get("events"), list):
        events = list(cal["events"])
    else:
        events = list(
            (profile.get("elections") or {}).get(f"events_{year}")
            or (profile.get("elections") or {}).get("events_2026")
            or seed_country.get(f"events_{year}")
            or seed_country.get("events_2026")
            or []
        )
    # Keep dated events for this year, plus undated / 없음·불명 markers.
    # Prior-year party_leadership that still defines the incumbent may carry forward.
    out: List[Dict[str, Any]] = []
    for e in events:
        date = e.get("date")
        if date is None or date in {"", "없음", "불명"}:
            out.append(e)
        elif str(date).startswith(str(year)):
            out.append(e)
        elif any(str(x).startswith(str(year)) for x in (e.get("date_span") or [])):
            out.append(e)
        elif e.get("type") == "party_leadership" and (
            e.get("carry_forward_incumbent")
            or year in (e.get("board_include_years") or [])
        ):
            out.append(e)
    return out


def build_board(
    *,
    seed_path: Optional[Path] = None,
    ticker_path: Optional[Path] = None,
    betting_cfg_path: Optional[Path] = None,
    year: Optional[int] = None,
    fetch_betting: bool = True,
) -> Dict[str, Any]:
    seed = load_json(seed_path or (ROOT / "config" / "country_seed.json"))
    spectrum_path = ROOT / "config" / "spectrum_rules.json"
    spectrum_rules = load_json(spectrum_path) if spectrum_path.exists() else {}
    year = year or int(seed.get("year") or datetime.now(timezone.utc).year)
    polls_doc = load_extracted("governance_polls.json") or {}
    usa_congress = load_extracted("usa_congress.json") or {}
    usa_gov = load_extracted("usa_governors.json") or {}
    usa_state_legs = load_extracted("usa_state_legislatures.json") or {}
    jpn_shugiin = load_extracted("jpn_shugiin.json") or {}
    jpn_gov = load_extracted("jpn_governors.json") or {}
    gbr_commons = load_extracted("gbr_commons.json") or {}
    isr_knesset = load_extracted("isr_knesset.json") or {}
    deu_bundestag = load_extracted("deu_bundestag.json") or {}
    fra_assemblee = load_extracted("fra_assemblee.json") or {}
    bra_congress = load_extracted("bra_congress.json") or {}
    rus_duma = load_extracted("rus_duma.json") or {}
    kor_assembly = load_extracted("kor_assembly.json") or {}
    kor_local = load_extracted("kor_local_2026.json") or {}
    kor_party_lead = load_extracted("kor_party_leadership.json") or {}
    extract_summary = load_extracted("summary.json") or {}
    learning_analysis = load_extracted("learning_analysis_v1.json") or {}
    factions_board = load_extracted("factions_board.json") or {}

    live_news: List[Dict[str, Any]] = []
    if ticker_path and Path(ticker_path).exists():
        ticker = load_json(Path(ticker_path))
        for it in ticker.get("items", []):
            cat = it.get("category")
            if cat in {"election", "cabinet_reshuffle"} or it.get("election_type"):
                live_news.append(
                    {
                        "title": (it.get("title") or {}).get("ko")
                        or (it.get("title") or {}).get("original"),
                        "url": it.get("url"),
                        "election_type": it.get("election_type"),
                        "category": cat,
                        "country_tier": it.get("country_tier"),
                        "info_grade": it.get("info_grade"),
                        "importance": (it.get("scores") or {}).get("importance"),
                        "source_region": (it.get("source") or {}).get("region"),
                        "published_at": it.get("published_at"),
                    }
                )

    countries_out = []
    for c in seed.get("countries", []):
        iso3 = c.get("iso3") or ""
        profile = load_profile(iso3) or {}
        system = profile.get("system") or c.get("system", "presidential")
        parties = list(profile.get("parties") or c.get("parties_tracked") or [])
        if system == "presidential":
            parties = parties[:2]
        elif system != "other":
            parties = parties[:4]
        # Prefer abbr for UI labels (e.g. LDP not 자민당)
        for p in parties:
            if p.get("abbr"):
                p["display"] = p["abbr"]
            elif p.get("name_en"):
                p["display"] = p["name_en"]
            else:
                p["display"] = p.get("name_ko") or p.get("id")

        events = resolve_events(iso3=iso3, year=year, profile=profile, seed_country=c)
        cal = load_calendar(iso3, year)

        head = profile.get("head")
        map_spectrum = profile.get("map_spectrum")
        if not map_spectrum and head:
            map_spectrum = head.get("spectrum")
        if not map_spectrum and parties:
            pid = (head or {}).get("party_id") or parties[0].get("id")
            key = f"{iso3}:{pid}"
            map_spectrum = (spectrum_rules.get("by_party") or {}).get(key, {}).get("spectrum")

        row: Dict[str, Any] = {
            "iso3": iso3,
            "name_ko": c.get("name_ko"),
            "priority_tier": profile.get("priority_tier") or c.get("priority_tier"),
            "region": profile.get("region") or c.get("region"),
            "system": system,
            "map_spectrum": map_spectrum,
            "head": head,
            "ruling_party": c.get("ruling_party")
            or next((p for p in parties if p.get("role") in {"ruling", "major_1"}), None),
            "parties_tracked": parties,
            "legislature": profile.get("legislature"),
            "subnational": profile.get("subnational"),
            "polls": profile.get("polls"),
            "events": events,
            "events_this_year": len(events),
            "ingest_mode": (profile.get("ingest") or {}).get("mode")
            or ("document_text_extract" if profile.get("document_ingest") else None),
        }
        if cal:
            row["calendar"] = {
                "as_of": cal.get("as_of"),
                "sources": cal.get("sources"),
                "notes": cal.get("notes"),
                "null_policy": cal.get("null_policy"),
            }
        if profile.get("mode"):
            row["mode"] = profile["mode"]
        if profile.get("regime"):
            row["regime"] = profile["regime"]
        # Tier-3 / non-electoral briefs: power card + optional emirates list
        if profile.get("power"):
            row["power"] = profile["power"]
        if profile.get("emirates"):
            row["emirates"] = profile["emirates"]
        if profile.get("document_ingest"):
            row["document_ingest"] = {
                "catalog": profile["document_ingest"].get("catalog"),
                "extract_file": profile["document_ingest"].get("extract_file"),
                "workspace_pdf_found": profile["document_ingest"].get("workspace_pdf_found"),
                "press_index": profile["document_ingest"].get("press_index"),
                "slots": profile["document_ingest"].get("slots"),
                "done": profile["document_ingest"].get("done"),
                "todo": profile["document_ingest"].get("todo"),
            }
        if iso3 == "USA":
            row["legislature_live"] = {
                "summary": usa_congress.get("summary"),
                "floor_leadership": usa_congress.get("floor_leadership"),
                "source": (usa_congress.get("source") or {}),
            }
            row["subnational_live"] = {
                "governors_summary": usa_gov.get("summary"),
                "governors": usa_gov.get("governors"),
                "state_legislatures_summary": usa_state_legs.get("summary"),
                "state_legislatures": usa_state_legs.get("states"),
                "source": {
                    "governors": usa_gov.get("source"),
                    "state_legislatures": usa_state_legs.get("source"),
                },
            }
            row["factions"] = factions_board.get("USA") or {
                "senate_factions": "없음",
                "parties": {},
                "note": "불명 — factions_board.json 미생성",
            }
            usa_rp = load_extracted("race_progress_usa_v1.json")
            if usa_rp:
                row["race_progress"] = usa_rp
        if iso3 == "JPN":
            row["legislature_live"] = {
                "shugiin_members": (jpn_shugiin.get("summary") or {}).get("members"),
                "shugiin_by_party_abbr": (jpn_shugiin.get("summary") or {}).get("by_party_abbr"),
                "house_composition_wikipedia": (jpn_shugiin.get("house_composition") or {}).get("by_abbr"),
                "sangiin_by_abbr": (jpn_shugiin.get("sangiin_composition") or {}).get("by_abbr"),
                "sangiin_rows": (jpn_shugiin.get("sangiin_composition") or {}).get("rows"),
                "source": jpn_shugiin.get("source"),
            }
            row["subnational_live"] = {
                "summary": jpn_gov.get("summary"),
                "governors": jpn_gov.get("governors"),
                "source": jpn_gov.get("source"),
            }
            row["factions"] = factions_board.get("JPN") or {
                "party_abbr": "LDP",
                "factions": [],
                "other_parties_factions": "없음",
                "note": "불명 — factions_board.json 미생성",
            }
        if iso3 == "GBR":
            row["legislature_live"] = {
                "summary": gbr_commons.get("summary"),
                "parties": gbr_commons.get("parties"),
                "floor_leadership": gbr_commons.get("floor_leadership"),
                "source": gbr_commons.get("source"),
            }
        if iso3 == "ISR":
            row["legislature_live"] = {
                "summary": isr_knesset.get("summary"),
                "parties": isr_knesset.get("parties"),
                "floor_leadership": isr_knesset.get("floor_leadership"),
                "source": isr_knesset.get("source"),
            }
        if iso3 == "DEU":
            row["legislature_live"] = {
                "summary": deu_bundestag.get("summary"),
                "parties": deu_bundestag.get("parties"),
                "floor_leadership": deu_bundestag.get("floor_leadership"),
                "source": deu_bundestag.get("source"),
            }
        if iso3 == "FRA":
            row["legislature_live"] = {
                "summary": fra_assemblee.get("summary"),
                "parties": fra_assemblee.get("parties"),
                "floor_leadership": fra_assemblee.get("floor_leadership"),
                "source": fra_assemblee.get("source"),
            }
        if iso3 == "BRA":
            row["legislature_live"] = {
                "summary": bra_congress.get("summary"),
                "chamber_of_deputies": bra_congress.get("chamber_of_deputies"),
                "senate": bra_congress.get("senate"),
                "floor_leadership": bra_congress.get("floor_leadership"),
                "source": bra_congress.get("source"),
            }
        if iso3 == "RUS":
            row["legislature_live"] = {
                "summary": rus_duma.get("summary"),
                "parties": rus_duma.get("parties"),
                "floor_leadership": rus_duma.get("floor_leadership"),
                "source": rus_duma.get("source"),
                "confidence": rus_duma.get("confidence") or "approximate_pre_election",
            }
        if iso3 == "KOR":
            row["legislature_live"] = {
                "summary": kor_assembly.get("summary"),
                "parties": kor_assembly.get("parties"),
                "floor_leadership": kor_assembly.get("floor_leadership"),
                "composition_date": kor_assembly.get("composition_date"),
                "source": kor_assembly.get("source"),
            }
            if kor_local:
                row["subnational_live"] = {
                    "summary": kor_local.get("summary"),
                    "highlights": kor_local.get("highlights"),
                    "source": kor_local.get("source"),
                }
            if kor_party_lead:
                row["party_leadership_live"] = {
                    "as_of": kor_party_lead.get("as_of_date") or kor_party_lead.get("as_of"),
                    "policy": kor_party_lead.get("policy"),
                    "parties": kor_party_lead.get("parties"),
                    "source": kor_party_lead.get("source"),
                }
            kor_rp = load_extracted("race_progress_kor_v1.json")
            if kor_rp:
                row["race_progress"] = kor_rp
            if profile.get("prime_minister"):
                row["prime_minister"] = profile["prime_minister"]
        # attach governance polls for this country
        series = [
            s
            for s in (polls_doc.get("series") or [])
            if s.get("iso3") == iso3
        ]
        if series:
            row["governance_polls"] = series
        if iso3 == "CHN":
            pla_path = ROOT / "config" / "china_leadership_extracted.json"
            bios = load_extracted("china_pla_bios.json") or {}
            if not bios:
                bios_alt = ROOT / "config" / "china_pla_bios.json"
                if bios_alt.exists():
                    bios = load_json(bios_alt)
            if pla_path.exists():
                pla = load_json(pla_path)
                row["pla"] = {
                    "as_of": pla.get("as_of"),
                    "source_primary": pla.get("source_primary"),
                    "theater_commands": pla.get("theater_commands"),
                    "cmc_members_mentioned": (pla.get("cmc") or {}).get("members_mentioned"),
                    "bios": {
                        "count": bios.get("count"),
                        "method": bios.get("method"),
                        "null_policy": bios.get("null_policy"),
                        "산둥성_출신_확인": bios.get("산둥성_출신_확인"),
                        "figures": bios.get("figures"),
                    }
                    if bios
                    else None,
                }
        if iso3 == "RUS":
            row["mode"] = profile.get("mode") or c.get("mode") or "managed_elections_document_extract"
        # Ensure mode from seed for tier-3 stubs without profile fields missing
        if not row.get("mode") and c.get("mode"):
            row["mode"] = c["mode"]
        countries_out.append(row)

    countries_out.sort(
        key=lambda x: (
            x.get("priority_tier") or 99,
            -x["events_this_year"],
            x.get("name_ko") or x.get("iso3") or "",
        )
    )

    betting_block: Dict[str, Any] = {
        "enabled": False,
        "markets": [],
        "note": "skipped",
    }
    if fetch_betting:
        bcfg = load_json(betting_cfg_path or (ROOT / "config" / "betting.json"))
        poly = bcfg.get("polymarket") or {}
        betting_block = fetch_us_election_markets(
            queries=list(poly.get("queries") or []),
            max_markets=int(poly.get("max_markets", 12)),
            timeout=float(poly.get("timeout_sec", 18)),
            enabled=bool(bcfg.get("enabled", True)),
        )
        betting_block["ticker_hints"] = [
            {
                "event_type": "election_betting",
                "question": m.get("question"),
                "url": m.get("url"),
                "top_outcome": (m.get("outcomes") or [{}])[0] if m.get("outcomes") else None,
            }
            for m in (betting_block.get("markets") or [])[:5]
        ]

    return {
        "schema_version": "elections-board-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "model": {
            "name": "election_watch_doc_extract_v1",
            "description": (
                "World election board from curated profiles + document/text extract "
                "(not numeric timeseries paint). Map color = head.spectrum. "
                "Governance approval polls only; US floor leadership; JP LDP factions; "
                "CN via DoD CMPR / Two Sessions docs."
            ),
            "learning_doc": "LEARNING.md",
            "learning_analysis": "config/extracted/learning_analysis_v1.json",
            "human_labels": "config/extracted/human_labels.jsonl",
            "leadership_policy": seed.get("leadership_policy"),
            "spectrum_rules": spectrum_rules.get("map_rule"),
            "polls": {"reject_horserace": True, "admit_governance": True},
            "betting_source": "polymarket",
        },
        "summary": {
            "countries": len(countries_out),
            "countries_with_head": sum(1 for c in countries_out if c.get("head")),
            "countries_with_map_spectrum": sum(1 for c in countries_out if c.get("map_spectrum")),
            "countries_with_events": sum(1 for c in countries_out if c["events_this_year"] > 0),
            "countries_with_governance_polls": sum(
                1 for c in countries_out if c.get("governance_polls")
            ),
            "countries_with_legislature_live": sum(
                1 for c in countries_out if c.get("legislature_live")
            ),
            "countries_with_race_progress": sum(
                1 for c in countries_out if c.get("race_progress")
            ),
            "live_election_headlines": len(live_news),
            "betting_markets": len(betting_block.get("markets") or []),
            "extract_summary": extract_summary,
            "learning": {
                "depth_buckets": (learning_analysis.get("aggregate") or {}),
                "next_queue": (learning_analysis.get("next_learning_queue") or [])[:5],
                "as_of": learning_analysis.get("as_of"),
            },
        },
        "countries": countries_out,
        "live_election_news": live_news[:40],
        "betting_markets": betting_block,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "elections_board_v1.json",
    )
    p.add_argument(
        "--ticker",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "ticker_v1.json",
    )
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--no-betting", action="store_true")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    doc = build_board(ticker_path=args.ticker, year=args.year, fetch_betting=not args.no_betting)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.print_stats:
        print(doc["summary"])
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
