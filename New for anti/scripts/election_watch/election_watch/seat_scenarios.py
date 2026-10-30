"""Conditional seat counts, with missing races retained and no win probabilities."""
from collections import Counter
from datetime import date, datetime, timezone
from .polls import require


PARTY = {'DEM': 'DEM', 'REP': 'GOP', 'GOP': 'GOP', 'IND': 'IND'}
COMPETITIVE = {'toss_up', 'lean_dem', 'lean_rep'}
PARTY_KO = {'DEM': '민주당', 'GOP': '공화당', 'IND': '무소속'}


def held_scenarios(as_of, checked_at, error_type):
    """Clear published counts when a roster/policy cannot be validated."""
    chambers = {office: {'lead_abbr': '없음',
                         'margin_note_ko': '의석 명부/집계 검증 실패로 조건부 집계를 보류합니다.'}
                for office in ('house', 'senate', 'governor')}
    return {'schema': 'usa_midterms_forecast_v1', 'status': 'hold',
            'as_of': as_of, 'generated_at': checked_at, 'default_window_days': 7,
            'refresh_seconds': 3600, 'error_type': error_type, 'chambers': chambers,
            'method_ko': '의석 명부/정책 검증 실패로 집계 보류. 여론조사 수집 상태와 별도.',
            'source_ko': '집계 자료 검증 실패',
            'sources': ['https://votehub.com/polls/api/'],
            'windows': {str(days): {'chambers': chambers} for days in (7, 14)}}


def build_scenarios(board, election_board, policy, as_of, checked_at, health=None):
    require(policy['schema'] == 'usa_seat_scenario_policy_v1', 'scenario schema')
    require(board['cycle'] == policy['cycle'], 'scenario cycle mismatch')
    day = date.fromisoformat(as_of)
    require(day.year == policy['cycle'], 'cycle policy must be reviewed for a new year')
    country = next(c for c in election_board['countries'] if c.get('iso3') == 'USA')
    congress = country['ui_ready']['congress']
    states = country['ui_ready']['state_drilldown']['states']
    senate = congress['senate_members']
    require(len(senate) == 100 and len({s['bioguideId'] for s in senate}) == 100,
            'incomplete or duplicated Senate roster')
    require(len(states) == 50 and len({s['id'] for s in states}) == 50, 'state roster')
    state_ids = {s['id'] for s in states}
    state_names = {s['state']: s['id'] for s in states}
    gov_up = set(policy['governor']['election_states'])
    require(len(gov_up) == 36 and gov_up <= state_ids, 'governor election schedule')
    retained_senators = []
    senate_up = set()
    for s in senate:
        state = s.get('state_abbr') or state_names.get(s['state'])
        require(state in state_ids and s.get('senate_class') in (1, 2, 3), 'Senate class/state')
        if s['senate_class'] != 2 and s['senate_class'] != policy['senate']['special_election_classes'].get(state):
            require(s['abbr'] in PARTY, 'unknown retained Senate party')
            retained_senators.append(s)
        else:
            senate_up.add(state)
    require(len(retained_senators) == 65 and len(senate_up) == 35,
            'Senate schedule/roster mismatch')
    senate_keep = Counter(PARTY[s['abbr']] for s in retained_senators)
    gov_keep = Counter()
    for s in states:
        if s['id'] not in gov_up:
            require(s['governor']['abbr'] in PARTY, 'unknown retained governor party')
            gov_keep[PARTY[s['governor']['abbr']]] += 1
    require(sum(gov_keep.values()) == 14, 'retained governors')
    parsed_at = datetime.fromisoformat(board['fetched_at'].replace('Z', '+00:00'))
    now = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
    require(parsed_at.tzinfo is not None and now.tzinfo is not None, 'poll timestamp timezone')
    poll_ok = (board.get('source_status') == 'ok' and board['as_of'] == as_of
               and 0 <= (now - parsed_at).total_seconds() <= 48 * 3600
               and (health is None or health.get('status') == 'ok'))
    require(policy['house']['total'] == 435 and policy['senate']['total'] == 100
            and policy['governor']['total'] == 50, 'national seat totals')
    sources = [policy[o]['source_url'] for o in ('house', 'senate', 'governor')]
    sources.append(policy['governor']['schedule_source_url'])
    sources.append('https://votehub.com/polls/api/')
    windows = {}
    for days in (7, 14):
        chambers = {}
        for office in ('house', 'senate', 'governor'):
            p = policy[office]
            after_election = as_of > policy['election_date']
            rating_ok = (not after_election
                         and 0 <= (day - date.fromisoformat(p['as_of'])).days <= policy['rating_max_age_days'])
            retained = Counter(senate_keep if office == 'senate' else gov_keep if office == 'governor' else {})
            rated = Counter()
            candidates = []
            if office == 'house':
                tiers = p['competitive_ratings']
                require(set(tiers) == {'toss_up', 'lean_dem', 'lean_rep'}, 'house rating tiers')
                codes = [code for values in tiers.values() for code in values]
                require(len(codes) == len(set(codes)), 'duplicated competitive house race')
                require(sum(p['baseline_by_party'].values()) + len(codes) == 435, 'House partition')
                if rating_ok:
                    rated.update(p['baseline_by_party'])
                candidates = [(f'USA:{code[:2]}:house:{code[3:]}', tier)
                              for tier, values in tiers.items() for code in values]
                # Aggregate baseline has no per-seat identity: stop treating it as
                # results after election day; it cannot absorb an unexpected flip.
                baseline_unknown = 0 if rating_ok else sum(p['baseline_by_party'].values())
            else:
                ratings = p['ratings']
                if office == 'senate':
                    codes = [code for values in ratings.values() for code in values]
                    require(len(codes) == 35 and len(set(codes)) == 35, 'Senate rating partition')
                    require(set(codes) == senate_up, 'Senate rating/schedule mismatch')
                    candidates = [(f'USA:{code}:senate', tier) for tier, values in ratings.items() for code in values]
                else:
                    codes = [code for values in ratings.values() for code in values]
                    require(len(codes) == 36 and len(set(codes)) == 36 and set(codes) == gov_up,
                            'governor rating/schedule mismatch')
                    candidates = [(f'USA:{state}:governor', tier)
                                  for tier, values in ratings.items() for state in values]
                baseline_unknown = 0
            confirmed, poll_leads, single_leads = Counter(), Counter(), Counter()
            pending = baseline_unknown
            details = []
            for rid, tier in candidates:
                item = board['races'].get(rid, {})
                result = item.get('result') or {}
                result_party = PARTY.get(result.get('party'))
                certified = (result.get('status') == 'certified' and result.get('race_id') == rid
                             and result.get('contest_id') == item.get('contest_id')
                             and policy['election_date'] <= result.get('certified_on', '') <= as_of)
                observed = item.get('windows', {}).get(str(days), {})
                poll_party = PARTY.get(observed.get('party'))
                party, basis = None, 'pending'
                if certified and result_party:
                    party, basis = result_party, 'certified_result'
                    confirmed[party] += 1
                elif (tier in COMPETITIVE and not after_election and poll_ok
                      and observed.get('status') in ('poll_lead', 'single_poll_lead') and poll_party):
                    party = poll_party
                    if observed['status'] == 'single_poll_lead':
                        basis = 'single_poll_lead'
                        single_leads[party] += 1
                    else:
                        basis = 'recent_poll_lead'
                        poll_leads[party] += 1
                elif rating_ok and tier in ('solid_dem', 'likely_dem', 'solid_rep', 'likely_rep'):
                    party, basis = ('DEM' if tier.endswith('dem') else 'GOP'), 'rated_baseline_assumption'
                    rated[party] += 1
                else:
                    pending += 1
                label = (f'{PARTY_KO[party]} 단일 조사에서 수치상 앞섬 · 참고' if basis == 'single_poll_lead' else
                         f'{PARTY_KO[party]} 조사상 우세' if basis == 'recent_poll_lead' else
                         f'{PARTY_KO[party]} 당선 확정' if basis == 'certified_result' else
                         f'{PARTY_KO[party]} 기초 유지 가정' if basis == 'rated_baseline_assumption' else
                         '판정 보류')
                details.append({'race_id': rid, 'rating': tier, 'competitive': tier in COMPETITIVE,
                                'basis': basis, 'party_abbr': party or '없음', 'conclusion_ko': label,
                                'poll_status': observed.get('status', 'no_recent_poll') if poll_ok else 'source_unavailable',
                                'evidence_quality': observed.get('evidence_quality') if poll_ok and basis in ('recent_poll_lead', 'single_poll_lead', 'pending') and not after_election else None,
                                'poll_details': observed.get('poll_details', []) if poll_ok and not after_election and tier in COMPETITIVE else [],
                                'included_poll_ids': observed.get('included_ids', []) if basis in ('recent_poll_lead', 'single_poll_lead') else []})
            assigned = retained + rated + confirmed + poll_leads + single_leads
            require(sum(assigned.values()) + pending == p['total'], 'seat conservation')
            lead = '없음'
            # Poll leads and qualitative ratings cannot claim chamber control.
            # Only retained seats + certified results can establish this label.
            factual = retained + confirmed
            for party, amount in factual.items():
                if amount > p['total'] / 2:
                    lead = party
            counts = {party: assigned[party] for party in ('DEM', 'GOP', 'IND')}
            chambers[office] = {
                'lead_abbr': lead,
                'margin_note_ko': f'조건부 집계 민주 {counts["DEM"]} · 공화 {counts["GOP"]} · 무소속 {counts["IND"]} · 미정 {pending}. 단일 기관 참고 {sum(single_leads.values())}곳 포함. 평가상 우세 유지 가정이며 확정·당선 예측 아님.',
                'total_seats': p['total'], 'scenario_counts': counts, 'unresolved_seats': pending,
                'buckets': {'retained': dict(retained), 'rated_baseline_assumption': dict(rated),
                            'recent_poll_lead': dict(poll_leads), 'single_poll_lead': dict(single_leads),
                            'certified_result': dict(confirmed)},
                'single_poll_lead_counts': {party: single_leads[party] for party in ('DEM', 'GOP', 'IND')},
                'scenario_counts_without_single_polls': {party: counts[party] - single_leads[party] for party in ('DEM', 'GOP', 'IND')},
                'unresolved_without_single_polls': pending + sum(single_leads.values()),
                'conditional_bounds': {party: {'min': counts[party], 'max': counts[party] + pending}
                                       for party in ('DEM', 'GOP', 'IND')},
                'ratings_as_of': p.get('as_of', '미확보'), 'ratings_usable': rating_ok,
                'polls_usable': poll_ok, 'races': details,
            }
        windows[str(days)] = {'chambers': chambers,
                             'competitive_conclusions': [r for c in chambers.values()
                                                         for r in c['races'] if r['competitive']]}
    return {'schema': 'usa_midterms_forecast_v1', 'cycle': policy['cycle'], 'as_of': as_of,
            'generated_at': checked_at, 'default_window_days': 7, 'refresh_seconds': 3600,
            'method_ko': '비선거 현직 + Solid/Likely 유지 가정. Toss-up/Lean은 최근 7일 조사만으로 판단, 14일 별도. 단일 기관은 참고 집계로 분리. 조사 없음·동률은 보류.',
            'source_ko': 'Cook 하원·상원·주지사 공개 등급 검토본 · 기존 명부 · NGA 일정 · VoteHub 선정 기관',
            'sources': sources, 'chambers': windows['7']['chambers'], 'windows': windows,
            'limitations_ko': [policy['note_ko'], 'seats·win_prob는 발행하지 않음. 조건부 범위는 통계적 신뢰구간이 아님.',
                               '단일 기관 수치상 앞섬은 참고값. 이를 제외한 집계와 미정 수를 별도 제공. 기관 수·일치도를 상/중/하 품질 등급으로 변환하지 않음.',
                               '평가 등급은 검토본이며 자동 갱신되지 않음. 21일 경과 시 집계에서 제외.',
                               policy['governor']['note_ko'], '비선거 현직은 기존 의석 명부 기준이며 임기 중 교체와 공석은 명부 갱신 필요.'],
            'roster_generated_at': election_board['generated_at']}
