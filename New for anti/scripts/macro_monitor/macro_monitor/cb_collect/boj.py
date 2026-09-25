"""Bank of Japan Policy Board: statements, named votes, forecasts, release dates.

The statement on each Monetary Policy Meeting names who voted for and against
and prints the dissenters' own reasons, the members present, and the dates the
Summary of Opinions and the Minutes will come out -- so unlike the FOMC (whose
statements stopped naming the "for" side) nothing here has to be inferred.

Sources, all English, no key:
  /en/mopo/mpmdeci/state_YYYY/index.htm   list of decision documents (htm or pdf)
  /en/mopo/outlook/gorYYMMa.pdf           "The Bank's View" of the quarterly Outlook Report
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from .common import collapse, fetch_bytes, fetch_text, pdf_text, pdf_text_by_row

BASE = "https://www.boj.or.jp"
_DOC_HREF = re.compile(r"/k(\d{2})(\d{2})(\d{2})a\.(htm|pdf)$")
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]
OUTLOOK_MONTHS = (1, 4, 7, 10)


def statements_index_url(year: int) -> str:
    return f"{BASE}/en/mopo/mpmdeci/state_{year}/index.htm"


def parse_statements_index(html: str) -> list[dict[str, str]]:
    """Decision documents listed on a year's index page, newest first.

    Only the main document of a meeting (file name k<yymmdd>a) -- the "b/c/d"
    files are references (asset-purchase plans, framework reviews).
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _DOC_HREF.search(a["href"])
        if not m:
            continue
        iso = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if iso in seen:
            continue
        seen.add(iso)
        href = a["href"]
        out.append({
            "meeting_date": iso,
            "title": collapse(a.get_text(" ")).split(" [PDF")[0].strip(),
            "url": href if href.startswith("http") else BASE + href,
            "format": m.group(4),
        })
    return out


def fetch_statement_text(url: str) -> str:
    if url.endswith(".pdf"):
        return pdf_text(fetch_bytes(url, min_size=2000))
    html = fetch_text(url, min_size=3000)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(id="contents") or soup
    return body.get_text("\n")


# --------------------------------------------------------------------------
# One statement -> facts
# --------------------------------------------------------------------------

def flatten(text: str) -> str:
    """One-line text. Lines that are only a number are page numbers or footnote
    markers (the html text and the pdf text both carry them) and would otherwise
    land in the middle of a sentence."""
    lines = [ln for ln in (text or "").replace("\xa0", " ").splitlines() if not re.fullmatch(r"\s*\d{1,2}\s*", ln)]
    return re.sub(r"\bV oting\b", "Voting", collapse(" ".join(lines)))     # a PDF kerning artifact


_RATE_RE = re.compile(
    r"uncollateralized\s+overnight\s+call\s+rate\s+to\s+remain\s+at\s+around\s+(minus\s+)?(\d+(?:\.\d+)?)\s+percent", re.I)
_VOTE_RE = re.compile(
    r"decided,\s+by\s+(?:an?\s+)?(?:(\d+)\s*-\s*(\d+)\s+majority\s+vote|(unanimous)\s+vote),\s+to\s+(?:set|change)", re.I)
_FOR_RE = re.compile(r"Voting\s+for\s+the\s+action:\s*(.*?)\s*Voting\s+against\s+the\s+action:\s*", re.S)
_AGAINST_START = re.compile(r"Voting\s+against\s+the\s+action:\s*")


def _person(family_tokens: list[str], given: str) -> str:
    """'TAKA', 'TA' + 'Hajime' -> 'Takata Hajime' (the statement's own body style)."""
    return f"{''.join(family_tokens).title()} {given}"


def parse_names(blob: str) -> list[str]:
    """'UEDA Kazuo, HIMINO Ryozo, and SATO Ayano' -> ['Ueda Kazuo', 'Himino Ryozo', 'Sato Ayano'].

    Family name is written in capitals (and may carry a stray space when a PDF
    splits it), the given name is the last token.
    """
    blob = re.sub(r"\.\s*$", "", blob.strip())
    out: list[str] = []
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", blob):
        tokens = part.split()
        if len(tokens) < 2:
            continue
        out.append(_person(tokens[:-1], tokens[-1]))
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()]


def _proposal_rate(sentences: list[str]) -> float | None:
    for s in sentences:
        if "proposed" in s or "proposal" in s:
            m = _RATE_RE.search(s)
            if m:
                return -float(m.group(2)) if m.group(1) else float(m.group(2))
    return None


def parse_dissents(against_text: str, names: list[str]) -> list[dict[str, Any]]:
    """Each dissenter with their own reason and, when they moved an alternative
    rate, that rate. `against_text` is everything after the names in the
    'Voting against the action' note. When several members dissent, the
    alternative is often stated once for all of them ("They proposed that the
    Bank ... at around 1.0 percent"); that rate is given to each dissenter who
    did not state a different one."""
    sentences = _sentences(against_text)
    group_rate = _proposal_rate([s for s in sentences if s.startswith(("They ", "Both "))])
    out = []
    for name in names:
        idx = next((i for i, s in enumerate(sentences) if s.startswith(name)), None)
        mine: list[str] = []
        if idx is not None:
            mine.append(sentences[idx])
            for s in sentences[idx + 1:]:
                if any(s.startswith(other) for other in names if other != name):
                    break
                if s.startswith(("The proposal", "They ", "Both ", "Reference")):
                    break
                mine.append(s)
        own_rate = _proposal_rate(mine)
        out.append({
            "name": name,
            "reason": " ".join(mine) if mine else None,
            "proposal_rate_pct": own_rate if own_rate is not None else group_rate,
        })
    return out


def parse_members_present(text: str) -> list[str]:
    m = re.search(r"Policy Board members present:\s*(.*?)\s*\[Others present\]", text, re.S)
    if not m:
        return []
    names = []
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        mm = re.match(r"^([A-Z][A-Z' -]*[A-Z])\s+([A-Z][a-z]+)\b", ln)
        if mm:
            names.append(_person(mm.group(1).split(), mm.group(2)))
    return names


def _release_date(month_day: str, meeting: date) -> str | None:
    """'October 1' -> ISO date in the year that follows the meeting (releases never precede it)."""
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})", month_day.strip())
    if not m or m.group(1) not in _MONTHS:
        return None
    month, day = _MONTHS.index(m.group(1)) + 1, int(m.group(2))
    year = meeting.year + (1 if month < meeting.month else 0)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_releases(text: str, meeting: date) -> dict[str, str | None]:
    """Dates the Summary of Opinions and the Minutes come out, as the statement itself prints them."""
    flat = flatten(text)
    out: dict[str, str | None] = {"summary_of_opinions": None, "minutes": None}
    m = re.search(r"Summary of Opinions\s*--\s*\w+day,\s+([A-Za-z]+\s+\d{1,2})", flat)
    if m:
        out["summary_of_opinions"] = _release_date(m.group(1), meeting)
    m = re.search(r"Minutes of the Monetary Policy Meeting\s*--\s*\w+day,\s+([A-Za-z]+\s+\d{1,2})", flat)
    if m:
        out["minutes"] = _release_date(m.group(1), meeting)
    return out


def _cut(flat: str, pattern: str) -> str:
    m = re.search(pattern, flat)
    return flat[: m.start()] if m else flat


def parse_narrative(flat: str) -> str | None:
    """The Bank's own assessment paragraphs of a statement (economy, prices, risks,
    conduct of policy), without the decision boilerplate, the vote note or the
    attachment. None when the statement carries none (Outlook-Report months only
    print the decision; the assessment is then in the Outlook Report's 'Bank's View')."""
    m = re.search(r"Japan's (?:economy|economic)", flat)
    if not m:
        return None
    body = flat[m.start():]
    body = _cut(body, r"\[Note\s*\d*\]\s*(?:V\s?oting|Voting)")
    body = _cut(body, r"(?:V\s?oting)\s+for\s+the\s+action")
    body = _cut(body, r"(?:Attachment\s+)?Economic Activity and Prices in Japan: Current Situation")
    body = _cut(body, r"\[Note\s*\d*\]\s*\S.{0,40}\s+(?:opposed|dissented)")
    body = _cut(body, r"\bReference\s+Meeting hours")
    body = re.sub(r"(?:\s*\[Note\s*\d*\]|\s*Attachment)\s*$", "", body).strip()
    return body if len(body) >= 800 else None


def parse_assessment_dissents(flat: str) -> list[dict[str, str]]:
    """Members who opposed the wording of the assessment (a separate vote from the rate):
    '[Note] Takata Hajime opposed the description regarding the outlook for prices, considering ...'"""
    out = []
    for m in re.finditer(r"([A-Z][a-z]+ [A-Z][a-z]+) (opposed[^.]*?considering[^.]*\.)", flat):
        out.append({"name": m.group(1), "text": collapse(m.group(1) + " " + m.group(2))})
    return out


def parse_statement(text: str, *, meeting_date: str, source_url: str, title: str = "") -> dict[str, Any]:
    flat = flatten(text)
    d = date.fromisoformat(meeting_date)

    vote = _VOTE_RE.search(flat)
    if not vote:
        raise ValueError(f"{meeting_date}: no policy-rate vote sentence at {source_url}")
    unanimous = bool(vote.group(3))
    n_for = n_against = None
    if not unanimous:
        n_for, n_against = int(vote.group(1)), int(vote.group(2))

    rate = _RATE_RE.search(flat)
    if not rate:
        raise ValueError(f"{meeting_date}: no guideline rate sentence at {source_url}")
    rate_pct = -float(rate.group(2)) if rate.group(1) else float(rate.group(2))

    present = parse_members_present(text)
    voted_for: list[str] = []
    against: list[dict[str, Any]] = []
    for_source = "statement"
    against_text = ""
    absent: list[str] = []
    fm = _FOR_RE.search(flat)
    if unanimous:
        # "decided, by a unanimous vote" prints no names: every member present voted for.
        # (A [Note] with names can still follow -- it then belongs to another decision in the
        # same statement, e.g. the JGB purchase plan, not to the rate.)
        voted_for = list(present)
        for_source = "unanimous_all_present"
    elif fm:
        voted_for = parse_names(fm.group(1))
        rest = flat[fm.end():]
        rest = _cut(rest, r"\bReference\s+Meeting hours")
        rest = _cut(rest, r"(?:Attachment\s+)?Economic Activity and Prices in Japan: Current Situation")
        head, _, tail = rest.partition(". ")          # names carry no periods
        against_names = parse_names(head)
        am = re.match(r"Absent:\s*([^.]*)\.\s*", tail)
        if am:
            absent = parse_names(am.group(1))
            tail = tail[am.end():]
        against = parse_dissents(tail, against_names)

    if not unanimous and (len(voted_for) != n_for or len(against) != n_against):
        raise ValueError(
            f"{meeting_date}: vote list {len(voted_for)}-{len(against)} does not match "
            f"the stated {n_for}-{n_against} at {source_url}")

    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "title": title,
        "guideline_rate_pct": rate_pct,
        "unanimous": unanimous,
        "vote_for_count": len(voted_for),
        "vote_against_count": len(against),
        "voting_for": voted_for,
        "voting_for_source": for_source,
        "voting_against": against,
        "assessment_dissents": parse_assessment_dissents(flat),
        "members_present": present,
        "members_absent": absent,
        "releases": parse_releases(text, d),
        "narrative": parse_narrative(flat),
    }


# --------------------------------------------------------------------------
# Outlook Report ("The Bank's View"): Policy Board forecasts + summary
# --------------------------------------------------------------------------

def outlook_url(meeting_date: str) -> str:
    return f"{BASE}/en/mopo/outlook/gor{meeting_date[2:4]}{meeting_date[5:7]}a.pdf"


_NUM = r"[+-]?\d+\.\d"
_CELL = re.compile(rf"({_NUM})\s+to\s+({_NUM})\s*\[({_NUM})\]|({_NUM})")
_VARIABLES = ("real_gdp", "cpi", "core_cpi")


def _cells(part: str) -> list[dict[str, Any]]:
    """Three cells in printed order (real GDP, CPI, core CPI). A cell is normally
    'lo to hi [median]'; a fiscal year that has already ended prints a bare figure."""
    out = []
    for m in _CELL.finditer(part):
        if m.group(4) is not None:
            out.append({"median": float(m.group(4)), "range_low": None, "range_high": None, "single": True})
        else:
            out.append({"median": float(m.group(3)), "range_low": float(m.group(1)),
                        "range_high": float(m.group(2)), "single": False})
    return out


def parse_forecast_table(row_text: str) -> dict[str, Any] | None:
    """'Forecasts of the Majority of the Policy Board Members' (the BOJ's SEP counterpart).

    Per fiscal year: real GDP, CPI (all items less fresh food) and the reference
    core CPI, each as the range covering the majority of members and the median
    (in brackets in the report), next to the same figures from the previous
    Outlook Report where there is one (a newly added fiscal year has none).
    Returned as printed -- the ranges are the report's, not ours.
    """
    flat = flatten(row_text)
    i = flat.find("Forecasts of the Majority")
    seg = flat[i:] if i >= 0 else flat
    seg = seg.split("Notes:")[0]
    years = []
    made_in = None
    blocks = re.split(r"(?=Fiscal\s+\d{4}\b)", seg)
    for block in blocks:
        head = re.match(r"Fiscal\s+(\d{4})\b", block)
        if not head:
            continue
        cur_part, _, prior_part = re.split(r"(Forecasts\s+made\s+in\s+[A-Za-z]+\s+\d{4})", block, maxsplit=1) \
            if "Forecasts made in" in re.sub(r"\s+", " ", block) else (block, "", "")
        m = re.search(r"Forecasts\s+made\s+in\s+([A-Za-z]+\s+\d{4})", block)
        cur = _cells(cur_part[head.end():])
        if len(cur) != 3:
            continue
        row = {"fiscal_year": int(head.group(1)), **{v: cur[k] for k, v in enumerate(_VARIABLES)}, "prior": None}
        prior = _cells(prior_part)
        if m and len(prior) == 3:
            made_in = made_in or m.group(1)
            row["prior"] = {v: prior[k] for k, v in enumerate(_VARIABLES)}
        years.append(row)
    if not years:
        return None
    return {"prior_made_in": made_in, "years": years}


def parse_bank_view_summary(text: str) -> str | None:
    """The Summary bullets that open 'The Bank's View' (outlook, prices, risks, balance of risks)."""
    flat = flatten(text)
    m = re.search(r"\bSummary\s+", flat)
    if not m:
        return None
    body = flat[m.end():]
    body = _cut(body, r"\bI\.\s+Current Situation of Economic Activity")
    body = body.replace("\u26ab", "").strip()   # bullet glyph
    return body if len(body) >= 500 else None


OUTLOOK_INDEX = f"{BASE}/en/mopo/outlook/index.htm"


def parse_outlook_index(html: str) -> list[str]:
    """URLs of every "The Bank's View" PDF (gorYYMMa.pdf) on the Outlook Report index."""
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        if re.search(r"/gor\d{4}a\.pdf$", a["href"]):
            urls.append(a["href"] if a["href"].startswith("http") else BASE + a["href"])
    return urls


def _first_page_date(text: str) -> str | None:
    m = re.match(r"\s*([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", flatten(text)[:60])
    if not m or m.group(1) not in _MONTHS:
        return None
    return date(int(m.group(3)), _MONTHS.index(m.group(1)) + 1, int(m.group(2))).isoformat()


def fetch_bank_view(meeting_date: str, outlook_urls: list[str]) -> dict[str, Any] | None:
    """The Bank's View released with this meeting's statement, or None when this
    meeting had no Outlook Report. The report is named for the month of the cycle
    (the 2025-05-01 meeting released 'April 2025'), so a candidate is accepted
    only when the date printed on its first page is the meeting date."""
    want = (int(meeting_date[2:4]), int(meeting_date[5:7]))
    for url in outlook_urls:
        m = re.search(r"/gor(\d{2})(\d{2})a\.pdf$", url)
        yy, mm = int(m.group(1)), int(m.group(2))
        if (yy, mm) not in (want, (want[0], want[1] - 1) if want[1] > 1 else (want[0] - 1, 12)):
            continue
        data = fetch_bytes(url, min_size=20000)
        text = pdf_text(data)
        if _first_page_date(text) != meeting_date:
            continue
        return {
            "source_url": url,
            "summary": parse_bank_view_summary(text),
            "forecasts": parse_forecast_table(pdf_text_by_row(data)),
        }
    return None


# --------------------------------------------------------------------------
# Meeting calendar
# --------------------------------------------------------------------------

SCHEDULE_URL = f"{BASE}/en/mopo/mpmsche_minu/index.htm"
_MON3 = {m[:3]: i for i, m in enumerate(_MONTHS, start=1)}


def _cell_date(text: str, year: int) -> str | None:
    """'Oct. 30 (Fri.)' -> ISO date; 'Jan. 27 (Wed.), 2027' carries its own year; '-' / 'To be announced' -> None."""
    m = re.match(r"\s*([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2})\b(?:[^,]*?,\s*(\d{4}))?", text)
    if not m or m.group(1) not in _MON3:
        return None
    try:
        return date(int(m.group(3) or year), _MON3[m.group(1)], int(m.group(2))).isoformat()
    except ValueError:
        return None


def parse_schedule(html: str) -> list[dict[str, Any]]:
    """Every Monetary Policy Meeting on the calendar page: its two days, the decision
    day, and the planned release dates (Outlook Report, Summary of Opinions, Minutes).
    A date the Bank has not fixed yet is None, never a guess."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.find_all("table"):
        cap = table.find("caption")
        ym = re.search(r"(20\d{2})", cap.get_text() if cap else "")
        if not ym:
            continue
        year = int(ym.group(1))
        for tr in table.find_all("tr"):
            tds = [collapse(td.get_text(" ")) for td in tr.find_all("td")]
            if len(tds) < 4:
                continue
            first = _cell_date(tds[0], year)
            if not first:
                continue
            m = re.search(r",\s*(\d{1,2})\s*\(", tds[0])
            decision = f"{first[:8]}{int(m.group(1)):02d}" if m else first
            out.append({
                "meeting_days": [first, decision] if decision != first else [first],
                "decision_date": decision,
                "outlook_release": _cell_date(tds[1], year),
                "opinions_release": _cell_date(tds[2], year),
                "minutes_release": _cell_date(tds[3], year),
            })
    return sorted(out, key=lambda r: r["decision_date"])
