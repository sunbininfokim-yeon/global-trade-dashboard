"""Official (state-published, uncertified) election-night counts.

Two publishing systems are read:

* Clarity ENR (SOE Software / Scytl), used by many states and counties:
  ``<base>/current_ver.txt`` gives a version, ``<base>/<ver>/json/en/summary.json``
  holds one row per contest with C (name), CH (choices), P (parties), V (votes),
  PR/TP (precincts reporting/total) and T (total votes).
* Enhanced Voting: ``results.ballotItems`` holds statewide counts. County rows
  can be in ``results.localResults`` or top-level ``localResults``.

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
HOUSE_ENHANCED = re.compile(r'^U\.S\. Representative in Congress\s*-\s*District No\.\s*(\d+)$', re.I)
PARTY = {'REP': 'REP', 'DEM': 'DEM', 'R': 'REP', 'D': 'DEM', 'GOP': 'REP', 'REPUBLICAN': 'REP', 'DEMOCRAT': 'DEM',
         'DEMOCRATIC': 'DEM', 'IND': 'IND', 'I': 'IND', 'LIB': 'LIB', 'LBR': 'LIB', 'GRN': 'GRN'}
NAME_PARTY = re.compile(r'\s*\((?:I\)\s*\()?(Rep|Dem|Lib|Ind|Grn|Nol|Pnd)\)\s*$', re.I)
PARTY.update({'INDEPENDENT': 'IND', 'LIBERTARIAN': 'LIB', 'GREEN': 'GRN', 'NO LABELS': 'NOL'})


def race_id(state: str, contest_name: str) -> str | None:
    name = ' '.join(str(contest_name or '').split())
    if SENATE.match(name):
        return f'USA:{state}:senate'
    if GOVERNOR.match(name):
        return f'USA:{state}:governor'
    m = HOUSE.match(name) or HOUSE_ENHANCED.match(name)
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
    named = [c for c in ranked if not c.get('is_write_in_aggregate')]
    if cast and len(named) >= 2 and named[0]['votes'] > named[1]['votes']:
        leader = {'name': named[0]['name'], 'party': named[0]['party'],
                  'margin_pct': round(named[0]['pct'] - named[1]['pct'], 2)}
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


def enhanced_local_results(export: dict) -> list[dict]:
    """Choose the documented county container, never sum both copies."""
    nested = (export.get('results') or {}).get('localResults')
    root = export.get('localResults')
    if root is not None and nested is not None and root != nested:
        raise ValueError('conflicting Enhanced Voting county containers')
    counties = root if root is not None else nested
    if counties is None:
        return []
    if not isinstance(counties, list):
        raise ValueError('Enhanced Voting localResults must be a list')
    return counties


def _count(value: Any, field: str, *, nullable=False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError(f'invalid {field}')
    return int(value)


def parse_enhanced_voting(state: str, export: dict) -> dict[str, dict]:
    results = export.get('results')
    if not isinstance(results, dict) or not isinstance(results.get('ballotItems'), list):
        raise ValueError('missing Enhanced Voting statewide ballotItems')
    precincts: dict[str, list[int | None]] = {}
    seen_counties = set()
    for county in enhanced_local_results(export):
        county_key = county.get('id') or county.get('name')
        if not county_key or county_key in seen_counties:
            raise ValueError('missing or duplicate county identity')
        seen_counties.add(county_key)
        seen_races = set()
        for item in county.get('ballotItems') or []:
            rid = race_id(state, item.get('name'))
            if not rid:
                continue
            if rid in seen_races:
                raise ValueError(f'duplicate county contest {rid}')
            seen_races.add(rid)
            reporting = _count(item.get('precinctsReporting'), 'precinctsReporting', nullable=True)
            total = _count(item.get('precinctsParticipating'), 'precinctsParticipating', nullable=True)
            if reporting is not None and total is not None and reporting > total:
                raise ValueError('reporting precincts exceed participating precincts')
            acc = precincts.setdefault(rid, [0, 0])
            for i, value in enumerate((reporting, total)):
                acc[i] = acc[i] + value if acc[i] is not None and value is not None else None
    races = {}
    for item in results.get('ballotItems') or []:
        rid = race_id(state, item.get('name'))
        if not rid:
            continue
        if rid in races:
            raise ValueError(f'duplicate statewide contest {rid}')
        if item.get('voteFor', 1) != 1:
            raise ValueError(f'unsupported multi-seat contest {rid}')
        candidates = []
        seen_candidates = set()
        for option in item.get('ballotOptions') or []:
            raw_name = str(option.get('name') or '').strip()
            name = NAME_PARTY.sub('', _ticket_head(rid, raw_name)).strip()
            name = re.sub(r'\s*\(I\)\s*$', '', name)  # incumbent marker
            identity = option.get('id') or (name, option.get('politicalParty'))
            if not name or identity in seen_candidates:
                raise ValueError(f'missing or duplicate candidate in {rid}')
            seen_candidates.add(identity)
            candidate = {'name': name, 'party': party_code(option.get('politicalParty')),
                         'votes': _count(option.get('voteCount'), 'voteCount'),
                         'incumbent': '(I)' in raw_name}
            if option.get('id') is not None:
                candidate['source_candidate_id'] = str(option['id'])
            if re.fullmatch(r'(?:(?:Unofficial|Unassigned)\s+)?Write[- ]?ins?', name, re.I):
                # Keep these votes in the denominator; this is not a named candidate.
                candidate['is_write_in_aggregate'] = True
            candidates.append(candidate)
        if not candidates:
            raise ValueError(f'missing candidates in {rid}')
        reporting, total = precincts.get(rid, [
            _count(item.get('precinctsReporting'), 'precinctsReporting', nullable=True),
            _count(item.get('precinctsParticipating'), 'precinctsParticipating', nullable=True)])
        if reporting is not None and total is not None and reporting > total:
            raise ValueError('reporting precincts exceed participating precincts')
        races[rid] = _race(state, rid, item.get('name'), candidates, reporting, total, None)
    return races
