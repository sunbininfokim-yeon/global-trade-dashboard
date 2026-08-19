"""Extract USA legislature/governors, JPN Diet/governors, governance polls into config/extracted/."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "config" / "extracted"
OUT.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_tags(html: str) -> str:
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def party_abbr_us(name: str) -> str:
    n = (name or "").lower()
    if "republican" in n:
        return "GOP"
    if "democrat" in n:
        return "DEM"
    if "independent" in n:
        return "IND"
    return name or "UNK"


def extract_usa_congress() -> Dict[str, Any]:
    members: List[Dict[str, Any]] = []
    for p in sorted((RAW / "usa").glob("members_p*.json")):
        members.extend(json.loads(p.read_text(encoding="utf-8")).get("members") or [])

    def chamber_of(m: Dict[str, Any]) -> str:
        terms = (m.get("terms") or {}).get("item") or []
        return (terms[-1].get("chamber") if terms else "") or "unknown"

    # congress.gov's current-member endpoint includes the six non-voting House
    # delegates/resident commissioner.  Keep them as roster rows, but do not add
    # them to the 435 voting-seat party breakdown used by the hemicycle UI.
    voting_states = {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
        "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
        "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
        "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin",
        "Wyoming",
    }
    house_voting = Counter()
    house_delegates = Counter()
    senate = Counter()
    rows = []
    for m in members:
        ch = chamber_of(m)
        party = m.get("partyName") or "Unknown"
        abbr = party_abbr_us(party)
        if "House" in ch:
            if m.get("state") in voting_states:
                house_voting[abbr] += 1
            else:
                house_delegates[abbr] += 1
            chamber = "house"
        elif "Senate" in ch:
            senate[abbr] += 1
            chamber = "senate"
        else:
            chamber = "other"
        rows.append(
            {
                "bioguideId": m.get("bioguideId"),
                "name": m.get("name"),
                "party": party,
                "abbr": abbr,
                "state": m.get("state"),
                "district": m.get("district"),
                "chamber": chamber,
            }
        )

    leadership = extract_house_leadership() + extract_senate_leadership()
    return {
        "as_of": now_iso(),
        "source": {
            "congress_api": "https://api.congress.gov/v3/member?currentMember=true",
            "house_leadership": "https://www.house.gov/leadership",
            "senate_leadership": "https://en.wikipedia.org/wiki/Party_leaders_of_the_United_States_Senate",
            "note": "DEMO_KEY pagination; house.gov + Wikipedia Senate leaders (senate.gov 403 here)",
        },
        "summary": {
            "members_total_including_house_delegates": len(rows),
            "house_voting_seats": 435,
            "house_voting_members": sum(house_voting.values()),
            "house_vacancies": 435 - sum(house_voting.values()),
            "house_by_party": dict(house_voting),
            "house_delegates_by_party": dict(house_delegates),
            "house_roster_rows_including_delegates": sum(house_voting.values()) + sum(house_delegates.values()),
            "senate_by_party": dict(senate),
        },
        "floor_leadership": leadership,
        "members": rows,
    }


def extract_senate_leadership() -> List[Dict[str, str]]:
    path = RAW / "usa" / "wiki_senate_leaders.html"
    if not path.exists():
        return []
    html = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_tags(html)
    out: List[Dict[str, str]] = []
    patterns = [
        (r"Majority Leader\s+([A-Z][A-Za-z .'-]+?)\s+\([RD]-", "majority_leader"),
        (r"Minority Leader\s+([A-Z][A-Za-z .'-]+?)\s+\([RD]-", "minority_leader"),
        (r"Majority Whip\s+([A-Z][A-Za-z .'-]+?)\s+\([RD]-", "majority_whip"),
        (r"Minority Whip\s+([A-Z][A-Za-z .'-]+?)\s+\([RD]-", "minority_whip"),
    ]
    # Prefer structured wiki text near current leaders
    for pat, office in [
        (r"Majority Leader\s+(John Thune|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\(R-", "majority_leader"),
        (r"Minority Leader\s+(Chuck Schumer|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\(D-", "minority_leader"),
        (r"Majority Whip\s+(John Barrasso|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\(R-", "majority_whip"),
        (r"Minority Whip\s+(Dick Durbin|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\(D-", "minority_whip"),
    ]:
        m = re.search(pat, text)
        if m:
            out.append(
                {
                    "office": f"senate_{office}",
                    "name": f"Sen. {m.group(1).strip()}",
                    "chamber": "senate",
                    "title": office.replace("_", " ").title(),
                }
            )
    # Fallback hardcoded from page content if regex brittle but names present
    if not any(x.get("chamber") == "senate" for x in out) and "John Thune" in text and "Chuck Schumer" in text:
        out = [
            {"office": "senate_majority_leader", "name": "Sen. John Thune", "chamber": "senate"},
            {"office": "senate_majority_whip", "name": "Sen. John Barrasso", "chamber": "senate"},
            {"office": "senate_minority_leader", "name": "Sen. Chuck Schumer", "chamber": "senate"},
            {"office": "senate_minority_whip", "name": "Sen. Dick Durbin", "chamber": "senate"},
        ]
    return out


def extract_usa_state_legislatures() -> Dict[str, Any]:
    path = RAW / "usa" / "wiki_state_legislatures.html"
    if not path.exists():
        return {"states": [], "summary": {}}
    html = path.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S | re.I
    )
    states = []
    senate_ctrl = Counter()
    house_ctrl = Counter()
    target = None
    for t in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
        if not rows:
            continue
        head = strip_tags(rows[0])
        if "State Senate" in head and "State House" in head:
            target = rows
            break
    if not target:
        return {"states": [], "summary": {}, "note": "table not found"}

    def parse_chamber(cell: str) -> Dict[str, Any]:
        # e.g. "Republican 27–8" or "Coalition 14–6" or "Democratic 21–19"
        cell = cell.replace("–", "-").replace("—", "-")
        m = re.search(
            r"(Republican|Democratic|Coalition|Split|Independent)\s*(\d+)\s*-\s*(\d+)",
            cell,
            re.I,
        )
        if m:
            ctrl = m.group(1).title()
            if ctrl == "Republican":
                abbr = "GOP"
            elif ctrl == "Democratic":
                abbr = "DEM"
            else:
                abbr = ctrl.upper()[:3]
            return {
                "control": ctrl,
                "abbr": abbr,
                "majority": int(m.group(2)),
                "minority": int(m.group(3)),
                "raw": cell[:80],
            }
        m2 = re.search(r"(Republican|Democratic|Coalition|Split)", cell, re.I)
        if m2:
            ctrl = m2.group(1).title()
            abbr = {"Republican": "GOP", "Democratic": "DEM"}.get(ctrl, ctrl[:3].upper())
            return {"control": ctrl, "abbr": abbr, "raw": cell[:80]}
        return {"control": "Unknown", "abbr": "UNK", "raw": cell[:80]}

    for r in target[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
        if len(cells) < 5:
            continue
        texts = [strip_tags(c) for c in cells]
        state = texts[0]
        if not state or state.lower() == "state":
            continue
        sen = parse_chamber(texts[3])
        hou = parse_chamber(texts[4])
        senate_ctrl[sen["abbr"]] += 1
        house_ctrl[hou["abbr"]] += 1
        # trifecta hint vs governor cell
        gov = texts[2]
        gov_abbr = party_abbr_us(gov) if any(x in gov for x in ("Republican", "Democratic")) else "UNK"
        states.append(
            {
                "state": state,
                "governor_party": gov_abbr,
                "state_senate": sen,
                "state_house": hou,
            }
        )

    return {
        "as_of": now_iso(),
        "source": {
            "url": "https://en.wikipedia.org/wiki/Political_party_strength_in_U.S._states",
            "grade": "aggregator_wikipedia",
            "note": "State Senate/House partisan control margins",
        },
        "summary": {
            "states": len(states),
            "state_senate_control": dict(senate_ctrl),
            "state_house_control": dict(house_ctrl),
        },
        "states": states,
    }


def extract_house_leadership() -> List[Dict[str, str]]:
    path = RAW / "usa" / "house_leadership.html"
    if not path.exists():
        return []
    html = path.read_text(encoding="utf-8", errors="ignore")
    out: List[Dict[str, str]] = []
    # Speaker block
    m = re.search(
        r"Speaker of the House</a></h2>.*?<h3>\s*(Rep\.\s*[^<]+)</h3>",
        html,
        re.S | re.I,
    )
    if m:
        out.append({"office": "speaker", "name": m.group(1).strip(), "chamber": "house"})
    # Pattern: <h4>Title</h4> ... <h3>Rep. Name</h3> or <p><strong>Title</strong> ... Name
    for title, name in re.findall(
        r"<h4>([^<]+)</h4>\s*(?:<p>[^<]*</p>\s*)?<h3>\s*(Rep\.\s*[^<]+)</h3>",
        html,
        re.S | re.I,
    ):
        office = title.strip().lower().replace(" ", "_")
        out.append({"office": office, "name": name.strip(), "chamber": "house", "title": title.strip()})
    # Democratic Leader / Whip use <a>Label</a><br>Rep. Name
    for label, office in [
        ("Democratic Leader", "minority_leader"),
        ("Democratic Whip", "minority_whip"),
        ("Democratic Caucus Chairman", "caucus_chair"),
        ("Assistant Democratic Leader", "assistant_democratic_leader"),
    ]:
        if any(x.get("office") == office for x in out):
            continue
        pat = rf"{re.escape(label)}</a><br>\s*(Rep\.\s*[^<]+)"
        mm = re.search(pat, html, re.I)
        if mm:
            out.append({"office": office, "name": mm.group(1).strip(), "chamber": "house", "title": label})
    # Fallback regex pairs from known roles
    for label, office in [
        ("Majority Leader", "majority_leader"),
        ("Majority Whip", "majority_whip"),
        ("Conference Chair", "conference_chair"),
        ("Minority Leader", "minority_leader"),
        ("Minority Whip", "minority_whip"),
        ("Assistant Democratic Leader", "assistant_democratic_leader"),
        ("Caucus Chair", "caucus_chair"),
    ]:
        if any(x.get("office") == office for x in out):
            continue
        pat = rf"{re.escape(label)}.*?(Rep\.\s*[A-Z][^<]{{2,60}})"
        mm = re.search(pat, html, re.S)
        if mm:
            out.append({"office": office, "name": mm.group(1).strip(), "chamber": "house", "title": label})
    # dedupe by office
    seen = set()
    deduped = []
    for item in out:
        if item["office"] in seen:
            continue
        seen.add(item["office"])
        deduped.append(item)
    return deduped


def extract_usa_governors() -> Dict[str, Any]:
    path = RAW / "usa" / "wiki_governors.html"
    html = path.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S | re.I)
    govs = []
    party_counts = Counter()
    if tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S | re.I)
        for r in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
            if len(cells) < 5:
                continue
            texts = [strip_tags(c) for c in cells]
            # State, Image, Governor, Party color junk, Party, ...
            # Wiki cells look like "Alabama ( list )" — spaces inside parens
            state = re.sub(r"\s*\(\s*list\s*\)\s*$", "", texts[0], flags=re.I).strip()
            name = texts[2]
            party = next((t for t in texts[3:8] if t in {"Republican", "Democratic", "Independent"}), None)
            if not party:
                joined = " ".join(texts)
                if "Democratic–Farmer–Labor" in joined or "Democratic-Farmer-Labor" in joined or "DFL" in joined:
                    party = "Democratic"
                else:
                    party = next(
                        (t for t in texts if t in {"Republican", "Democratic", "Independent"}),
                        "Unknown",
                    )
            abbr = party_abbr_us(party)
            party_counts[abbr] += 1
            govs.append({"state": state, "name": name, "party": party, "abbr": abbr})
    return {
        "as_of": now_iso(),
        "source": {
            "url": "https://en.wikipedia.org/wiki/List_of_current_United_States_governors",
            "secondary": "https://www.nga.org/governors/",
            "grade": "aggregator_wikipedia_crosscheck_nga",
        },
        "summary": {"count": len(govs), "by_party": dict(party_counts)},
        "governors": govs,
    }


KAHA_TO_ABBR = {
    "自民": "LDP",
    "自由民主党": "LDP",
    "立憲": "CDP",
    "立憲民主": "CDP",
    "立憲民主党": "CDP",
    "維新": "Ishin",
    "日本維新の会": "Ishin",
    "公明": "Komeito",
    "公明党": "Komeito",
    "国民": "DPP",
    "国民民主": "DPP",
    "国民民主党": "DPP",
    "共産": "JCP",
    "日本共産党": "JCP",
    "れいわ": "Reiwa",
    "れいわ新選組": "Reiwa",
    "社民": "SDP",
    "参政": "Sanseito",
    "参政党": "Sanseito",
    "保守": "CPJ",
    "日本保守党": "CPJ",
    "無所属": "IND",
}


def extract_jpn_shugiin() -> Dict[str, Any]:
    members = []
    parties = Counter()
    pages_used = []
    # Full kana pages 1giin.htm … 10giin.htm (あ–わ)
    page_paths = sorted((RAW / "jpn").glob("[0-9]*giin.htm"), key=lambda p: int(re.match(r"(\d+)", p.name).group(1)))
    if not page_paths and (RAW / "jpn" / "shugiin_giin.html").exists():
        page_paths = [RAW / "jpn" / "shugiin_giin.html"]

    for path in page_paths:
        html = path.read_bytes().decode("cp932", errors="ignore")
        pages_used.append(path.name)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
        for r in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)
            if len(cells) < 4:
                continue
            texts = [strip_tags(c) for c in cells]
            if not texts[0] or "氏名" in texts[0]:
                continue
            kaiha = texts[2]
            abbr = None
            for k, v in KAHA_TO_ABBR.items():
                if k in kaiha:
                    abbr = v
                    break
            if not abbr:
                if "中道" in kaiha:
                    abbr = "Chudo"
                elif "みらい" in kaiha:
                    abbr = "Mirai"
                elif kaiha.startswith("無"):
                    abbr = "IND"
                else:
                    abbr = kaiha or "UNK"
            parties[abbr] += 1
            members.append(
                {
                    "name": texts[0].replace("君", "").strip(),
                    "kaiha": kaiha,
                    "abbr": abbr,
                    "district": texts[3] if len(texts) > 3 else None,
                    "wins": texts[4] if len(texts) > 4 else None,
                    "page": path.name,
                }
            )

    composition = extract_jpn_hr_composition_wikipedia()
    sangiin = extract_jpn_sangiin_composition()
    return {
        "as_of": now_iso(),
        "source": {
            "url_pattern": "https://www.shugiin.go.jp/Internet/itdb_annai.nsf/html/statics/syu/{n}giin.htm",
            "pages": pages_used,
            "encoding": "Shift_JIS",
            "grade": "official",
            "composition_source": composition.get("source"),
            "sangiin_source": sangiin.get("source"),
        },
        "summary": {
            "members": len(members),
            "by_party_abbr": dict(parties),
            "house_composition_wikipedia": composition.get("by_abbr"),
            "sangiin_by_abbr": sangiin.get("by_abbr"),
        },
        "house_composition": composition,
        "sangiin_composition": sangiin,
        "members": members,
    }


def extract_jpn_sangiin_composition() -> Dict[str, Any]:
    path = RAW / "jpn" / "wiki_hc_composition.html"
    if not path.exists():
        return {"by_abbr": {}}
    html = path.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S | re.I
    )
    by_abbr: Dict[str, int] = {}
    rows_out = []
    for t in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
        if not rows:
            continue
        head = strip_tags(rows[0] if rows else "") + " " + strip_tags(rows[1] if len(rows) > 1 else "")
        if "Caucus" not in head and "Members" not in head:
            continue
        for r in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
            texts = [strip_tags(c) for c in cells]
            if len(texts) < 4:
                continue
            label = " ".join(texts[:3])
            # last numeric cell = total members for caucus
            nums = [int(x) for x in texts if re.fullmatch(r"\d+", x)]
            if not nums:
                continue
            seats = nums[-1]
            low = label.lower()
            if seats > 200 or "total" in low or "government" in low or "opposition" in low:
                continue
            abbr = None
            if "liberal democratic" in low or re.search(r"\bldp\b", low):
                abbr = "LDP"
            elif "ishin" in low or "innovation" in low:
                abbr = "Ishin"
            elif "constitutional democratic" in low or re.search(r"\bcdp\b", low):
                abbr = "CDP"
            elif "democratic party for the people" in low or "dpfp" in low:
                abbr = "DPP"
            elif "komeito" in low:
                abbr = "Komeito"
            elif "sanseit" in low:
                abbr = "Sanseito"
            elif "communist" in low:
                abbr = "JCP"
            elif "reiwa" in low:
                abbr = "Reiwa"
            elif "conservative party" in low:
                abbr = "CPJ"
            elif "mirai" in low:
                abbr = "Mirai"
            elif "social democratic" in low:
                abbr = "SDP"
            elif "okinawa" in low:
                abbr = "Okinawa"
            else:
                continue
            by_abbr[abbr] = max(by_abbr.get(abbr, 0), seats)
            rows_out.append({"label": label[:100], "abbr": abbr, "seats": seats})
        if by_abbr:
            break
    return {
        "source": {
            "url": "https://en.wikipedia.org/wiki/House_of_Councillors_(Japan)",
            "grade": "aggregator_wikipedia",
            "seats_sum": sum(by_abbr.values()),
        },
        "by_abbr": by_abbr,
        "rows": rows_out,
    }


def extract_jpn_hr_composition_wikipedia() -> Dict[str, Any]:
    path = RAW / "jpn" / "wiki_hr_composition.html"
    if not path.exists():
        return {"by_abbr": {}, "note": "missing wiki_hr_composition.html"}
    html = path.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S | re.I
    )
    by_abbr: Dict[str, int] = {}
    rows_out = []
    for t in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
        if len(rows) < 3:
            continue
        header = strip_tags(rows[1] if len(rows) > 1 else rows[0])
        if "Parliamentary groups" not in header and not (
            "Seats" in header and "Parties" in header
        ):
            continue
        for r in rows[2:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
            texts = [strip_tags(c) for c in cells]
            if len(texts) < 2:
                continue
            label = " ".join(texts[:-1])
            seat_s = texts[-1]
            if not re.fullmatch(r"\d+", seat_s):
                continue
            seats = int(seat_s)
            low = label.lower()
            if seats > 400 or "total" in low or "vacant" in low or "합계" in label:
                continue
            abbr = None
            if "liberal democratic" in low or re.search(r"\bldp\b", low):
                abbr = "LDP"
            elif "centrist reform" in low or "chūdō" in low or "chudo" in low:
                abbr = "Chudo"
            elif "ishin" in low or "innovation" in low:
                abbr = "Ishin"
            elif "democratic party for the people" in low or "dpfp" in low:
                abbr = "DPP"
            elif "sanseit" in low:
                abbr = "Sanseito"
            elif "mirai" in low:
                abbr = "Mirai"
            elif "constitutional democratic" in low or re.search(r"\bcdp\b", low):
                abbr = "CDP"
            elif "komeito" in low:
                abbr = "Komeito"
            elif "communist" in low:
                abbr = "JCP"
            elif "reiwa" in low:
                abbr = "Reiwa"
            else:
                continue  # skip unclassified junk rows
            # keep max if duplicate labels appear
            by_abbr[abbr] = max(by_abbr.get(abbr, 0), seats)
            rows_out.append({"label": label[:120], "abbr": abbr, "seats": seats})
        if by_abbr:
            break
    return {
        "source": {
            "url": "https://en.wikipedia.org/wiki/House_of_Representatives_(Japan)",
            "grade": "aggregator_wikipedia",
            "note": "Post-2026 election caucus seat totals; cross-check with 衆議院 会派一覧 when available",
            "seats_sum": sum(by_abbr.values()),
        },
        "by_abbr": by_abbr,
        "rows": rows_out,
    }


def extract_jpn_governors() -> Dict[str, Any]:
    path = RAW / "jpn" / "wiki_governors.html"
    html = path.read_bytes().decode("utf-8", errors="ignore")
    tables = re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S | re.I)
    govs = []
    if tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S | re.I)
        for r in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
            if len(cells) < 4:
                continue
            texts = [strip_tags(c) for c in cells]
            # "01/ 北海道 （ 一覧 ）" → "北海道"
            pref = re.sub(r"^\d+\s*/\s*", "", texts[0])
            pref = re.sub(r"[（(]\s*一覧\s*[）)]|[（(]\s*list\s*[）)]", "", pref, flags=re.I)
            pref = re.sub(r"\s+", " ", pref).strip()
            name_raw = texts[2]
            # Drop dumped CSS / template noise then ruby reading in parens
            name = re.sub(r"\.mw-parser-output\S*", " ", name_raw)
            name = re.sub(r"\{[^}]*\}", " ", name)
            name = re.sub(r"（[^）]+）|\([^)]+\)", "", name)
            name = re.sub(r"\s+", " ", name).strip() or name_raw
            party = texts[7] if len(texts) > 7 else (texts[-1] if texts else "")
            party = re.sub(r"\s+", " ", party).strip()

            def _jp_date(s: Optional[str]) -> Optional[str]:
                if not s:
                    return None
                m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*/\s*(\d{1,2})", s)
                if m:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                m2 = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
                if m2:
                    return f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
                return s.strip()

            govs.append(
                {
                    "prefecture": pref,
                    "name": name,
                    "party": party,
                    "term_start": _jp_date(texts[4] if len(texts) > 4 else None),
                    "term_end": _jp_date(texts[5] if len(texts) > 5 else None),
                }
            )
    return {
        "as_of": now_iso(),
        "source": {
            "url": "https://ja.wikipedia.org/wiki/都道府県知事の一覧",
            "grade": "aggregator_wikipedia",
            "note": "Prefectural executives only (no municipal basics)",
        },
        "summary": {"count": len(govs)},
        "governors": govs,
    }


def write_governance_polls() -> Dict[str, Any]:
    """Governance approval snapshots — document-sourced, not horserace."""
    existing_path = OUT / "governance_polls.json"
    existing: Dict[str, Any] = {}
    if existing_path.exists():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
    generated = [
        {
            "iso3": "USA",
            "kind": "presidential_job_approval",
            "subject": "Donald J. Trump",
            "pollster": "Gallup",
            "approve_pct": 41,
            "field_note": "Gallup Presidential Job Approval Center / recent articles cite Trump ~41% (2025–2026 tracking). Exact field dates vary by release.",
            "sources": [
                {
                    "url": "https://news.gallup.com/interactives/507569/presidential-job-approval-center.aspx",
                    "label": "Gallup Presidential Job Approval Center",
                },
                {
                    "url": "https://news.gallup.com/poll/654197/congress-job-rating-sinks-trump-steady.aspx",
                    "label": "Gallup: Congress 15%; Trump steady at 41% (URL may rotate)",
                    "status": "url_may_404_use_center",
                },
            ],
            "confidence": "medium",
            "refresh": "manual_or_scrape_gallup_center",
        },
        {
            "iso3": "JPN",
            "kind": "cabinet_approval",
            "subject": "Takaichi cabinet",
            "pollster": "NHK",
            "approve_pct": 58,
            "disapprove_pct": 27,
            "field_date": "2026-07",
            "sources": [
                {
                    "url": "https://news.web.nhk/newsweb/na/na-k10015175451000",
                    "label": "NHK: 高市内閣支持率58％ 不支持27％ (2026-07-13)",
                },
                {
                    "url": "https://news.web.nhk/senkyo/shijiritsu/",
                    "label": "NHK 内閣支持率 hub",
                },
            ],
            "confidence": "high",
            "refresh": "monthly_nhk",
        },
        {
            "iso3": "KOR",
            "kind": "presidential_job_approval",
            "subject": "Lee Jae Myung",
            "pollster": "Gallup Korea",
            "approve_pct": 54,
            "field_note": "Example governance series for KR-style presidential approval; refresh from Gallup Korea / NEC-reviewed polls",
            "sources": [
                {
                    "url": "https://en.yna.co.kr/view/AEN20260703004600315",
                    "label": "Yonhap citing Gallup Korea (~54%, early Jul 2026)",
                }
            ],
            "confidence": "medium",
            "refresh": "weekly_gallup_korea",
        },
    ]
    generated_keys = {(row["iso3"], row["kind"]) for row in generated}
    preserved = [
        row
        for row in (existing.get("series") or [])
        if (row.get("iso3"), row.get("kind")) not in generated_keys
    ]
    admit = set((existing.get("policy") or {}).get("admit") or [])
    admit.update(["presidential_job_approval", "cabinet_approval"])
    return {
        "as_of": now_iso(),
        "policy": {
            "admit": sorted(admit),
            "reject": ["national_horserace_headline"],
        },
        "series": generated + preserved,
    }


def main() -> int:
    usa_congress = extract_usa_congress()
    usa_gov = extract_usa_governors()
    usa_state_legs = extract_usa_state_legislatures()
    jpn_diet = extract_jpn_shugiin()
    jpn_gov = extract_jpn_governors()
    polls = write_governance_polls()

    (OUT / "usa_congress.json").write_text(
        json.dumps(usa_congress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "usa_governors.json").write_text(
        json.dumps(usa_gov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "usa_state_legislatures.json").write_text(
        json.dumps(usa_state_legs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "jpn_shugiin.json").write_text(
        json.dumps(jpn_diet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "jpn_governors.json").write_text(
        json.dumps(jpn_gov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "governance_polls.json").write_text(
        json.dumps(polls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "generated_at": now_iso(),
        "usa": {
            "congress_summary": usa_congress["summary"],
            "floor_leadership": usa_congress["floor_leadership"],
            "governors_summary": usa_gov["summary"],
            "state_legislatures_summary": usa_state_legs.get("summary"),
        },
        "jpn": {
            "shugiin_members": jpn_diet["summary"].get("members"),
            "shugiin_by_party_abbr": jpn_diet["summary"].get("by_party_abbr"),
            "house_composition_wikipedia": jpn_diet["summary"].get("house_composition_wikipedia"),
            "sangiin_by_abbr": jpn_diet["summary"].get("sangiin_by_abbr"),
            "governors_count": jpn_gov["summary"]["count"],
        },
        "polls": {
            "series": [
                {
                    "iso3": s["iso3"],
                    "kind": s["kind"],
                    "approve_pct": s.get("approve_pct"),
                    "pollster": s.get("pollster"),
                    "field_date": s.get("field_date"),
                }
                for s in polls["series"]
            ]
        },
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
