"""Prioritize the House races actually marked Lean/Toss-Up in the overview.

Cook ratings and the user's additional cautions remain separate evidence. This
orders review work; it neither changes Cook ratings nor manufactures polls.
"""
from copy import deepcopy
from datetime import date
from .polls import https_url, require

COMPETITIVE = {'lean_dem', 'lean_rep', 'toss_up'}
RATINGS = COMPETITIVE | {'solid_dem', 'likely_dem', 'solid_rep', 'likely_rep'}


def party(value):
    return 'GOP' if value in ('REP', 'GOP') else 'DEM' if value == 'DFL' else value


def caution_reasons(race, country, config):
    reasons = []
    state = race['state']
    state_class = ('swing' if state in config['swing_states_2024'] else
                   'blue' if state in config['blue_states_2024'] else 'red')
    if ((state_class == 'blue' and race.get('cook_held_party') == 'GOP') or
            (state_class == 'red' and race.get('cook_held_party') == 'DEM')):
        reasons.append({'criterion': 'state_presidential_held_party_mismatch',
            'basis_ko': '2024 대선 주 전체 승리 정당과 Cook 표기 지역구 보유 정당이 다름. 지역구 대선 교차투표의 증거는 아님.',
            'source_url': config['classification_sources']['winner']})
    for record in country.get('ui_ready', {}).get('congress', {}).get('swing_seats', []):
        if (record.get('chamber'), record.get('state'), record.get('district')) != ('house', state, race['district']):
            continue
        evidence = record.get('evidence') or []
        same_boundary = record.get('boundary_lineage_verified') is True or race['district'] == '00'
        parties = [party(e.get('party_abbr')) for e in evidence]
        changes = sum(a != b for a, b in zip(parties, parties[1:]))
        history = (record.get('criterion') == 'two_party_changes_last_three_general_elections'
            and [e.get('year') for e in evidence] == [2020, 2022, 2024]
            and all(p in ('DEM', 'GOP') for p in parties) and changes >= 2)
        split = (record.get('criterion') == 'presidential_congressional_split_ticket'
            and any(e.get('year') == 2024 and party(e.get('presidential_party_abbr')) in ('DEM', 'GOP')
                and party(e.get('party_abbr')) in ('DEM', 'GOP')
                and party(e.get('presidential_party_abbr')) != party(e.get('party_abbr')) for e in evidence))
        if evidence and all(https_url(e.get('source_url')) for e in evidence) and same_boundary and (history or split):
            reasons.append({'criterion': record['criterion'], 'basis_ko': record.get('basis_ko'),
                            'source_url': evidence[-1]['source_url']})
    return reasons


def apply_house_focus(policy, ratings, election_board, config, as_of):
    day = date.fromisoformat(as_of)
    require(config['schema'] == 'usa_house_poll_focus_policy_v1' and config['cycle'] == policy['cycle'],
            'House focus policy schema/cycle')
    require(date.fromisoformat(config['reviewed_on']) <= day, 'future House focus review')
    require(set(config['blue_states_2024']).isdisjoint(config['swing_states_2024'])
            and all(https_url(u) for u in config['classification_sources'].values()), 'House classification sources')
    require(ratings['schema'] == 'usa_election_ratings_review_v1' and ratings['cycle'] == policy['cycle'],
            'House ratings schema/cycle')
    row = ratings['offices']['house']
    reviewed = date.fromisoformat(row['as_of'])
    require(reviewed <= day and https_url(row['source_url']), 'House ratings date/source')
    require(election_board['year'] == policy['cycle'], 'House context cycle')
    countries = [c for c in election_board['countries'] if c.get('iso3') == 'USA']
    require(len(countries) == 1, 'House country context')
    country = countries[0]
    races = row['races']
    expected = {rid for rid, r in policy['races'].items() if r['office'] == 'house'}
    require(len(races) == row['total_contests'] == 435 and len({r['race_id'] for r in races}) == 435
            and {r['race_id'] for r in races} == expected, 'House focus scheduled universe')
    selected = deepcopy(policy)
    focused = {}
    for race in races:
        rid = race['race_id']
        target = selected['races'][rid]
        require(rid == f'USA:{race["state"]}:house:{race["district"]}'
                and race['state'] == target['state'] and race['district'] == target['district']
                and race['rating'] in RATINGS, 'House rating identity')
        reasons = caution_reasons(race, country, config)
        additional = bool(reasons) and race['rating'] not in COMPETITIVE
        if race['rating'] not in COMPETITIVE and not additional:
            continue
        previous = target.get('collection_priority', {'order': 4, 'reasons': []})
        target['collection_priority'] = {**previous, 'order': 0, 'within_focus_order': previous['order'],
            'reasons': list(dict.fromkeys(['house_toss_up_lean_first', *previous['reasons']]))}
        focused[rid] = {'race_id': rid, 'state': race['state'], 'district': race['district'],
            'cook_rating': race['rating'], 'cook_held_party': race.get('cook_held_party'),
            'effective_rating': 'toss_up' if additional else race['rating'],
            'classification': 'user_added_caution' if additional else 'cook_toss_up_or_lean',
            'caution_reasons': reasons, 'rating_as_of': row['as_of'], 'rating_source_url': row['source_url']}
    selected['house_poll_focus'] = {'schema': 'usa_house_poll_focus_v1', 'cycle': policy['cycle'],
        'checked_as_of': as_of, 'requested_display_count': config['requested_display_count'],
        'race_count': len(focused), 'cook_competitive_count': sum(r['classification'] == 'cook_toss_up_or_lean' for r in focused.values()),
        'user_added_count': sum(r['classification'] == 'user_added_caution' for r in focused.values()),
        'rating_as_of': row['as_of'], 'rating_source_url': row['source_url'],
        'ratings_status': 'reviewed_current' if (day-reviewed).days <= ratings.get('max_age_days', 21) else 'stale_reviewed_snapshot',
        'context_generated_at': election_board.get('generated_at'), 'classification_sources': config['classification_sources'],
        'races': focused,
        'limitations_ko': ['Cook 공식 Lean/Toss-Up과 사용자 추가 주의 지역구를 분리합니다. 추가 분류는 Cook 평가가 아닙니다.',
            '주 전체 대선 승리 정당과 지역구 보유 정당 차이는 실제 지역구 경합도·대선 교차투표의 증거가 아닙니다.',
            '공개 API는 전국 응답을 한 번 가져오며, 우선순위는 누락 조사·원문·대진 검토 목록에 적용합니다.',
            '대상 수는 현행 데이터로 재계산합니다. 요청 당시 104를 고정하거나 임의 지역구를 추가하지 않습니다.']}
    return selected


def attach_house_focus(board, policy):
    if policy.get('house_poll_focus_health'):
        board['house_poll_focus_health'] = deepcopy(policy['house_poll_focus_health'])
    focus = deepcopy(policy.get('house_poll_focus'))
    if not focus:
        return board
    coverage = board['monitoring']['race_coverage']
    queue = board.get('review_queue', [])
    for rid, row in focus['races'].items():
        item = coverage[rid]
        race = board['races'][rid]
        excluded = race.get('ballot_competition', {}).get('general_unopposed') is True
        action = ('election_closed' if race['phase'] != 'pre_election' else
                  'not_required_official_general_unopposed' if excluded else
                  'review_ballot_matchup' if not item['matchup_reviewed'] else
                  'review_source_records' if item['review_queue_ids'] else
                  'monitor_new_polls' if item['accepted_count'] else 'discover_original_release')
        row.update({'collection_priority': item['priority'], 'coverage_status': item['status'],
            'accepted_count': item['accepted_count'], 'aggregation_eligible_count': item['aggregation_eligible_count'],
            'matchup_reviewed': item['matchup_reviewed'], 'provider_record_count': item['provider_record_count'],
            'recent_7d_pollsters': item['windows']['7']['pollster_count'],
            'recent_14d_pollsters': item['windows']['14']['pollster_count'],
            'poll_comparison_required': not excluded, 'next_action': action,
            'rejection_reasons': item['rejection_reasons'], 'review_queue_ids': item['review_queue_ids'],
            'finance_join': item['finance_join']})
    focused = focus['races']
    focus['races'] = dict(sorted(focused.items(), key=lambda x: (x[1]['collection_priority']['within_focus_order'], x[0])))
    focus['summary'] = {'with_observations': sum(r['accepted_count'] > 0 for r in focused.values()),
        'without_observations': sum(r['accepted_count'] == 0 for r in focused.values()),
        'with_eligible_observations': sum(r['aggregation_eligible_count'] > 0 for r in focused.values()),
        'recent_7d': sum(r['recent_7d_pollsters'] > 0 for r in focused.values()),
        'recent_14d': sum(r['recent_14d_pollsters'] > 0 for r in focused.values()),
        'matchup_reviewed': sum(r['matchup_reviewed'] for r in focused.values()),
        'comparison_not_required_unopposed': sum(not r['poll_comparison_required'] for r in focused.values())}
    focus['without_observations'] = [rid for rid, r in focus['races'].items() if not r['accepted_count']]
    focus['review_queue'] = sorted([r for r in queue if r['race_id'] in focused],
        key=lambda r: (focused[r['race_id']]['collection_priority']['within_focus_order'], r['race_id'], r['id']))
    board['house_poll_focus'] = focus
    board['monitoring']['groups']['house_toss_up_lean_first'] = {'race_count': focus['race_count'],
        'with_observations': focus['summary']['with_observations'], 'recent_7d': focus['summary']['recent_7d'],
        'recent_14d': focus['summary']['recent_14d']}
    refresh_house_focus_lifecycle(board)
    return board


def refresh_house_focus_lifecycle(board):
    """Close active focus counts on election completion, including API failure."""
    focus = board.get('house_poll_focus')
    if not focus:
        return
    closed = []
    for rid, row in focus['races'].items():
        race = board.get('races', {}).get(rid, {})
        if race.get('phase') in ('awaiting_certified_result', 'certified_result'):
            row.update({'coverage_status': 'election_closed', 'accepted_count': 0,
                'aggregation_eligible_count': 0, 'recent_7d_pollsters': 0,
                'recent_14d_pollsters': 0, 'next_action': 'election_closed'})
            closed.append(rid)
    live = [r for rid, r in focus['races'].items() if rid not in closed]
    focus['summary'].update({'with_observations': sum(r['accepted_count'] > 0 for r in live),
        'without_observations': sum(not r['accepted_count'] for r in live),
        'with_eligible_observations': sum(r['aggregation_eligible_count'] > 0 for r in live),
        'recent_7d': sum(r['recent_7d_pollsters'] > 0 for r in live),
        'recent_14d': sum(r['recent_14d_pollsters'] > 0 for r in live), 'closed_elections': len(closed)})
    focus['without_observations'] = [rid for rid, r in focus['races'].items() if rid not in closed and not r['accepted_count']]
    focus['lifecycle_checked_as_of'] = board.get('lifecycle_checked_as_of', board['as_of'])
    if board.get('monitoring', {}).get('groups', {}).get('house_toss_up_lean_first'):
        board['monitoring']['groups']['house_toss_up_lean_first'].update({k: focus['summary'][k]
            for k in ('with_observations', 'recent_7d', 'recent_14d')})
