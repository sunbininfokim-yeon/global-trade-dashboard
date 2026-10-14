"""Audit the current UI's display roster coverage, not polling coverage.

Existing display rosters and reviewed polling fallback fields are distinct.
No absence here means a primary is unfinished, no candidate exists, or a seat
has been won. The universe is the 50 states / 435 House / 35 Senate / 36 governors.
"""
from collections import Counter
from datetime import date


def candidate_coverage(board, polls, catalog, as_of):
    day = date.fromisoformat(as_of)
    if catalog.get('schema') != 'usa_poll_target_catalog_v1' or catalog.get('cycle') != 2026:
        raise ValueError('Unknown candidate universe')
    if date.fromisoformat(catalog['reviewed_on']) > day:
        raise ValueError('Future candidate universe')
    if len(catalog['states']) != 50 or sum(s['house_seats'] for s in catalog['states'].values()) != 435:
        raise ValueError('Incomplete candidate universe')
    usa = [c for c in board['countries'] if c['iso3'] == 'USA']
    if len(usa) != 1: raise ValueError('Expected one USA board')
    states = {s['id']: s for s in usa[0]['ui_ready']['state_drilldown']['states']}
    if set(states) != set(catalog['states']): raise ValueError('Incomplete USA state display')
    if len(set(catalog['senate_states'])) != 35 or len(set(catalog['governor_states'])) != 36:
        raise ValueError('Incomplete statewide contest schedule')
    totals = {office: Counter() for office in ('house', 'senate', 'governor')}
    output = {}
    for sid, state in sorted(catalog['states'].items()):
        seats = state['house_seats']
        ids = {'house': [f'USA:{sid}:house:{"00" if seats == 1 else f"{n:02d}"}' for n in range(1, seats + 1)],
               'senate': [f'USA:{sid}:senate'] if sid in catalog['senate_states'] else [],
               'governor': [f'USA:{sid}:governor'] if sid in catalog['governor_states'] else []}
        row = {'state': sid, 'state_name': state['name'], 'offices': {}}
        for office, race_ids in ids.items():
            counts = Counter(expected=len(race_ids), display_roster=0, poll_fallback=0, missing=0,
                             complete_active_listing=0, official_certified=0, major_party_only=0,
                             reported_active_listing=0, unconfirmed_candidates=0)
            details = []; missing = []
            for rid in race_ids:
                roster = states[sid].get('election_matchups', {}).get(rid)
                displayed = roster and roster.get('race_id') == rid \
                    and roster.get('status') in ('certified_ballot', 'reported_general_matchup') \
                    and roster.get('election_date') == '2026-11-03' and roster.get('candidates') \
                    and date.fromisoformat(roster['reviewed_on']) <= day
                poll = polls.get('races', {}).get(rid, {})
                if displayed:
                    method = 'display_roster'; candidates = roster['candidates']; counts[method] += 1
                    if roster.get('coverage') in ('complete_ballot', 'complete_active_agency_listing'):
                        counts['complete_active_listing'] += 1
                    elif roster.get('coverage') == 'reported_active_candidate_listing':
                        counts['reported_active_listing'] += 1
                    else: counts['major_party_only'] += 1
                    counts['unconfirmed_candidates'] += len(roster.get('unconfirmed_candidates', []))
                    if roster['status'] == 'certified_ballot': counts['official_certified'] += 1
                    source = roster.get('source_url'); reviewed = roster['reviewed_on']
                elif poll.get('schedule_status') == 'reported_general_matchup' and len(poll.get('required_candidates', [])) >= 2:
                    method = 'poll_fallback'; counts[method] += 1
                    candidates = [{'name': name, **poll.get('candidates', {}).get(name, {})}
                                  for name in poll['required_candidates']]
                    review = poll.get('ballot_review') or poll.get('governor_roster') or {}
                    source = review.get('source_url'); reviewed = review.get('reviewed_on')
                    counts['major_party_only'] += 1
                else:
                    method = 'missing'; candidates = []; counts[method] += 1; missing.append(rid)
                    source = None; reviewed = None
                details.append({'race_id': rid, 'connection': method, 'candidates': candidates,
                                'source_url': source, 'reviewed_on': reviewed,
                                'coverage': roster.get('coverage') if displayed else None,
                                'source_role': roster.get('source_role') if displayed else None,
                                'ballot_competition': poll.get('ballot_competition')})
            counts['available'] = counts['display_roster'] + counts['poll_fallback']
            totals[office].update(counts)
            row['offices'][office] = {**dict(counts), 'missing_race_ids': missing, 'races': details,
                                     'status': 'not_on_2026_ballot' if not race_ids else 'complete_connection' if not missing else 'partial_connection' if counts['available'] else 'unconnected'}
        output[sid] = row
    return {'schema': 'usa_candidate_coverage_v1', 'cycle': 2026, 'checked_as_of': as_of,
            'scope': '50_states_scheduled_contests_display_connection',
            'board_generated_at': board.get('generated_at'), 'polls_fetched_at': polls.get('fetched_at'),
            'totals': {k: dict(v) for k, v in totals.items()}, 'states': output,
            'limitations_ko': ['후보 화면 연결 감사이며 50주 공식 후보 전수 인증이나 여론조사 확보율이 아닙니다.',
                               '주지사·상원 비선거 주는 후보 누락으로 세지 않습니다.',
                               '주요 정당 대진만 검토한 기록은 제3당·기명 후보 완전 명부가 아닙니다.',
                               '후보 명부 누락은 경선 미완료·후보 부재·무투표 당선 판정이 아닙니다.']}
