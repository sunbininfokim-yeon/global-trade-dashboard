"""One-state election evidence joins; collection, coverage and review stay distinct."""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import re

from .polls import atomic, read, require
from .superpac import STATES
from .live_polls import summarize
from .house_rosters import same_source_name

FEDERAL = ('super_pac',)
STATE_IE = ('state_independent_expenditure_committee', 'state_independent_spender_unclassified')


def ordered_states(plan, as_of):
    require(plan['schema'] == 'usa_state_evidence_plan_v1' and plan['cycle'] == 2026, 'state plan schema/cycle')
    require(date.fromisoformat(plan['reviewed_on']) <= date.fromisoformat(as_of), 'future state plan')
    require(plan['group_order'] == list('ABCDE') and set(plan['groups']) == set('ABCDE'), 'state groups')
    rows = []
    for group in plan['group_order']:
        states = plan['groups'][group]['states']
        require(len(states) == 10, 'state group must contain ten states')
        rows.extend((group, state) for state in states)
    require(len(rows) == 50 and {s for _, s in rows} == set(STATES) and len({s for _, s in rows}) == 50,
            'missing or duplicated state')
    require(set(plan['states']) == set(STATES) and plan['poll_windows'] == [7, 14], 'state metadata/windows')
    return rows


def expected_races(state, catalog):
    seats = catalog['states'][state]['house_seats']
    ids = [f'USA:{state}:house:{"00" if seats == 1 else f"{n:02d}"}' for n in range(1, seats + 1)]
    ids += [f'USA:{state}:{office}' for office in ('senate', 'governor') if state in catalog[f'{office}_states']]
    return ids


def amounts(totals, categories):
    selected = [totals[c] for c in categories if totals.get(c, {}).get('records', 0) > 0]
    return {'status': 'observed_partial' if selected else 'no_observed_records',
            'support_cents': sum(r['support_cents'] for r in selected) if selected else None,
            'oppose_cents': sum(r['oppose_cents'] for r in selected) if selected else None,
            'records': sum(r['records'] for r in selected) if selected else None}


def candidate_finance(candidate, asset, office):
    categories = STATE_IE if office == 'governor' else FEDERAL
    ident = candidate.get('finance_candidate_id') or candidate.get('candidate_id')
    matches = [c for c in asset.get('candidates', []) if ident and c['candidate_id'] == ident]
    require(len(matches) <= 1, 'ambiguous candidate finance ID')
    row = matches[0] if matches else {}
    return {'join_status': 'same_reviewed_candidate_id' if row else 'candidate_finance_not_linked',
            'measure': 'state_independent_spending' if office == 'governor' else 'federal_super_pac',
            'all_reported_election_types': amounts(row.get('totals_by_category', {}), categories),
            'by_election_type': {k: amounts(v['totals_by_category'], categories)
                                 for k, v in sorted(row.get('election_types', {}).items())},
            'reported_names': row.get('reported_names', []),
            'reported_parties': row.get('reported_parties', []),
            'note_ko': '후보 캠프가 받은 후원금이 아닌 후보 대상 독립지출. 반대액을 상대 후보 지지액으로 전환하지 않습니다.'}


def build_state(state, group, plan, catalog, federal_rosters, governors, polls, finance, source_directory, as_of, identity_reviews=None, governor_audits=None, governor_access=None):
    require(state in catalog['states'] and finance['cycle'] == 2026 and polls['cycle'] == 2026, 'state evidence cycle')
    require(date.fromisoformat(polls['as_of']) <= date.fromisoformat(as_of), 'future polling snapshot')
    races = []
    for rid in expected_races(state, catalog):
        poll = polls['races'].get(rid)
        require(poll and poll['race_id'] == rid and poll['state'] == state, 'missing/wrong state poll slot')
        poll_as_of = poll.get('as_of', polls['as_of'])
        require(date.fromisoformat(poll_as_of) <= date.fromisoformat(as_of), 'future state polling snapshot')
        office = poll['office']; roster = federal_rosters['races'].get(rid)
        if office == 'governor':
            roster = governors['contests'].get(state)
        require(roster and roster['candidates'], 'missing candidate roster')
        require(roster['state'] == state and (office == 'governor' or roster['office'] == office), 'candidate scope')
        asset = finance['races'].get(rid, {})
        require(not asset or asset['race_id'] == rid and asset['state_id'] == state and asset['office'] == office,
                'finance race scope mismatch')
        candidates = deepcopy(roster['candidates'])
        for candidate in candidates:
            for review in (identity_reviews or {}).get('races', {}).get(rid, []):
                if review['candidate_name'] == candidate['name'] and review['party'] == candidate['party']:
                    require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of), 'future finance identity review')
                    require(re.fullmatch(r'S[0-9A-Z]{8}', review['candidate_id']) is not None and office == 'senate', 'invalid Senate identity')
                    provenance = [p for p in federal_rosters.get('source_snapshots', [])
                                  if p.get('state') == state and p.get('source_url') == review['source_url']
                                  and p.get('sha256') == review['source_sha256']]
                    require(len(provenance) == 1, 'identity source snapshot mismatch')
                    candidate['finance_candidate_id'] = review['candidate_id']
                    candidate['finance_identity_evidence'] = deepcopy(review)
            candidate['finance'] = candidate_finance(candidate, asset, office)
            candidate['finance_identity_hold'] = next((deepcopy(h) for h in (identity_reviews or {}).get('held_candidates', [])
                if h['race_id'] == rid and h['name'] == candidate['name']), None)
        def matched(answer):
            party = 'REP' if answer.get('party') == 'GOP' else answer.get('party')
            return any(c['party'] == party and any(same_source_name(answer['name'], n) for n in
                [c['name'], *c.get('poll_name_aliases', []), *c.get('reported_name_aliases', [])]) for c in candidates)
        held = [p['id'] for p in poll.get('observations', [])
                if any(a.get('party') in ('DEM', 'REP', 'GOP') and not matched(a) for a in p['answers'])]
        unmatched_nonmajor = sorted({a['name'] for p in poll.get('observations', []) for a in p['answers']
                                     if a.get('party') not in ('DEM', 'REP', 'GOP') and not matched(a)})
        changed = bool(held)
        phase = poll.get('phase', 'pre_election')
        if date.fromisoformat(as_of) > date.fromisoformat(poll['election_date']) and phase != 'certified_result':
            phase = 'awaiting_certified_result'
        closed = phase in ('awaiting_certified_result', 'certified_result')
        observations = [] if changed or closed else deepcopy(poll.get('observations', []))
        fetched = poll.get('fetched_at', polls['fetched_at'])
        age_hours = max(0, (datetime.combine(date.fromisoformat(as_of), datetime.min.time(), timezone.utc)
                           - datetime.fromisoformat(fetched.replace('Z', '+00:00'))).total_seconds() / 3600)
        source_status = poll.get('source_status', polls['source_status'])
        source_held = source_status not in ('ok', 'replay') or age_hours > polls.get('stale_after_hours', 192)
        neutral = ('changed_matchup_review_required' if changed else phase if closed else
                   'source_error_or_stale' if source_held else None)
        windows = {str(d): {'status': neutral, 'party': None, 'pollster_count': 0} if neutral
                   else summarize(observations, poll, as_of, d) for d in (7, 14)}
        polling = {'as_of': poll_as_of, 'fetched_at': fetched,
            'source_status': source_status, 'schedule_status': poll.get('schedule_status'),
            'observations': observations, 'windows': windows, 'windows_checked_as_of': as_of,
            'held_observation_ids': held, 'phase': phase, 'result': deepcopy(poll.get('result')),
            'unmatched_nonmajor_answer_names': unmatched_nonmajor,
            'source_url': poll.get('source_url', polls['source']['request_url']),
            'monitoring': deepcopy(polls.get('monitoring', {}).get('race_coverage', {}).get(rid, {})),
            'automatic_admission': poll.get('schedule_status') == 'reported_general_matchup' and not neutral,
            'note_ko': 'API 발견·후보 명부 연결·집계 적격·최근 조사 확보는 별개. 기관 수를 품질 등급으로 바꾸지 않습니다.'}
        races.append({'race_id': rid, 'state': state, 'office': office, 'district': poll.get('district'),
            'candidate_source_url': roster['source_url'],
            'candidate_coverage': roster.get('coverage', 'reported_major_party_field'),
            'candidate_source_role': roster.get('source_role', 'reported_governor_matchup'),
            'candidates': candidates, 'polling': polling,
            'finance': {'status': asset.get('status', 'asset_not_available'), 'data_file': asset.get('data_file'),
                'source_status': deepcopy(finance['source_status'].get(state + '_governor' if office == 'governor' else 'federal')),
                'all_reported_candidates': amounts(asset.get('totals_by_category', {}), STATE_IE if office == 'governor' else FEDERAL),
                'note_ko': '레이스 전체 금액에는 과거·경선 후보가 포함될 수 있습니다. 현재 후보별 금액은 검증한 후보 ID로 별도 연결합니다.'},
            'ballot_competition': deepcopy(poll.get('ballot_competition', {}))})
    counts = {}
    for office in ('house', 'senate', 'governor'):
        selected = [r for r in races if r['office'] == office]
        counts[office] = {'scheduled_races': len(selected), 'non_election': not selected,
            'with_poll_observations': sum(bool(r['polling']['observations']) for r in selected),
            'with_recent_7d': sum(r['polling']['windows']['7']['pollster_count'] > 0 for r in selected),
            'with_recent_14d': sum(r['polling']['windows']['14']['pollster_count'] > 0 for r in selected),
            'with_observed_current_candidate_spending': sum(any(c['finance']['all_reported_election_types']['records']
                                                              for c in r['candidates']) for r in selected),
            'candidate_id_links': sum(c['finance']['join_status'] == 'same_reviewed_candidate_id'
                                     for r in selected for c in r['candidates'])}
    agency = deepcopy(source_directory['states'].get(state))
    audit = deepcopy((governor_audits or {}).get(state))
    if audit:
        require(audit['schema'] == 'usa_governor_finance_audit_v1' and audit['state'] == state
                and audit['cycle'] == 2026 and audit['status'] == 'collected_normalization_held'
                and date.fromisoformat(audit['captured_at'][:10]) <= date.fromisoformat(as_of),
                'governor finance audit scope/date mismatch')
    access = deepcopy((governor_access or {}).get(state))
    if access:
        from .governor_source_access import validate_access
        validate_access(access, state, 2026, as_of)
    if state not in catalog['governor_states']:
        governor_route = {'status': 'non_election', 'agency': agency}
    elif finance['source_status'].get(state + '_governor'):
        governor_route = {'status': 'implemented_partial', 'agency': agency}
    elif audit:
        governor_route = {'status': 'collected_normalization_held', 'agency': agency, 'audit': audit}
    elif access:
        governor_route = {'status': access['status'], 'agency': agency}
    else:
        governor_route = {'status': 'adapter_or_source_review_required', 'agency': agency,
            'directory_url': source_directory['directory_url']}
    if access:
        governor_route['access_check'] = access
    receipt = deepcopy(polls.get('state_captures', {}).get(state))
    governor_success = finance['source_status'].get(state + '_governor', {}).get('last_success_at')
    governor_reviewed = state not in catalog['governor_states'] or bool(receipt and (
        governor_success and receipt.get('governor_last_success_at') == governor_success or
        audit and receipt.get('governor_audit_captured_at') == audit['captured_at']))
    primary_reviewed = bool(receipt and receipt.get('primary_rechecked_ids'))
    if primary_reviewed and receipt.get('primary_review_data_file'):
        verified = {p['id'] for r in races for p in r['polling']['observations']
                    if p.get('source_quality', {}).get('verification_level') == 'primary_toplines_checked'}
        primary_reviewed = set(receipt['primary_rechecked_ids']) <= verified
    reviewed = bool(receipt and receipt.get('cycle') == 2026 and receipt.get('state') == state
                    and governor_reviewed and primary_reviewed)
    blocked_review = bool(not reviewed and receipt and receipt.get('cycle') == 2026 and
        receipt.get('state') == state and primary_reviewed and access and
        access['status'] in ('source_access_blocked', 'source_unavailable') and
        receipt.get('governor_source_checked_at') == access['checked_at'])
    return {'schema': 'usa_state_election_evidence_v1', 'cycle': 2026, 'state': state,
        'state_name': catalog['states'][state]['name'], 'group': group, 'checked_as_of': as_of,
        'status': 'partial_observed', 'work_status': 'live_sources_reviewed_partial' if reviewed else
            'live_poll_sources_reviewed_finance_blocked' if blocked_review else 'baseline_join_checked',
        'live_capture_receipt': receipt,
        'priority': deepcopy(plan['states'][state]), 'office_coverage': counts, 'races': races,
        'governor_source_route': governor_route,
        'unmatched_reported_finance_races': [r for r in finance['unmatched'] if r.startswith(f'USA:{state}:')],
        'source_dates': {'poll_as_of': polls['as_of'], 'poll_fetched_at': polls['fetched_at'],
                         'finance_index_generated_at': finance['generated_at'],
                         'federal_last_success_at': finance['source_status'].get('federal', {}).get('last_success_at')},
        'limitations_ko': ['50주 연결 점검을 주별 실제 원문 수집/공식 공시 전수 완성과 동일시하지 않습니다.',
            '미확보는0달러·조사0%·승패가 아닙니다. 주 공시 독립지출은 연방 Super PAC 유형과 구분합니다.',
            '원문 선거유형 코드별 본선·경선·미확인을 보존합니다. 처리 기준일이 원래 자료 기준일을 대체하지 않습니다.',
            '후보 이름 변경으로 대진이 맞지 않는 조사는 새 후보에게 넘기지 않습니다.']}


def load_finance(index_path, cycle):
    root = index_path.parent.resolve(); index = read(index_path)
    require(index['schema'] == 'usa_election_finance_index_v1', 'finance index schema')
    def asset(relative):
        target = (root / relative).resolve()
        require(target.is_relative_to(root) and target.suffix == '.json', 'unsafe finance path')
        return read(target)
    meta = index['cycles'][str(cycle)]; national = asset(meta['national_file'])
    require(national['schema'] == 'usa_election_finance_national_v1' and national['cycle'] == cycle, 'finance national cycle')
    races = {}
    for state, entry in national['states'].items():
        shard = asset(entry['data_file'])
        require(shard['state_id'] == state and shard['cycle'] == cycle, 'finance state cycle')
        for link in shard['races']:
            row = asset(link['data_file']); rid = link['race_id']
            require(rid not in races and row['cycle'] == cycle and row['race_id'] == rid
                    and row['schema'] == 'usa_election_finance_race_v1' and row['state_id'] == state,
                    'invalid/duplicate finance race')
            races[rid] = {**row, 'data_file': link['data_file']}
    return {'cycle': cycle, 'races': races, 'source_status': meta['source_status'],
            'generated_at': index['generated_at'], 'unmatched': national['unmatched_district_race_ids']}


def publish_states(public, plan, selected, builder, checked_at):
    """Publish each state serially; failures keep its last file and source dates."""
    path = public / 'usa_election_state_evidence_index_v1.json'
    previous = read(path) if path.exists() else None
    if previous:
        require(previous['schema'] == 'usa_state_evidence_index_v1' and previous['cycle'] == plan['cycle'], 'state index cycle')
    result = deepcopy(previous) if previous else {'schema': 'usa_state_evidence_index_v1', 'cycle': plan['cycle'], 'states': {}}
    result.update({'checked_at': checked_at, 'groups': deepcopy(plan['groups']), 'group_order': plan['group_order'],
                   'deployment_hold': True, 'note_ko': '주별 연결 점검과 수집 완료는 별개. 각 주 work_status/출처 범위 확인 필요.'})
    failures = deepcopy(result.get('errors', {}))
    for group, state in selected:
        try:
            payload = builder(state, group)
            require(payload['state'] == state and payload['group'] == group and payload['cycle'] == plan['cycle'], 'published state scope')
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
            relative = f'usa_election_state_evidence/{plan["cycle"]}/{state}-{digest}.json'
            target = public / relative
            if not target.exists(): atomic(target, payload)
            result['states'][state] = {'group': group, 'data_file': relative,
                'status': payload['status'], 'work_status': payload['work_status'],
                'office_coverage': payload['office_coverage'], 'source_dates': payload['source_dates'],
                'governor_source_status': payload['governor_source_route']['status'], 'checked_at': checked_at}
            failures.pop(state, None)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures[state] = type(exc).__name__
            if state in result['states']:
                result['states'][state].update({'status': 'carried_forward', 'carried_at': checked_at, 'error_type': type(exc).__name__})
        # Persist progress after each state so interrupted runs can resume.
        result['last_processed_state'] = state
        result['errors'] = failures
        result['processed_state_count'] = len(result['states'])
        atomic(path, result)
    result['status'] = 'partial_observed' if len(result['states']) == 50 and not failures else 'incomplete'
    result['deep_source_review_remaining'] = [s for _, s in ordered_states(plan, checked_at[:10])
        if result['states'].get(s, {}).get('work_status') != 'live_sources_reviewed_partial' or s in failures]
    result['source_review_blocked_states'] = [s for s in result['deep_source_review_remaining']
        if result['states'].get(s, {}).get('work_status') == 'live_poll_sources_reviewed_finance_blocked'
        and s not in failures]
    result['next_state_to_review'] = next((s for s in result['deep_source_review_remaining']
        if s not in result['source_review_blocked_states']), None)
    result['next_state_to_retry'] = next(iter(result['source_review_blocked_states']), None)
    atomic(path, result)
    return result
