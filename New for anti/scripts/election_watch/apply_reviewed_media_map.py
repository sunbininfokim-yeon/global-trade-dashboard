#!/usr/bin/env python3
"""Apply one human-reviewed public win-label snapshot, with ambiguity held.

No network requests, licensed API access, vote-lead inference, or publication.
The source snapshot and candidate-identity proof remain reviewable in the PR.
"""
import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path

from election_watch.media_calls import POLLS_CLOSE, check, resolve_reviewed_party_call

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1] / 'public/data'


def apply(review, board, previous, ratings, certified, now):
    if (review.get('schema') != 'usa_reviewed_public_media_map_v1' or review.get('cycle') != 2026
            or review.get('election_date') != '2026-11-03'
            or review.get('publisher') != 'AP'
            or review.get('method') != 'manual_review_of_public_map_win_labels_only'
            or review.get('source_url') != 'https://interactives.apelections.org/election-results/assets/apnews/embeds/ge-bop-map/index.html'):
        raise ValueError('unreviewed source/scope')
    verified = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
    if verified.tzinfo is None or verified < POLLS_CLOSE or verified > now:
        raise ValueError('invalid review time')
    existing_problems = check(previous, ratings, certified, now)
    if existing_problems:
        raise ValueError('invalid previous calls: ' + '; '.join(existing_problems))
    calls = {c['race_id']: dict(c) for c in previous.get('calls', [])}
    seen = set()
    held = []
    for entry in review['calls']:
        rid, party = entry['race_id'], entry['party']
        if entry.get('status', 'called') != 'called':
            raise ValueError('only explicit win labels may be applied')
        if rid in seen:
            raise ValueError('duplicate reviewed race')
        seen.add(rid)
        if rid in calls:
            if calls[rid]['status'] != 'called' or calls[rid]['party'] != party:
                raise ValueError(f'conflicting existing call: {rid}')
            continue  # Keep direct article evidence and its original verification time.
        try:
            winner, proof = resolve_reviewed_party_call(board[rid], party)
        except (KeyError, ValueError) as exc:
            held.append({'race_id': rid, 'party': party, 'reason': str(exc)})
            continue
        calls[rid] = {'race_id': rid, 'status': 'called', 'winner': winner, 'party': party,
                      'called_by': ['AP'], 'called_at': None, 'call_time_status': 'not_reported',
                      'verified_at': review['reviewed_at'], 'recorded_at': review['reviewed_at'],
                      'source_url': review['source_url'], 'winner_resolution': proof}
    latest = review['reviewed_at']
    if previous.get('updated_at') and datetime.fromisoformat(previous['updated_at'].replace('Z', '+00:00')) > verified:
        latest = previous['updated_at']
    out = dict(previous, updated_at=latest, calls=sorted(calls.values(), key=lambda c: c['race_id']))
    # Keep full identity evidence, but share repeated state ballot URLs in the
    # public asset instead of sending the same proof hundreds of times.
    evidence = dict(out.get('candidate_identity_sources', {}))
    for call in out['calls']:
        proof = call.pop('winner_resolution', None)
        if proof is not None:
            key = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()[:16]
            if key in evidence and evidence[key] != proof:
                raise ValueError('identity evidence hash collision')
            evidence[key] = proof
            call['winner_resolution_ref'] = key
    out['candidate_identity_sources'] = evidence
    problems = check(out, ratings, certified, now)
    if problems:
        raise ValueError('; '.join(problems))
    return out, held


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, default=PUBLIC / 'usa_election_media_calls_v1.json')
    p.add_argument('--held', type=Path, required=True)
    a = p.parse_args()
    review = json.loads(a.review.read_text())
    board = json.loads((PUBLIC / 'usa_election_live_polls_v1.json').read_text())['races']
    previous = json.loads(a.output.read_text())
    ratings = json.loads((PUBLIC / 'usa_election_ratings_review_v1.json').read_text())
    certified = {r['race_id']: r for r in json.loads((ROOT / 'config/usa_polls/results_2026.json').read_text())['results']}
    out, held = apply(review, board, previous, ratings, certified, datetime.now(timezone.utc))
    a.held.write_text(json.dumps({'reviewed_at': review['reviewed_at'], 'held': held}, ensure_ascii=False, indent=2) + '\n')
    a.output.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'calls': len(out['calls']), 'held': len(held)}))


if __name__ == '__main__':
    main()
