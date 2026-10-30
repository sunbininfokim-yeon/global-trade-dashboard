"""European Central Bank Governing Council: press release, monetary policy statement, account.

Three documents per monetary policy meeting:
  - the press release ("Monetary policy decisions") the afternoon of day 2: the three key rates,
    and in the March/June/September/December rounds the staff projections in prose;
  - the introductory statement read at the press conference (the Q&A after it is not read);
  - the "account" of the meeting, about four weeks later: the Governing Council's discussion in
    paragraphs, the attendance list with the voting members marked, and the one sentence that
    says how far members agreed with the President-designate's proposal.

The Governing Council does not publish votes. What it publishes is the wording of that sentence
("all members agreed", "almost all members supported") and, where members held another view,
a paragraph that starts "Some members ..." -- both are carried verbatim and nothing is inferred.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .common import collapse

BASE = "https://www.ecb.europa.eu"
CALENDAR_URL = f"{BASE}/press/calendars/mgcgc/html/index.en.html"
_MONTH_NUM = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                               "august", "september", "october", "november", "december"])}


def mopo_listing_url(year: int) -> str:
    return f"{BASE}/press/govcdec/mopo/{year}/html/index_include.en.html"


def accounts_listing_url(year: int) -> str:
    """The accounts' own listing: the combined "monetary policy decisions" listing lags it (the
    27 August 2026 account was on this one weeks before it reached the other)."""
    return f"{BASE}/press/accounts/{year}/html/index_include.en.html"


def statement_listing_url(year: int) -> str:
    return f"{BASE}/press/press_conference/monetary-policy-statement/{year}/html/index_include.en.html"


def _iso(text: str) -> str | None:
    m = re.search(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", text)
    if not m or m.group(2).lower() not in _MONTH_NUM:
        return None
    return f"{m.group(3)}-{_MONTH_NUM[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def _sentences(paragraph: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", collapse(paragraph)) if s]


# --------------------------------------------------------------------------
# listings
# --------------------------------------------------------------------------

def parse_listing(html: str) -> list[dict[str, str]]:
    """Rows of an index_include fragment: <dt isodate=...> then <dd><a href>. Returns
    {date, title, url, kind} with kind in press_release / statement / account (other rows, such
    as the combined PDF, are left out)."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        a = dd.find("a") if dd else None
        if a is None or not dt.get("isodate"):
            continue
        href = a["href"].split("?")[0]
        title = collapse(a.get_text(" ", strip=True))
        if not href.endswith(".en.html"):
            continue
        if "/press/pr/" in href and title == "Monetary policy decisions":
            kind = "press_release"
        elif "/monetary-policy-statement/" in href and re.search(r"/ecb\.is\d+", href):
            kind = "statement"
        elif "/press/accounts/" in href and title.startswith("Meeting of"):
            kind = "account"
        else:
            continue
        rows.append({"date": dt["isodate"], "title": title, "url": BASE + href, "kind": kind})
    return rows


def account_decision_date(title: str) -> str | None:
    """"Meeting of 22-23 July 2026" / "Meeting of 30 April-1 May 2025" -> the second day (the decision day)."""
    m = re.match(r"Meeting of (\d{1,2})(?: ([A-Za-z]+))?\s*[-–]\s*(\d{1,2}) ([A-Za-z]+) (\d{4})", collapse(title))
    if not m or m.group(4).lower() not in _MONTH_NUM:
        return None
    return f"{m.group(5)}-{_MONTH_NUM[m.group(4).lower()]:02d}-{int(m.group(3)):02d}"


# --------------------------------------------------------------------------
# press release
# --------------------------------------------------------------------------

def _body_paragraphs(soup: BeautifulSoup) -> list[tuple[str | None, str]]:
    """(h2 heading in force, paragraph text) for the paragraphs of the document body, in order.
    List items, the "***" rule, the tag disclaimer and the footer are not body."""
    main = soup.find("main") or soup
    out: list[tuple[str | None, str]] = []
    heading: str | None = None
    for el in main.find_all(["h1", "h2", "h3", "p"]):
        text = collapse(el.get_text(" ", strip=True))
        if el.name == "h2":
            if text == "European Central Bank":
                break
            heading = text
            continue
        if el.name != "p" or el.find_parent("li") is not None or not text:
            continue
        if text in ("***", "* * *") or text.startswith(("Disclaimer", "Reproduction is permitted")):
            continue
        out.append((heading, text))
    return out


_FACILITY = (("dfr", re.compile(r"deposit facility")), ("mro", re.compile(r"main refinancing operations")),
             ("mlf", re.compile(r"marginal lending facility")))


def parse_rates(paragraphs: list[str], *, whole_text: str | None = None) -> dict[str, Any]:
    """The three key rates and the move, from the "Key ECB interest rates" paragraphs.

    Every wording the Council has used lists the facilities and then the rates in the same order
    ("the deposit facility, the main refinancing operations and the marginal lending facility will
    be decreased to 3.25%, 3.40% and 3.65% respectively"; in June/July 2024 the order was MRO, MLF,
    DFR; in September 2024 the deposit rate and the other two came in separate sentences), so each
    sentence that carries rates assigns them to the facilities it names, in order of mention."""
    joined = " ".join(paragraphs)
    # the verb sits in the lead paragraph ("The Governing Council today decided to keep the three key
    # ECB interest rates unchanged"); on hold meetings the rates section itself only restates the levels
    whole = whole_text or joined
    verb = re.search(r"decided to (raise|lower|keep)", whole)
    if not verb:
        raise ValueError(f"no 'decided to raise/lower/keep' in: {whole[:200]!r}")
    bp = re.search(r"by (\d+) basis points", whole)
    rates: dict[str, float] = {}
    for s in _sentences(joined):
        found = [float(x) for x in re.findall(r"(\d\.\d\d)%", s)]
        if not found:
            continue
        named = sorted(((m.start(), key) for key, rx in _FACILITY for m in [rx.search(s)] if m))
        if len(named) == len(found):
            for (_, key), value in zip(named, found):
                rates[key] = value
    if set(rates) != {"dfr", "mro", "mlf"}:
        raise ValueError(f"could not read all three rates from: {joined[:300]!r}")
    action = {"raise": "raise", "lower": "lower", "keep": "maintain"}[verb.group(1)]
    change = 0 if action == "maintain" else (int(bp.group(1)) if bp else None)
    if change is None:
        raise ValueError("move without a stated size")
    change = change if action == "raise" else -change if action == "lower" else 0
    eff = re.search(r"(?:with effect from|take effect from) (\d{1,2} [A-Za-z]+ \d{4})", joined)
    return {
        "action": action,
        "change_bp": change,
        "dfr_pct": rates["dfr"], "mro_pct": rates["mro"], "mlf_pct": rates["mlf"],
        "prior_dfr_pct": round(rates["dfr"] - change / 100, 2),
        "effective_date": _iso(eff.group(1)) if eff else None,
    }


_PROJ_VALUE = re.compile(r"(-?\d\.\d)% (?:in|for) (\d{4})(?: and (\d{4}))?")


def parse_projections(paragraphs: list[str]) -> dict[str, dict[int, float]]:
    """Staff projections quoted in prose: "headline inflation averaging 3.0% in 2026, 2.5% in 2027
    and 2.1% in 2028", "excluding energy and food ... 2.5% in 2026 and 2027 and 2.2% in 2028",
    "growth at an average of 0.8% in 2026, 1.2% in 2027 and 1.5% in 2028".

    A sentence counts only when it gives at least three consecutive years; anything looser
    ("grow by 1.2% in 2025, revised up from the 0.9% expected in June") is left out rather than
    guessed at. Keys: hicp, core, gdp."""
    out: dict[str, dict[int, float]] = {}
    for p in paragraphs:
        for s in _sentences(p):
            pairs: list[tuple[int, float]] = []
            for m in _PROJ_VALUE.finditer(s):
                pairs.append((int(m.group(2)), float(m.group(1))))
                if m.group(3):
                    pairs.append((int(m.group(3)), float(m.group(1))))
            years = [y for y, _ in pairs]
            if len(pairs) < 3 or years != list(range(years[0], years[0] + len(years))):
                continue
            low = s.lower()
            if "excluding energy and food" in low:
                key = "core"
            elif "inflation" in low and "growth" not in low:
                key = "hicp"
            elif "growth" in low or "grow" in low or "economy" in low:
                key = "gdp"
            else:
                continue
            out.setdefault(key, dict(pairs))
    return out


def parse_press_release(html: str, *, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    date = None
    for p in main.find_all("p"):
        t = collapse(p.get_text())
        if re.fullmatch(r"\d{1,2} [A-Za-z]+ \d{4}", t):
            date = _iso(t)
            break
    if date is None:
        raise ValueError(f"no date on {url}")
    body = _body_paragraphs(soup)
    if not body or "Governing Council" not in " ".join(t for _, t in body):
        raise ValueError(f"not a monetary policy press release: {url}")
    key_paras = [t for h, t in body if h == "Key ECB interest rates"]
    lead = [t for h, t in body if h is None or h == "Monetary policy decisions"]
    texts = [t for _, t in body if not re.fullmatch(r"\d{1,2} [A-Za-z]+ \d{4}", t)]
    rates = parse_rates(key_paras or texts, whole_text=" ".join(texts))
    return {
        "meeting_date": date,
        "source_url": url,
        **rates,
        "paragraphs": texts,
        "lead_paragraphs": [t for t in lead if not re.fullmatch(r"\d{1,2} [A-Za-z]+ \d{4}", t)],
        "projections": {k: {str(y): v for y, v in d.items()} for k, d in parse_projections(texts).items()},
    }


# --------------------------------------------------------------------------
# introductory statement (press conference)
# --------------------------------------------------------------------------

def parse_statement(html: str, *, url: str) -> dict[str, Any]:
    """The prepared statement: from the dateline to "We are now ready to take your questions".
    The greeting paragraph is dropped; the Q&A is not read."""
    soup = BeautifulSoup(html, "html.parser")
    body = _body_paragraphs(soup)
    date = None
    start = None
    for i, (_, t) in enumerate(body):
        if date is None and re.search(r"\d{1,2} [A-Za-z]+ \d{4}$", t) and len(t) < 60:
            date, start = _iso(t), i + 1
            break
    if date is None or start is None:
        raise ValueError(f"no dateline on {url}")
    paras: list[dict[str, Any]] = []
    for heading, t in body[start:]:
        if t.startswith("We are now ready to take your questions"):
            break
        paras.append({"heading": heading if heading and not heading.startswith("Christine Lagarde") else None, "text": t})
    else:
        raise ValueError(f"no end of the prepared statement on {url}")
    if paras and re.match(r"^Good (afternoon|morning|evening)", paras[0]["text"]):
        paras = paras[1:]
    if len(paras) < 8:
        raise ValueError(f"statement too short on {url}")
    return {"meeting_date": date, "source_url": url, "paragraphs": paras}


# --------------------------------------------------------------------------
# account of the meeting
# --------------------------------------------------------------------------

_QUANT = re.compile(r"\b(almost all|all|most|many|some|a large majority of|a majority of)\s+members\b", re.I)
_AGREE = re.compile(r"\b(?:agreed|supported|concurred)\b")
_NOTE_LEAD = re.compile(r"^(?:(?:Some|Many|Most|Several|A few|A number of|A large number of) members\b|A dissenting view\b|One member\b)")


def _member(li_text: str) -> dict[str, Any]:
    t = collapse(li_text)
    voting = not t.split(",")[0].endswith("*")
    name = re.sub(r"^(Mr|Ms|Mrs|Dr)\s+", "", t.split(",")[0].rstrip("*").strip())
    role = t.split(",", 1)[1].strip() if "," in t else None
    return {"name": name, "role": role, "voting": voting}


def parse_account(html: str, *, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    h1 = main.find("h1")
    title = collapse(h1.get_text()) if h1 else ""
    decision_date = account_decision_date(title)
    if decision_date is None:
        raise ValueError(f"not an account page: {title!r} ({url})")
    released = None
    part: str | None = None
    heading: str | None = None
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    members: list[dict[str, Any]] = []
    footnote_seen = False
    next_release = None
    in_attendance = False
    for el in main.find_all(["h2", "h3", "p", "li"]):
        text = collapse(el.get_text(" ", strip=True))
        if not text:
            continue
        if el.name == "h2":
            if text == "European Central Bank":
                break
            part, heading, current, in_attendance = text, None, None, False
            continue
        if el.name == "h3":
            in_attendance = text.startswith("Meeting of the ECB")
            heading = text
            current = None if in_attendance else {"part": part, "heading": text, "paragraphs": []}
            if current:
                sections.append(current)
            continue
        if el.name == "li":
            if in_attendance and not footnote_seen:
                members.append(_member(text))
            continue
        if el.find_parent("li") is not None:
            continue
        if released is None and re.fullmatch(r"\d{1,2} [A-Za-z]+ \d{4}", text):
            released = _iso(text)
            continue
        if in_attendance:
            if text.startswith("* Members not holding"):
                footnote_seen = True
            m = re.search(r"next monetary policy account foreseen on (\d{1,2} [A-Za-z]+ \d{4})", text)
            if m:
                next_release = _iso(m.group(1))
            continue
        if current is None:
            current = {"part": part, "heading": None, "paragraphs": []}
            sections.append(current)
        current["paragraphs"].append(text)
    if not members or not sections or released is None:
        raise ValueError(f"account page not fully read (members {len(members)}, sections {len(sections)}, released {released}): {url}")
    if not any(not m["voting"] for m in members):
        # the asterisk marks the non-voting members; a page with none marked is one whose footnote we failed to see
        raise ValueError(f"no non-voting members marked on {url}")

    decision_section = next((s for s in sections if (s["heading"] or "").startswith("Monetary policy decisions and communication")), None)
    agreement = None
    notes: list[dict[str, str]] = []
    if decision_section:
        for para in decision_section["paragraphs"]:
            for s in _sentences(para):
                if agreement is None and "proposal" in s and _AGREE.search(s) and _QUANT.search(s):
                    agreement = {"quantifier": _QUANT.search(s).group(1).lower(), "sentence": s}
            first = _sentences(para)[0]
            if _NOTE_LEAD.match(first):
                notes.append({"lead": first, "text": para})
    return {
        "meeting_date": decision_date,
        "title": title,
        "released_on": released,
        "source_url": url,
        "sections": sections,
        "members": members,
        "agreement": agreement,
        "record_notes": notes,
        "next_account_release": next_release,
    }


# --------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------

def parse_calendar(html: str) -> list[dict[str, Any]]:
    """Monetary policy meetings on the Council's schedule: day 1, day 2 (the decision, with the
    press conference)."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    days: dict[str, dict[str, Any]] = {}
    rows = []
    for dt in main.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", collapse(dt.get_text()))
        if not m or dd is None:
            continue
        rows.append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", collapse(dd.get_text(" ", strip=True))))
    out = []
    prev_day1 = None
    for date, text in rows:
        if "monetary policy meeting" not in text:
            continue
        if "followed by press conference" in text:
            out.append({"decision_date": date, "day1": prev_day1})
            prev_day1 = None
        else:
            prev_day1 = date
    return out
