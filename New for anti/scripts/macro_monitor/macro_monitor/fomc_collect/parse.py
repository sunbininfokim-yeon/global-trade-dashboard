"""Extract structured facts from FOMC statement / Beige Book HTML.

Checked against many live pages before writing this, because the Fed is not
consistent about which shape a given release uses:

  Format B (rarer; has an explicit count): "...approved the following
  statement... by a 9 - 3 vote:" ... "Voting against the monetary policy
  action were [names], who preferred to raise..." (July 2026, 3 dissents;
  June 2026, unanimous "12 - 0").

  Format A (the common one): "Voting for the monetary policy action were
  [names]." with no vote count at all, sometimes followed by "Voting
  against this action was/were [names], who preferred to [verb]..." -- and
  that dissent clause can repeat, each group with its own reason and its
  own direction:

    "...who preferred to lower the target range... at this meeting; and
     Austan D. Goolsbee and Jeffrey R. Schmid, who preferred no change to
     the target range... at this meeting."           (2025-12-10)

  and can end with a third, unrelated notation:

    "Absent and not voting was Adriana D. Kugler."     (2025-07-30)

8 of the 13 meetings checked used Format A with a "Voting against" clause;
2 used Format A fully unanimous (no "Voting against" at all); only 3 used
Format B. Format A -- not B -- is the one this needs to actually parse well.

One real case (2026-04-29) nests a third kind of dissent ("who supported
maintaining... but did not support inclusion of an easing bias") that isn't
a rate-direction preference at all -- a policy-communication dissent, not
a policy-action one. That shape isn't handled; a meeting with it raises
rather than mis-filing it as an ordinary "preferred to X" dissent, since
folding it into tighter/easier would misstate what was actually contested.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

_VOTE_COUNT_RE = re.compile(
    r"approved the following statement.*?by an?\s+(\d+)\s*[-–—]\s*(\d+)\s+vote",
    re.IGNORECASE | re.DOTALL,
)
_SEMI_SPLIT_RE = re.compile(r";\s*")

# "Voting for..." and "Voting against..." are each captured up to a trailing
# boundary phrase rather than the next period -- every name in these lists
# has a middle initial ("Jerome H. Powell"), so a plain ".+?\." capture stops
# after the first "H." instead of the end of the sentence.
_VOTING_FOR_RE = re.compile(
    r"Voting for the monetary policy action (?:was|were)\s+(.+?)\s*\.\s*"
    r"(?=Voting against|Absent and not voting|For media inquiries|Implementation Note|Last Update|$)",
    re.IGNORECASE,
)
_VOTING_AGAINST_RE = re.compile(
    r"Voting against (?:the monetary policy action|this action) (?:was|were)\s+(.+?)\s*\.\s*"
    r"(?=Absent and not voting|For media inquiries|Implementation Note|Last Update|$)",
    re.IGNORECASE,
)
_ABSENT_RE = re.compile(
    r"Absent and not voting (?:was|were)\s+(.+?)\.",
    re.IGNORECASE,
)

# Within a "Voting against" capture, each dissent group is <names>, who
# preferred to <verb>... -- groups are joined by "; and " or ", and "
# ahead of the next name list, which is also how names within one group's
# own list are joined, so splitting has to walk group-by-group rather than
# split the whole string on one separator.
_DISSENT_GROUP_RE = re.compile(
    r"who preferred (to (raise|lower)|no change)([^,;.]*)",
    re.IGNORECASE,
)


def _clean_text(soup: BeautifulSoup) -> str:
    # Whole-page text rather than guessing at a content div's class -- tried
    # narrowing to a specific div first, but the Fed's template puts that
    # class on an element that doesn't contain the release body, silently
    # returning empty matches instead of an error. The regexes below are
    # specific enough (fixed phrases like "approved the following statement")
    # that scanning the full page is safe.
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _direction_label(verb: str | None) -> str:
    if not verb:
        return "other_public_dissent"  # "no change" -- opposed the move itself, not its size
    verb = verb.lower()
    if verb.startswith("raise"):
        return "tighter"
    if verb.startswith("lower"):
        return "easier"
    return "other_public_dissent"


def _split_names(blob: str) -> list[str]:
    # Two shapes show up here: the "Voting for" roster, which is
    # semicolon-separated because titled names carry their own comma
    # ("Jerome H. Powell, Chair"); and plain dissenter lists, which have no
    # titles and use an ordinary Oxford-comma list instead ("Beth M.
    # Hammack, Neel Kashkari, and Lorie K. Logan") -- confirmed on the
    # 2026-07-29 statement, where a semicolon-only split left "Hammack,
    # Kashkari," as one undivided token. Semicolons are tried first since
    # they're unambiguous; a comma-based split only runs when there wasn't
    # one to split on.
    tokens = _SEMI_SPLIT_RE.split(blob)
    if len(tokens) == 1 and "," in blob:
        tokens = re.split(r",\s*and\s+|,\s+|\s+and\s+", blob)
    out = []
    for token in tokens:
        name = re.sub(r"^and\s+", "", token.strip(), flags=re.IGNORECASE)
        # A two-name group inside one dissent clause ("Michelle W. Bowman
        # and Christopher J. Waller, who preferred...") has no semicolon
        # between them, so a lone "X and Y" that survived the split above
        # (the semicolon path doesn't touch "and") is split again here.
        for sub in re.split(r"\s+and\s+", name):
            # A single-name dissent group's blob is "Stephen I. Miran, "
            # (comma before "who preferred..." that _parse_against_clause's
            # slice keeps) -- stripped here rather than upstream, since the
            # comma is a real separator elsewhere (the Chair/Vice Chair
            # suffix, the Oxford-list case above) and only spurious here.
            sub = sub.strip().rstrip(",").strip()
            if sub:
                out.append(sub)
    return out


def _parse_against_clause(against_text: str) -> list[dict[str, str]]:
    dissenters: list[dict[str, str]] = []
    matches = list(_DISSENT_GROUP_RE.finditer(against_text))
    if not matches:
        return dissenters
    cursor = 0
    for m in matches:
        names_blob = against_text[cursor:m.start()]
        names_blob = re.sub(r"^[;,]\s*(?:and\s+)?", "", names_blob.strip())
        verb = m.group(2)  # 'raise' / 'lower' / None (for "no change")
        direction = _direction_label(verb)
        for name in _split_names(names_blob):
            dissenters.append({"name": name, "dissent_direction": direction})
        cursor = m.end()
    return dissenters


def parse_statement(html: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = _clean_text(soup)

    vote_match = _VOTE_COUNT_RE.search(text)
    for_count = int(vote_match.group(1)) if vote_match else None
    against_count = int(vote_match.group(2)) if vote_match else None

    voters: list[str] = []
    dissenters: list[dict[str, str]] = []

    voting_for_match = _VOTING_FOR_RE.search(text)
    if voting_for_match:
        voters = _split_names(voting_for_match.group(1))
        if for_count is None:
            for_count = len(voters)

    voting_against_match = _VOTING_AGAINST_RE.search(text)
    if voting_against_match:
        against_text = voting_against_match.group(1)
        group_matches = list(_DISSENT_GROUP_RE.finditer(against_text))
        # "who supported" (2026-04-29's third clause: "who supported
        # maintaining... but did not support inclusion of an easing bias")
        # is checked for on its own, not only when zero ordinary matches
        # exist -- 04-29 DOES have one ordinary "who preferred to lower"
        # match (Miran) before the qualified clause, so a
        # zero-matches-only check let that clause through uncounted and
        # silently dropped three real dissenters instead of raising.
        if not group_matches or "who supported" in against_text.lower():
            raise ValueError(
                f"{meeting_date}: found a 'Voting against' clause this parser can't "
                f"fully categorize (a qualified, non-rate-direction dissent, or one "
                f"with no 'who preferred to raise/lower/no change' at all) -- "
                f"check {source_url} by hand: {against_text[:300]!r}"
            )
        dissenters = _parse_against_clause(against_text)
        if against_count is None:
            against_count = len(dissenters)
    elif against_count is None:
        against_count = 0  # no "Voting against" sentence at all -- unanimous

    if vote_match and len(dissenters) != against_count:
        # Format B states its own count ("9 - 3 vote"); if the dissent
        # sentence didn't yield that many names, the sentence shape drifted
        # from what these regexes expect and a partial list would misreport
        # who dissented.
        raise ValueError(
            f"{meeting_date}: vote count says {against_count} dissents but "
            f"parsed {len(dissenters)} name(s) -- statement wording may have changed, "
            f"check {source_url} by hand"
        )

    parsed_ok = bool(voting_for_match or vote_match)
    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "vote_for": for_count,
        "vote_against": against_count,
        "dissenters": dissenters,
        "voters_for": voters,  # only populated when Format A's "Voting for" list was found
        "parsed_ok": parsed_ok,
    }


# Section headers the National Summary page's top-level narrative uses, in
# the order they appear. "Prices" (and sometimes "Labor Markets") repeats
# again per-district under "Highlights by Federal Reserve District" -- that
# boundary marks the end of the national narrative, not another section, so
# splitting stops there rather than picking up those per-district repeats
# as if they were more top-level sections.
_KNOWN_SECTIONS = ["Overall Economic Activity", "Labor Markets", "Prices", "Community Perspectives"]
_END_BOUNDARY = "Highlights by Federal Reserve District"


def parse_beige_book_summary(html: str, *, edition: str, source_url: str) -> dict[str, Any]:
    # Whole-page text, same reasoning as _clean_text above: a div-id guess
    # ("article", "content") matched nothing useful on this template and
    # silently produced zero sections instead of an error.
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    end_match = re.search(re.escape(_END_BOUNDARY), text)
    scan_end = end_match.start() if end_match else len(text)

    sections: list[dict[str, str]] = []
    pattern = "|".join(re.escape(h) for h in _KNOWN_SECTIONS)
    splits = list(re.finditer(pattern, text[:scan_end]))
    for i, m in enumerate(splits):
        start = m.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else scan_end
        body = text[start:end].strip(" \n:")
        if body:
            sections.append({"section": m.group(0), "text": body})

    return {
        "edition": edition,
        "source_url": source_url,
        "national_sections": sections,
        "parsed_ok": bool(sections),
    }
