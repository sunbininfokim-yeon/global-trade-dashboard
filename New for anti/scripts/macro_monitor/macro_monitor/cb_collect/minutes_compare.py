"""Latest minutes against the previous ones: which topics the committee talked about more or less.

Deterministic and readable, not a hawk/dove score:
  * the minutes' own sentences, flattened from the collected file (no re-download);
  * a fixed topic lexicon per language, counted per 1,000 words (Korean: per 1,000 eojeol);
  * for the topics that rose most, one sentence from the new minutes that mentions the topic and
    does not appear in the previous minutes;
  * where the bank's minutes tag sentences by how many members held a view (FOMC 'Most/Some/A few',
    BoK '대다수/일부 위원'), the shares of each group.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

SKIP_KEYS = {"present", "absent", "page_url", "pdf_url", "hwp_url", "source_url", "released_on", "session_no"}

TOPICS_EN: list[tuple[str, str, str]] = [
    ("inflation", "물가", r"inflation|price pressures?|\bprices\b|disinflation"),
    ("wages", "임금", r"\bwages?\b|labou?r costs?|pay growth|earnings"),
    ("labor", "고용", r"employment|unemployment|labou?r market|\bjobs?\b|payrolls?"),
    ("growth", "성장·경기", r"economic activity|\bgrowth\b|\bGDP\b|\boutput\b|recession"),
    ("consumption", "소비", r"consumption|consumer spending|household spending"),
    ("investment", "투자", r"\binvestment\b|capital expenditure|business spending|capex"),
    ("housing", "부동산", r"housing|house prices|property|real estate|mortgage"),
    ("fx", "환율", r"exchange rates?|\byen\b|\bdollar\b|euro (?:exchange|appreciat|depreciat)|sterling|currenc|depreciat|appreciat"),
    ("trade", "관세·무역", r"tariffs?|trade polic|trade tension|\bexports?\b|\bimports?\b"),
    ("energy", "에너지", r"\benergy\b|\boil\b|gas prices|commodity prices"),
    ("finstab", "금융안정·여건", r"financial stability|financial conditions|\bcredit\b|bank lending|asset (?:prices|valuations)|valuations"),
    ("ai", "AI·반도체", r"artificial intelligence|\bAI\b|semiconductor|data cent"),
    ("uncertainty", "불확실성", r"uncertain"),
    ("easing", "완화·인하", r"\b(?:rate )?cuts?\b|reduc\w* (?:in )?(?:the )?(?:policy |bank |interest )?rates?|lower(?:ing)? (?:the )?(?:policy |bank )?rate|\beasing\b|accommodat"),
    ("tightening", "긴축·인상", r"\bhikes?\b|rais\w* (?:the )?(?:policy |bank |interest )?rates?|tighten|restrictive"),
]

TOPICS_KO: list[tuple[str, str, str]] = [
    ("inflation", "물가", r"물가|인플레이션"),
    ("wages", "임금", r"임금"),
    ("labor", "고용", r"고용|취업|실업"),
    ("growth", "성장·경기", r"성장|경기|GDP"),
    ("consumption", "소비", r"소비(?!자)|내수"),
    ("investment", "투자", r"투자"),
    ("housing", "부동산", r"부동산|주택|아파트"),
    ("fx", "환율", r"환율|원화|달러"),
    ("trade", "관세·무역", r"관세|수출|통상"),
    ("energy", "에너지", r"유가|에너지"),
    ("finstab", "금융안정·여건", r"금융안정|가계부채|가계대출|신용|금융여건|금융불균형"),
    ("ai", "AI·반도체", r"반도체|AI|인공지능"),
    ("uncertainty", "불확실성", r"불확실"),
    ("easing", "완화·인하", r"인하|완화"),
    ("tightening", "긴축·인상", r"인상|긴축"),
]


def sentences_of(x: Any, out: list[str] | None = None) -> list[str]:
    """Every sentence-length string in a collected minutes block, in document order."""
    out = [] if out is None else out
    if isinstance(x, str):
        if len(x) >= 30 and not x.startswith("http"):
            out += [s.strip() for s in re.split(r"(?<=[.!?。])\s+|(?<=음\.)\s*|(?<=다\.)\s*", x) if len(s.strip()) >= 15]
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in SKIP_KEYS:
                sentences_of(v, out)
    elif isinstance(x, list):
        for v in x:
            sentences_of(v, out)
    return out


def _words(sents: list[str]) -> int:
    return sum(len(s.split()) for s in sents)


def _groups(x: Any, out: Counter | None = None) -> Counter:
    """Counts of the 'group' tags some collectors attach to sentences (all / most / some / few)."""
    out = Counter() if out is None else out
    if isinstance(x, dict):
        if isinstance(x.get("group"), str) and isinstance(x.get("text"), str):
            out[x["group"]] += 1
        for v in x.values():
            _groups(v, out)
    elif isinstance(x, list):
        for v in x:
            _groups(v, out)
    return out


def compare(prev: dict[str, Any], cur: dict[str, Any], *, lang: str, min_words: int = 300) -> dict[str, Any] | None:
    """prev/cur: {"meeting_date", "released_on", "source_url", "body"} where body is the collected minutes."""
    ps, cs = sentences_of(prev["body"]), sentences_of(cur["body"])
    pw, cw = _words(ps), _words(cs)
    if pw < min_words or cw < min_words:
        return None
    topics = TOPICS_KO if lang == "ko" else TOPICS_EN
    flags = 0 if lang == "ko" else re.I
    prev_set = {re.sub(r"\s+", " ", s) for s in ps}
    rows = []
    for tid, ko, pat in topics:
        rx = re.compile(pat, flags)
        pn = sum(len(rx.findall(s)) for s in ps)
        cn = sum(len(rx.findall(s)) for s in cs)
        pr, cr = pn / pw * 1000, cn / cw * 1000
        new = [s for s in cs if rx.search(s) and re.sub(r"\s+", " ", s) not in prev_set]
        rows.append({"id": tid, "label_ko": ko, "prev_count": pn, "cur_count": cn,
                     "prev_per_1k": round(pr, 2), "cur_per_1k": round(cr, 2), "change_per_1k": round(cr - pr, 2),
                     "new_sentence": (min(new, key=len) if new else None)})
    rows.sort(key=lambda r: -abs(r["change_per_1k"]))
    # Example sentences only for the three topics that rose most.
    risers = {r["id"] for r in sorted(rows, key=lambda r: -r["change_per_1k"])[:3] if r["change_per_1k"] > 0}
    for r in rows:
        s = r["new_sentence"] if r["id"] in risers else None
        r["new_sentence"] = (s[:417] + "…") if s and len(s) > 420 else s
    pg, cg = _groups(prev["body"]), _groups(cur["body"])
    groups = None
    if sum(pg.values()) >= 5 and sum(cg.values()) >= 5 and len(set(pg) | set(cg)) >= 2:
        keys = sorted(set(pg) | set(cg), key=lambda g: -(pg[g] + cg[g]))
        groups = [{"group": g, "prev_share": round(pg[g] / sum(pg.values()) * 100, 1),
                   "cur_share": round(cg[g] / sum(cg.values()) * 100, 1)} for g in keys]
    return {
        "previous": {k: prev.get(k) for k in ("meeting_date", "released_on", "source_url")} | {"words": pw, "sentences": len(ps)},
        "current": {k: cur.get(k) for k in ("meeting_date", "released_on", "source_url")} | {"words": cw, "sentences": len(cs)},
        "unit_ko": "1,000단어당 언급" if lang == "en" else "1,000어절당 언급",
        "topics": rows,
        "groups": groups,
        "note_ko": ("고정된 주제 단어 목록의 언급 빈도를 직전 의사록과 비교한 것입니다. 많이 언급했다고 그 방향으로 "
                    "움직인다는 뜻은 아닙니다(성향 점수 아님). 예문은 이번 의사록에만 있는 문장 중 가장 짧은 것입니다."),
    }


def latest_two(meetings: list[dict[str, Any]], key: str) -> tuple[dict, dict] | None:
    ms = [m for m in sorted(meetings, key=lambda m: m["meeting_date"]) if m.get(key)]
    if len(ms) < 2:
        return None

    def pack(m: dict) -> dict:
        body = m[key]
        own = (body.get("page_url") or body.get("source_url")) if isinstance(body, dict) else None
        return {"meeting_date": m["meeting_date"],
                "released_on": body.get("released_on") if isinstance(body, dict) else None,
                "source_url": own or m.get("source_url"),
                "body": body}
    return pack(ms[-2]), pack(ms[-1])
