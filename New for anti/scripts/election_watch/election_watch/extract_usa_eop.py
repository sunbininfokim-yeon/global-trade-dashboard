"""Refresh USA White House / EOP senior roster from official pages.

Official White House HTML and the annual WHO staff PDF may update extracted
names. Media-grade fields (VP CoS, CEQ acting, CEA if only secondary) are
never filled in from press reports. Unknown stays null.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from election_watch.extract_usa_wh_advisors import classify_topical_advisors
from election_watch.extract_usa_wh_office_status import (
    CEA_URL,
    CEQ_URL,
    ONDCP_URL,
    apply_office_status,
    build_office_status,
    parse_cea_chair,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "usa"
OUT = ROOT / "config" / "extracted"
UA = "election-watch/1.0 (+global-trade-dashboard research)"

CABINET_URL = "https://www.whitehouse.gov/administration/cabinet/"
ADMIN_URL = "https://www.whitehouse.gov/administration/"
STAFF_PDF_NAME = "{year}-Annual-Report-to-Congress-on-White-House-Staff.pdf"

# Person pages confirmed on official .gov sites. Agency homepages or the White
# House cabinet roster are used only when a dedicated biography page was not
# found. Refresh keeps the URL only while the same name_en is still in office.
CABINET_OFFICIAL_URLS: Dict[str, str] = {
    "Scott Bessent": "https://home.treasury.gov/about/general-information/officials/scott-bessent",
    "Todd Blanche": "https://www.justice.gov/ag/staff-profile/meet-attorney-general",
    "Doug Burgum": "https://www.doi.gov/secretary-doug-burgum",
    "Jay Clayton": CABINET_URL,
    "Doug Collins": "https://department.va.gov/staff-biographies/douglas-a-collins/",
    "Sean Duffy": "https://www.transportation.gov/meet-secretary/us-transportation-secretary-sean-duffy",
    "Jamieson Greer": "https://ustr.gov/about/leadership/us-trade-representative/jamieson-greer-united-states-trade-representative",
    "Pete Hegseth": "https://www.defense.gov/About/Biographies/Biography/Article/4040890/hon-pete-hegseth/",
    "Robert F. Kennedy, Jr.": CABINET_URL,
    "Kelly Loeffler": "https://www.sba.gov/about-sba/organization/sba-leadership/",
    "Howard Lutnick": "https://www.commerce.gov/about/leadership/howard-lutnick",
    "Linda McMahon": "https://www.ed.gov/",
    "Markwayne Mullin": "https://www.dhs.gov/markwayne-mullin",
    "John Ratcliffe": "https://www.cia.gov/about/director-of-cia/",
    "Brooke Rollins": "https://www.usda.gov/our-agency/about-usda/our-secretary",
    "Marco Rubio": "https://www.state.gov/biographies/marco-rubio/",
    "Keith E. Sonderling": CABINET_URL,
    "Scott Turner": CABINET_URL,
    "Russ Vought": "https://www.whitehouse.gov/omb/",
    "Chris Wright": "https://www.energy.gov/person/chris-wright",
    "Lee Zeldin": "https://www.epa.gov/aboutepa/epa-administrator",
}
CORE_OFFICIAL_URLS: Dict[str, str] = {
    "Donald J. Trump": "https://www.whitehouse.gov/administration/donald-j-trump/",
    "JD Vance": "https://www.whitehouse.gov/administration/jd-vance/",
    "Susan S. Wiles": ADMIN_URL,
}

CABINET_PORTFOLIO: Dict[str, Dict[str, str]] = {
    "Secretary of the Treasury": {"portfolio_ko": "재무장관"},
    "Attorney General": {"portfolio_ko": "법무장관"},
    "Secretary of the Interior": {"portfolio_ko": "내무장관"},
    "Director of National Intelligence": {"portfolio_ko": "국가정보국장"},
    "Secretary of Veterans Affairs": {"portfolio_ko": "보훈장관"},
    "Secretary of Transportation": {"portfolio_ko": "교통장관"},
    "United States Trade Representative": {"portfolio_ko": "미국무역대표"},
    "Secretary of War": {"portfolio_ko": "전쟁장관"},
    "Secretary of Defense": {"portfolio_ko": "국방장관"},
    "Secretary of Health and Human Services": {"portfolio_ko": "보건복지장관"},
    "Administrator of the Small Business Administration": {"portfolio_ko": "중소기업청장"},
    "Secretary of Commerce": {"portfolio_ko": "상무장관"},
    "Secretary of Education": {"portfolio_ko": "교육장관"},
    "Secretary of Homeland Security": {"portfolio_ko": "국토안보장관"},
    "Director of the Central Intelligence Agency": {"portfolio_ko": "중앙정보국장"},
    "Secretary of Agriculture": {"portfolio_ko": "농무장관"},
    "Secretary of State": {"portfolio_ko": "국무장관"},
    "Secretary of Labor": {"portfolio_ko": "노동장관"},
    "Secretary of Housing and Urban Development": {"portfolio_ko": "주택도시개발장관"},
    "Director of the Office of Management and Budget": {"portfolio_ko": "관리예산처장"},
    "Secretary of Energy": {"portfolio_ko": "에너지장관"},
    "Administrator of the Environmental Protection Agency": {"portfolio_ko": "환경보호청장"},
}

SKIP_CABINET_TITLES = {
    "subscribe to the wh newsletter",
    "initiatives",
    "about",
    "media",
    "the cabinet",
}

# Longest unique title fragment first.
ASSISTANT_RULES: List[Tuple[str, str, str]] = [
    ("nsa", "NATIONAL SECURITY ADVISOR", "exclude:DEPUTY NATIONAL SECURITY"),
    ("nec_director", "DIRECTOR OF THE NATIONAL ECONOMIC COUNCIL", ""),
    ("dpc_director", "DIRECTOR OF THE DOMESTIC POLICY COUNCIL", ""),
    ("homeland_security_advisor", "HOMELAND SECURITY ADVISOR", ""),
    ("wh_counsel", "COUNSEL TO THE PRESIDENT", "exclude:ASSOCIATE COUNSEL"),
    ("press_secretary", "PRESS SECRETARY", "exclude:DEPUTY,ASSISTANT PRESS"),
    ("communications_director", "DIRECTOR OF COMMUNICATIONS", "exclude:DEPUTY"),
    ("wh_chief_of_staff", "CHIEF OF STAFF", "exclude:DEPUTY,FIRST LADY,VICE PRESIDENT"),
    ("oa", "DIRECTOR OF THE OFFICE OF ADMINISTRATION", ""),
    ("nedc", "NATIONAL ENERGY DOMINANCE COUNCIL", "require:EXECUTIVE DIRECTOR"),
    ("policy_assistant", "ASSISTANT TO THE PRESIDENT FOR POLICY", "exclude:ECONOMIC POLICY,DEPUTY"),
    ("cabinet_secretary", "CABINET SECRETARY", ""),
    ("legislative_affairs", "DIRECTOR OF LEGISLATIVE AFFAIRS", "exclude:DEPUTY"),
    ("staff_secretary", "STAFF SECRETARY", ""),
    ("border_czar", "BORDER CZAR", ""),
    ("trade_counselor", "SENIOR COUNSELOR FOR TRADE AND MANUFACTURING", ""),
    ("speechwriting", "DIRECTOR OF SPEECHWRITING", ""),
    ("flotus_cos", "CHIEF OF STAFF TO THE FIRST LADY", ""),
    ("peace_envoy", "SPECIAL ENVOY FOR PEACE MISSIONS", ""),
    ("dcos_operations", "DEPUTY CHIEF OF STAFF FOR OPERATIONS", ""),
    ("dcos_personnel", "DIRECTOR OF THE OFFICE OF PRESIDENTIAL PERSONNEL", ""),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> date:
    return date.today()


def write_json(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_tags(chunk: str) -> str:
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    return re.sub(r"\s+", " ", unescape(chunk)).strip()


def fetch(url: str, dest: Path, timeout: float = 40.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    curl = shutil.which("curl")
    if curl:
        result = subprocess.run(
            [curl, "-sL", "--max-time", str(int(timeout)), "-A", UA, "-o", str(dest), "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 200:
            code = (result.stdout or "").strip()
            if code.startswith("2"):
                return True
            dest.unlink(missing_ok=True)
            return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            dest.write_bytes(resp.read())
        return dest.exists() and dest.stat().st_size > 200
    except Exception:
        dest.unlink(missing_ok=True)
        return False


def heading_pairs(html: str) -> List[Tuple[str, str, str]]:
    parts = re.findall(r"<h([123])[^>]*>(.*?)</h\1>", html, flags=re.I | re.S)
    return [(lvl, strip_tags(body), body) for lvl, body in parts]


def parse_cabinet_html(html: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    pairs = heading_pairs(html)
    i = 0
    while i < len(pairs) - 1:
        lvl, name, _ = pairs[i]
        nxt_lvl, title, _ = pairs[i + 1]
        if lvl == "2" and nxt_lvl == "3":
            title_key = re.sub(r"\s+", " ", title).strip()
            acting = bool(re.search(r"\bActing\b", title_key, flags=re.I))
            title_norm = re.sub(r"^\s*Acting\s+", "", title_key, flags=re.I).strip()
            meta = CABINET_PORTFOLIO.get(title_norm)
            if meta and name.lower() not in SKIP_CABINET_TITLES and title_norm.lower() not in SKIP_CABINET_TITLES:
                row: Dict[str, Any] = {
                    "portfolio_ko": meta["portfolio_ko"],
                    "name_en": name,
                    "office_en": title_norm,
                }
                if acting:
                    row["status"] = "acting"
                    if "직무대행" not in row["portfolio_ko"]:
                        row["portfolio_ko"] = f"{row['portfolio_ko']} (직무대행)"
                rows.append(row)
            i += 2
            continue
        i += 1
    return rows


def parse_administration_html(html: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {"president": None, "vice_president": None}
    for lvl, text, _ in heading_pairs(html):
        if lvl != "2":
            continue
        m = re.match(r"President\s+(.+)$", text)
        if m:
            out["president"] = m.group(1).strip()
            continue
        m = re.match(r"Vice President\s+(.+)$", text)
        if m:
            out["vice_president"] = m.group(1).strip()
    return out


def staff_pdf_urls(year: Optional[int] = None) -> List[str]:
    year = year or today().year
    urls: List[str] = []
    for y in (year, year - 1):
        for month in range(1, 13):
            urls.append(
                f"https://www.whitehouse.gov/wp-content/uploads/{y}/{month:02d}/{STAFF_PDF_NAME.format(year=y)}"
            )
    return urls


def pdf_links_in_html(html: str) -> List[str]:
    found = []
    for href in re.findall(r'href="([^"]+)"', html):
        if "White-House-Staff" in href or "White-House-Office" in href:
            if href.startswith("/"):
                href = "https://www.whitehouse.gov" + href
            found.append(href)
    return found


def pdf_text(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required to parse the WHO staff PDF") from exc
    with pdfplumber.open(path) as doc:
        return "\n".join((page.extract_text() or "") for page in doc.pages)


def _titlecase_name_part(part: str) -> str:
    part = part.strip(" ,")
    if part.upper() in {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}:
        return part.title() if part[-1] == "." or len(part) <= 3 else part.upper()
    bits = []
    for token in part.split():
        if re.fullmatch(r"[A-Z]\.", token):
            bits.append(token)
        else:
            bits.append(token.capitalize())
    return " ".join(bits)


def payroll_name_to_display(last_first: str) -> str:
    raw = last_first.strip().rstrip(",")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    suffix = ""
    if len(parts) >= 3 and parts[1].upper().rstrip(".") in {"JR", "SR", "II", "III", "IV"}:
        last, suffix, first = parts[0], parts[1], ", ".join(parts[2:])
    elif len(parts) == 2:
        last, first = parts[0], parts[1]
        m = re.search(r"\s+(JR\.?|SR\.?|II|III|IV)$", first, flags=re.I)
        if m:
            suffix = m.group(1)
            first = first[: m.start()].strip()
    elif parts:
        return _titlecase_name_part(parts[0])
    else:
        return raw
    display = f"{_titlecase_name_part(first)} {_titlecase_name_part(last)}"
    if suffix:
        suffix_u = suffix.upper().rstrip(".")
        pretty = {"JR": "Jr.", "SR": "Sr.", "II": "II", "III": "III", "IV": "IV"}.get(suffix_u, suffix)
        display = f"{display}, {pretty}"
    return re.sub(r"\s+", " ", display).strip()


def parse_payroll_rows(text: str) -> List[Dict[str, Any]]:
    cleaned = re.sub(
        r"For Official Use Only(?:\s+Page \d+ of \d+)?(?:\s+For Official Use Only)?(?:\s+EXECUTIVE OFFICE OF THE PRESIDENT[\s\S]{0,200}?POSITION TITLE)?",
        " ",
        text,
    )
    lines = [re.sub(r"\s+", " ", line).strip() for line in cleaned.splitlines() if line.strip()]
    records: List[str] = []
    buf = ""
    start = re.compile(r"^[A-Z][A-Z0-9' .\-]+,\s+(?:JR\.,\s+)?[A-Z]")
    for line in lines:
        if start.match(line) and re.search(r"\b(EMPLOYEE|DETAILEE|PART-TIME DETAILEE)\b", line):
            if buf:
                records.append(buf)
            buf = line
        elif buf:
            buf = f"{buf} {line}"
    if buf:
        records.append(buf)
    row_re = re.compile(
        r"^(?P<name>.+?)\s+(?P<status>EMPLOYEE|DETAILEE|PART-TIME DETAILEE)\s+"
        r"\$(?P<salary>[\d,]+\.\d{2})\s+Per Annum\s+(?P<title>.+)$"
    )
    parsed: List[Dict[str, Any]] = []
    for rec in records:
        match = row_re.match(rec.strip())
        if not match:
            continue
        title = match.group("title").strip()
        parsed.append(
            {
                "payroll_name": match.group("name").strip(),
                "name_en": payroll_name_to_display(match.group("name")),
                "status": match.group("status"),
                "salary_usd": float(match.group("salary").replace(",", "")),
                "title": title,
                "title_u": title.upper(),
            }
        )
    return parsed


def parse_staff_pdf_text(text: str) -> Dict[str, Any]:
    as_of = None
    m = re.search(r"As of Date:\s+[A-Za-z]+,\s+([A-Za-z]+ \d{1,2}, \d{4})", text)
    if m:
        as_of = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()

    payroll_rows = parse_payroll_rows(text)
    parsed: List[Dict[str, Any]] = []
    for row in payroll_rows:
        title_u = row["title_u"]
        if "ASSISTANT TO THE PRESIDENT" not in title_u:
            continue
        if "DEPUTY ASSISTANT TO THE PRESIDENT" in title_u or "SPECIAL ASSISTANT TO THE PRESIDENT" in title_u:
            if not any(key in title_u for key in ("DEPUTY CHIEF OF STAFF", "CHIEF OF STAFF TO THE FIRST LADY")):
                continue
        parsed.append(row)

    matched: Dict[str, Dict[str, Any]] = {}
    for office_id, needle, extra in ASSISTANT_RULES:
        for row in parsed:
            title_u = row["title_u"]
            if needle not in title_u:
                continue
            if extra.startswith("exclude:"):
                banned = extra.split(":", 1)[1].split(",")
                if any(b and b in title_u for b in banned):
                    continue
            if extra.startswith("require:"):
                needed = extra.split(":", 1)[1]
                if needed not in title_u:
                    continue
            matched[office_id] = row
            break
    classified = classify_topical_advisors(payroll_rows)
    return {
        "as_of": as_of,
        "assistants": matched,
        "assistant_rows": parsed,
        "payroll_row_count": len(payroll_rows),
        "topical_advisors": classified["members"],
        "unscoped_senior_advisors": classified["unscoped_senior_advisors"],
        "topical_counts": classified["counts"],
        "topical_inclusion_ko": classified["inclusion_ko"],
        "topical_exclusion_ko": classified["exclusion_ko"],
    }


def load_eop() -> Dict[str, Any]:
    path = OUT / "usa_eop.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _set_name(row: Dict[str, Any], name: str, source: str) -> Optional[str]:
    old = row.get("name_en")
    if old == name:
        row["source"] = source
        return None
    row["name_en"] = name
    row["source"] = source
    if old:
        row.pop("note_ko", None)
    return f"{old} -> {name}"


def apply_official(
    eop: Dict[str, Any],
    *,
    cabinet: List[Dict[str, Any]],
    admin: Dict[str, Optional[str]],
    staff: Optional[Dict[str, Any]],
    cabinet_as_of: str,
    staff_source_id: Optional[str],
) -> List[str]:
    changes: List[str] = []
    eop["as_of"] = cabinet_as_of
    if staff and staff.get("as_of"):
        eop["payroll_as_of"] = staff["as_of"]

    core_by_id = {row.get("id"): row for row in eop.get("core") or [] if row.get("id")}
    if admin.get("president") and "president" in core_by_id:
        change = _set_name(core_by_id["president"], admin["president"], "wh_administration")
        if change:
            changes.append(f"core.president {change}")
    if admin.get("vice_president") and "vice_president" in core_by_id:
        change = _set_name(core_by_id["vice_president"], admin["vice_president"], "wh_administration")
        if change:
            changes.append(f"core.vice_president {change}")

    assistants = staff.get("assistants") if staff else {}
    if assistants.get("wh_chief_of_staff") and "wh_chief_of_staff" in core_by_id:
        change = _set_name(
            core_by_id["wh_chief_of_staff"],
            assistants["wh_chief_of_staff"]["name_en"],
            staff_source_id or "wh_staff_report",
        )
        if change:
            changes.append(f"core.wh_chief_of_staff {change}")

    def patch_list(items: Iterable[Dict[str, Any]], office_id: str, key: str) -> None:
        row = assistants.get(office_id)
        if not row:
            return
        for item in items:
            if item.get("id") != office_id:
                continue
            change = _set_name(item, row["name_en"], staff_source_id or "wh_staff_report")
            if row.get("salary_usd") == 0:
                item["wh_salary_usd"] = 0
            if change:
                changes.append(f"{key}.{office_id} {change}")

    patch_list(eop.get("assistants_to_the_president") or [], "nsa", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "nec_director", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "dpc_director", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "homeland_security_advisor", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "wh_counsel", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "press_secretary", "assistants")
    patch_list(eop.get("assistants_to_the_president") or [], "communications_director", "assistants")

    for office_id, field in (
        ("nsa", "staff_director"),
        ("nec_director", "director"),
        ("dpc_director", "director"),
        ("homeland_security_advisor", "advisor"),
        ("nedc", "executive_director"),
    ):
        row = assistants.get(office_id)
        if not row:
            continue
        for council in eop.get("councils") or []:
            cell = council.get(field)
            if not isinstance(cell, dict):
                continue
            mapped = {
                "nsa": "nsc",
                "nec_director": "nec",
                "dpc_director": "dpc",
                "homeland_security_advisor": "hsc",
                "nedc": "nedc",
            }
            if council.get("id") != mapped[office_id]:
                continue
            if cell.get("name_en") != row["name_en"]:
                changes.append(f"councils.{council['id']}.{field} {cell.get('name_en')} -> {row['name_en']}")
                cell["name_en"] = row["name_en"]

    omb = next((row for row in cabinet if row.get("portfolio_ko", "").startswith("관리예산처장")), None)
    if omb:
        for head in eop.get("eop_office_heads") or []:
            if head.get("id") == "omb" and head.get("name_en") != omb["name_en"]:
                changes.append(f"eop_office_heads.omb {head.get('name_en')} -> {omb['name_en']}")
                head["name_en"] = omb["name_en"]
                head["source"] = "wh_cabinet"
            if head.get("id") == "oa" and assistants.get("oa"):
                change = _set_name(head, assistants["oa"]["name_en"], staff_source_id or "wh_staff_report")
                if change:
                    changes.append(f"eop_office_heads.oa {change}")

    other_map = {
        "cabinet_secretary": "Cabinet Secretary",
        "legislative_affairs": "Director of Legislative Affairs",
        "staff_secretary": "Staff Secretary",
        "border_czar": "Border Czar",
        "trade_counselor": "Senior Counselor for Trade and Manufacturing",
        "policy_assistant": "Assistant to the President for Policy",
        "speechwriting": "Director of Speechwriting",
        "flotus_cos": "Chief of Staff to the First Lady",
        "peace_envoy": "Special Envoy for Peace Missions",
    }
    others = eop.get("other_assistants_to_the_president") or []
    for office_id, office_en in other_map.items():
        row = assistants.get(office_id)
        if not row:
            continue
        item = next((x for x in others if x.get("office_en") == office_en), None)
        if item is None:
            continue
        if item.get("name_en") != row["name_en"]:
            changes.append(f"other.{office_en} {item.get('name_en')} -> {row['name_en']}")
            item["name_en"] = row["name_en"]

    if staff and staff.get("topical_advisors") is not None:
        payload = {
            "schema": "usa_wh_topical_advisors_v1",
            "payroll_as_of": staff.get("as_of"),
            "source": staff_source_id or "wh_staff_report",
            "inclusion_ko": staff.get("topical_inclusion_ko"),
            "exclusion_ko": staff.get("topical_exclusion_ko"),
            "counts": staff.get("topical_counts"),
            "members": staff.get("topical_advisors") or [],
            "unscoped_senior_advisors": staff.get("unscoped_senior_advisors") or [],
        }
        prev = len((eop.get("topical_advisors") or {}).get("members") or [])
        eop["topical_advisors"] = payload
        changes.append(f"topical_advisors {prev} -> {len(payload['members'])}")

    eop["_cabinet_live"] = cabinet
    return changes


def merge_tier12(eop: Dict[str, Any]) -> None:
    path = OUT / "tier12_executives.json"
    tier = json.loads(path.read_text(encoding="utf-8"))
    usa = tier.setdefault("countries", {}).setdefault("USA", {})
    usa["coverage"] = "full_cabinet_plus_eop_senior"
    usa["generated_at"] = eop.get("as_of") or today().isoformat()
    usa["sources"] = [
        {"org": src.get("org"), "url": src.get("url"), "grade": src.get("grade"), "as_of": src.get("as_of")}
        for src in eop.get("sources") or []
        if str(src.get("url") or "").startswith("http")
    ]
    core_out = []
    for row in eop.get("core") or []:
        slim = {k: v for k, v in row.items() if k in {"office_ko", "name_en", "party_abbr", "status", "note_ko", "kr_analog", "official_url"} and v is not None}
        name = slim.get("name_en")
        if name and not slim.get("official_url") and CORE_OFFICIAL_URLS.get(name):
            slim["official_url"] = CORE_OFFICIAL_URLS[name]
        core_out.append(slim)
    usa["core"] = core_out
    if eop.get("_cabinet_live"):
        cabinet_out = []
        for row in eop["_cabinet_live"]:
            slim = {k: v for k, v in row.items() if k in {"portfolio_ko", "name_en", "status", "official_url"} and v is not None}
            name = slim.get("name_en")
            if name and CABINET_OFFICIAL_URLS.get(name):
                slim["official_url"] = CABINET_OFFICIAL_URLS[name]
            cabinet_out.append(slim)
        usa["cabinet"] = cabinet_out
    usa["white_house"] = {
        "assistants_to_the_president": eop.get("assistants_to_the_president"),
        "councils": eop.get("councils"),
        "eop_office_heads": eop.get("eop_office_heads"),
        "deputy_chiefs_of_staff": eop.get("deputy_chiefs_of_staff"),
        "other_assistants_to_the_president": eop.get("other_assistants_to_the_president"),
        "topical_advisors": eop.get("topical_advisors"),
        "office_status": eop.get("office_status"),
        "missing": eop.get("missing"),
        "correction": eop.get("correction"),
        "kr_analog_note_ko": eop.get("kr_analog_note_ko"),
        "payroll_as_of": eop.get("payroll_as_of"),
    }
    usa["source_conflicts_excluded"] = usa.get("source_conflicts_excluded") or []
    tier["generated_at"] = usa["generated_at"]
    write_json(path, tier)


def refresh_sources_block(eop: Dict[str, Any], staff_url: Optional[str], staff_as_of: Optional[str], as_of: str) -> None:
    sources = eop.setdefault("sources", [])
    by_id = {src.get("id"): src for src in sources if src.get("id")}
    by_id["wh_administration"] = {
        "id": "wh_administration",
        "org": "The White House",
        "url": ADMIN_URL,
        "grade": "official",
        "as_of": as_of,
    }
    by_id["wh_cabinet"] = {
        "id": "wh_cabinet",
        "org": "The White House Cabinet",
        "url": CABINET_URL,
        "grade": "official",
        "as_of": as_of,
    }
    if staff_url and staff_as_of:
        by_id["wh_staff_report"] = {
            "id": "wh_staff_report",
            "org": "White House Office",
            "url": staff_url,
            "local_raw": f"raw/usa/wh_staff_report_{staff_as_of}.pdf",
            "grade": "official",
            "as_of": staff_as_of,
        }
    by_id["wh_sacks_ai_crypto_official"] = {
        "id": "wh_sacks_ai_crypto_official",
        "org": "The White House",
        "url": "https://www.whitehouse.gov/wp-content/uploads/2025/06/David-Sacks.pdf",
        "grade": "official",
        "as_of": "2025-06",
        "note": (
            "Ethics waiver: David O. Sacks, special government employee, "
            "Special Advisor for AI and Crypto. Not on WHO 2026-07-01 payroll. "
            "Also America's AI Action Plan 2025-07; PCAST co-chair WH release 2026-03-25."
        ),
    }
    by_id["wh_cea"] = {
        "id": "wh_cea",
        "org": "Council of Economic Advisers",
        "url": CEA_URL,
        "grade": "official",
        "as_of": as_of,
    }
    by_id["wh_ondcp_confirm"] = {
        "id": "wh_ondcp_confirm",
        "org": "The White House",
        "url": "https://www.whitehouse.gov/releases/2026/01/sara-carter-confirmed-as-drug-czar/",
        "grade": "official",
        "as_of": "2026-01-06",
    }
    keep_ids = [
        "wh_staff_report",
        "wh_staff_report_2026-07-01",
        "wh_administration",
        "wh_cabinet",
        "wh_sacks_ai_crypto_official",
        "wh_cea",
        "wh_ondcp_confirm",
    ]
    ordered = []
    seen = set()
    for key in keep_ids:
        if key in by_id and key not in seen:
            ordered.append(by_id[key])
            seen.add(key)
    for src in sources:
        sid = src.get("id")
        if sid in seen:
            continue
        ordered.append(src)
        if sid:
            seen.add(sid)
    eop["sources"] = ordered


def run_fetch() -> Dict[str, Any]:
    RAW.mkdir(parents=True, exist_ok=True)
    cabinet_path = RAW / "wh_cabinet.html"
    admin_path = RAW / "wh_administration.html"
    cea_path = RAW / "wh_cea.html"
    ceq_path = RAW / "wh_ceq.html"
    ondcp_path = RAW / "wh_ondcp.html"
    result = {
        "cabinet_fetched": fetch(CABINET_URL, cabinet_path),
        "admin_fetched": fetch(ADMIN_URL, admin_path),
        "cea_fetched": fetch(CEA_URL, cea_path),
        "ceq_fetched": fetch(CEQ_URL, ceq_path),
        "ondcp_fetched": fetch(ONDCP_URL, ondcp_path),
        "staff_pdf": None,
        "staff_url": None,
    }
    html_bits = []
    if cabinet_path.exists():
        html_bits.append(cabinet_path.read_text(errors="replace"))
    if admin_path.exists():
        html_bits.append(admin_path.read_text(errors="replace"))
    candidates = pdf_links_in_html("\n".join(html_bits)) + staff_pdf_urls()
    # Prefer a previously known working URL first.
    known = "https://www.whitehouse.gov/wp-content/uploads/2026/07/2026-Annual-Report-to-Congress-on-White-House-Staff.pdf"
    ordered = []
    for url in [known, *candidates]:
        if url not in ordered:
            ordered.append(url)
    tmp = RAW / "wh_staff_report_latest.pdf"
    for url in ordered:
        if fetch(url, tmp):
            result["staff_url"] = url
            result["staff_pdf"] = str(tmp)
            break
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Download White House cabinet/admin/staff PDF")
    parser.add_argument("--merge-tier12", action="store_true", help="Write countries.USA into tier12_executives.json")
    parser.add_argument("--write-report", action="store_true", help="Write usa_eop_refresh_report_v1.json")
    args = parser.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    fetch_info: Dict[str, Any] = {}
    if args.fetch:
        fetch_info = run_fetch()

    cabinet_path = RAW / "wh_cabinet.html"
    admin_path = RAW / "wh_administration.html"
    staff_path = Path(fetch_info["staff_pdf"]) if fetch_info.get("staff_pdf") else RAW / "wh_staff_report_latest.pdf"
    if not staff_path.exists():
        dated = sorted(RAW.glob("wh_staff_report_*.pdf"))
        if dated:
            staff_path = dated[-1]

    cabinet: List[Dict[str, Any]] = []
    admin: Dict[str, Optional[str]] = {}
    staff: Optional[Dict[str, Any]] = None
    errors: List[str] = []

    if cabinet_path.exists():
        cabinet = parse_cabinet_html(cabinet_path.read_text(errors="replace"))
        if not cabinet:
            errors.append("cabinet_html_parsed_empty")
    elif args.fetch:
        errors.append("cabinet_fetch_failed")

    if admin_path.exists():
        admin = parse_administration_html(admin_path.read_text(errors="replace"))
    elif args.fetch:
        errors.append("admin_fetch_failed")

    staff_source_id = None
    if staff_path.exists():
        try:
            staff = parse_staff_pdf_text(pdf_text(staff_path))
            staff_source_id = "wh_staff_report"
            if staff.get("as_of"):
                dated = RAW / f"wh_staff_report_{staff['as_of']}.pdf"
                if staff_path.resolve() != dated.resolve():
                    shutil.copyfile(staff_path, dated)
        except Exception as exc:
            errors.append(f"staff_pdf_parse_failed:{exc}")
    elif args.fetch:
        errors.append("staff_pdf_not_found")

    eop = load_eop()
    as_of = today().isoformat()
    changes: List[str] = []
    if cabinet or admin or staff:
        changes = apply_official(
            eop,
            cabinet=cabinet,
            admin=admin,
            staff=staff,
            cabinet_as_of=as_of,
            staff_source_id=staff_source_id,
        )
        cea_html = ""
        ceq_html = ""
        cea_path = RAW / "wh_cea.html"
        ceq_path = RAW / "wh_ceq.html"
        if cea_path.exists():
            cea_html = cea_path.read_text(errors="replace")
        if ceq_path.exists():
            ceq_html = ceq_path.read_text(errors="replace")
        cea = parse_cea_chair(cea_html)
        office_status = build_office_status(as_of=as_of, cea=cea, ceq_html=ceq_html)
        changes.extend(apply_office_status(eop, office_status))
        refresh_sources_block(eop, fetch_info.get("staff_url"), (staff or {}).get("as_of"), as_of)
        live_cabinet = eop.pop("_cabinet_live", cabinet)
        write_json(OUT / "usa_eop.json", eop)
        if eop.get("topical_advisors") is not None:
            write_json(OUT / "usa_wh_topical_advisors.json", eop["topical_advisors"])
        write_json(OUT / "usa_wh_office_status.json", eop.get("office_status") or {})
        eop["_cabinet_live"] = live_cabinet
        if args.merge_tier12:
            merge_tier12(eop)
    elif args.merge_tier12:
        merge_tier12(eop)

    report = {
        "schema": "usa_eop_refresh_report_v1",
        "generated_at": now_iso(),
        "fetch_requested": bool(args.fetch),
        "fetch": fetch_info,
        "cabinet_count": len(cabinet),
        "staff_as_of": (staff or {}).get("as_of"),
        "assistant_ids": sorted(((staff or {}).get("assistants") or {}).keys()),
        "payroll_row_count": (staff or {}).get("payroll_row_count"),
        "topical_advisor_count": len((staff or {}).get("topical_advisors") or []),
        "unscoped_senior_advisor_count": len((staff or {}).get("unscoped_senior_advisors") or []),
        "topical_counts": (staff or {}).get("topical_counts"),
        "changes": changes,
        "errors": errors,
        "policy_ko": (
            "백악관 공식 HTML·WHO 연례 PDF만 인명을 갱신한다. "
            "부통령 비서실장·CEQ/CEA 언론 보도는 자동 승격하지 않는다. "
            "주제별 보좌관은 WHO 급여명부 직함의 포트폴리오 키워드로만 분류한다."
        ),
    }
    if args.write_report:
        write_json(OUT / "usa_eop_refresh_report_v1.json", report)
    print(json.dumps({k: report[k] for k in ("cabinet_count", "staff_as_of", "assistant_ids", "payroll_row_count", "topical_advisor_count", "unscoped_senior_advisor_count", "changes", "errors")}, ensure_ascii=False, indent=2))
    return 1 if errors and args.fetch else 0


if __name__ == "__main__":
    raise SystemExit(main())
