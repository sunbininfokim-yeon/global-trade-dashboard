"""House and Senate officers (Clerk, Sergeant at Arms, Chaplain, ...) as cards.

Every name comes from an official page of the chamber itself or from the
Congressional Record on govinfo. Raw pages stay in raw/usa (gitignored).

House: history.house.gov officer tables (last row is the sitting officer),
chaplain.house.gov contact footer, Clerk MemberData.xml <clerk>.
Senate: senate.gov leadership / officers-staff / party-secretaries / chaplain
pages. senate.gov answers 403 from some networks; when a Senate page is
missing, the previously committed card is carried forward with stale=True
instead of being dropped or guessed.
Congressional Record PRAYER granules confirm that each chaplain is still
opening sessions.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "usa"
OUT = ROOT / "config" / "extracted"
OUT_PATH = OUT / "usa_congress_officers.json"

UA = "Mozilla/5.0 (compatible; election-watch/1.0)"

HOUSE_HISTORY = {
    "clerk": ("Clerks", "https://history.house.gov/People/Office/Clerks/"),
    "sergeant_at_arms": ("Sergeants-at-Arms", "https://history.house.gov/People/Office/Sergeants-at-Arms/"),
    "chief_administrative_officer": (
        "Chief-Administrative-Officers",
        "https://history.house.gov/People/Office/Chief-Administrative-Officers/",
    ),
    "chaplain": ("Chaplains", "https://history.house.gov/People/Office/Chaplains/"),
    "parliamentarian": ("Parliamentarians", "https://history.house.gov/People/Office/Parliamentarians/"),
}
HOUSE_CHAPLAIN_URL = "https://chaplain.house.gov/"
CLERK_XML_URL = "https://clerk.house.gov/xml/lists/MemberData.xml"

SENATE_PAGES = {
    "leadership": "https://www.senate.gov/senators/leadership.htm",
    "officers_staff": "https://www.senate.gov/about/officers-staff.htm",
    "party_secretaries": "https://www.senate.gov/about/officers-staff/party-secretaries.htm",
    "chaplain": "https://www.senate.gov/about/officers-staff/chaplain.htm",
}

HOUSE_OFFICES = [
    ("clerk", "하원 사무총장", "Clerk of the House", "elected_officer"),
    ("sergeant_at_arms", "하원 경위총감", "Sergeant at Arms of the House", "elected_officer"),
    ("chief_administrative_officer", "하원 행정최고책임자", "Chief Administrative Officer of the House", "elected_officer"),
    ("chaplain", "하원 원목", "Chaplain of the House", "elected_officer"),
    ("parliamentarian", "하원 의사규칙관", "Parliamentarian of the House", "nonpartisan_official"),
]
SENATE_OFFICES = [
    ("president_pro_tempore", "상원 임시의장", "President pro tempore", "constitutional_officer"),
    ("secretary", "상원 사무총장", "Secretary of the Senate", "elected_officer"),
    ("sergeant_at_arms", "상원 경위총감", "Sergeant at Arms and Doorkeeper", "elected_officer"),
    ("chaplain", "상원 원목", "Chaplain of the Senate", "elected_officer"),
    ("parliamentarian", "상원 의사규칙관", "Parliamentarian of the Senate", "nonpartisan_official"),
    ("majority_secretary", "다수당 원내사무관", "Secretary for the Majority", "party_officer"),
    ("minority_secretary", "소수당 원내사무관", "Secretary for the Minority", "party_officer"),
]

ROLE_KO = {
    "clerk": "의사록·표결 기록, 의원 명부, 입법 문서를 관리한다. 회기 첫날 의장 선출 전까지 회의를 주재한다.",
    "sergeant_at_arms": "본회의장 질서와 의회 경비를 맡는 최고 법집행 책임자. 의사당 경찰위원회 위원.",
    "chief_administrative_officer": "하원 재무·인사·IT·조달 등 행정 지원을 총괄한다.",
    "chaplain": "매 회기 개회 기도를 하고 의원·직원의 목회 상담을 맡는다. 초당·초교파 직책.",
    "parliamentarian": "의사 규칙과 선례를 해석해 의장석에 조언하는 초당적 직원.",
    "president_pro_tempore": "부통령 부재 시 상원을 주재한다. 관례상 다수당 최다선 의원. 대통령 승계 3순위.",
    "secretary": "상원의 입법·행정 사무(의사록, 서기, 급여, 공문서)를 총괄하는 선출 직원.",
    "majority_secretary": "다수당 원내 일정·표결 준비와 휴게실(cloakroom) 운영을 맡는 정당 선출 직원.",
    "minority_secretary": "소수당 원내 일정·표결 준비와 휴게실(cloakroom) 운영을 맡는 정당 선출 직원.",
}

APPOINTMENT_KO = {
    "elected": "본회의 선출",
    "appointed": "임명 (직무 수행)",
}

POLICY_KO = (
    "이름은 각 원의 공식 페이지(history.house.gov·chaplain.house.gov·Clerk XML·senate.gov)와 "
    "govinfo 의회의사록에서만 읽는다. 공식 페이지를 못 받은 회차에는 직전 값을 stale로 유지하고 "
    "새 이름을 추측하지 않는다."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_of(markup: str) -> str:
    markup = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    markup = re.sub(r"<[^>]+>", " ", markup)
    return re.sub(r"\s+", " ", htmllib.unescape(markup)).strip()


def table_rows(markup: str) -> List[List[str]]:
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", markup, re.S | re.I):
        cells = [text_of(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if cells and cells[0]:
            rows.append(cells)
    if rows:
        return rows
    for line in markup.splitlines():
        line = line.strip().lstrip("- ").strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] and not re.fullmatch(r"[-: ]+", cells[0]):
            rows.append(cells)
    return rows


def flip_name(name: str) -> str:
    """'MCFARLAND, William' -> 'William McFarland'; leaves 'First Last' alone."""
    name = re.sub(r"\s*\d+$", "", name.replace("\xa0", " ")).strip()
    if "," not in name:
        return re.sub(r"\b([A-Z]{2,})\b", lambda m: _title_surname(m.group(1)), name)
    last, first = [p.strip() for p in name.split(",", 1)]
    return f"{first} {_title_surname(last)}".strip()


def _title_surname(word: str) -> str:
    if not word.isupper():
        return word
    w = word.capitalize()
    w = re.sub(r"^Mc([a-z])", lambda m: "Mc" + m.group(1).upper(), w)
    return w


DATE_RE = re.compile(r"([A-Z][a-z]{2}) (\d{2}), (\d{4})")
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def iso_date(text: str) -> Optional[str]:
    match = DATE_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(3)}-{MONTHS[match.group(1)]:02d}-{match.group(2)}"


def parse_house_history(markup: str) -> Optional[Dict[str, Any]]:
    """Last row of a history.house.gov officer table is the sitting officer."""
    rows = [r for r in table_rows(markup) if re.match(r"\d+(st|nd|rd|th) \(", r[0])]
    if not rows:
        return None
    last = rows[-1]
    raw_name = re.sub(r"^The Reverend (Dr\. )?", "", last[1]).strip()
    date_cell = next((c for c in reversed(last) if DATE_RE.search(c)), "")
    lead = date_cell.lower()
    how = "appointed" if lead.startswith("appointed") else "elected" if lead.startswith("elected") else None
    out: Dict[str, Any] = {
        "name_en": flip_name(raw_name),
        "congress": last[0],
        "since": iso_date(date_cell),
        "appointment": how,
    }
    if len(rows) >= 2 and rows[-2][1] != last[1] and rows[-2][0] == last[0]:
        out["predecessor_en"] = flip_name(re.sub(r"^The Reverend (Dr\. )?", "", rows[-2][1]))
    if len(last) >= 3 and not re.match(r"^[A-Z]{2}$", last[2]) and last[2] not in ("Parliamentarian",):
        if "Chief Administrative" not in last[2]:
            out["denomination"] = last[2]
    return out


def parse_house_chaplain_page(markup: str) -> Optional[str]:
    """The sitting chaplain is in the contact footer; the message block can lag."""
    match = re.search(
        r"The Reverend (?:Dr\. )?((?:(?!The Reverend)[\w\. ])+?), Chaplain, U\.S\. House", text_of(markup)
    )
    return match.group(1).strip() if match else None


def parse_clerk_xml(xml: str) -> Optional[str]:
    match = re.search(r"<clerk>(.*?)</clerk>", xml or "")
    return " ".join(match.group(1).split()) if match else None


SENATE_LABELS = {
    "president_pro_tempore": r"President Pro Tempore",
    "parliamentarian": r"Parliamentarian",
    "majority_secretary": r"Secretary for the Majority",
    "minority_secretary": r"Secretary for the Minority",
    "chaplain": r"Chaplain",
    "secretary": r"Secretary of the Senate",
    "sergeant_at_arms": r"Sergeant at Arms",
}
NAME_AFTER = r"\s+([A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)?, [A-Z][A-Za-z\.\- ]*?[A-Za-z\.])(?:\s+\(([RDI])-([A-Z]{2})\))?(?=\s|$)"


def parse_senate_leadership(markup: str) -> Dict[str, Dict[str, Any]]:
    text = text_of(markup)
    section = text.split("Senate-Elected Officers", 1)
    officers_text = section[1] if len(section) == 2 else ""
    out: Dict[str, Dict[str, Any]] = {}
    for office_id, label in SENATE_LABELS.items():
        hay = text if office_id == "president_pro_tempore" else officers_text
        match = re.search(label + NAME_AFTER, hay)
        if not match:
            continue
        row: Dict[str, Any] = {"name_en": flip_name(match.group(1))}
        if match.group(2):
            row["party_abbr"] = match.group(2)
            row["state"] = match.group(3)
        out[office_id] = row
    return out


def parse_senate_officers_staff(markup: str) -> Dict[str, Dict[str, Any]]:
    text = text_of(markup)
    out: Dict[str, Dict[str, Any]] = {}
    for office_id, phrase in (("secretary", "secretary of the Senate"), ("sergeant_at_arms", "sergeant at arms")):
        match = re.search(rf"The current {phrase} is ([A-Z][\w\.\- ]+?[a-z]{{2}})\.(?:\s|$)", text, re.I)
        if match:
            out[office_id] = {"name_en": match.group(1).strip()}
    return out


def parse_senate_party_secretaries(markup: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    current = [(r[0], r[1]) for r in table_rows(markup) if len(r) >= 2 and r[1].endswith("present")]
    text = text_of(markup)
    dem_at = text.find("Democratic Party Secretaries")
    rep_at = text.find("Republican Party Secretaries")
    for name, years in current:
        pos = text.find(name)
        party = "D" if dem_at <= pos < (rep_at if rep_at > dem_at else len(text)) else "R"
        out[party] = {"name_en": name, "since_year": years.split("–")[0].split("-")[0]}
    return out


def parse_senate_chaplain_table(markup: str) -> Optional[Dict[str, Any]]:
    rows = [r for r in table_rows(markup) if len(r) >= 3 and re.search(r"\d{4}", r[2])]
    if not rows:
        return None
    name, denom, date = rows[-1][0], rows[-1][1], rows[-1][2]
    clean = re.split(r",\s*(?:Ph\.D|D\.D|D\. Min|S\.T\.D|LL\.D|M\.D)", name)[0].strip()
    match = re.search(r"([A-Z][a-z]+)\.? (\d{1,2}), (\d{4})", date)
    since = None
    if match:
        month = MONTHS.get(match.group(1)[:3])
        since = f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}" if month else None
    return {"name_en": clean, "denomination": denom, "since": since}


PRAYER_RE = re.compile(r"The Chaplain, (?:the Reverend |Dr\. )?(?:Dr\. )?(.+?), offered the following prayer")


def parse_crec_prayer(text: str) -> Optional[str]:
    match = PRAYER_RE.search(re.sub(r"\s+", " ", text or ""))
    return match.group(1).strip() if match else None


def _get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def govinfo_key() -> str:
    return os.environ.get("GOVINFO_API_KEY") or os.environ.get("DATA_GOV_API_KEY") or "DEMO_KEY"


def fetch_crec_prayers(days: int = 10) -> Dict[str, Any]:
    """Latest sitting-chaplain prayer per chamber from the Congressional Record."""
    key = govinfo_key()
    found: Dict[str, Any] = {}
    since = "2026-01-01T00:00:00Z"
    listing = json.loads(_get(
        f"https://api.govinfo.gov/collections/CREC/{since}?pageSize=100&offsetMark=*&api_key={key}"
    ))
    packages = sorted((p["packageId"] for p in listing.get("packages") or []), reverse=True)[:days]
    for package in packages:
        if {"house", "senate"} <= set(found):
            break
        granules = json.loads(_get(
            f"https://api.govinfo.gov/packages/{package}/granules?pageSize=300&offsetMark=*&api_key={key}"
        ))
        for granule in granules.get("granules") or []:
            if (granule.get("title") or "").strip().upper() != "PRAYER":
                continue
            chamber = (granule.get("granuleClass") or "").lower()
            if chamber not in ("house", "senate") or chamber in found:
                continue
            day = package.replace("CREC-", "")
            url = f"https://www.govinfo.gov/content/pkg/{package}/html/{granule['granuleId']}.htm"
            name = parse_crec_prayer(text_of(_get(url)))
            if name:
                found[chamber] = {"chaplain_en": name, "date": day, "granule_id": granule["granuleId"], "url": url}
    return found


def run_fetch() -> Dict[str, Any]:
    RAW.mkdir(parents=True, exist_ok=True)
    info: Dict[str, Any] = {"errors": []}
    targets = {f"house_history_{slug}.html": url for slug, url in HOUSE_HISTORY.values()}
    targets["house_chaplain.html"] = HOUSE_CHAPLAIN_URL
    targets.update({f"senate_{key}.html": url for key, url in SENATE_PAGES.items()})
    for name, url in targets.items():
        try:
            (RAW / name).write_text(_get(url), encoding="utf-8")
            if name.startswith("senate_"):
                (RAW / "senate_fetch_meta.json").unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            info["errors"].append(f"{name}: {exc}")
    try:
        prayers = fetch_crec_prayers()
        (RAW / "crec_prayers.json").write_text(json.dumps(prayers, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        info["errors"].append(f"crec_prayers: {exc}")
    return info


def _read(name: str) -> str:
    path = RAW / name
    if not path.exists():
        return ""
    body = path.read_text(encoding="utf-8", errors="replace")
    return "" if "Access Denied" in body[:2000] else body


def _source(url: str, as_of: Optional[str], org: str) -> Dict[str, Any]:
    return {"url": url, "org": org, "grade": "official", "as_of": as_of}


def _card(chamber: str, spec: tuple, data: Optional[Dict[str, Any]], source: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    office_id, office_ko, office_en, kind = spec
    data = data or {}
    card = {
        "id": f"{chamber}_{office_id}",
        "chamber": chamber,
        "office_id": office_id,
        "office_ko": office_ko,
        "office_en": office_en,
        "kind": kind,
        "role_ko": ROLE_KO.get(office_id),
        "name_en": data.get("name_en"),
        "since": data.get("since"),
        "appointment": data.get("appointment"),
        "appointment_ko": APPOINTMENT_KO.get(data.get("appointment") or ""),
        "source": source if data.get("name_en") else None,
        "vacant": False,
        "stale": False,
    }
    for extra in ("denomination", "predecessor_en", "party_abbr", "state", "since_year", "congress"):
        if data.get(extra):
            card[extra] = data[extra]
    if not card["name_en"]:
        card["ui_ko"] = "미확인 (공석 아님)"
    return card


def build_house(as_of: str, prayers: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards = []
    for spec in HOUSE_OFFICES:
        office_id = spec[0]
        slug, url = HOUSE_HISTORY[office_id]
        data = parse_house_history(_read(f"house_history_{slug}.html"))
        source = _source(url, as_of, "Office of the Historian, U.S. House")
        if office_id == "clerk":
            xml_name = parse_clerk_xml(_read("MemberData.xml"))
            if xml_name and data:
                data["clerk_xml_name"] = xml_name
        card = _card("house", spec, data, source)
        if office_id == "clerk" and data and data.get("clerk_xml_name"):
            card["confirmations"] = [{"org": "Clerk of the House", "url": CLERK_XML_URL, "name_as_printed": data["clerk_xml_name"]}]
        if office_id == "chaplain":
            footer = parse_house_chaplain_page(_read("house_chaplain.html"))
            confirmations = []
            if footer:
                confirmations.append({"org": "Office of the House Chaplain", "url": HOUSE_CHAPLAIN_URL, "name_as_printed": footer})
            prayer = prayers.get("house")
            if prayer:
                confirmations.append({"org": "Congressional Record (govinfo)", "url": prayer["url"], "date": prayer["date"], "name_as_printed": prayer["chaplain_en"]})
            if confirmations:
                card["confirmations"] = confirmations
        cards.append(card)
    return cards


def build_senate(as_of: str, prayers: Dict[str, Any], previous: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    leadership_html = _read("senate_leadership.html")
    leadership = parse_senate_leadership(leadership_html) if leadership_html else {}
    staff_html = _read("senate_officers_staff.html")
    staff = parse_senate_officers_staff(staff_html) if staff_html else {}
    party_html = _read("senate_party_secretaries.html")
    parties = parse_senate_party_secretaries(party_html) if party_html else {}
    chaplain_html = _read("senate_chaplain.html")
    chaplain = parse_senate_chaplain_table(chaplain_html) if chaplain_html else None

    found: Dict[str, Dict[str, Any]] = {}
    for office_id, row in leadership.items():
        found[office_id] = dict(row, _url=SENATE_PAGES["leadership"])
    for office_id, row in staff.items():
        found[office_id] = dict(row, _url=SENATE_PAGES["officers_staff"])
    party_map = {"majority_secretary": "R", "minority_secretary": "D"}
    for office_id, party in party_map.items():
        if parties.get(party):
            row = dict(found.get(office_id) or {}, **parties[party], _url=SENATE_PAGES["party_secretaries"])
            found[office_id] = row
    if chaplain:
        found["chaplain"] = dict(found.get("chaplain") or {}, **chaplain, _url=SENATE_PAGES["chaplain"])

    meta_path = RAW / "senate_fetch_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    cards = []
    for spec in SENATE_OFFICES:
        office_id = spec[0]
        data = found.get(office_id)
        if data:
            source = _source(data["_url"], meta.get("fetched_at") or as_of, "U.S. Senate")
            if meta.get("fetched_via"):
                source["fetched_via"] = meta["fetched_via"]
            card = _card("senate", spec, data, source)
        elif previous.get(f"senate_{office_id}", {}).get("name_en"):
            card = dict(previous[f"senate_{office_id}"])
            card["stale"] = True
            card["stale_note_ko"] = "이번 회차에 senate.gov를 받지 못해 직전 공식 값을 유지했다."
        else:
            card = _card("senate", spec, None, None)
        if office_id == "chaplain":
            prayer = prayers.get("senate")
            if prayer:
                card["confirmations"] = [{"org": "Congressional Record (govinfo)", "url": prayer["url"], "date": prayer["date"], "name_as_printed": prayer["chaplain_en"]}]
        cards.append(card)
    return cards


def load_previous() -> Dict[str, Dict[str, Any]]:
    if not OUT_PATH.exists():
        return {}
    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for chamber in ("house", "senate") for c in data.get(chamber) or []}


def build(as_of: Optional[str] = None) -> Dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    prayers_path = RAW / "crec_prayers.json"
    prayers = json.loads(prayers_path.read_text(encoding="utf-8")) if prayers_path.exists() else {}
    previous = load_previous()
    house = build_house(as_of, prayers)
    senate = build_senate(as_of, prayers, previous)
    all_cards = house + senate
    return {
        "schema": "usa_congress_officers_v1",
        "as_of": as_of,
        "generated_at": now_iso(),
        "policy_ko": POLICY_KO,
        "house": house,
        "senate": senate,
        "counts": {
            "cards": len(all_cards),
            "named": sum(1 for c in all_cards if c.get("name_en")),
            "stale": sum(1 for c in all_cards if c.get("stale")),
        },
        "sources": {
            "house_history": {k: v[1] for k, v in HOUSE_HISTORY.items()},
            "house_chaplain": HOUSE_CHAPLAIN_URL,
            "clerk_xml": CLERK_XML_URL,
            "senate": SENATE_PAGES,
            "congressional_record": "https://www.govinfo.gov/app/collection/crec",
        },
    }


def changes_between(old: Dict[str, Dict[str, Any]], new: Iterable[Dict[str, Any]]) -> List[str]:
    out = []
    for card in new:
        before = (old.get(card["id"]) or {}).get("name_en")
        if before != card.get("name_en"):
            out.append(f"{card['id']}: {before} -> {card.get('name_en')}")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args(argv)
    errors: List[str] = []
    if args.fetch:
        errors = run_fetch()["errors"]
    previous = load_previous()
    data = build()
    data["fetch_errors"] = errors
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "counts": data["counts"],
        "changes": changes_between(previous, data["house"] + data["senate"]),
        "fetch_errors": errors,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
