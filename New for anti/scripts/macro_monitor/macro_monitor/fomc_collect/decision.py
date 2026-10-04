"""The policy action itself, read off a statement's own operative text.

The panel already showed the vote, the roster and the wording diff, but never
what the Committee actually did -- the 2026-09-16 hike (3-1/2 to 3-3/4 ->
3-3/4 to 4) appeared nowhere on it. The decision sentence is the same across
every collected statement: "The Committee decided to [raise|lower|maintain]
the target range for the federal funds rate [by 1/4 percentage point to |at]
<range> percent". Older statements put a clause before it and some use a
non-breaking hyphen inside the fractions, so the text is normalized first.

The prior range is derived from the statement's own stated change, not from
whichever meeting happens to precede it in our collection -- a meeting missing
from the collection (a statement whose dissent clause the parser refused)
would otherwise make "직전 범위" silently wrong.
"""

from __future__ import annotations

import re
from typing import Any

_HYPHENS = str.maketrans({"‑": "-", "‐": "-", "‒": "-", "–": "-"})

_DECISION_RE = re.compile(
    r"decided to (?P<action>raise|lower|maintain) the target range for the federal funds rate"
    r"(?: by (?P<step>[\d\-/ ]+?) percentage points?)?"
    r"(?: to| at) (?P<low>\d+(?:-\d/\d)?) to (?P<high>\d+(?:-\d/\d)?) percent",
    re.IGNORECASE,
)


def _frac(text: str) -> float:
    """'3-3/4' -> 3.75, '4' -> 4.0, '1/4' -> 0.25."""
    text = text.strip()
    if "-" in text:
        whole, frac = text.split("-", 1)
        return int(whole) + _frac(frac)
    if "/" in text:
        num, den = text.split("/", 1)
        return int(num) / int(den)
    return float(text)


def parse_decision(operative_text: str) -> dict[str, Any] | None:
    """Action, stated step, and the resulting target range; None if the
    decision sentence isn't found (never guessed from surrounding prose)."""
    text = operative_text.translate(_HYPHENS)
    match = _DECISION_RE.search(text)
    if not match:
        return None
    action = match.group("action").lower()
    low, high = _frac(match.group("low")), _frac(match.group("high"))
    step = _frac(match.group("step")) if match.group("step") else 0.0
    change_bp = {"raise": step, "lower": -step, "maintain": 0.0}[action] * 100
    prev_low = low - change_bp / 100
    prev_high = high - change_bp / 100
    return {
        "action": action,
        "change_bp": round(change_bp),
        "range_low": low,
        "range_high": high,
        "prior_range_low": prev_low,
        "prior_range_high": prev_high,
    }
