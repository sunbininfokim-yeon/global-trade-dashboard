"""FOMC minutes: who voted which way, and how many participants said what.

Minutes come out three weeks after a decision (the calendar page prints the
actual date once they are out: "Minutes: ... (Released August 19, 2026)").
Two things in them are not anywhere else the dashboard reads:

* the named "Voting for this action" / "Voting against this action" lists.
  Since the 2026 chair transition the statement itself no longer names the
  "for" side, so the panel had to infer it from the roster; minutes name it.
* the participant-count wording of the discussion -- "Almost all", "Many",
  "Several", "Some", "A few" -- which is how the Fed itself signals how widely
  a view was held. Sentences are kept verbatim with their leading quantifier;
  nothing is scored, ranked by topic, or turned into a hawk/dove reading.

Only the two sections that carry that (Participants' Views..., Committee
Policy Actions) are kept; the full text stays at the source URL.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

_HEADINGS = {
    "participants' views on current conditions and the economic outlook": "participants_views",
    "committee policy actions": "policy_actions",
}

# (regex on the sentence start, key, group). Longest alternatives first.
_QUANTIFIERS: list[tuple[str, str, str]] = [
    (r"almost all", "almost all", "all"),
    (r"nearly all", "nearly all", "all"),
    (r"all", "all", "all"),
    (r"a large majority of", "a large majority of", "most"),
    (r"a majority of", "a majority of", "most"),
    (r"most", "most", "most"),
    (r"many", "many", "many"),
    (r"several", "several", "several"),
    (r"various", "various", "several"),
    (r"a number of", "a number of", "several"),
    (r"some", "some", "some"),
    (r"a few", "a few", "few"),
    (r"a couple of", "a couple of", "few"),
    (r"one", "one", "few"),
    (r"two", "two", "few"),
    (r"three", "three", "few"),
    (r"four", "four", "few"),
]
_QUANT_RES = [
    (re.compile(rf"^{pat}\s+(participants|members|of the participants|of the members)\b", re.I), key, group)
    for pat, key, group in _QUANTIFIERS
]
_UNQUANTIFIED_RE = re.compile(r"^(participants|members)\s+(?!who\b)", re.I)

# A sentence can end inside a closing quote ('... "will deliver price stability."
# Almost all members agreed ...'), so a quote after the period still counts.
_SENTENCE_SPLIT = re.compile(r'(?:(?<=[.!?])|(?<=[.!?]["”]))\s+(?=[A-Z"“])')
_SPLIT_NEXT_GROUP = re.compile(r"(?:,|;)?\s+and\s+(?=[A-Z])")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def minutes_url(meeting_date: str) -> str:
    return f"https://www.federalreserve.gov/monetarypolicy/fomcminutes{meeting_date.replace('-', '')}.htm"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace(" ", " ")).strip()


def _names(blob: str) -> list[str]:
    """Names in one list. Two shapes: the semicolon form used when titles ride
    along ("Jerome H. Powell, Chair; John C. Williams, Vice Chair; ...; and X.")
    and the plain Oxford-comma form ("A, B, and C")."""
    blob = blob.strip().rstrip(".").strip()
    if ";" in blob:
        parts = [re.sub(r"^and\s+", "", x.strip()) for x in blob.split(";")]
    else:
        parts = [x.strip() for x in re.split(r",\s*(?:and\s+)?|\s+and\s+", blob)]
    out = []
    for part in parts:
        name = re.sub(r",?\s*(?:Vice )?Chair(?:man)?$", "", part).strip()
        if name:
            out.append(name)
    return out


def _parse_against(body: str) -> list[dict[str, Any]]:
    """Dissenters, each with the reason of the "who ..." clause they belong to.

    A release can carry several clauses ("X, who preferred to lower ..., and A,
    B, and C, who supported maintaining ... but did not support an easing
    bias"), so the text is walked clause by clause: everything before a
    ", who " is that clause's names, and inside the clause text the next
    "and <Capitalized name>" starts the following group.
    """
    body = body.strip()
    if body.lower().startswith("none"):
        return []
    parts = body.split(", who ")
    if len(parts) == 1:
        return [{"name": n, "reason": None} for n in _names(parts[0])]
    groups: list[tuple[str, str]] = []  # (names blob, reason)
    names_blob = parts[0]
    for seg in parts[1:]:
        nxt = _SPLIT_NEXT_GROUP.search(seg)
        reason, following = (seg[: nxt.start()], seg[nxt.end():]) if nxt else (seg, "")
        groups.append((names_blob, reason.strip().rstrip(".")))
        names_blob = following
    out: list[dict[str, Any]] = []
    for blob, reason in groups:
        out.extend({"name": n, "reason": reason or None} for n in _names(blob))
    return out


def _sentence_quantifier(sentence: str) -> tuple[str, str] | None:
    for regex, key, group in _QUANT_RES:
        if regex.match(sentence):
            return key, group
    if _UNQUANTIFIED_RE.match(sentence):
        return "participants", "unqualified"
    return None


def parse_minutes(html: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find(id="article")
    if article is None:
        raise ValueError(f"{meeting_date}: no article body at {source_url}")

    section: str | None = None
    paragraphs: dict[str, list[str]] = {"participants_views": [], "policy_actions": []}
    voting_for: list[str] = []
    voting_against: list[dict[str, Any]] = []
    seen_against = False
    saw_heading = False

    for p in article.find_all("p"):
        if p.find_parent("blockquote") is not None:
            continue
        text = _norm(p.get_text(" ", strip=True))
        if not text:
            continue
        # A section heading is a leading <strong> followed by a line break (or
        # nothing): "<p><strong>Committee Policy Actions</strong><br/> In
        # support of ...". The heading and the section's first paragraph share
        # one <p>, so the remainder after the heading text is kept.
        lead = next((c for c in p.children if getattr(c, "name", None) or str(c).strip()), None)
        if lead is not None and getattr(lead, "name", None) == "strong":
            after = next((c for c in lead.next_siblings if getattr(c, "name", None) or str(c).strip()), None)
            heading = _norm(lead.get_text(" ", strip=True))
            if len(heading) < 120 and (after is None or getattr(after, "name", None) == "br"):
                saw_heading = True
                section = _HEADINGS.get(heading.lower())
                text = text[len(heading):].strip() if text.startswith(heading) else text
                if not text:
                    continue
        lowered = text.lower()
        if lowered.startswith("voting for this action"):
            # The first list is the policy vote; later ones belong to notation
            # votes or other actions recorded in the same minutes.
            if not voting_for:
                voting_for = _names(text.split(":", 1)[1])
            continue
        if lowered.startswith("voting against this action"):
            if not seen_against:
                seen_against = True
                voting_against = _parse_against(text.split(":", 1)[1])
            continue
        if section in paragraphs:
            paragraphs[section].append(text)

    if not saw_heading:
        raise ValueError(f"{meeting_date}: no section headings found at {source_url}")
    if not paragraphs["participants_views"] and not paragraphs["policy_actions"]:
        raise ValueError(f"{meeting_date}: neither section was found at {source_url}")

    statements: list[dict[str, str]] = []
    for name, paras in paragraphs.items():
        for para in paras:
            for sentence in _SENTENCE_SPLIT.split(para):
                hit = _sentence_quantifier(sentence.strip())
                if hit:
                    statements.append({
                        "section": name,
                        "quantifier": hit[0],
                        "group": hit[1],
                        "text": sentence.strip(),
                    })

    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "voting_for": voting_for,
        "voting_against": voting_against,
        "policy_actions_text": paragraphs["policy_actions"],
        "statements": statements,
    }


def parse_release_dates(calendar_html: str) -> dict[str, str]:
    """{decision_date: minutes_release_date} for every meeting whose minutes are out.

    Read from the Fed's own calendar page, which prints "Minutes: PDF | HTML
    (Released August 19, 2026)" under each meeting once published. The
    release is *usually* decision + 21 days but not always (2025-12-10 was
    released 12-30), so the printed date is used, never computed.
    """
    text = _norm(BeautifulSoup(calendar_html, "html.parser").get_text(" ", strip=True))
    year_marks = [(m.start(), int(m.group(1))) for m in re.finditer(r"(20\d{2}) FOMC Meetings", text)]
    meeting_re = re.compile(
        rf"(?P<m1>{_MONTHS})\s+(?P<d1>\d{{1,2}})(?:-(?:(?P<m2>{_MONTHS})\s+)?(?P<d2>\d{{1,2}}))?\*?\s+Statement:"
    )
    starts = list(meeting_re.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(starts):
        year = next((y for pos, y in reversed(year_marks) if pos < m.start()), None)
        if year is None:
            continue
        chunk = text[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        released = re.search(rf"Minutes:[^()]*\(Released ({_MONTHS}) (\d{{2}}), (\d{{4}})\)", chunk)
        if not released:
            continue
        end_month = m.group("m2") or m.group("m1")
        end_day = m.group("d2") or m.group("d1")
        try:
            decision = datetime.strptime(f"{end_month} {end_day} {year}", "%B %d %Y").date()
            release = datetime.strptime(
                f"{released.group(1)} {released.group(2)} {released.group(3)}", "%B %d %Y"
            ).date()
        except ValueError:
            continue
        out[decision.isoformat()] = release.isoformat()
    return out
