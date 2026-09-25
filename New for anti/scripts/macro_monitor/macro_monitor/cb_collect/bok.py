"""Bank of Korea Monetary Policy Board (금융통화위원회): decision, named dissent,
statement wording, calendar, roster, minutes.

Everything is read from bok.or.kr (Korean, no key). Four pieces:

  * the 통화정책방향 press release (board P0000559): the rate decision, the
    Committee's assessment, and -- since the February 2026 meeting -- one closing
    sentence with the vote ("위원 6명은 찬성하였으며, 황건일 위원은 ... 의견을 나타냈다").
    That sentence names only the *dissenters*; the members who voted for are not
    listed, so the for-side is the attendees of that meeting minus the dissenters.
  * the minutes (board B0000245, released ~19 days later): the attendee list.
  * the yearly meeting calendar (통화정책방향 결정회의 일정).
  * the members page (name, role, term).

The list pages are filled by an ajax call (listCont.do); the detail pages need a
menuNo or they answer 404.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from .common import collapse, fetch_bytes, fetch_text, pdf_text

BASE = "https://www.bok.or.kr"
LIST_URL = f"{BASE}/portal/singl/newsData/listCont.do"
SCHEDULE_URL = f"{BASE}/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755"
ROSTER_URL = f"{BASE}/portal/main/contents.do?menuNo=201696"
PRESS_BOARD, PRESS_MENU = "P0000559", "200690"      # 통화정책 보도자료
MINUTES_BOARD, MINUTES_MENU = "B0000245", "200789"   # 금융통화위원회 의사록


def detail_url(board: str, ntt_id: str, menu: str) -> str:
    return f"{BASE}/portal/bbs/{board}/view.do?nttId={ntt_id}&menuNo={menu}"


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------

def search_url(keyword: str, page: int = 1, page_unit: int = 100) -> str:
    q = {"pageIndex": str(page), "pageUnit": str(page_unit), "targetDepth": "4", "menuNo": "200789",
         "syncMenuChekKey": "0", "depthSubMain": "", "subMainAt": "", "searchCnd": "1", "searchKwd": keyword}
    return f"{LIST_URL}?{urllib.parse.urlencode(q)}"


def parse_search(html: str) -> list[dict[str, str]]:
    """Rows of a search result: title, board id, nttId, registration date (YYYY-MM-DD)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for li in soup.find_all("li"):
        a = li.find("a", href=re.compile(r"/portal/bbs/([A-Z]\d+)/view\.do\?nttId=(\d+)"))
        if not a:
            continue
        m = re.search(r"/portal/bbs/([A-Z]\d+)/view\.do\?nttId=(\d+)", a["href"])
        reg = re.search(r"등록일\s*(\d{4})\.(\d{2})\.(\d{2})", li.get_text(" "))
        rows.append({
            "title": collapse(a.get_text(" ")),
            "board": m.group(1),
            "ntt_id": m.group(2),
            "registered_on": f"{reg.group(1)}-{reg.group(2)}-{reg.group(3)}" if reg else "",
        })
    return rows


_DECISION_TITLE = re.compile(r"^통화정책방향\((\d{4})\.(\d{1,2})\.(\d{1,2})\)$")
_MINUTES_TITLE = re.compile(r"^금융통화위원회 의사록\((\d{4})년도? ?제(\d+)차\)\((\d{4})\.(\d{1,2})\.(\d{1,2})\)")


def decision_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Monetary-policy press releases (not the 의결사항 or blog rows that share the title) with their meeting date."""
    out = []
    for r in rows:
        m = _DECISION_TITLE.match(r["title"])
        if m and r["board"] == PRESS_BOARD:
            out.append({**r, "meeting_date": f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"})
    return out


def minutes_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for r in rows:
        m = _MINUTES_TITLE.match(r["title"])
        if m and r["board"] == MINUTES_BOARD:
            out.append({**r, "meeting_date": f"{m.group(3)}-{int(m.group(4)):02d}-{int(m.group(5)):02d}",
                        "session_no": int(m.group(2))})
    return out


# --------------------------------------------------------------------------
# The decision press release
# --------------------------------------------------------------------------

_RATE = re.compile(
    r"기준금리를\s*(?:현재의\s*(?P<a>\d+\.\d+)\s*%\s*수준|현\s*수준\(\s*(?P<a2>\d+\.\d+)\s*%\s*\))에서\s*"
    r"(?:(?P<b>\d+\.\d+)\s*%\s*로\s*(?P<dir>상향|하향)\s*조정|유지)")
_VOTE_ALL = re.compile(r"금융통화위원\s*(\d+)명\s*모두\s*찬성")
_VOTE_SPLIT = re.compile(r"금융통화위원\s*(\d+)명은?\s*찬성하였으며,?\s*(.+)$")
_DISSENT = re.compile(
    r"((?:[가-힣]{2,4}\s*위원(?:\s*(?:과|와|,)\s*)?)+)(?:은|는)\s*기준금리를\s*(\d+\.\d+)\s*%\s*(?:로|를)?\s*(인상|인하|유지)")


def normalize_text(text: str) -> str:
    """The pages space punctuation inconsistently ("하였다 ." on some, "하였다." on others);
    normalised so a meeting-to-meeting comparison sees wording, not spacing."""
    t = collapse(text)
    t = re.sub(r"\s+([.,;:)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    return t


def parse_vote(paragraph: str) -> dict[str, Any] | None:
    """The closing vote sentence, or None when the release has none (before 2026-02)."""
    p = normalize_text(paragraph)
    m = _VOTE_ALL.search(p)
    if m:
        return {"favor_count": int(m.group(1)), "against": [], "unanimous": True, "text": p.lstrip("□ ").strip()}
    m = _VOTE_SPLIT.search(p)
    if not m:
        return None
    against = []
    for dm in _DISSENT.finditer(m.group(2)):
        for name in re.findall(r"([가-힣]{2,4})\s*위원", dm.group(1)):
            against.append({
                "name": name,
                "preferred_rate_pct": float(dm.group(2)),
                "direction": {"인상": "higher", "인하": "lower", "유지": "hold"}[dm.group(3)],
            })
    return {"favor_count": int(m.group(1)), "against": against, "unanimous": False, "text": p.lstrip("□ ").strip()}


def parse_decision(html: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.dbdata")
    if body is None:
        raise ValueError(f"{meeting_date}: no statement body at {source_url}")
    paras = [normalize_text(p.get_text("")) for p in body.find_all("p")]
    paras = [p for p in paras if p and p != "통화정책방향"]
    first = next((p for p in paras if "다음 통화정책방향 결정시까지" in p), None)
    if first is None:
        raise ValueError(f"{meeting_date}: no decision paragraph at {source_url}")
    m = _RATE.search(first)
    if not m:
        raise ValueError(f"{meeting_date}: no base-rate sentence at {source_url}")
    prior = float(m.group("a") or m.group("a2"))
    new = float(m.group("b")) if m.group("b") else prior
    vote_para = next((p for p in paras if "찬성하였" in p), None)
    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "prior_rate_pct": prior,
        "rate_pct": new,
        "action": "raise" if new > prior else ("lower" if new < prior else "maintain"),
        "change_bp": int(round((new - prior) * 100)),
        "vote": parse_vote(vote_para) if vote_para else None,
        "paragraphs": [p for p in paras if p is not vote_para],
    }


_OUTLOOK_HINT = re.compile(r"(?:성장률|물가)[^.]*?(?:전망치|전망)\s*\((?:각각\s*)?\d")


def outlook_sentences(paragraphs: list[str]) -> list[str]:
    """Sentences that state the Bank's new growth / inflation projection against the
    previous round ("... 지난 5월 전망치(각각 2.6%, 2.1%)를 큰 폭 상회하는 3.3% 및 2.9%를 ..."),
    present only at the four meetings that carry a new forecast (Feb/May/Aug/Nov).
    Kept verbatim: the sentences vary too much in form to turn into a table without
    guessing which number is which."""
    out = []
    for para in paragraphs:
        for s in re.split(r"(?<=다\.)\s+", para):
            if "%" in s and _OUTLOOK_HINT.search(s):
                out.append(s.lstrip("□ ").strip())
    return out


# --------------------------------------------------------------------------
# Calendar, roster, minutes
# --------------------------------------------------------------------------

def parse_schedule(html: str, year: int) -> list[str]:
    """Decision dates of one year's 통화정책방향 결정회의 ("10월 22일(목)" rows), ISO, ascending."""
    soup = BeautifulSoup(html, "html.parser")
    text = collapse(soup.get_text(" "))
    out = []
    for m in re.finditer(r"(\d{2})월\s*(\d{2})일\s*\([월화수목금토일]\)", text):
        try:
            out.append(date(year, int(m.group(1)), int(m.group(2))).isoformat())
        except ValueError:
            continue
    return sorted(set(out))


def schedule_url(year: int) -> str:
    return f"{SCHEDULE_URL}&pYear={year}"


_MEMBER = re.compile(
    r"(?P<role>의장|위원)\s+(?P<name>[가-힣]{2,4})\s+(?P<hanja>[一-鿿]{2,4})\s+임\s*기\s+"
    r"(?P<s>\d{4}\.\s*\d{2}\.\s*\d{2})\s*~\s*(?P<e>\d{4}\.\s*\d{2}\.\s*\d{2})")


def _iso_dot(text: str) -> str:
    y, m, d = re.findall(r"\d+", text)
    return f"{y}-{m}-{d}"


def parse_roster(html: str) -> list[dict[str, Any]]:
    """The seven members with their role and term, from the 금융통화위원회 page.

    The Governor chairs (의장), the Deputy Governor is the one whose 선임절차 says
    부총재(당연직); the other five are 위원.
    """
    text = collapse(BeautifulSoup(html, "html.parser").get_text(" "))
    hits = list(_MEMBER.finditer(text))
    out = []
    for i, m in enumerate(hits):
        tail = text[m.end(): hits[i + 1].start() if i + 1 < len(hits) else m.end() + 200]
        role = "의장(총재)" if m.group("role") == "의장" else ("부총재" if "부총재(당연직)" in tail[:120] else "위원")
        out.append({"name": m.group("name"), "role": role,
                    "term_start": _iso_dot(m.group("s")), "term_end": _iso_dot(m.group("e"))})
    return out


def parse_minutes_attendance(text: str) -> dict[str, list[str]]:
    """Attendees and absentees from the first page of a Board meeting's minutes.

    pdfminer prints the header with a space between every syllable ("장 용 성 위 원"),
    so the segment is unspaced before the names are read.
    """
    flat = collapse(text)
    m = re.search(r"3\.\s*출\s*석\s*위\s*원(.*?)4\.\s*결\s*석\s*위\s*원(.*?)5\.\s*참\s*여\s*자", flat)
    if not m:
        raise ValueError("no 출석위원/결석위원 block in the minutes")

    def names(segment: str) -> list[str]:
        s = re.sub(r"\s+", "", segment)
        return re.findall(r"([가-힣]{2,4}?)(?:의장|위원)(?=\(|[가-힣]{2}|$)", s)

    present = names(m.group(1))
    absent = [] if re.sub(r"\s+", "", m.group(2)) == "없음" else names(m.group(2))
    return {"present": present, "absent": absent}


def minutes_pdf_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("/fileSrc/") and a["href"].endswith(".pdf"):
            return BASE + a["href"]
    return None


def fetch_minutes_attendance(ntt_id: str) -> dict[str, Any]:
    page_url = detail_url(MINUTES_BOARD, ntt_id, MINUTES_MENU)
    pdf_url = minutes_pdf_url(fetch_text(page_url, min_size=100000))
    if not pdf_url:
        raise ValueError(f"no pdf attached to {page_url}")
    return {"page_url": page_url, "pdf_url": pdf_url,
            **parse_minutes_attendance(pdf_text(fetch_bytes(pdf_url, min_size=20000)))}
