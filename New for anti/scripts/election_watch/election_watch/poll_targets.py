"""Scheduled election discovery, reviewed ballot fields and competition status.

Discovery is nationwide; poll admission still requires a reviewed matchup and
the existing source/methodology checks. No ballot status is an election result.
"""
from collections import Counter
from copy import deepcopy
from datetime import date

from .polls import https_url, require
from .superpac import STATES


def apply_targets(policy, catalog, ballots, as_of):
    day = date.fromisoformat(as_of)
    require(catalog['schema'] == 'usa_poll_target_catalog_v1'
            and catalog['cycle'] == policy['cycle'], 'target catalog schema/cycle')
    require(date.fromisoformat(catalog['reviewed_on']) <= day, 'future target review')
    require(date.fromisoformat(catalog['election_date']).year == policy['cycle'], 'target election cycle')
    states = catalog['states']
    require(set(states) == set(STATES), 'target state universe')
    require(all(type(s['house_seats']) is int and s['house_seats'] > 0
                and s['name'] for s in states.values())
            and sum(s['house_seats'] for s in states.values()) == 435, 'House apportionment')
    require(len(catalog['senate_states']) == len(set(catalog['senate_states'])) == 35
            and set(catalog['senate_states']) <= set(states), 'Senate schedule')
    require(len(catalog['governor_states']) == len(set(catalog['governor_states'])) == 36
            and set(catalog['governor_states']) <= set(states), 'governor schedule')
    require(all(https_url(s['url']) for s in catalog['sources']), 'target source URL')
    require(ballots['schema'] == 'usa_poll_ballot_reviews_v1'
            and ballots['cycle'] == policy['cycle'], 'poll ballot schema/cycle')
    require(date.fromisoformat(ballots['reviewed_on']) <= day, 'future ballot review')
    selected = deepcopy(policy)
    universe = {}
    for state, item in states.items():
        for number in range(1, item['house_seats'] + 1):
            # FEC/map uses 00 for at-large; VoteHub reports e.g. AK-01.
            district = '00' if item['house_seats'] == 1 else f'{number:02}'
            rid = f'USA:{state}:house:{district}'
            subject = f'{policy["cycle"]} {state}-{number:02}'
            universe[rid] = (state, 'house', district, subject, 'us-representative', f'{state}-{number:02}')
        for office, poll_type in [('senate', 'us-senator'), ('governor', 'governor')]:
            if state in catalog[f'{office}_states']:
                universe[f'USA:{state}:{office}'] = (
                    state, office, None, f'{policy["cycle"]} {item["name"]}', poll_type, None)
    require(set(selected['races']) <= set(universe), 'existing poll target outside scheduled universe')
    for rid, (state, office, district, subject, poll_type, seat_name) in universe.items():
        if rid not in selected['races']:
            requested = state in selected.get('priority_regions', {}).get('requested_states', [])
            # apply_priorities publishes requested_states under priority_regions.
            if not requested:
                requested = state in catalog['requested_states']
            selected['races'][rid] = {
                'state': state, 'office': office, 'district': district,
                'subject': subject, 'poll_type': poll_type, 'seat_name': seat_name,
                'contest_id': f'{rid}:{policy["cycle"]}:general',
                'general_from': f'{policy["cycle"]}-09-01',
                'election_date': catalog['election_date'],
                'schedule_status': 'scheduled_matchup_unreviewed',
                'required_candidates': [], 'candidates': {},
                'collection_priority': {'order': 1 if requested else 4,
                    'reasons': ['requested_state'] if requested else ['national_scheduled_election']},
                'selection_reason_ko': '전국 본선 발견 대상. 대진·출처 검토를 통과해야 수치 편입.'}
        if district == '00':
            selected['races'][rid]['district_transport'] = {
                'provider_district': '01', 'canonical_district': '00',
                'basis': 'reviewed_single_seat_apportionment'}
        if office == 'house':
            selected['races'][rid]['seat_name'] = seat_name
    require(set(ballots['races']) <= set(universe), 'ballot review outside scheduled universe')
    for rid, review in ballots['races'].items():
        race = selected['races'][rid]
        require(review['race_id'] == rid and review['election_date'] == race['election_date']
                and review['office'] == race['office'] and review['state'] == race['state']
                and review['district'] == race['district'], 'ballot review race mismatch')
        require(date.fromisoformat(review['reviewed_on']) <= day
                and https_url(review['source_url']), 'ballot review date/source')
        if review.get('reviewed_general_from'):
            begin = date.fromisoformat(review['reviewed_general_from'])
            require(begin.year == policy['cycle'] and begin < date.fromisoformat(race['election_date'])
                    and https_url(review.get('period_source_url')), 'ballot general period evidence')
            race['general_from'] = begin.isoformat()
            race['general_period_source_url'] = review['period_source_url']
        names, candidates = [], {}
        for candidate in review['candidates']:
            require(candidate['name'] and candidate['party'] and https_url(candidate['source_url']),
                    'ballot candidate evidence')
            for name in [candidate['name'], *candidate.get('poll_name_aliases', [])]:
                require(name not in candidates, 'duplicate ballot alias')
                candidates[name] = {'party': candidate['party'],
                    'source_url': candidate['source_url'], 'candidate_id': None,
                    'canonical_name': candidate['name']}
            names.append(candidate['name'])
        require(len(names) == len(set(names)) and names, 'empty/duplicate ballot candidates')
        race['ballot_competition'] = competition(review)
        race['ballot_review'] = {k: review[k] for k in
            ('source_url', 'source_role', 'reviewed_on', 'coverage')}
        # Preserve previously reviewed poll spellings; aliases are explicitly
        # reviewed, not automatically fuzzy-matched to registrants.
        if race['required_candidates']:
            if not set(race['required_candidates']) <= set(candidates):
                race['required_candidates'] = []
                race['candidates'] = candidates
                race['schedule_status'] = 'changed_matchup_review_required'
                race['ballot_review']['hold_reason'] = 'changed_reviewed_poll_matchup'
                continue
            for name, candidate in candidates.items():
                if name not in race['candidates']:
                    race['candidates'][name] = candidate
                else:
                    require(race['candidates'][name]['party'] == candidate['party'], 'changed candidate party requires review')
                    race['candidates'][name]['canonical_name'] = candidate['canonical_name']
        elif len(names) >= 2:
            major = [c['name'] for c in review['candidates'] if c['party'] in ('DEM', 'REP')]
            chosen = major if len(major) >= 2 else names
            race['required_candidates'] = chosen
            race['candidates'] = candidates
            race['schedule_status'] = 'reviewed_general_matchup'
        else:
            # A single candidate is separately audited, never admitted as a poll
            # comparison, a confirmed winner or a 100% vote share.
            race['schedule_status'] = 'single_candidate_ballot_listing'
    for race in selected['races'].values():
        race.setdefault('ballot_competition', {
            'status': 'ballot_review_incomplete', 'candidate_count': None,
            'general_unopposed': None, 'no_vote_status': 'not_verified',
            'confirmed_winner': False})
    selected['states'] = sorted(states)
    selected['target_catalog'] = {'reviewed_on': catalog['reviewed_on'],
        'sources': deepcopy(catalog['sources']), 'scope': 'scheduled_general_elections',
        'counts': dict(Counter(r['office'] for r in selected['races'].values())),
        'ballot_review_count': len(ballots['races']),
        'meaning_ko': '대상 등록과 여론조사 확보는 다릅니다. 후보 명부·출처·기간 검사를 통과한 관측만 집계합니다.'}
    return selected


def competition(review):
    candidates = review['candidates']
    full = review['coverage'] in ('complete_ballot', 'complete_active_agency_listing')
    parties = {c['party'] for c in candidates}
    official_general_unopposed = (full and len(candidates) == 1
        and review.get('official_general_unopposed') is True
        and review['source_role'] == 'state_election_agency')
    status = ('official_general_unopposed_listing' if official_general_unopposed else
              'single_listed_candidate_requires_review' if len(candidates) == 1 else
              'same_party_contest' if len(parties) == 1 else
              'minor_party_or_independent_opposition' if not {'DEM', 'REP'} <= parties else
              'contested')
    return {'status': status, 'candidate_count': len(candidates), 'parties': sorted(parties),
        'coverage': review['coverage'], 'source_url': review['source_url'],
        'reviewed_on': review['reviewed_on'],
        'general_unopposed': True if official_general_unopposed else False if full and len(candidates) >= 2 else None,
        'write_in_candidates': [c['name'] for c in candidates if c['party'] == 'WRI'],
        'no_vote_status': 'official_listing_ballot_omission_rule' if official_general_unopposed
            and review.get('no_vote_law_url') else 'not_verified',
        'no_vote_law_url': review.get('no_vote_law_url'),
        'confirmed_winner': False,
        'note_ko': '주 선관위 명부의 본선 무경쟁과 법령 근거를 별도 기록. 인증된 당선 결과로 간주하지 않습니다.'}
