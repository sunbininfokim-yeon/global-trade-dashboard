"""Race-level poll/spending coverage, including missing and non-election states."""
from collections import Counter, defaultdict


def attach_gaps(board, finance):
    races, states = {}, defaultdict(dict)
    for rid, race in board['races'].items():
        coverage = board['monitoring']['race_coverage'][rid]
        asset = finance.get('races', {}).get(rid, {})
        category = asset.get('totals_by_category', {}).get('super_pac', {})
        general = asset.get('totals_by_election_type', {}).get(f'G{board["cycle"]}', {}).get('super_pac', {})
        state_ie = {k: v for k, v in asset.get('totals_by_category', {}).items()
                    if k.startswith('state_independent')}
        finance_status = ('source_unsupported' if asset.get('status') == 'unsupported' else
                          'asset_not_available' if not asset else
                          'observed_partial' if category.get('records', 0) > 0 else 'no_observed_super_pac')
        record = {'state': race['state'], 'office': race['office'], 'district': race['district'],
            'priority': coverage['priority'], 'poll_status': coverage['status'],
            'phase': race.get('phase'),
            'poll_observation_count': coverage['accepted_count'],
            'poll_eligible_count': coverage['aggregation_eligible_count'],
            'recent_7d_pollsters': coverage['windows']['7']['pollster_count'],
            'recent_14d_pollsters': coverage['windows']['14']['pollster_count'],
            'provider_record_count': coverage['provider_record_count'],
            'rejection_reasons': coverage['rejection_reasons'],
            'matchup_reviewed': coverage['matchup_reviewed'],
            'poll_comparison_requirement': 'not_required_official_general_unopposed'
                if race.get('ballot_competition', {}).get('general_unopposed') is True
                else 'required_or_matchup_unreviewed',
            'poll_route': {'transport': 'VoteHub_public_API', 'api_key_required': False,
                'status': 'connected' if board['source_status'] in ('ok', 'replay') else 'source_error',
                'request_url': board['source']['request_url'],
                'automatic_admission': coverage['matchup_reviewed'],
                'limitations_ko': '미등록 출처·변경 대진은 검토 대기. 제공 API 밖 모든 조사 발견을 보장하지 않습니다.'},
            'super_pac': {'status': finance_status,
                'records': category.get('records') if asset else None,
                'general_records': general.get('records') if asset else None,
                'data_file': asset.get('data_file')},
            'state_external_spending': {'status': 'observed_partial' if any(v.get('records', 0) > 0 for v in state_ie.values())
                else 'source_unsupported' if asset.get('status') == 'unsupported' else 'not_observed',
                'records': sum(v.get('records', 0) for v in state_ie.values()) if state_ie else None,
                'measure': 'state_independent_spending_not_federal_super_pac'},
            'ballot_competition': race.get('ballot_competition', {'status': 'ballot_review_incomplete'})}
        races[rid] = record
        states[race['state']].setdefault(race['office'], []).append(rid)
    for state, offices in states.items():
        for office in ('house', 'senate', 'governor'):
            ids = offices.get(office, [])
            offices[office] = {'race_ids': sorted(ids), 'race_count': len(ids),
                'scheduled': bool(ids),
                'polls_without_observations': [r for r in sorted(ids) if not races[r]['poll_observation_count']],
                'polls_without_7d': [r for r in sorted(ids) if not races[r]['recent_7d_pollsters']],
                'polls_not_required_general_unopposed': [r for r in sorted(ids)
                    if races[r]['poll_comparison_requirement'] == 'not_required_official_general_unopposed'],
                'super_pac_without_observed_records': [r for r in sorted(ids) if races[r]['super_pac']['status'] != 'observed_partial']}
    board['data_gaps'] = {'schema': 'usa_election_data_gaps_v1', 'cycle': board['cycle'],
        'as_of': board['as_of'], 'fetched_at': board['fetched_at'],
        'finance_generated_at': finance.get('generated_at'),
        'counts_by_office': {office: {'races': sum(r['office'] == office for r in races.values()),
            'with_polls': sum(r['office'] == office and r['poll_observation_count'] > 0 for r in races.values()),
            'with_recent_7d': sum(r['office'] == office and r['recent_7d_pollsters'] > 0 for r in races.values()),
            'with_recent_14d': sum(r['office'] == office and r['recent_14d_pollsters'] > 0 for r in races.values()),
            'with_super_pac': sum(r['office'] == office and r['super_pac']['status'] == 'observed_partial' for r in races.values())}
            for office in ('house', 'senate', 'governor')},
        'ballot_counts': dict(Counter(r['ballot_competition']['status'] for r in races.values())),
        'official_general_unopposed_listings': sorted(rid for rid, r in races.items()
            if r['ballot_competition']['status'] == 'official_general_unopposed_listing'),
        'races': races, 'states': dict(sorted(states.items())),
        'limitations_ko': ['여론조사 API 미발견은 조사 자체가 없다는 판정이 아닙니다.',
            '본선 슈퍼팩과 경선 포함 회기 전체 지출은 구분합니다. 미수집·미관측은 0달러가 아닙니다.',
            '주지사 주별 독립지출은 연방 슈퍼팩 유형과 동일하지 않습니다.',
            '무경쟁 명부는 당선 확정 결과가 아닙니다. 전체 명부 미확보 시 무투표 여부 미확인.']}
    refresh_gap_lifecycle(board)
    return board


def refresh_gap_lifecycle(board):
    """Close the new audit's live counts even when the polling API has failed.

    Original collection dates, provider counts and finance evidence remain;
    lifecycle checks do not make an old observation a freshly collected poll.
    """
    gaps = board.get('data_gaps')
    if not gaps:
        return
    for rid, row in gaps['races'].items():
        race = board.get('races', {}).get(rid, {})
        if race.get('phase') not in ('awaiting_certified_result', 'certified_result'):
            continue
        row.update({'phase': race['phase'], 'poll_status': 'election_closed',
            'poll_observation_count': 0, 'poll_eligible_count': 0,
            'recent_7d_pollsters': 0, 'recent_14d_pollsters': 0})
        row['poll_route'].update({'status': 'election_closed', 'automatic_admission': False})
    for offices in gaps['states'].values():
        for item in offices.values():
            live = [rid for rid in item['race_ids'] if gaps['races'][rid]['poll_status'] != 'election_closed']
            item['polls_without_observations'] = [rid for rid in live if not gaps['races'][rid]['poll_observation_count']]
            item['polls_without_7d'] = [rid for rid in live if not gaps['races'][rid]['recent_7d_pollsters']]
    for office, counts in gaps['counts_by_office'].items():
        rows = [r for r in gaps['races'].values() if r['office'] == office]
        counts.update({'with_polls': sum(r['poll_observation_count'] > 0 for r in rows),
            'with_recent_7d': sum(r['recent_7d_pollsters'] > 0 for r in rows),
            'with_recent_14d': sum(r['recent_14d_pollsters'] > 0 for r in rows),
            'closed_elections': sum(r['poll_status'] == 'election_closed' for r in rows)})
    gaps['lifecycle_checked_as_of'] = board.get('lifecycle_checked_as_of', board['as_of'])
