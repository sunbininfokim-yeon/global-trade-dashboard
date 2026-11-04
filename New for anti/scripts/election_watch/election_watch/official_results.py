"""Official (state-published, uncertified) election-night counts.

Two publishing systems are read:

* Clarity ENR (SOE Software / Scytl), used by many states and counties:
  ``<base>/current_ver.txt`` gives a version, ``<base>/<ver>/json/en/summary.json``
  holds one row per contest with C (name), CH (choices), P (parties), V (votes),
  PR/TP (precincts reporting/total) and T (total votes).
* Enhanced Voting (Georgia): one export JSON with ``results.ballotItems`` for the
  state and ``results.localResults`` per county, where precinct counts live.

Only federal and governor contests are matched to our race ids. Everything here
is a count the state itself published; nothing is projected, and a race is never
marked won.
"""
from __future__ import annotations

import re
from typing import Any

SENATE = re.compile(r'^(?:US Senate|United States Senator)$', re.I)
GOVERNOR = re.compile(r'^Governor(?:\s*(?:/|and)\s*(?:Lt\.?|Lieutenant) Governor)?$', re.I)
HOUSE = re.compile(r'^(?:US House of Representatives|United States Representative|Representative to the \S+ United States Congress)'
                   r'\s*-?\s*District\s+(\d+)$', re.I)
PARTY = {'REP': 'REP', 'DEM': 'DEM', 'R': 'REP', 'D': 'DEM', 'GOP': 'REP', 'REPUBLICAN': 'REP', 'DEMOCRAT': 'DEM',
         'DEMOCRATIC': 'DEM', 'IND': 'IND', 'I': 'IND', 'LIB': 'LIB', 'LBR': 'LIB', 'GRN': 'GRN'}
NAME_PARTY = re.compile(r'\s*\((?:I\)\s*\()?(Rep|Dem|Lib|Ind|Grn)\)\s*$', re.I)


def race_id(state: str, contest_name: str) -> str | None:
    name = ' '.join(str(contest_name or '').split())
    if SENATE.match(name):
        return f'USA:{state}:senate'
    if GOVERNOR.match(name):
        return f'USA:{state}:governor'
    m = HOUSE.match(name)
    if m:
        return f'USA:{state}:house:{int(m.group(1)):02d}'
    return None


def party_code(raw: Any) -> str | None:
    text = str(raw or '').strip().upper()
    return PARTY.get(text, text or None)


def _ticket_head(rid: str, name: str) -> str:
    # Governor tickets print the running mate too ('A / B', 'A and B'); keep the governor.
    if rid.endswith(':governor'):
        return re.split(r'\s+/\s+|\s+and\s+', name, maxsplit=1)[0].strip()
    return name


def _race(state, rid, contest, candidates, reporting, total, total_votes, unit='precinct'):
    cast = sum(c['votes'] for c in candidates)
    for c in candidates:
        c['pct'] = round(100 * c['votes'] / cast, 2) if cast else None
    ranked = sorted(candidates, key=lambda c: c['votes'], reverse=True)
    leader = None
    if cast and len(ranked) >= 2 and ranked[0]['votes'] > ranked[1]['votes']:
        leader = {'name': ranked[0]['name'], 'party': ranked[0]['party'],
                  'margin_pct': round(ranked[0]['pct'] - ranked[1]['pct'], 2)}
    return {'race_id': rid, 'state': state, 'contest_name': contest,
            'precincts_reporting': reporting, 'precincts_total': total, 'reporting_unit': unit,
            'total_votes': total_votes if total_votes is not None else cast,
            'candidates': ranked, 'leader': leader, 'status': 'unofficial_count'}


def parse_clarity(state: str, summary: list[dict]) -> dict[str, dict]:
    races = {}
    for row in summary or []:
        rid = race_id(state, row.get('C'))
        if not rid:
            continue
        names, parties, votes = row.get('CH') or [], row.get('P') or [], row.get('V') or []
        candidates = []
        for i, name in enumerate(names):
            if not name or str(name).strip().lower() in ('write-in', 'write-ins', 'write in'):
                continue
            candidates.append({'name': _ticket_head(rid, str(name).strip()), 'party': party_code(parties[i] if i < len(parties) else None),
                               'votes': int(votes[i]) if i < len(votes) and votes[i] is not None else 0})
        total = (row.get('T') or [None])[0]
        # A state-level Clarity summary counts reporting counties, not precincts.
        races[rid] = _race(state, rid, row.get('C'), candidates, row.get('PR'), row.get('TP'), total, unit='county')
    return races


def parse_enhanced_voting(state: str, export: dict) -> dict[str, dict]:
    results = (export or {}).get('results') or {}
    precincts: dict[str, list[int]] = {}
    for county in results.get('localResults') or []:
        for item in county.get('ballotItems') or []:
            rid = race_id(state, item.get('name'))
            if not rid:
                continue
            acc = precincts.setdefault(rid, [0, 0])
            acc[0] += item.get('precinctsReporting') or 0
            acc[1] += item.get('precinctsParticipating') or 0
    races = {}
    for item in results.get('ballotItems') or []:
        rid = race_id(state, item.get('name'))
        if not rid:
            continue
        candidates = []
        for option in item.get('ballotOptions') or []:
            name = NAME_PARTY.sub('', str(option.get('name') or '')).strip()
            name = re.sub(r'\s*\(I\)\s*$', '', name)  # incumbent marker
            candidates.append({'name': _ticket_head(rid, name), 'party': party_code(option.get('politicalParty')),
                               'votes': int(option.get('voteCount') or 0),
                               'incumbent': '(I)' in str(option.get('name') or '')})
        reporting, total = precincts.get(rid, [item.get('precinctsReporting'), item.get('precinctsParticipating')])
        races[rid] = _race(state, rid, item.get('name'), candidates, reporting, total, None)
    return races
