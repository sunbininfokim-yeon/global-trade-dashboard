"""Bank of England Monetary Policy Committee: "Monetary Policy Summary and Minutes" pages.

One HTML page per meeting (/monetary-policy-summary-and-minutes/<year>/<month>-<year>),
published the day the decision is announced: the Summary (the Committee's assessment),
then the Minutes -- numbered paragraphs under h3 headings, the vote paragraph naming every
member, the attendance list, and (from November 2025) each member's own rationale grouped
by how they voted.

The vote is read from the vote paragraph and then checked twice: the head-count must equal
the tally the Summary states ("majority of 6-3"), and -- where the page has member-view
groups -- the groups must name the same people. A page that fails either check raises; a
wrong vote list is worse than a missing meeting.
"""

from __future__ import annotations

import re
import urllib.error
from typing import Any

from bs4 import BeautifulSoup

from .common import collapse, fetch_text

BASE = "https://www.bankofengland.co.uk"
DATES_URL = f"{BASE}/monetary-policy/upcoming-mpc-dates"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


class NotHeld(ValueError):
    """The page exists but the meeting has not happened yet (the Bank pre-creates a page for
    every scheduled month)."""


def meeting_slug(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]}-{year}"


def meeting_url(year: int, month: int) -> str:
    return f"{BASE}/monetary-policy-summary-and-minutes/{year}/{meeting_slug(year, month)}"


def fetch_meeting(year: int, month: int) -> str | None:
    """The page HTML, or None when the Bank has no page for that month (404: not a meeting month)."""
    try:
        return fetch_text(meeting_url(year, month), min_size=20000)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


# --------------------------------------------------------------------------
# rate sentence and vote paragraph
# --------------------------------------------------------------------------

_DECISION = re.compile(
    r"voted (?P<how>unanimously|by a majority of (?P<for>\d+)\s*[–\-]\s*(?P<against>\d+)) to "
    r"(?P<verb>maintain|reduce|increase) Bank Rate (?:by (?P<pp>[\d.]+) percentage points?, )?(?:at|to) (?P<rate>[\d.]+)%")


def parse_decision(tally_text: str) -> dict[str, Any]:
    """The Summary's opening sentence: "voted by a majority of 6-3 to maintain Bank Rate at 3.75%"
    / "voted unanimously to reduce Bank Rate by 0.25 percentage points, to 4%". The prior rate
    is the stated rate moved back by the stated change, so every meeting stands on its own."""
    m = _DECISION.search(collapse(tally_text))
    if not m:
        raise ValueError(f"no decision sentence in: {tally_text[:160]!r}")
    rate = float(m["rate"])
    change = float(m["pp"]) if m["pp"] else 0.0
    verb = m["verb"]
    prior = rate + change if verb == "reduce" else rate - change if verb == "increase" else rate
    unanimous = m["how"] == "unanimously"
    return {
        "action": {"maintain": "maintain", "reduce": "lower", "increase": "raise"}[verb],
        "rate_pct": rate,
        "prior_rate_pct": round(prior, 2),
        "change_bp": int(round((rate - prior) * 100)),
        "unanimous": unanimous,
        "tally_for": None if unanimous else int(m["for"]),
        "tally_against": None if unanimous else int(m["against"]),
    }


_PREF_RATE = re.compile(r"(?:at|to) ([\d.]+)%\s*\.?\s*$")


def _target(pref: str | None) -> float | None:
    """The rate a "preferring to ..." / "voted to ..." clause names ("... to 4%", "... unchanged, at 4.5%")."""
    if not pref:
        return None
    m = _PREF_RATE.search(pref.strip())
    return float(m.group(1)) if m else None


def _names(text: str | None) -> list[str] | None:
    if not text:
        return None
    return [n.strip() for n in re.split(r",\s*|\s+and\s+", text) if n.strip()]


def _sentences(paragraph: str) -> list[str]:
    return [s for s in re.split(r"(?<=\.)\s+(?=[A-Z])", collapse(paragraph)) if s]


def _check_count(word: str, names: list[str], sentence: str) -> None:
    n = _COUNTS.get(word.lower())
    if n is not None and n != len(names):
        raise ValueError(f"'{word} members' but {len(names)} names: {sentence[:140]!r}")


_S_FOR = re.compile(r"^(?P<cnt>\w+) members? (?:\((?P<names>[^)]*)\) )?voted in favour of (?:the|this) (?:first )?proposition(?: \((?P<names2>[^)]*)\))?\.?$")
_S_AGAINST = re.compile(r"^(?P<cnt>\w+) members? (?:\((?P<names>[^)]*)\) )?voted against (?:the|this) (?:first )?proposition(?:, preferring to (?P<pref>.+?))?\.?$")
_S_AGAINST_ONE = re.compile(r"^(?P<name>[A-Z][^,()]*?) voted against (?:the|this) (?:first )?proposition, preferring to (?P<pref>.+?)\.?$")
_S_PREF = re.compile(r"^(?P<cnt>\w+) members? (?:\((?P<names>[^)]*)\) )?(?:preferred|voted) (?:to )?(?P<pref>(?:reduce|increase|maintain|leave) Bank Rate.+?)\.?$")
_S_PREF_ONE = re.compile(r"^(?P<name>[A-Z][^,()]*?) preferred (?:to )?(?P<pref>(?:reduce|increase|maintain|leave) Bank Rate.+?)\.?$")


def parse_vote_paragraph(paragraph: str, *, rate_pct: float) -> dict[str, Any]:
    """Names on each side of one Bank Rate vote paragraph. A group that names the decided rate
    is the for-side; a group that names another rate is a set of dissenters with that rate.
    Not yet validated against the tally -- see `choose_vote`."""
    for_names: list[str] = []
    against: list[dict[str, Any]] = []
    notes: list[str] = []
    for s in _sentences(re.sub(r"^\d+[:.]\s+", "", collapse(paragraph))):
        m = _S_FOR.match(s)
        if m:
            names = _names(m["names"] or m["names2"]) or []
            _check_count(m["cnt"], names, s)
            for_names += names
            continue
        m = _S_AGAINST.match(s)
        if m:
            names = _names(m["names"])
            if names is None:               # "Three members voted against ..." -- the names follow as "preferred" sentences
                continue
            _check_count(m["cnt"], names, s)
            against += [{"name": n, "alt_rate_pct": _target(m["pref"])} for n in names]
            continue
        m = _S_AGAINST_ONE.match(s)
        if m:
            against.append({"name": m["name"].strip(), "alt_rate_pct": _target(m["pref"])})
            continue
        m = _S_PREF.match(s)
        if m:
            names = _names(m["names"])
            if names is None:
                continue
            _check_count(m["cnt"], names, s)
            target = _target(m["pref"])
            if target == rate_pct:
                for_names += names
            else:
                against += [{"name": n, "alt_rate_pct": target} for n in names]
            continue
        m = _S_PREF_ONE.match(s)
        if m:
            target = _target(m["pref"])
            if target == rate_pct:
                for_names.append(m["name"].strip())
            else:
                against.append({"name": m["name"].strip(), "alt_rate_pct": target})
            continue
        if "Bank Rate" in s:
            notes.append(s)
    return {"for": for_names, "against": against, "notes": notes}


_CAND = re.compile(r"voted in favour of the (?:first )?proposition|voted to (?:reduce|maintain|increase) Bank Rate")
_UNANIMOUS = re.compile(r"voted unanimously in favour of the (?:first )?proposition")


def choose_vote(paragraphs: list[str], decision: dict[str, Any]) -> dict[str, Any]:
    """The Bank Rate vote out of the "immediate policy decision" paragraphs.

    Most meetings have one vote paragraph. In August 2025 the Committee voted in two steps
    (a 4-4-1 split, then 5-4 for a 25bp cut once one member accepted it) and the tally the
    Summary quotes is the last step, so the candidate whose head-count matches the tally wins.
    Paragraphs about the second proposition (the gilt-stock vote) are not Bank Rate votes."""
    cands = [p for p in paragraphs if "second proposition" not in p and (_CAND.search(p) or _UNANIMOUS.search(p))]
    if decision["unanimous"]:
        if not any(_UNANIMOUS.search(p) for p in cands):
            raise ValueError("Summary says unanimous but no unanimous vote paragraph found")
        return {"kind": "unanimous", "for": None, "against": [], "notes": [], "earlier": []}
    problems = []
    for i in range(len(cands) - 1, -1, -1):
        parsed = parse_vote_paragraph(cands[i], rate_pct=decision["rate_pct"])
        if len(parsed["for"]) == decision["tally_for"] and len(parsed["against"]) == decision["tally_against"]:
            earlier = [collapse(p) for p in cands[:i]
                       if (lambda r: r["for"] or r["against"])(parse_vote_paragraph(p, rate_pct=decision["rate_pct"]))]
            return {"kind": "majority", **parsed, "earlier": earlier}
        problems.append(f"{len(parsed['for'])}-{len(parsed['against'])}")
    raise ValueError(f"vote paragraph(s) do not add up to the stated {decision['tally_for']}-{decision['tally_against']} "
                     f"(read {', '.join(problems) or 'nothing'})")


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

_GROUP = re.compile(r"^Votes? to (?P<verb>maintain|reduce|increase|leave) Bank Rate", re.I)
_PRESENT_NAME = re.compile(r"^(?P<name>[A-Z][A-Za-z.'’\- ]+?)(?:, (?P<role>Chair|Governor|Deputy Governor[^,]*))?$")
_MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}


def _iso(text: str) -> str | None:
    m = re.search(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", text)
    if not m or m.group(2).lower() not in _MONTH_NUM:
        return None
    return f"{m.group(3)}-{_MONTH_NUM[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def _items(start) -> list[tuple[str, str, Any]]:
    """h2/h3/p/li elements in document order after `start`, up to the page's news footer.
    A <p> inside an <li> is read once (through the li)."""
    out: list[tuple[str, str, Any]] = []
    for el in start.find_all_next(["h2", "h3", "p", "li"]):
        text = collapse(el.get_text(" ", strip=True))
        if el.name == "h2" and text.startswith("Other Monetary Policy Committee"):
            break
        if el.name == "h3" and text.startswith("Latest and upcoming"):
            break
        if el.name in ("p", "li") and el.find_parent("li") is not None and el.name == "p":
            continue
        if text:
            out.append((el.name, text, el))
    return out


def parse_meeting(html: str, *, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    summary_h2 = next((h for h in soup.find_all("h2") if collapse(h.get_text()).startswith("Monetary Policy Summary")), None)
    minutes_h2 = next((h for h in soup.find_all("h2") if collapse(h.get_text()).startswith("Minutes of the Monetary Policy Committee")), None)
    if summary_h2 is None or minutes_h2 is None:
        raise NotHeld(f"no Summary/Minutes on {url}")
    m_pub = re.search(r"Published on\s+(\d{1,2} [A-Za-z]+ \d{4})", soup.get_text(" ", strip=True))
    published = _iso(m_pub.group(1)) if m_pub else None
    if published is None:
        raise ValueError(f"no 'Published on' date on {url}")
    end = _iso(collapse(minutes_h2.get_text()))

    items = _items(summary_h2)
    split = next(i for i, (name, text, _) in enumerate(items) if name == "h2" and text.startswith("Minutes of the Monetary Policy Committee"))
    summary_items, minutes_items = items[:split], items[split + 1:]

    tally_text = next((t for n, t, _ in summary_items if n == "p" and "At its meeting ending on" in t), None)
    if tally_text is None:
        raise ValueError(f"no 'At its meeting ending on ...' paragraph in the Summary of {url}")
    decision = parse_decision(tally_text)
    summary_paragraphs = [t for n, t, _ in summary_items if n == "p" and t != tally_text and not t.startswith("Correction made")]

    sections: list[dict[str, Any]] = []
    present: list[dict[str, Any]] = []
    treasury_rep = None
    corrections: list[str] = []
    decision_paragraphs: list[str] = []
    views: list[dict[str, Any]] = []
    heading: str | None = None
    current: dict[str, Any] | None = None
    group: dict[str, Any] | None = None
    view: dict[str, Any] | None = None
    in_present = False

    def open_section(title: str | None) -> dict[str, Any]:
        sec = {"heading": title, "paragraphs": []}
        sections.append(sec)
        return sec

    for name, text, el in minutes_items:
        if name == "h3":
            heading, in_present, group, view = text, False, None, None
            current = open_section(text)
            continue
        if text.startswith("Correction made"):
            if text not in corrections:
                corrections.append(text)
            continue
        if text.startswith(("The Bank of England Act 1998", "Monetary Policy Committee voting history")) or re.match(r"^\(XLSX", text):
            continue
        is_views = heading is not None and heading.startswith("MPC members")
        if in_present:
            m_rep = re.match(r"^(?P<name>.+?) was (?:also )?present as the Treasury representative", text)
            if m_rep:
                treasury_rep = m_rep["name"].strip()
                continue
            if " was present" in text or " was also present" in text or " were present" in text:
                in_present = False
            else:
                mm = _PRESENT_NAME.match(text)
                if mm and len(text) < 60:
                    present.append({"name": mm["name"].strip(), "role": mm["role"]})
                    continue
                in_present = False
        if re.match(r"^(?:\d+[:.] )?The following members of the Committee were present", text):
            in_present = True
            continue
        if is_views and name == "p":
            strong = el.find("strong")
            whole = collapse(el.get_text(" ", strip=True))
            lead = collapse(strong.get_text(" ", strip=True)) if strong is not None else ""
            if lead and whole == lead and _GROUP.match(lead):
                group = {"label": lead, "action": _GROUP.match(lead)["verb"].lower(), "rate_pct": _target(lead)}
                view = None
                continue
            rest = whole[len(lead):] if lead and whole.startswith(lead) else None
            if rest is not None and (lead.endswith(":") or rest.lstrip().startswith(":")):
                who = lead.rstrip(" :").strip()
                view = {"name": who, "group": (group or {}).get("label"), "group_action": (group or {}).get("action"),
                        "group_rate_pct": (group or {}).get("rate_pct"), "paragraphs": [rest.lstrip(" :").strip()]}
                views.append(view)
                continue
            if view is not None:
                view["paragraphs"].append(text)
                continue
        m_num = re.match(r"^(\d+)[:.] (.*)$", text, re.S)
        if current is None:
            current = open_section(None)
        para = {"n": int(m_num[1]), "text": m_num[2].strip()} if m_num else {"n": None, "text": text}
        current["paragraphs"].append(para)
        if heading and heading.startswith("The immediate policy decision"):
            decision_paragraphs.append(para["text"])

    if not present:
        raise ValueError(f"no attendance list on {url}")

    vote = choose_vote(decision_paragraphs, decision)

    # every member's own rationale (from Nov 2025): the groups must name the people the vote paragraph names
    if views:
        group_for = sorted(v["name"] for v in views if v["group_rate_pct"] == decision["rate_pct"])
        group_against = sorted(v["name"] for v in views if v["group_rate_pct"] != decision["rate_pct"])
        if vote["kind"] == "majority":
            if group_for != sorted(vote["for"]) or group_against != sorted(a["name"] for a in vote["against"]):
                raise ValueError(f"member-view groups disagree with the vote paragraph on {url}")
        else:
            vote["for"], vote["for_source"] = group_for, "member_views"
    if vote["for"] is None:
        vote["for"], vote["for_source"] = [p["name"] for p in present], "unanimous_all_present"
    elif "for_source" not in vote:
        vote["for_source"] = "minutes_vote_paragraph"

    return {
        "meeting_date": published,
        "meeting_end_date": end,
        "source_url": url,
        **decision,
        "vote": vote,
        "summary_tally_text": tally_text,
        "summary_paragraphs": summary_paragraphs,
        "minutes": {"sections": [s for s in sections if s["paragraphs"] and not (s["heading"] or "").startswith("MPC members")],
                    "present": present, "treasury_representative": treasury_rep},
        "member_views": views,
        "corrections": corrections,
    }


# --------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------

def parse_calendar(html: str) -> dict[str, Any]:
    """The Bank's confirmed MPC dates: one table per year under "<year> confirmed dates", each row
    a Thursday and the documents due that day (a "Monetary Policy Report" marks a forecast round),
    plus "Next due: <date>"."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for h in soup.find_all("h2"):
        m = re.match(r"^(\d{4}) confirmed dates", collapse(h.get_text()))
        table = h.find_next("table") if m else None
        if not m or table is None:
            continue
        for tr in table.find_all("tr"):
            cells = [collapse(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
            d = re.search(r"(\d{1,2}) ([A-Za-z]+)", cells[0]) if cells else None
            if not d or d.group(2).lower() not in _MONTH_NUM:
                continue
            rows.append({"decision_date": f"{m.group(1)}-{_MONTH_NUM[d.group(2).lower()]:02d}-{int(d.group(1)):02d}",
                         "monetary_policy_report": "Monetary Policy Report" in " ".join(cells[1:])})
    nd = re.search(r"Next due:\s*(\d{1,2} [A-Za-z]+ \d{4})", soup.get_text(" ", strip=True))
    return {"rows": sorted(rows, key=lambda r: r["decision_date"]), "next_due": _iso(nd.group(1)) if nd else None}
