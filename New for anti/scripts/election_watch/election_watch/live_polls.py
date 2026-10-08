"""Daily public poll transport + conservative, auditable election map signals.

VoteHub is a licensed aggregator, not an election authority. Records are labelled
as automatically imported; they are never labelled primary-source transcriptions.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
import math
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from .polls import atomic, digest, require
from .poll_quality import source_quality, evidence_context, corrected_provider_answers, corrected_provider_source, answer_correction_fingerprint

OFFICES = {'governor': 'governor', 'us-senator': 'senate', 'us-representative': 'house'}
API = 'https://api.votehub.com/polls'


def apply_watchlist(policy, watchlist):
    """Add verified competitive race IDs as discovery slots, never as polls."""
    require(watchlist.get('schema') == 'usa_poll_watchlist_v1'
            and watchlist.get('cycle') == policy['cycle'], 'watchlist schema or cycle')
    selected = deepcopy(policy)
    seen = set()
    for office in ('house', 'senate', 'governor'):
        source = watchlist['sources'][office]
        date.fromisoformat(source['as_of'])
        require(urlparse(source['url']).hostname == 'www.cookpolitical.com', 'watchlist source')
        for tier, entries in watchlist['ratings'][office].items():
            require(tier in ('toss_up', 'lean_dem', 'lean_rep'), 'watchlist tier')
            for code in entries:
                if office == 'house':
                    match = re.fullmatch(r'([A-Z]{2})-(\d{2})', code)
                    require(match is not None, 'invalid house watch ID')
                    state, district = match.groups()
                    rid = f'USA:{state}:house:{district}'
                    subject = f'{policy["cycle"]} {state}-{district}'
                    poll_type = 'us-representative'
                else:
                    require(re.fullmatch(r'[A-Z]{2}', code) is not None, 'invalid state watch ID')
                    state, district = code, None
                    rid = f'USA:{state}:{office}'
                    require(state in watchlist['state_names'], 'missing state name')
                    subject = f'{policy["cycle"]} {watchlist["state_names"][state]}'
                    poll_type = 'us-senator' if office == 'senate' else 'governor'
                require(state in watchlist['state_names'] and rid not in seen, 'duplicate or unknown watch ID')
                seen.add(rid)
                if rid not in selected['races']:
                    selected['races'][rid] = {
                        'state': state, 'office': office, 'district': district,
                        'subject': subject, 'poll_type': poll_type, 'seat_name': None,
                        'contest_id': f'{rid}:{policy["cycle"]}:general',
                        'general_from': f'{policy["cycle"]}-09-01',
                        'election_date': f'{policy["cycle"]}-11-03',
                        'schedule_status': 'watch_slot_unverified',
                        'required_candidates': [], 'candidates': {},
                        'selection_reason_ko': '접전 선거 조사 발견 우선순위. 대진 미검증 시 자동 수치 편입 보류.'}
                race = selected['races'][rid]
                require((race['state'], race['office'], race['district']) == (state, office, district),
                        'watchlist race mismatch')
                race['monitor_priority'] = {'tier': tier, 'basis': 'Cook Political Report',
                                            'as_of': source['as_of'], 'url': source['url'],
                                            'use': 'discovery_only'}
    selected['states'] = sorted(set(selected['states']) | {r['state'] for r in selected['races'].values()})
    subjects = [(r['subject'], r['poll_type']) for r in selected['races'].values()]
    require(len(subjects) == len(set(subjects)), 'ambiguous poll subject')
    selected['watchlist'] = {'reviewed_on': watchlist['reviewed_on'],
                             'priority_race_count': len(seen), 'sources': watchlist['sources'],
                             'meaning_ko': watchlist['basis_ko']}
    return selected


def fetch_polls(cycle, as_of):
    # Re-fetch the whole cycle to pick up corrections and withdrawals, not an
    # append-only date cursor that would silently keep retracted observations.
    url = API + '?' + urlencode({'subject': str(cycle), 'from_date': f'{cycle-1}-01-01', 'to_date': as_of})
    with urlopen(Request(url, headers={'User-Agent': 'ElectionPollPipeline/2.0'}), timeout=45) as response:
        require(response.url.startswith('https://api.votehub.com/'), 'unexpected API redirect')
        raw = response.read(24 * 1024 * 1024 + 1)
        require(len(raw) <= 24 * 1024 * 1024, 'oversized response')
    import json
    data = json.loads(raw)
    if isinstance(data, dict):
        require(not data.get('next') and not data.get('next_page'), 'pagination needs adapter update')
        data = data.get('polls')
    require(isinstance(data, list) and len(data) > 0, 'empty or changed API schema')
    return data, url


def reviewed_source(raw, policy, as_of):
    """A reviewed release can qualify without an institution-wide registration.

    Never trust an arbitrary link, or allow a shared document host wholesale.
    The release's URL, pollster and later normalized fingerprint must all match.
    """
    review = policy.get('quality_reviews', {}).get(raw['id'], {})
    admission = review.get('admission')
    if admission:
        require(len(review.get('primary_toplines', {})) >= 2 and review.get('sources')
                and review.get('disclosure_review'), 'incomplete_source_review')
        require(date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(as_of),
                'future_quality_review')
        require(admission['pollster'] == raw['pollster']
                and admission['provider_url'] == raw.get('url'), 'source_review_changed')
        for value in [admission['provider_url'], admission['methodology_url'], *review['sources']]:
            url = urlparse(value)
            require(url.scheme == 'https' and url.hostname and not url.username and not url.password,
                    'invalid_reviewed_source_url')
        require(admission['source_role'] in ('pollster_primary', 'commissioner_primary'),
                'unverified_source_role')
        require(type(admission['signal_eligible']) is bool and admission['group'],
                'invalid_source_admission')
        require(admission['signal_eligible'] or admission.get('signal_exclusion_reasons'),
                'missing_reference_reason')
        return {'group': admission['group'], 'methodology_url': admission['methodology_url']}, admission
    source = policy['pollsters'].get(raw.get('pollster'))
    require(source is not None, 'pollster_not_selected')
    url = urlparse(raw.get('url') if isinstance(raw.get('url'), str) else '')
    require(url.scheme == 'https' and not url.username and not url.password
            and url.hostname in source['hosts'], 'unregistered_primary_host')
    if source.get('approved_sponsor_sets'):
        require(sorted(raw.get('sponsors') or []) in
                [sorted(s) for s in source['approved_sponsor_sets']], 'commissioner_not_reviewed')
    return source, None


def normalize(rows, policy, as_of):
    day = date.fromisoformat(as_of)
    races = policy['races']
    by_subject = {(r['subject'], r['poll_type']): rid for rid, r in races.items()}
    accepted, rejected = [], []
    seen_ids = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError('invalid API row')
        rid = by_subject.get((raw.get('subject'), raw.get('poll_type')))
        if not rid:
            continue
        p = deepcopy(raw)
        require(all(k in p for k in ('id','pollster','start_date','end_date','created_at','answers','population','sample_size')), 'provider schema changed')
        try:
            require(isinstance(p.get('id'), str) and p['id'], 'missing_id')
            require(p['id'] not in seen_ids, 'duplicate_id')
            seen_ids.add(p['id'])
            require(p['id'] not in policy.get('excluded_records', {}), policy.get('excluded_records', {}).get(p['id'], 'excluded_record'))
            reviewed_raw = policy.get('quality_reviews', {}).get(p['id'], {}).get('provider_record_sha256')
            require(not reviewed_raw or reviewed_raw==answer_correction_fingerprint(p), 'primary_review_provider_metadata_changed')
            p, answer_correction = corrected_provider_answers(p, policy.get('quality_reviews', {}).get(p['id'], {}), as_of)
            p, source_correction = corrected_provider_source(p, policy.get('quality_reviews', {}).get(p['id'], {}), as_of)
            source, admission = reviewed_source(p, policy, as_of)
            partisan_reference = (admission and admission.get('allow_partisan_reference') is True
                                  and admission['signal_eligible'] is False
                                  and p.get('internal') is False
                                  and p.get('partisan') == admission.get('reviewed_partisan')
                                  and p.get('sponsors') == admission.get('reviewed_sponsors'))
            require(p.get('internal') is False and (p.get('partisan') is None or partisan_reference),
                    'internal_or_partisan')
            start, end, published = (date.fromisoformat(p[k]) for k in ('start_date', 'end_date', 'created_at'))
            require(start <= end <= published <= day, 'date_order_or_future')
            race = races[rid]
            require(len(race['required_candidates']) >= 2, 'matchup_not_reviewed')
            in_general_period = date.fromisoformat(race['general_from']) <= start
            historical_reference = (admission and admission.get('allow_historical_reference') is True
                                    and not admission['signal_eligible'])
            require((in_general_period or historical_reference)
                    and end < date.fromisoformat(race['election_date']), 'outside_reviewed_general_period')
            require(p.get('population') in ('lv', 'rv'), 'unsupported_population')
            require(type(p.get('sample_size')) is int and p['sample_size'] > 0, 'missing_sample_size')
            require(p.get('seat_name') in (None, race.get('seat_name')), 'ambiguous_seat')
            answers = p.get('answers')
            require(isinstance(answers, list) and len(answers) >= 2, 'missing_answers')
            names = [a.get('choice') for a in answers]
            require(all(isinstance(n, str) and n for n in names) and len(names) == len(set(names)), 'duplicate_answer')
            for a in answers:
                require(type(a.get('pct')) in (int, float) and math.isfinite(a['pct'])
                        and 0 <= a['pct'] <= 100, 'invalid_percentage')
            require(sum(a['pct'] for a in answers) <= 102, 'invalid_total')
            # Exact reviewed matchup, not name fuzzing against a list of FEC
            # registrants (which contains withdrawn/primary candidates too).
            def canonical(name):
                return race['candidates'].get(name, {}).get('canonical_name', name)
            require(len({canonical(n) for n in names}) == len(names), 'duplicate_candidate_alias')
            require({canonical(n) for n in race['required_candidates']}
                    <= {canonical(n) for n in names}, 'unreviewed_matchup')
            normalized = []
            for a in answers:
                identity = race['candidates'].get(a['choice'])
                normalized.append({'name': a['choice'], 'pct': a['pct'],
                                   'party': identity['party'] if identity else None})
            require(not any(a['name'].casefold() in ('dem', 'rep', 'democrat', 'republican') for a in normalized), 'generic_ballot')
            observation = {'id': p['id'], 'race_id': rid, 'contest_id': race['contest_id'],
                             'pollster': p['pollster'], 'pollster_group': source['group'],
                             'field_start': p['start_date'], 'field_end': p['end_date'],
                             'provider_record_date': p['created_at'], 'population': p['population'],
                             'sample_n': p['sample_size'], 'answers': normalized,
                             'sponsors': p.get('sponsors') or [], 'source_url': p['url'],
                             'verification': ('reviewed_release_aggregator_import' if admission
                                              else 'selected_source_aggregator_import'),
                             'methodology_url': source['methodology_url'],
                             'margin_of_error_pp': None,
                             'limitations_ko': 'VoteHub 자동 수집값. 원문 수기 검토의 범위는 source_quality에 별도 표기. 원문별 오차범위·문항별 표본은 API 미제공.'}
            primary = p.get('primary_source_capture')
            if primary:
                review = policy.get('quality_reviews', {}).get(p['id'], {})
                require(admission and admission['source_role']=='pollster_primary'
                        and review.get('primary_supplement_record_sha256')==answer_correction_fingerprint(p)
                        and primary.get('original_reviewed_on')==review['reviewed_on']
                        and primary.get('status') in ('primary_documents_rechecked','carried_forward_reference_only'),
                        'unreviewed_primary_supplement')
                expected_documents={d['url']:d['sha256'] for d in review.get('primary_documents', [])}
                checked_documents=primary.get('documents', [])
                require(expected_documents and len(checked_documents)==len(expected_documents)
                        and {d['url'] for d in checked_documents}==set(expected_documents),
                        'primary_document_receipt_mismatch')
                if primary['status']=='primary_documents_rechecked':
                    require(all(d.get('status')=='unchanged' and d.get('sha256')==expected_documents[d['url']]
                                for d in checked_documents), 'primary_document_receipt_mismatch')
                observation['primary_source_capture'] = deepcopy(primary)
                observation['verification'] = 'reviewed_primary_source_snapshot'
                observation['limitations_ko'] = 'API 미편입 원문 보완 기록. 원문 PDF 지문을 재확인하며 장애/변경 시 원래 검토일의 참고 전용 자료를 보존합니다. 새 발표 전체 발견을 보장하지 않습니다.'
            if answer_correction:
                observation['provider_answer_correction'] = answer_correction
            if source_correction:
                observation['provider_source_correction'] = source_correction
            observation['commissioning'] = {'internal': p.get('internal'), 'partisan': p.get('partisan'),
                                             'sponsors': p.get('sponsors') or []}
            observation['source_admission'] = 'reviewed_release' if admission else 'registered_pollster'
            reasons = list(admission.get('signal_exclusion_reasons', [])) if admission else []
            if primary and primary['status']=='carried_forward_reference_only':
                reasons.append('primary_source_unavailable_or_changed')
            if partisan_reference:
                reasons.append('party_commissioned_reference')
            if not in_general_period:
                reasons.append('outside_reviewed_general_period')
            observation['aggregation_eligibility'] = {
                'eligible': not reasons, 'reasons': sorted(set(reasons))}
            observation['display_group'] = 'general' if in_general_period else 'historical_matchup_reference'
            observation['source_quality'] = source_quality(observation, policy.get('quality_reviews', {}), as_of)
            accepted.append(observation)
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({'id': raw.get('id'), 'race_id': rid, 'pollster': raw.get('pollster'),
                             'reason': str(exc) if isinstance(exc, ValueError) else 'malformed_record',
                             'source_url': raw.get('url'), 'field_start': raw.get('start_date'),
                             'field_end': raw.get('end_date'), 'population': raw.get('population'),
                             'sample_n': raw.get('sample_size'), 'sponsors': raw.get('sponsors') or [],
                             'internal': raw.get('internal'), 'partisan': raw.get('partisan'),
                             'verification': 'not_accepted_not_verified'})
    return accepted, rejected


def poll_detail(poll):
    values = sorted((a['pct'] for a in poll['answers']), reverse=True)
    return {'id': poll['id'], 'source_quality': poll['source_quality'],
            'leading_margin_pp': round(values[0] - values[1], 3),
            'significance': 'not_evaluated'}


def summarize(rows, race, as_of, days):
    end = date.fromisoformat(as_of)
    start = end - timedelta(days=days - 1)
    eligible = [p for p in rows if start <= date.fromisoformat(p['field_end']) <= end]
    references = [p for p in eligible if not p.get('aggregation_eligibility', {}).get('eligible', True)]
    eligible = [p for p in eligible if p.get('aggregation_eligibility', {}).get('eligible', True)]
    # LV and RV never vote in the same count. Prefer LV, with an explicitly
    # labelled RV fallback only if no LV observation exists in this window.
    population = 'lv' if any(p['population'] == 'lv' for p in eligible) else 'rv'
    eligible = [p for p in eligible if p['population'] == population]
    by_group = defaultdict(list)
    for p in eligible:
        by_group[p['pollster_group']].append(p)
    chosen, conflicting = [], []
    for group, surveys in sorted(by_group.items()):
        latest = max(p['field_end'] for p in surveys)
        wave = [p for p in surveys if p['field_end'] == latest]
        # Same release linked twice counts once; inconsistent variants of the
        # latest wave do not get resolved by arbitrary API ordering.
        variants = {digest(sorted(p['answers'], key=lambda a: a['name'])) for p in wave}
        if len(variants) > 1:
            conflicting.append(group)
        else:
            chosen.append(sorted(wave, key=lambda p: p['id'])[0])
    counts, parties = Counter(), {}
    ties = 0
    for p in chosen:
        high = max(a['pct'] for a in p['answers'])
        leaders = [a for a in p['answers'] if a['pct'] == high]
        if len(leaders) != 1:
            ties += 1
        else:
            leader = leaders[0]
            # Preserve source spellings in the published signal contract, which
            # the browser also recomputes from the same observations.
            counts[leader['name']] += 1
            parties[leader['name']] = leader['party']
    leading = [name for name, count in counts.items() if count == max(counts.values(), default=0)]
    name = leading[0] if len(leading) == 1 else None
    status, party = 'no_recent_poll', None
    if chosen:
        status = 'tie'
    if chosen and name and counts[name] > len(chosen) / 2:
        status = ('single_poll_lead' if len(chosen) == 1 else 'poll_lead') if parties[name] else 'unknown_leader_party'
        party = parties[name]
    quality = evidence_context(len(chosen), max(counts.values(), default=0) / len(chosen) if chosen else 0,
                               conflicting)
    return {'window_days': days, 'from': start.isoformat(), 'through': as_of,
            'population': population if chosen else None, 'status': status, 'party': party,
            'leader': name if status in ('poll_lead', 'single_poll_lead') else None,
            'evidence_quality': quality,
            'poll_details': [poll_detail(p) for p in chosen],
            'reference_ids': [p['id'] for p in references],
            'reference_poll_count': len(references),
            'reference_details': [{'id': p['id'], 'reasons': p['aggregation_eligibility']['reasons']}
                                  for p in references],
            'status_note_ko': ('기간 내 참고 전용 자료는 있으나 우세 집계 가능한 조사는 없습니다.'
                               if references and not chosen else None),
            'lead_counts': dict(counts), 'tie_count': ties, 'pollster_count': len(chosen),
            'included_ids': [p['id'] for p in chosen], 'conflicting_pollsters': conflicting,
            'latest_field_end': max((p['field_end'] for p in chosen), default=None)}


def validated_results(data, policy, as_of):
    require(data.get('schema') == 'usa_confirmed_results_v1', 'results schema')
    require(data.get('cycle', policy['cycle']) == policy['cycle'], 'results cycle')
    output = {}
    for row in data['results']:
        race = policy['races'].get(row.get('race_id'))
        require(race is not None and row.get('contest_id') == race['contest_id'], 'result contest mismatch')
        require(row['race_id'] not in output, 'duplicate result')
        require(row.get('status') == 'certified', 'only certified results can override')
        require(race['election_date'] <= row['certified_on'] <= as_of, 'result date')
        date.fromisoformat(row['certified_on'])
        require(row['winner'] in race['candidates'], 'unverified winner identity')
        require(row['party'] == race['candidates'][row['winner']]['party'], 'winner party mismatch')
        url = urlparse(row['source_url'])
        require(url.scheme == 'https' and url.hostname in policy['official_result_hosts'][race['state']]
                and not url.username and not url.password, 'unregistered official results source')
        require(row.get('reviewed_on') and row['certified_on'] <= row['reviewed_on'] <= as_of
                and row.get('evidence_note'), 'result evidence required')
        output[row['race_id']] = row
    return output


def poll_history(rows, policy, as_of):
    """Keep accepted source observations separate from the active map signal."""
    accepted, _ = normalize(rows, policy, as_of)
    by_race = defaultdict(list)
    for row in accepted:
        by_race[row['race_id']].append(row)
    return {'schema': 'usa_poll_history_v1', 'cycle': policy['cycle'], 'as_of': as_of,
            'note_ko': '감사·출처 확인용 기록. 선거 종료 후 지도 우세 신호로 사용하지 않습니다.',
            'race_count': len(by_race), 'observation_count': len(accepted),
            'races': {rid: {'contest_id': policy['races'][rid]['contest_id'],
                            'election_date': policy['races'][rid]['election_date'],
                            'observations': sorted(items, key=lambda p: (p['field_end'], p['id']), reverse=True)}
                      for rid, items in sorted(by_race.items())}}


def close_finished_races(board, policy, confirmed, as_of):
    """Clear poll display after election day, including when transport fails."""
    changed = False
    day = date.fromisoformat(as_of)
    for rid, item in board.get('races', {}).items():
        race = policy['races'].get(rid)
        if not race:
            continue
        result = confirmed.get(rid)
        phase = ('certified_result' if result else
                 'awaiting_certified_result' if day > date.fromisoformat(race['election_date']) else
                 'pre_election')
        if item.get('result') != result:
            item['result'] = result
            changed = True
        if item.get('phase') != phase:
            item['phase'] = phase
            changed = True
        if phase != 'pre_election':
            if item.get('observations'):
                item['observations'] = []
                changed = True
            for days in (7, 14):
                window = item.get('windows', {}).get(str(days))
                if window and window.get('status') != 'election_closed':
                    window.update({'status': 'election_closed', 'party': None, 'leader': None,
                                   'lead_counts': {}, 'tie_count': 0, 'pollster_count': 0,
                                   'included_ids': [], 'conflicting_pollsters': [],
                                   'latest_field_end': None, 'population': None,
                                   'evidence_quality': evidence_context(0, 0), 'poll_details': [],
                                   'reference_ids': [], 'reference_details': [],
                                   'reference_poll_count': 0, 'status_note_ko': None})
                    changed = True
    if changed:
        board['lifecycle_checked_as_of'] = as_of
    return changed


def build_live(rows, policy, results, as_of, fetched_at, source_url):
    require(policy['schema'] == 'usa_live_poll_policy_v1', 'policy schema')
    accepted, rejected = normalize(rows, policy, as_of)
    confirmed = validated_results(results, policy, as_of)
    races = {}
    for rid, race in policy['races'].items():
        observations = sorted([p for p in accepted if p['race_id'] == rid], key=lambda p: (p['field_end'], p['id']), reverse=True)
        races[rid] = {**deepcopy(race), 'race_id': rid, 'observations': observations,
                      'windows': {str(days): summarize(observations, race, as_of, days) for days in (7, 14)},
                      'result': confirmed.get(rid)}
    board = {'schema': 'usa_live_polls_v1', 'cycle': policy['cycle'], 'as_of': as_of,
            'fetched_at': fetched_at, 'source_status': 'ok', 'default_window_days': 7,
            'history_file': f'usa_election_poll_history_{policy["cycle"]}.json',
            'refresh_cadence': deepcopy(policy.get('refresh_cadence', {'interval_days': 1})),
            'stale_after_hours': policy.get('refresh_cadence', {}).get('stale_after_hours', 48), 'source': {'name': 'VoteHub', 'url': 'https://votehub.com/polls/api/',
                'request_url': source_url, 'license': 'CC BY 4.0', 'modified': '선정·정규화·기관별 최신 조사 집계'},
            'rules_ko': ['최근 7일 기본·14일 선택. 조사 종료일 기준(UTC), 오늘 포함.',
                '기관별 최신 1회. 단일 기관은 수치상 앞섬 참고값, 복수 기관 과반 우세는 별도 신호.',
                '기관 수·일치도는 사실값으로 표시하며 상/중/하 품질 등급으로 변환하지 않습니다. 원문 검토·방법론 공개 상태는 별도.',
                '기관 미등록이라도 원문·방법·대진·개별 레코드 대조 완료 시 편입. 참고 전용 조사는 누적 목록에 보관하고 우세 집계에서 제외.',
                'LV 우선·없을 때 RV 별도 집계. 내부·정파 조사는 우세 집계 제외. 원문 대조한 정당 의뢰 조사만 참고 목록 편입. 경선·미검증 대진 보류.',
                '색상은 조사상 우세이며 통계적 유의성·당선확률·당선 예측이 아닙니다.',
                '선거 다음 날부터 화면용 조사 목록과 우세 신호를 비웁니다. 검증용 과거 조사 기록은 별도 파일에 보존합니다.',
                '선거일 이후 공식 확정 결과 전에는 회색. 인증된 승자 결과가 여론조사보다 우선합니다.'],
            'coverage': {'selected_states': policy['states'], 'race_count': len(races),
                         'accepted_observations': len(accepted), 'excluded_observations': len(rejected),
                         'aggregation_eligible_observations': sum(p['aggregation_eligibility']['eligible'] for p in accepted),
                         'reference_only_observations': sum(not p['aggregation_eligibility']['eligible'] for p in accepted),
                         'exclusion_reasons': dict(Counter(p['reason'] for p in rejected))},
            'watchlist': policy.get('watchlist'),
            'governor_roster_coverage': deepcopy(policy.get('governor_roster_coverage')),
            'target_catalog': deepcopy(policy.get('target_catalog')),
            'excluded_watch_slots': deepcopy(policy.get('excluded_watch_slots', [])),
            'races': races, 'review_queue': rejected,
            'results_collection': {'status': 'official_source_review_required',
                'note_ko': '주별 인증 결과 자동 수집기는 아직 미연결. 공식 출처를 검토한 결과 파일이 들어오면 자동 우선 표시.'}}
    close_finished_races(board, policy, confirmed, as_of)
    board['coverage']['displayed_observations'] = sum(len(r['observations']) for r in board['races'].values())
    return board
