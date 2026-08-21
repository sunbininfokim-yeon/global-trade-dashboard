"""Evidence-limited comparison of public FOMC votes."""

from __future__ import annotations

from typing import Any


def _vote_map(meeting: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(vote["person_id"]): vote
        for vote in (meeting.get("votes") or [])
        if vote.get("person_id")
    }


def compare_fomc_meetings(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare public votes without manufacturing hawk/dove scores."""
    prev_votes = _vote_map(previous)
    cur_votes = _vote_map(current)
    prev_voters = set(previous.get("eligible_voters") or prev_votes)
    cur_voters = set(current.get("eligible_voters") or cur_votes)
    transitions = []
    for person_id in sorted(prev_votes.keys() & cur_votes.keys()):
        before = prev_votes[person_id]
        after = cur_votes[person_id]
        before_direction = before.get("dissent_direction") or "none"
        after_direction = after.get("dissent_direction") or "none"
        if before.get("vote") != after.get("vote") or before_direction != after_direction:
            transitions.append(
                {
                    "person_id": person_id,
                    "name": after.get("name") or before.get("name"),
                    "from_vote": before.get("vote"),
                    "to_vote": after.get("vote"),
                    "from_direction": before_direction,
                    "to_direction": after_direction,
                    "evidence": after.get("evidence"),
                }
            )

    def dissent_summary(meeting: dict[str, Any]) -> dict[str, Any]:
        votes = meeting.get("votes") or []
        dissents = [vote for vote in votes if vote.get("vote") == "against"]
        directions: dict[str, int] = {}
        for vote in dissents:
            direction = str(vote.get("dissent_direction") or "unknown")
            directions[direction] = directions.get(direction, 0) + 1
        return {"count": len(dissents), "directions": directions}

    return {
        "previous_meeting": previous.get("meeting_date"),
        "current_meeting": current.get("meeting_date"),
        "previous_dissents": dissent_summary(previous),
        "current_dissents": dissent_summary(current),
        "roster_changes": {
            "new_voters": sorted(cur_voters - prev_voters),
            "lost_vote": sorted(prev_voters - cur_voters),
        },
        "public_vote_transitions": transitions,
        "interpretation": "public_votes_only_no_latent_preference_inference",
    }
