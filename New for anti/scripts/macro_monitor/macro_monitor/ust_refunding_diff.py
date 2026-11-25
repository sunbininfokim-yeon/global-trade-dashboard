"""Quarter-to-quarter wording changes in Treasury's quarterly refunding policy statement.

The refunding statement is where Treasury signals its next move -- 2026-11-04 dropped 'at least' from
'maintaining nominal coupon and FRN auction sizes for at least the next several quarters' and added that it
will 'engage with a variety of market participants'. This compares each section of the latest statement with
the same section of the previous one, word by word (the FOMC statement differ), and leaves the reading to the
reader. The opening paragraph (this refunding's amounts and dates) and the auction-size table change every
quarter by construction and are left out.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

from .fomc_collect.statement_diff import diff_operative_text

_CALENDAR = re.compile(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December|"
                       r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}|20\d{2})[.,;]?$")


def changed_word_count(segments: list[dict[str, Any]]) -> int:
    """Words touched by an insert/delete/replace, leaving out month names and years -- every statement
    moves its quarter forward, which is not a change of wording."""
    n = 0
    for seg in segments:
        if seg["op"] == "equal":
            continue
        for key in ("before", "after"):
            n += sum(1 for w in (seg.get(key) or "").split() if not _CALENDAR.match(w))
    return n

HEADERS_KO = {
    "NOMINAL COUPON AND FRN FINANCING": "이표채·FRN 발행", "TIPS FINANCING": "물가연동채(TIPS) 발행",
    "BILL ISSUANCE": "단기채 발행", "CASH BALANCE": "현금 잔고(TGA)", "BUYBACKS": "바이백",
    "SMALL-VALUE BUYBACKS": "소액 바이백", "OTHER ISSUES": "기타", "PLANNED ISSUANCE": "발행 계획",
}


def statement_text(page_html: str) -> str:
    m = re.search(r"<main.*?</main>", page_html, re.S)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", m.group(0) if m else page_html, flags=re.S)
    t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t)))
    i, j = t.find("WASHINGTON"), t.find("###")
    return t[i if i >= 0 else 0: j if j > 0 else len(t)].strip()


def sections(text: str) -> dict[str, str]:
    """{HEADER: body} for the statement's all-caps section headers; the opening paragraph is dropped."""
    names = "|".join(re.escape(h) for h in sorted(HEADERS_KO, key=len, reverse=True))
    parts = re.split(rf"\b({names})\b", text)
    out: dict[str, str] = {}
    for k in range(1, len(parts) - 1, 2):
        body = parts[k + 1].strip()
        # the auction-size table: 'The table below presents ... 2-Year 3-Year ... Jan-27 69 58 ...'
        body = re.sub(r"2-Year 3-Year 5-Year 7-Year 10-Year 20-Year 30-Year FRN(?: [A-Z][a-z]{2}-\d{2}(?: \d+){8})+", "[입찰 규모 표]", body)
        body = re.sub(r"The next quarterly refunding announcement.*$", "", body).strip()
        out[parts[k]] = body
    return out


def compare(prev: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    """prev/cur: {"date", "url", "text"}. Sections that changed, in the current statement's order."""
    a, b = sections(prev["text"]), sections(cur["text"])
    rows = []
    for h in b:
        if h not in a:
            rows.append({"header": h, "header_ko": HEADERS_KO.get(h, h), "new_section": True,
                         "segments": [{"op": "insert", "after": b[h]}], "changed_word_count": len(b[h].split())})
            continue
        segs = diff_operative_text(a[h], b[h])
        n = changed_word_count(segs)
        if n:
            rows.append({"header": h, "header_ko": HEADERS_KO.get(h, h), "segments": segs, "changed_word_count": n})
    for h in a:
        if h not in b:
            rows.append({"header": h, "header_ko": HEADERS_KO.get(h, h), "dropped_section": True,
                         "segments": [{"op": "delete", "before": a[h]}], "changed_word_count": len(a[h].split())})
    return {"previous": {k: prev[k] for k in ("date", "url")}, "current": {k: cur[k] for k in ("date", "url")},
            "sections": rows, "changed_word_count": sum(r["changed_word_count"] for r in rows)}
