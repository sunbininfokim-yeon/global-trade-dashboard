#!/usr/bin/env python3
"""Build public/data/election_records/<ISO3>.json for the country 선거 card.

One file per country, offices in the order the card reads them:
executive (president / prime minister) -> legislature (each chamber) -> local.
Each office carries the last election (date, turnout, rounds with candidates
or seats), earlier ones, the next scheduled one and the office's term.

Inputs, weakest first -- a later input replaces a record with the same
election_id, field by field:

1. public/data/elections_system_v1.json      offices, term length, method, runoff rule
2. public/data/elections_board_v1.json       events: result / winner / previous / status / date
3. public/data/elections_contests/*.json     candidate vote counts for single-seat contests
4. config/election_records/<iso3>.json       researched records (contract:
                                             docs/ops/ELECTION_RECORDS_REQUEST_20261107.md)

Nothing here estimates a number. Vote shares are only computed when the
contest file gives vote counts, and the record says so (vote_pct_basis).

    python3 build_election_records.py          # write
    python3 build_election_records.py --check  # fail if the published files differ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parents[1] / "public" / "data"
CONFIG = ROOT / "config" / "election_records"
TARGET = DATA / "election_records"
DATE_FULL = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UPCOMING = {"scheduled", "tentative", "ongoing"}
# 대통령선거급 쟁점을 조사해 붙이는 나라 (사용자 지시 2026-11-07).
ISSUE_COUNTRIES = ["USA", "JPN", "KOR", "TWN", "DEU", "GBR", "FRA", "ESP", "IND", "BRA"]
OFFICE_ORDER = {"executive": 0, "legislature": 1, "local": 2}


def load(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def urls(value) -> list[str]:
    out = []
    for item in value or []:
        url = item.get("url") if isinstance(item, dict) else item
        if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out


def office_key(system: dict) -> str:
    kind = system.get("type")
    if kind == "presidential":
        return "executive"
    if kind == "local":
        return "local"
    return "legislature"


def offices_for(iso3: str, systems: list[dict]) -> list[dict]:
    """Offices from the electoral systems table, plus a prime-minister office
    for countries whose head of government comes out of a chamber."""
    offices = []
    for system in systems:
        if system.get("type") == "by_election":
            continue
        key = office_key(system)
        offices.append({
            "key": key,
            "system_id": system["id"],
            "title_ko": system.get("name_ko"),
            "chamber": None if system.get("chamber") in (None, "없음") else system.get("chamber"),
            "elected_how": "direct" if key != "legislature" or system.get("type") == "general" else None,
            "term_years": system.get("term_years"),
            "seats_total": system.get("seats_total"),
            "method_ko": system.get("method_ko"),
            "runoff_rule_ko": None if system.get("runoff_rule_ko") in (None, "없음") else system.get("runoff_rule_ko"),
            "head_selection_ko": None if system.get("head_selection_ko") in (None, "없음") else system.get("head_selection_ko"),
            "records": [],
            "next": None,
        })
    if not any(o["key"] == "executive" for o in offices):
        # 의원내각제: 행정수반은 따로 뽑지 않는다. 그를 낳는 의회 선거를 가리킨다.
        source = next((o for o in offices if o["key"] == "legislature"
                       and re.search(r"총리|수상|Chancellor|Kanzler|First Minister", o.get("head_selection_ko") or "")), None)
        if source:
            offices.append({
                "key": "executive",
                "system_id": None,
                "title_ko": "총리(행정수반)",
                "chamber": None,
                "elected_how": "by_legislature",
                "selected_by_system_id": source["system_id"],
                "term_years": None,
                "method_ko": source["head_selection_ko"],
                "records": [],
                "next": None,
            })
    offices.sort(key=lambda o: (OFFICE_ORDER[o["key"]], o["system_id"] or ""))
    return offices


def match_office(offices: list[dict], event: dict) -> dict | None:
    sid = event.get("system_id")
    for office in offices:
        if sid and office["system_id"] == sid:
            return office
    kind = event.get("type")
    chamber = event.get("chamber")
    if kind == "presidential":
        return next((o for o in offices if o["key"] == "executive" and o["system_id"]), None)
    if kind in ("general", "by_election"):
        same = [o for o in offices if o["key"] == "legislature" and chamber and o["chamber"] == chamber]
        if same:
            return same[0]
        legislature = [o for o in offices if o["key"] == "legislature"]
        return legislature[0] if len(legislature) == 1 else None
    if kind == "local":
        local = [o for o in offices if o["key"] == "local"]
        return local[0] if len(local) == 1 else None
    return None


def text(value):
    return value if isinstance(value, str) and value.strip() and value not in ("없음", "불명") else None


def winner_ko(value):
    if isinstance(value, dict):
        return " · ".join(x for x in [value.get("name_ko") or value.get("name_en"), value.get("party")] if x) or None
    return text(value)


def record_from_event(event: dict) -> dict:
    return {
        "election_id": event["id"],
        "date": event["date"],
        "label_ko": event.get("label_ko"),
        "status": event.get("status"),
        "round": 2 if re.search(r"-r2$|runoff|결선", event["id"] + (event.get("label_ko") or "")) else 1,
        "summary_ko": text(event.get("result")),
        "detail_ko": text(event.get("result_summary")),
        "winner_ko": winner_ko(event.get("winner")),
        "contested_ko": text(event.get("contested_ko")),
        "sources": urls(event.get("sources")),
        "origin": "board_event",
    }


def record_from_previous(event: dict) -> dict | None:
    prev = event.get("previous")
    if not isinstance(prev, dict) or not DATE_FULL.match(str(prev.get("date") or "")):
        return None
    seats = [{
        "party": row.get("abbr"),
        "party_ko": row.get("name_ko"),
        "seats": row.get("seats"),
        "vote_pct": row.get("vote_pct"),
    } for row in prev.get("by_party") or []]
    return {
        "election_id": f"{event['id']}:previous",
        "date": prev["date"],
        "label_ko": None,
        "status": "completed",
        "turnout_pct": prev.get("turnout_pct"),
        "seats_total": prev.get("seats_total"),
        "seats": seats,
        "sources": urls(prev.get("sources")),
        "origin": "board_previous",
    }


def contest_candidates(contest: dict) -> list[dict] | None:
    """Candidates of a single-seat national contest, with vote counts."""
    for column in contest.get("columns") or []:
        districts = column.get("districts") or []
        if len(districts) != 1:
            continue
        rows = [c for c in districts[0].get("candidates") or [] if isinstance(c.get("votes"), (int, float))]
        if len(rows) < 2:
            continue
        total = sum(c["votes"] for c in rows)
        rows.sort(key=lambda c: -c["votes"])
        return [{
            "name": c.get("name_ko") or c.get("name"),
            "party": c.get("party_abbr"),
            "votes": c["votes"],
            "vote_pct": round(c["votes"] * 100 / total, 2) if total else None,
            "elected": c.get("elected"),
            "incumbent": c.get("incumbent") or None,
        } for c in rows]
    return None


def final_winner(rec: dict) -> str | None:
    """Winner of a runoff: the elected candidate, else the runoff's own winner line.
    Never the first round's line -- that names the two finalists, not a winner."""
    for cand in rec.get("candidates") or []:
        if cand.get("elected"):
            return " · ".join(x for x in (cand.get("name"), cand.get("party")) if x)
    return rec.get("winner_ko")


def merge_rounds(records: list[dict]) -> list[dict]:
    """A first round and its runoff on the same office become one record."""
    records.sort(key=lambda r: r["date"])
    out: list[dict] = []
    for rec in records:
        prev = out[-1] if out else None
        if (prev and rec.get("round") == 2 and prev.get("round", 1) == 1 and not prev.get("rounds_merged")
                and (date.fromisoformat(rec["date"]) - date.fromisoformat(prev["date"])).days <= 60):
            first = {k: prev.get(k) for k in ("date", "summary_ko", "detail_ko", "winner_ko", "candidates", "turnout_pct", "vote_pct_basis")}
            second = {k: rec.get(k) for k in ("date", "summary_ko", "detail_ko", "winner_ko", "candidates", "turnout_pct", "vote_pct_basis")}
            merged = {**prev, "rounds": [{"round": 1, **first}, {"round": 2, **second}], "rounds_merged": True,
                      "date": rec["date"], "first_round_date": prev["date"], "winner_ko": final_winner(rec),
                      "sources": prev["sources"] + [u for u in rec["sources"] if u not in prev["sources"]],
                      "election_id": prev["election_id"].removesuffix("-r1"),
                      "label_ko": "1차·결선"}
            for key in ("summary_ko", "detail_ko", "candidates", "turnout_pct"):
                merged.pop(key, None)
            out[-1] = merged
        else:
            out.append(rec)
    for rec in out:
        rec.pop("round", None)
        rec.pop("rounds_merged", None)
        if "candidates" in rec and rec["candidates"] is None:
            rec.pop("candidates")
    return out


def deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        elif value is not None:
            out[key] = value
    return out


def validate_input(iso3: str, extra: dict) -> list[str]:
    errors = []
    if extra.get("schema") != "election_records_input_v1":
        errors.append(f"{iso3}: schema {extra.get('schema')!r}")
    if extra.get("country") != iso3:
        errors.append(f"{iso3}: country {extra.get('country')!r}")
    if not extra.get("as_of"):
        errors.append(f"{iso3}: as_of missing")
    for office in extra.get("offices") or []:
        if office.get("key") not in OFFICE_ORDER:
            errors.append(f"{iso3}: office key {office.get('key')!r}")
        for rec in office.get("records") or []:
            where = f"{iso3}:{rec.get('election_id')}"
            if not rec.get("election_id") or not DATE_FULL.match(str(rec.get("date") or "")):
                errors.append(f"{where}: election_id/date")
            if not urls(rec.get("sources")):
                errors.append(f"{where}: sources missing")
            for value in (rec.get("turnout_pct"), *[r.get("turnout_pct") for r in rec.get("rounds") or []]):
                if value is not None and not (isinstance(value, (int, float)) and 0 <= value <= 100):
                    errors.append(f"{where}: turnout_pct {value!r}")
    for issue in extra.get("issues") or []:
        if not issue.get("title_ko") or not urls(issue.get("sources")):
            errors.append(f"{iso3}: issue {issue.get('title_ko')!r} needs title_ko and sources")
    return errors


def fill_vote_pct(candidates: list[dict] | None) -> bool:
    """Researched rows without an official share get one from the listed votes,
    and the record is marked so the card says it is computed."""
    rows = candidates or []
    if not rows or all(c.get("vote_pct") is not None for c in rows):
        return False
    total = sum(c["votes"] for c in rows if isinstance(c.get("votes"), (int, float)))
    if not total:
        return False
    for c in rows:
        if c.get("vote_pct") is None and isinstance(c.get("votes"), (int, float)):
            c["vote_pct"] = round(c["votes"] * 100 / total, 2)
    return True


def apply_input(doc: dict, extra: dict) -> None:
    """Researched input wins over derived data, record by record."""
    by_key = {(o["key"], o.get("system_id")): o for o in doc["offices"]}
    for office in extra.get("offices") or []:
        key = (office.get("key"), office.get("system_id"))
        target = by_key.get(key)
        if target is None:
            target = {"key": office.get("key"), "system_id": office.get("system_id"), "records": [], "next": None}
            doc["offices"].append(target)
            by_key[key] = target
        for field, value in office.items():
            if field not in ("records", "key", "system_id") and value is not None:
                target[field] = value
        known = {r["election_id"]: i for i, r in enumerate(target["records"])}
        for rec in office.get("records") or []:
            rec = {**rec, "origin": "researched"}
            if fill_vote_pct(rec.get("candidates")):
                rec["vote_pct_basis"] = "listed_candidates"
            for rnd in rec.get("rounds") or []:
                if fill_vote_pct(rnd.get("candidates")):
                    rnd["vote_pct_basis"] = "listed_candidates"
            if rec.get("election_id") in known:
                i = known[rec["election_id"]]
                target["records"][i] = deep_merge(target["records"][i], rec)
            else:
                target["records"].append(rec)
    if extra.get("issues"):
        doc["issues"] = extra["issues"]
    for field in ("as_of", "note_ko"):
        if extra.get(field):
            doc[f"input_{field}"] = extra[field]
    doc["offices"].sort(key=lambda o: (OFFICE_ORDER.get(o["key"], 9), o.get("system_id") or ""))


def build(today: str) -> dict[str, dict]:
    systems = load(DATA / "elections_system_v1.json")["systems"]
    board = load(DATA / "elections_board_v1.json")
    index = load(DATA / "elections_contests_index_v1.json")
    contests = {}
    for row in index.get("events") or []:
        path = DATA / row["path"]
        if path.exists():
            contests[row["event_id"]] = load(path)

    docs: dict[str, dict] = {}
    for country in board["countries"]:
        iso3 = country["iso3"]
        offices = offices_for(iso3, [s for s in systems if s["iso3"] == iso3])
        for event in country.get("events") or []:
            if event.get("type") in ("party_leadership", "party_convention", "leadership_review", "speaker_election"):
                continue
            office = match_office(offices, event)
            if office is None:
                continue
            day = str(event.get("date") or "")
            if event.get("status") == "completed" and DATE_FULL.match(day):
                rec = record_from_event(event)
                if event.get("type") == "by_election":
                    rec["by_election"] = True
                cands = contest_candidates(contests.get(event["id"]) or {})
                if cands:
                    rec["candidates"] = cands
                    rec["vote_pct_basis"] = "listed_candidates"
                office["records"].append(rec)
            elif event.get("status") in UPCOMING and event.get("type") != "by_election":
                nxt = {"election_id": event["id"], "date": day if DATE_FULL.match(day) else None,
                       "date_status": event.get("status"), "label_ko": event.get("label_ko"),
                       "note_ko": text(event.get("notes"))}
                if nxt["date"] is None or nxt["date"] >= today:
                    cur = office["next"]
                    if cur is None or (nxt["date"] or "9999") < (cur["date"] or "9999"):
                        office["next"] = nxt
            prev = record_from_previous(event)
            if prev and not any(r["date"] == prev["date"] for r in office["records"]):
                office["records"].append(prev)
        for office in offices:
            office["records"] = merge_rounds([r for r in office["records"]])
            office["records"].sort(key=lambda r: r["date"], reverse=True)
            main = next((r for r in office["records"] if not r.get("by_election")), None)
            if main and office.get("term_years") and office["next"] is None:
                # 다음 정기 선거 날짜를 모를 때: 직전 정기 선거 + 임기. 날짜가 아니라 연도만, 근거를 붙여서.
                office["next_due"] = {"year": int(main["date"][:4]) + int(office["term_years"]),
                                      "basis": "last_election_plus_term",
                                      "note_ko": "직전 정기 선거 연도 + 임기. 조기 선거·해산이 있으면 앞당겨진다."}
        head = country.get("head") or {}
        role = head.get("role")
        exec_office = next((o for o in offices if o["key"] == "executive"), None)
        if exec_office and (head.get("name_ko") or head.get("name_en")):
            if ((role == "president" and exec_office.get("system_id"))
                                or (role in ("prime_minister", "chancellor") and not exec_office.get("system_id"))):
                exec_office["incumbent"] = {"name": head.get("name_ko") or head.get("name_en"), "party_id": head.get("party_id"),
                                            "since": head.get("since"), "sources": urls(head.get("sources"))}
        docs[iso3] = {
            "schema": "election_records_v1",
            "country": iso3,
            "name_ko": country.get("name_ko"),
            "issues_expected": iso3 in ISSUE_COUNTRIES,
            "offices": offices,
            "issues": [],
        }
    for path in sorted(CONFIG.glob("*.json")) if CONFIG.exists() else []:
        iso3 = path.stem.upper()
        extra = load(path)
        errors = validate_input(iso3, extra)
        if errors:
            raise SystemExit("\n".join(errors))
        doc = docs.setdefault(iso3, {"schema": "election_records_v1", "country": iso3, "offices": [], "issues": [],
                                     "issues_expected": iso3 in ISSUE_COUNTRIES})
        apply_input(doc, extra)
    for doc in docs.values():
        dates = [r["date"] for o in doc["offices"] for r in o["records"]]
        doc["latest_election"] = max(dates) if dates else None
        doc["records_total"] = sum(len(o["records"]) for o in doc["offices"])
    return docs


def render(docs: dict[str, dict], today: str) -> dict[str, str]:
    files = {f"{iso3}.json": json.dumps(doc, ensure_ascii=False, indent=1) + "\n" for iso3, doc in sorted(docs.items())}
    index = {
        "schema": "election_records_index_v1",
        "built_for": today,
        "countries": {iso3: {"records": doc["records_total"], "latest_election": doc["latest_election"],
                             "researched": any(r.get("origin") == "researched" for o in doc["offices"] for r in o["records"])}
                      for iso3, doc in sorted(docs.items())},
    }
    files["index.json"] = json.dumps(index, ensure_ascii=False, indent=1) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--today", default=None, help="YYYY-MM-DD; defaults to the board's as_of")
    args = parser.parse_args()
    board = load(DATA / "elections_board_v1.json")
    today = args.today or str(board.get("as_of") or board.get("generated_at") or date.today().isoformat())[:10]
    files = render(build(today), today)
    if args.check:
        stale = [name for name, body in files.items()
                 if not (TARGET / name).exists() or (TARGET / name).read_text(encoding="utf-8") != body]
        if stale:
            print("election_records out of date:", ", ".join(stale[:10]))
            return 1
        return 0
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (TARGET / name).write_text(body, encoding="utf-8")
    print(f"wrote {len(files) - 1} countries to {TARGET.relative_to(ROOT.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
