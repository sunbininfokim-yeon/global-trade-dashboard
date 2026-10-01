"""Turn the collected BOJ / BOK records into the block the macro panel reads.

Both banks end up with the same top-level shape (decision, decision_history,
votes, vote_history, statement_diffs, outlook, schedule, releases, roster) so the
UI has one renderer. Differences that are real are kept as fields, not smoothed
over: the BOJ names the members who voted for; the BOK names only the
dissenters, so its for-side is attendance minus dissenters and says so.

Nothing here scores or classifies wording. A diff is a redline; a vote is a
list of names.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from ..fomc_collect.statement_diff import changed_word_count, diff_operative_text

HISTORY_LEN = 8


def _action(prior: float | None, new: float) -> tuple[str | None, int | None]:
    if prior is None:
        return None, None
    bp = int(round((new - prior) * 100))
    return ("raise" if bp > 0 else "lower" if bp < 0 else "maintain"), bp


def _diff_block(kind: str, kind_ko: str, prev: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    segments = diff_operative_text(prev["text"], cur["text"])
    return {
        "kind": kind,
        "kind_ko": kind_ko,
        "previous_meeting": prev["meeting_date"],
        "current_meeting": cur["meeting_date"],
        "previous_source_url": prev["source_url"],
        "current_source_url": cur["source_url"],
        "changed_word_count": changed_word_count(segments),
        "segments": segments,
    }


def _latest_pair(items: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    return (items[-2], items[-1]) if len(items) >= 2 else None


def _direction(alt: float | None, rate: float) -> str | None:
    if alt is None:
        return None
    return "higher" if alt > rate else "lower" if alt < rate else "hold"


# --------------------------------------------------------------------------
# Bank of Japan
# --------------------------------------------------------------------------

def assemble_boj(doc: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    meetings = sorted(doc.get("meetings", []), key=lambda m: m["meeting_date"])
    if not meetings:
        return None

    history = []
    prior = None
    prior_of: dict[str, float | None] = {}
    for m in meetings:
        action, bp = _action(prior, m["guideline_rate_pct"])
        if action is not None:
            history.append({"meeting_date": m["meeting_date"], "action": action, "change_bp": bp,
                            "prior_rate_pct": prior, "rate_pct": m["guideline_rate_pct"]})
        prior_of[m["meeting_date"]] = prior
        prior = m["guideline_rate_pct"]

    last = meetings[-1]
    action, bp = _action(prior_of[last["meeting_date"]], last["guideline_rate_pct"])
    decision = {
        "meeting_date": last["meeting_date"],
        "action": action,
        "change_bp": bp,
        "prior_rate_pct": prior_of[last["meeting_date"]],
        "rate_pct": last["guideline_rate_pct"],
        "majority": "만장일치" if last["unanimous"] else f"{last['vote_for_count']}-{last['vote_against_count']}",
        "unanimous": last["unanimous"],
        "source_url": last["source_url"],
    }

    def vote_row(m: dict[str, Any]) -> dict[str, Any]:
        return {
            "meeting_date": m["meeting_date"],
            "for_count": m["vote_for_count"],
            "against_count": m["vote_against_count"],
            "unanimous": m["unanimous"],
            "dissenters": [a["name"] for a in m["voting_against"]],
        }

    votes = {
        "meeting_date": last["meeting_date"],
        "for": [{"name": n} for n in last["voting_for"]],
        "for_source": last["voting_for_source"],
        "against": [
            {"name": a["name"], "reason": a["reason"], "alt_rate_pct": a["proposal_rate_pct"],
             "direction": _direction(a["proposal_rate_pct"], last["guideline_rate_pct"])}
            for a in last["voting_against"]
        ],
        "absent": last.get("members_absent", []),
        "assessment_dissents": last.get("assessment_dissents", []),
    }

    # Two kinds of assessment text: the statement body (meetings without an Outlook
    # Report) and the Outlook Report's Bank's View summary. A diff only makes sense
    # between two texts of the same kind, so each kind gets its own latest pair.
    kinds: dict[str, list[dict[str, Any]]] = {"statement": [], "bank_view": []}
    for m in meetings:
        if m.get("narrative"):
            kinds["statement"].append({"meeting_date": m["meeting_date"], "text": m["narrative"], "source_url": m["source_url"]})
        bv = m.get("bank_view")
        if bv and bv.get("summary"):
            kinds["bank_view"].append({"meeting_date": m["meeting_date"], "text": bv["summary"], "source_url": bv["source_url"]})
    diffs = []
    for kind, kind_ko in (("statement", "성명서 본문"), ("bank_view", "전망보고서 요약(Bank's View)")):
        pair = _latest_pair(kinds[kind])
        if pair:
            diffs.append(_diff_block(kind, kind_ko, *pair))
    diffs.sort(key=lambda d: d["current_meeting"], reverse=True)

    outlook = None
    for m in reversed(meetings):
        bv = m.get("bank_view")
        if bv and bv.get("forecasts"):
            outlook = {"kind": "forecast_table", "meeting_date": m["meeting_date"], "source_url": bv["source_url"], **bv["forecasts"]}
            break

    calendar = doc.get("calendar", [])
    by_decision = {r["decision_date"]: r for r in calendar}
    upcoming = next((r for r in calendar if r["decision_date"] > today.isoformat()), None)
    releases = []
    for m in meetings[-2:]:
        row = by_decision.get(m["meeting_date"])
        for key, kind, ko in (("opinions_release", "summary_of_opinions", "주요 의견 요약(Summary of Opinions)"),
                              ("minutes_release", "minutes", "의사록")):
            when = (row or {}).get(key) or (m.get("releases") or {}).get("summary_of_opinions" if kind == "summary_of_opinions" else "minutes")
            if when:
                releases.append({"meeting_date": m["meeting_date"], "kind": kind, "kind_ko": ko, "date": when,
                                 "status": "released" if when <= today.isoformat() else "scheduled",
                                 "basis": "boj_calendar" if row else "statement"})

    opinions = minutes = None
    for m in reversed(meetings):
        if opinions is None and m.get("opinions"):
            opinions = {"meeting_date": m["meeting_date"], **m["opinions"]}
        if minutes is None and m.get("minutes"):
            minutes = {"meeting_date": m["meeting_date"], **m["minutes"]}

    present = last.get("members_present", [])
    return {
        "iso3": "JPN",
        "bank_ko": "일본은행 정책위원회(금융정책결정회의)",
        "rate_label_ko": "무담보콜금리 유도목표",
        "decision": decision,
        "decision_history": history[-HISTORY_LEN:],
        "votes": votes,
        "vote_history": [vote_row(m) for m in meetings[-HISTORY_LEN:]],
        "statement_diffs": diffs,
        "outlook": outlook,
        "opinions": opinions,
        "minutes": minutes,
        "schedule": {
            "next_meeting_date": upcoming["decision_date"] if upcoming else None,
            "next_meeting_days": upcoming["meeting_days"] if upcoming else None,
            "next_outlook_release": upcoming["outlook_release"] if upcoming else None,
        },
        "releases": releases,
        "roster": {"asof": last["meeting_date"], "source": "성명서의 출석 위원",
                   "members": [{"name": n, "role": None} for n in present]},
    }


# --------------------------------------------------------------------------
# Bank of Korea
# --------------------------------------------------------------------------

def _term_covers(member: dict[str, Any], on: str) -> bool:
    return member["term_start"] <= on <= member["term_end"]


def effective_vote(meeting: dict[str, Any]) -> dict[str, Any] | None:
    """The vote sentence of the press release when it has one (2026-02 onward), otherwise the
    vote the minutes record in their deliberation-result paragraph. Either way it says where
    it came from."""
    if meeting.get("vote"):
        return {**meeting["vote"], "source": "press_release"}
    mv = (meeting.get("minutes") or {}).get("vote")
    return dict(mv) if mv else None


def voters_for(meeting: dict[str, Any], roster: list[dict[str, Any]]) -> tuple[list[str] | None, str | None]:
    """Who voted for. The release names only the dissenters, so this is attendance minus
    dissenters: from the minutes' attendee list when the minutes are out, otherwise (the
    newest meeting) from the current roster -- but only when every member's term covers the
    meeting date and the counts match the stated tally, the same test the FOMC panel uses
    for its inferred roster."""
    vote = effective_vote(meeting)
    if not vote:
        return None, None
    dissenters = [a["name"] for a in vote["against"]]
    minutes = meeting.get("minutes")
    if minutes and minutes.get("present"):
        present = [n for n in minutes["present"] if n not in dissenters]
        if len(present) == vote["favor_count"] and all(d in minutes["present"] for d in dissenters):
            return present, "minutes_attendance"
        return None, None
    valid = [r for r in roster if _term_covers(r, meeting["meeting_date"])]
    names = [r["name"] for r in valid]
    if all(d in names for d in dissenters) and len(names) - len(dissenters) == vote["favor_count"]:
        return [n for n in names if n not in dissenters], "roster_inferred"
    return None, None


def _minutes_lag_days(meetings: list[dict[str, Any]]) -> int | None:
    lags = []
    for m in meetings:
        mi = m.get("minutes")
        if mi and mi.get("released_on"):
            lags.append((date.fromisoformat(mi["released_on"]) - date.fromisoformat(m["meeting_date"])).days)
    return int(median(lags[-4:])) if len(lags) >= 3 else None


def assemble_bok(doc: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    meetings = sorted(doc.get("meetings", []), key=lambda m: m["meeting_date"])
    if not meetings:
        return None
    roster = doc.get("roster", [])
    last = meetings[-1]

    majority = None
    last_vote = effective_vote(last)
    if last_vote:
        v = last_vote
        majority = "만장일치" if v["unanimous"] else f"{v['favor_count']}-{len(v['against'])}"
    decision = {
        "meeting_date": last["meeting_date"],
        "action": last["action"],
        "change_bp": last["change_bp"],
        "prior_rate_pct": last["prior_rate_pct"],
        "rate_pct": last["rate_pct"],
        "majority": majority,
        "unanimous": last_vote["unanimous"] if last_vote else None,
        "source_url": last["source_url"],
    }
    history = [{"meeting_date": m["meeting_date"], "action": m["action"], "change_bp": m["change_bp"],
                "prior_rate_pct": m["prior_rate_pct"], "rate_pct": m["rate_pct"]} for m in meetings][-HISTORY_LEN:]

    for_names, for_source = voters_for(last, roster)
    votes = None
    if last_vote:
        votes = {
            "meeting_date": last["meeting_date"],
            "for": [{"name": n} for n in for_names] if for_names is not None else None,
            "for_source": for_source,
            "for_count": last_vote["favor_count"],
            "against": [
                {"name": a["name"], "reason": None, "alt_rate_pct": a["preferred_rate_pct"], "direction": a["direction"]}
                for a in last_vote["against"]
            ],
            "absent": (last.get("minutes") or {}).get("absent", []),
            "text": last_vote["text"],
            "source": last_vote["source"],
        }
    vote_history = []
    for m in meetings:
        v = effective_vote(m)
        if v:
            vote_history.append({
                "meeting_date": m["meeting_date"], "for_count": v["favor_count"],
                "against_count": len(v["against"]), "unanimous": v["unanimous"],
                "dissenters": [a["name"] for a in v["against"]], "source": v["source"],
            })

    texts = [{"meeting_date": m["meeting_date"], "text": " ".join(m["paragraphs"]), "source_url": m["source_url"]} for m in meetings]
    pair = _latest_pair(texts)
    diffs = [_diff_block("statement", "통화정책방향 본문", *pair)] if pair else []

    outlook = None
    table = next(({"meeting_date": m["meeting_date"], **m["outlook_table"]} for m in reversed(meetings) if m.get("outlook_table")), None)
    if last.get("outlook_sentences") or table:
        outlook = {"kind": "sentences", "meeting_date": last["meeting_date"], "source_url": last["source_url"],
                   "forecast_round": int(last["meeting_date"][5:7]) in (2, 5, 8, 11),
                   "sentences": last.get("outlook_sentences") or [], "table": table}

    minutes = None
    for m in reversed(meetings):
        mi = m.get("minutes")
        if mi and mi.get("discussion"):
            minutes = {
                "meeting_date": m["meeting_date"], "released_on": mi.get("released_on"), "page_url": mi.get("page_url"),
                "present": mi.get("present", []), "absent": mi.get("absent", []),
                "opinions": mi.get("opinions"), "discussion": mi["discussion"],
            }
            break

    calendar = sorted(d for ds in doc.get("calendar", {}).values() for d in ds)
    upcoming = next((d for d in calendar if d > today.isoformat()), None)

    releases = []
    for m in meetings[-2:]:
        mi = m.get("minutes")
        if mi:
            releases.append({"meeting_date": m["meeting_date"], "kind": "minutes", "kind_ko": "의사록", "date": mi["released_on"],
                             "status": "released", "basis": "bok_board", "source_url": mi.get("page_url")})
    lag = _minutes_lag_days(meetings)
    for m in meetings[-2:]:
        if not m.get("minutes") and lag is not None:
            releases.append({"meeting_date": m["meeting_date"], "kind": "minutes", "kind_ko": "의사록",
                             "date": (date.fromisoformat(m["meeting_date"]) + timedelta(days=lag)).isoformat(),
                             "status": "expected", "basis": f"recent_lag_{lag}_days"})

    return {
        "iso3": "KOR",
        "bank_ko": "한국은행 금융통화위원회",
        "rate_label_ko": "기준금리",
        "decision": decision,
        "decision_history": history,
        "votes": votes,
        "vote_history": vote_history[-HISTORY_LEN:],
        "vote_history_note_ko": ("2026-02 이전 회의의 표결은 결정문에 표결 문장이 없어 의사록 '심의결과'의 기재(반대 위원 실명)로 채웠습니다."
                                 if any(v["source"] == "minutes" for v in vote_history) else None),
        "statement_diffs": diffs,
        "outlook": outlook,
        "minutes": minutes,
        "opinions": None,
        "schedule": {"next_meeting_date": upcoming, "next_meeting_days": [upcoming] if upcoming else None, "next_outlook_release": None},
        "releases": releases,
        "roster": {"asof": (doc.get("retrieved_at") or "")[:10], "source": "한국은행 금융통화위원회 위원 명단",
                   "members": [{"name": r["name"], "role": r["role"]} for r in roster]},
    }
