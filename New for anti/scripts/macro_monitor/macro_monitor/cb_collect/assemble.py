"""Turn the collected BOJ / BOK / BoE / ECB records into the block the macro panel reads.

Every bank ends up with the same top-level shape (decision, decision_history,
votes, vote_history, statement_diffs, outlook, schedule, releases, roster) so the
UI has one renderer. Differences that are real are kept as fields, not smoothed
over: the BOJ and the BoE name the members who voted for; the BOK names only the
dissenters, so its for-side is attendance minus dissenters and says so; the ECB
publishes no votes at all, only how far members agreed, and says so.

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


# --------------------------------------------------------------------------
# Bank of England
# --------------------------------------------------------------------------

def _member_groups(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Member rationales grouped the way the Bank prints them ("Votes to maintain Bank Rate at 3.75%")."""
    groups: list[dict[str, Any]] = []
    for v in views:
        g = next((x for x in groups if x["label"] == v["group"]), None)
        if g is None:
            g = {"label": v["group"], "action": v["group_action"], "rate_pct": v["group_rate_pct"], "members": []}
            groups.append(g)
        g["members"].append({"name": v["name"], "paragraphs": v["paragraphs"]})
    return groups


_BOE_ROW_KO = {
    "cpi": "CPI 인플레이션(전년 동기 대비 %)", "gdp": "실질 GDP 성장률(전년 동기 대비 %)", "excess": "수급갭(잠재 GDP 대비 %)",
    "unemployment": "실업률(ILO 기준 %)", "wages": "민간 정규 주간임금 상승률(%)", "bank_rate": "Bank Rate(시장 내재 경로 %)",
    "energy": "에너지 가격의 CPI 기여도(%p)", "world_export": "세계 수출물가(%)",
}


def _boe_table(entry: dict[str, Any]) -> dict[str, Any]:
    """A Report table as the panel draws it: every row keeps the Bank's English label and the
    definition its footnote gives; a Korean label is added only for the rows we know."""
    notes = entry.get("footnotes", {})
    blocks = []
    for b in entry["blocks"]:
        rows = []
        for r in b["rows"]:
            defs = [notes[k] for k in r.get("notes", []) if k in notes]
            rows.append({"id": r["id"], "label_en": r["label_en"], "label_ko": _BOE_ROW_KO.get(r["id"]),
                         "values": r["values"], "definition_en": " ".join(defs) or None})
        blocks.append({"name": b["name"], "rows": rows})
    prior_note = next((v for v in notes.values() if v.startswith("Figures in parentheses")), None)
    used = {k for b in entry["blocks"] for r in b["rows"] for k in r.get("notes", [])}
    general = [v for k, v in notes.items() if k not in used and v != prior_note]          # the notes on the table as a whole
    return {"table_id": entry["table_id"], "title": entry["title"], "columns": entry["columns"], "blocks": blocks,
            "prior_note_en": prior_note, "general_en": general}


def _boe_outlook(doc: dict[str, Any], last_meeting_date: str) -> dict[str, Any] | None:
    reports = sorted(doc.get("reports", []), key=lambda r: r["meeting_date"])
    if not reports:
        return None
    cur = reports[-1]
    prev = reports[-2] if len(reports) >= 2 else None
    return {
        "kind": "projection_blocks",
        "meeting_date": cur["meeting_date"], "title": cur["title"], "source_url": cur["source_url"],
        "forecast_round": cur["meeting_date"] == last_meeting_date,
        "summary": _boe_table(cur["summary"]),
        "annual": [_boe_table(a) for a in cur.get("annual", [])],
        "previous": {"meeting_date": prev["meeting_date"], "title": prev["title"], "source_url": prev["source_url"],
                     "summary": _boe_table(prev["summary"])} if prev else None,
    }


def assemble_boe(doc: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    meetings = sorted(doc.get("meetings", []), key=lambda m: m["meeting_date"])
    if not meetings:
        return None
    last = meetings[-1]
    lv = last["vote"]

    decision = {
        "meeting_date": last["meeting_date"], "action": last["action"], "change_bp": last["change_bp"],
        "prior_rate_pct": last["prior_rate_pct"], "rate_pct": last["rate_pct"],
        "majority": "만장일치" if last["unanimous"] else f"{last['tally_for']}-{last['tally_against']}",
        "unanimous": last["unanimous"], "source_url": last["source_url"],
    }
    history = [{"meeting_date": m["meeting_date"], "action": m["action"], "change_bp": m["change_bp"],
                "prior_rate_pct": m["prior_rate_pct"], "rate_pct": m["rate_pct"]} for m in meetings][-HISTORY_LEN:]

    votes = {
        "meeting_date": last["meeting_date"],
        "for": [{"name": n} for n in lv["for"]],
        "for_source": lv["for_source"],
        "for_count": len(lv["for"]),
        "against": [{"name": a["name"], "reason": None, "alt_rate_pct": a["alt_rate_pct"],
                     "direction": _direction(a["alt_rate_pct"], last["rate_pct"])} for a in lv["against"]],
        "absent": [],
        "text": last["summary_tally_text"],
        "earlier_steps": lv.get("earlier", []),
        "notes": lv.get("notes", []),
    }
    vote_history = [{
        "meeting_date": m["meeting_date"], "for_count": len(m["vote"]["for"]), "against_count": len(m["vote"]["against"]),
        "unanimous": m["unanimous"], "dissenters": [a["name"] for a in m["vote"]["against"]], "source": m["vote"]["for_source"],
    } for m in meetings][-HISTORY_LEN:]

    texts = [{"meeting_date": m["meeting_date"], "text": " ".join(m["summary_paragraphs"]), "source_url": m["source_url"]}
             for m in meetings if m["summary_paragraphs"]]
    pair = _latest_pair(texts)
    diffs = [_diff_block("statement", "통화정책 요약(Monetary Policy Summary)", *pair)] if pair else []

    minutes = {
        "meeting_date": last["meeting_date"], "released_on": last["meeting_date"], "page_url": last["source_url"],
        "kind": "sections", "sections": last["minutes"]["sections"],
        "present": [p["name"] for p in last["minutes"]["present"]],
        "treasury_representative": last["minutes"].get("treasury_representative"),
    }
    views = None
    if last.get("member_views"):
        views = {"meeting_date": last["meeting_date"], "groups": _member_groups(last["member_views"])}

    rows = (doc.get("calendar") or {}).get("rows", [])
    upcoming = next((r for r in rows if r["decision_date"] > today.isoformat()), None)
    next_date = upcoming["decision_date"] if upcoming else (doc.get("calendar") or {}).get("next_due")
    releases = [{"meeting_date": m["meeting_date"], "kind": "minutes", "kind_ko": "의사록 (요약과 같은 날 공개)",
                 "date": m["meeting_date"], "status": "released", "basis": "boe_page", "source_url": m["source_url"]}
                for m in meetings[-2:]]

    return {
        "iso3": "GBR",
        "bank_ko": "영란은행 통화정책위원회(MPC)",
        "rate_label_ko": "기준금리(Bank Rate)",
        "decision": decision,
        "decision_history": history,
        "votes": votes,
        "vote_history": vote_history,
        "statement_diffs": diffs,
        "outlook": _boe_outlook(doc, last["meeting_date"]),
        "minutes": minutes,
        "member_views": views,
        "opinions": None,
        "schedule": {"next_meeting_date": next_date, "next_meeting_days": [next_date] if next_date else None,
                     "next_outlook_release": next_date if upcoming and upcoming.get("monetary_policy_report") else None},
        "releases": releases,
        "roster": {"asof": last["meeting_date"], "source": "의사록의 출석 위원 명단(재무부 대표·감독 참관인은 제외)",
                   "members": [{"name": p["name"], "role": p["role"]} for p in last["minutes"]["present"]]},
    }


# --------------------------------------------------------------------------
# European Central Bank
# --------------------------------------------------------------------------

_PROJ_ROWS = (("hicp", "소비자물가(HICP, 헤드라인)"), ("core", "근원(에너지·식품 제외)"), ("gdp", "실질 GDP 성장률"))


def _ecb_outlook(meetings: list[dict[str, Any]]) -> dict[str, Any] | None:
    rounds = [m for m in meetings if m.get("projections")]
    if not rounds:
        return None
    cur = rounds[-1]
    prev = rounds[-2] if len(rounds) >= 2 else None
    years = sorted({int(y) for d in cur["projections"].values() for y in d})
    rows = []
    for key, label in _PROJ_ROWS:
        series = cur["projections"].get(key)
        if not series:
            continue
        rows.append({
            "id": key, "label_ko": label, "unit": "%",
            "values": [{"year": y, "value": series.get(str(y)),
                        "prior": ((prev or {}).get("projections", {}).get(key) or {}).get(str(y)), "forecast": True}
                       if str(y) in series else None for y in years],
        })
    if not rows:
        return None
    sentences = [p for p in cur["paragraphs"] if "projection" in p.lower() or "baseline" in p.lower()]
    return {
        "kind": "sentences", "meeting_date": cur["meeting_date"], "source_url": cur["source_url"],
        "forecast_round": cur["meeting_date"] == meetings[-1]["meeting_date"],
        "sentences": sentences,
        "sentences_label_ko": "해당 회의 보도자료의 전망 서술", "sentences_unit_ko": "단락",
        "sentences_note_ko": "보도자료 단락을 그대로 옮겼습니다(영어).",
        "table": {
            "meeting_date": cur["meeting_date"], "prior_made_in": prev["meeting_date"][:7] if prev else None,
            "years": [str(y) for y in years], "rows": rows, "source_url": cur["source_url"],
            "title_ko": "ECB·Eurosystem 스태프 전망", "prior_label_ko": (prev["meeting_date"][:7] if prev else None),
            "note_ko": ("보도자료 본문에 적힌 수치를 옮겼습니다. 세 개 연도가 이어서 적힌 문장만 읽고, 그렇지 않은 서술은 싣지 않았습니다. "
                        "작은 글씨는 직전 전망 회의의 같은 연도 값과 그 대비 변화입니다."),
        },
    }


def assemble_ecb(doc: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    meetings = sorted(doc.get("meetings", []), key=lambda m: m["meeting_date"])
    if not meetings:
        return None
    last = meetings[-1]
    decision = {
        "meeting_date": last["meeting_date"], "action": last["action"], "change_bp": last["change_bp"],
        "prior_rate_pct": last["prior_dfr_pct"], "rate_pct": last["dfr_pct"],
        "majority": None, "unanimous": None, "source_url": last["source_url"],
        "also": {"mro_pct": last["mro_pct"], "mlf_pct": last["mlf_pct"], "effective_date": last["effective_date"]},
    }
    history = [{"meeting_date": m["meeting_date"], "action": m["action"], "change_bp": m["change_bp"],
                "prior_rate_pct": m["prior_dfr_pct"], "rate_pct": m["dfr_pct"]} for m in meetings][-HISTORY_LEN:]

    with_account = [m for m in meetings if m.get("account")]
    votes = None
    if with_account:
        acct = with_account[-1]["account"]
        votes = {
            "meeting_date": acct["meeting_date"], "kind": "consensus_only",
            "for": None, "for_source": None, "for_count": None, "against": [], "absent": [],
            "agreement": acct["agreement"], "notes": acct["record_notes"], "account_url": acct["source_url"],
            "history": [{"meeting_date": m["meeting_date"], "quantifier": (m["account"]["agreement"] or {}).get("quantifier"),
                         "notes": len(m["account"]["record_notes"])} for m in with_account][-HISTORY_LEN:],
            "note_ko": ("ECB 정책이사회는 위원별 표결을 공개하지 않습니다. 결정은 의장 제안에 대한 합의로 기록되고, "
                        "회의 요약(account)에는 '모든 위원이 동의' 같은 합의 정도와 다른 견해를 적은 문단만 실립니다. 아래는 그 원문입니다."),
        }

    diffs = []
    pr_pair = _latest_pair([{"meeting_date": m["meeting_date"], "text": " ".join(m["paragraphs"]), "source_url": m["source_url"]} for m in meetings])
    if pr_pair:
        diffs.append(_diff_block("press_release", "통화정책 결정 보도자료", *pr_pair))
    # The introductory statement is rewritten in full every meeting (a redline of it is nearly all
    # red and green), so it is collected but not redlined; the press release is the stable text.
    diffs.sort(key=lambda d: d["current_meeting"], reverse=True)

    minutes = None
    if with_account:
        a = with_account[-1]["account"]
        minutes = {
            "meeting_date": a["meeting_date"], "released_on": a["released_on"], "page_url": a["source_url"], "kind": "sections",
            "sections": a["sections"], "present": [m["name"] for m in a["members"] if m["voting"]],
            "agreement": a["agreement"], "next_release": a["next_account_release"],
        }

    upcoming = next((r for r in doc.get("calendar", []) if r["decision_date"] > today.isoformat()), None)
    releases = []
    pending_date = with_account[-1]["account"]["next_account_release"] if with_account else None
    first_pending_used = False
    for m in meetings[-2:]:
        if m.get("account"):
            releases.append({"meeting_date": m["meeting_date"], "kind": "minutes", "kind_ko": "요약(Account)",
                             "date": m["account"]["released_on"], "status": "released", "basis": "ecb_account",
                             "source_url": m["account"]["source_url"]})
        elif pending_date and not first_pending_used:
            first_pending_used = True
            releases.append({"meeting_date": m["meeting_date"], "kind": "minutes", "kind_ko": "요약(Account)", "date": pending_date,
                             "status": "scheduled" if pending_date > today.isoformat() else "expected", "basis": "ecb_account"})

    roster = None
    if with_account:
        a = with_account[-1]["account"]
        roster = {
            "asof": a["meeting_date"],
            "source": "회의 요약(account)의 참석자 명단 — 별표(*)는 그 달 투표권이 없는 위원(순환, ESCB 규정 10.2조)",
            "members": [{"name": m["name"], "role": " · ".join(x for x in (m["role"], None if m["voting"] else "투표권 없음") if x) or None}
                        for m in a["members"]],
        }

    return {
        "iso3": "EMU",
        "bank_ko": "유럽중앙은행 정책이사회(Governing Council)",
        "rate_label_ko": "예금금리(DFR)",
        "decision": decision,
        "decision_history": history,
        "votes": votes,
        "vote_history": [],
        "statement_diffs": diffs,
        "outlook": _ecb_outlook(meetings),
        "minutes": minutes,
        "opinions": None,
        "schedule": {"next_meeting_date": upcoming["decision_date"] if upcoming else None,
                     "next_meeting_days": [d for d in ((upcoming or {}).get("day1"), (upcoming or {}).get("decision_date")) if d] or None,
                     "next_outlook_release": None},
        "releases": releases,
        "roster": roster,
    }
