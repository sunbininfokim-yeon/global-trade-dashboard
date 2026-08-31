"""Word-level redline between two FOMC statements' operative text.

Fed-watchers read meeting-to-meeting wording changes ("solid" -> "moderate")
as a signal in their own right, independent of the vote count. This produces
that comparison directly from the statements' own text rather than a
sentiment score -- each segment is either unchanged, or a same-position
replacement/insertion/deletion, so nothing here asserts what a change means.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_WORD_RE = re.compile(r"\S+|\s+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def diff_operative_text(previous_text: str, current_text: str) -> list[dict[str, Any]]:
    """Segments describing how current_text differs from previous_text.

    Each segment is {"op": "equal"|"replace"|"insert"|"delete", "before": str, "after": str}.
    "before"/"after" are only populated on the sides relevant to that op, so a
    renderer can strike the "before" text and highlight the "after" text for
    a "replace" without checking op-specific field presence itself.
    """
    prev_tokens = _tokenize(previous_text)
    cur_tokens = _tokenize(current_text)
    matcher = SequenceMatcher(a=prev_tokens, b=cur_tokens, autojunk=False)
    segments: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        before = "".join(prev_tokens[i1:i2])
        after = "".join(cur_tokens[j1:j2])
        if tag == "equal":
            segments.append({"op": "equal", "text": after})
        elif tag == "replace":
            segments.append({"op": "replace", "before": before, "after": after})
        elif tag == "insert":
            segments.append({"op": "insert", "after": after})
        elif tag == "delete":
            segments.append({"op": "delete", "before": before})
    return segments


def changed_word_count(segments: list[dict[str, Any]]) -> int:
    """Count of non-whitespace words touched by a replace/insert/delete."""
    count = 0
    for seg in segments:
        if seg["op"] == "equal":
            continue
        for key in ("before", "after"):
            value = seg.get(key)
            if value:
                count += len([tok for tok in _WORD_RE.findall(value) if tok.strip()])
    return count
