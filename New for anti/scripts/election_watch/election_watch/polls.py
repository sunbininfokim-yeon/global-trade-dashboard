"""Evidence-bounded election polling read model. Standard library only.

Inputs are reviewed transcriptions, never predictions or scraped headlines.
One observation is a question/population, not an independent survey.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        f.write(raw)
        temp = Path(f.name)
    temp.replace(path)


def https_url(value):
    p = urlparse(value)
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password


def validate(data, as_of):
    """Fail before publishing anything if a reviewed record loses its evidence."""
    day = date.fromisoformat(as_of)
    require(data['schema'] == 'usa_poll_inputs_v1', 'input schema')
    require(type(data['cycle']) is int and data['cycle'] % 2 == 0, 'even election cycle')
    states = data['states']
    require(len(states) == len(set(states)), 'duplicate states')
    require(all(re.fullmatch('[A-Z]{2}', s) for s in states), 'state format')
    targets = {t['race_id']: t for t in data['targets']}
    require(len(targets) == len(data['targets']), 'duplicate targets')
    for rid, t in targets.items():
        require(t['state'] in states and t['office'] in ('house', 'senate', 'governor'), 'target scope')
        suffix = ':' + t['district'] if t['office'] == 'house' else ''
        require(rid == f"USA:{t['state']}:{t['office']}" + suffix, 'race_id')
        require(bool(t['selection_reason_ko']), 'selection reason')
        if t['office'] == 'house':
            require(bool(re.fullmatch(r'\d{2}', t['district'])), 'district format')
        else:
            require(t['district'] is None, 'statewide district must be null')
    sources = data['sources']
    for sid, s in sources.items():
        require(s['institution'] and s['selection_reason_ko'], 'source provenance')
        require(s['review_status'] in ('reviewed', 'pending'), 'source review status')
        for url in s['urls']:
            require(https_url(url), 'public HTTPS source URL')
    ids, fingerprints = set(), set()
    waves = {}
    for p in data['observations']:
        require(p['id'] not in ids, 'duplicate observation id')
        ids.add(p['id'])
        require(p['race_id'] in targets, 'untracked race')
        require(p['source_id'] in sources, 'unknown source')
        require(sources[p['source_id']]['review_status'] == 'reviewed', 'unreviewed source')
        require(p['review']['status'] == 'verified_primary_source', 'unreviewed observation')
        require(date.fromisoformat(p['field_start']) <= date.fromisoformat(p['field_end'])
                <= date.fromisoformat(p['published_on']) <= day, 'poll date ordering/future data')
        require(date.fromisoformat(p['published_on']) <= date.fromisoformat(p['review']['reviewed_on']) <= day,
                'review date ordering')
        require(data['cycle'] - 1 <= int(p['field_start'][:4]) <= int(p['field_end'][:4]) <= data['cycle'], 'poll cycle mismatch')
        require(p['phase'] in ('primary', 'general', 'runoff'), 'phase')
        require(p['matchup_status'] in ('hypothetical_nominees', 'reported_general_matchup', 'primary_field'), 'matchup')
        require((p['phase'] == 'primary') == (p['primary_party'] in ('DEM', 'REP')), 'primary party')
        require(p['population'] in ('likely_voters', 'registered_voters', 'likely_primary_voters'), 'population')
        for key in ('sample_n', 'question_n'):
            require(type(p[key]) is int and p[key] > 0, 'sample size')
        require(p['question_n'] <= p['sample_n'], 'question n exceeds survey n')
        require(p['question_summary_ko'] and p['question_locator'] and p['question_wording_verified'], 'question evidence')
        for key in ('method_summary_ko', 'sponsor', 'weighting_summary_ko'):
            require(bool(p[key]), key)
        for key in ('results_url', 'methodology_url'):
            require(p[key] in sources[p['source_id']]['urls'], 'unregistered evidence URL')
        u = p['uncertainty']
        require(u['type'] in ('margin_of_error', 'credibility_interval'), 'uncertainty type')
        require(u['scope'] in ('survey', 'population', 'question'), 'uncertainty scope')
        require(type(u['value_pp']) in (int, float) and math.isfinite(u['value_pp']) and 0 < u['value_pp'] < 100, 'uncertainty value')
        require(len(p['answers']) >= 2, 'answers')
        labels = set()
        total = 0
        for a in p['answers']:
            require(a['label'] and a['label'] not in labels, 'duplicate answer')
            labels.add(a['label'])
            require(a['kind'] in ('candidate', 'undecided', 'unknown_refused', 'other', 'would_not_vote'), 'answer type')
            require(type(a['pct']) in (int, float) and math.isfinite(a['pct']) and 0 <= a['pct'] <= 100, 'percentage')
            total += a['pct']
            # Names alone must never be treated as a verified FEC/campaign identity.
            require(a['candidate_id'] is None, 'v1 does not implement verified candidate identity mapping')
        require(p['precision_decimals'] in (0, 1, 2), 'reported precision')
        require(abs(total - 100) <= len(p['answers']) * 0.5 * 10 ** (-p['precision_decimals']) + 0.01, 'incomplete answer table')
        fingerprint = (p['survey_id'], p['race_id'], p['question_locator'], p['population'])
        require(fingerprint not in fingerprints, 'duplicate question/population')
        fingerprints.add(fingerprint)
        wave = (p['source_id'], p['field_start'], p['field_end'], p['sample_n'])
        require(p['survey_id'] not in waves or waves[p['survey_id']] == wave, 'inconsistent survey metadata')
        waves[p['survey_id']] = wave
    return targets


def build(data, public, as_of, monitor=None):
    targets = validate(data, as_of)
    day = date.fromisoformat(as_of)
    cycle = data['cycle']
    public = Path(public)
    assets = {}
    def asset(prefix, payload):
        path = f'usa_election_polls/{cycle}/{prefix}-{digest(payload)[:16]}.json'
        assets[path] = payload
        return path
    monitor = monitor or {'checked_at': None, 'sources': {}}
    if 'input_fingerprint' in monitor:
        require(monitor['input_fingerprint'] == digest(data), 'monitor input has changed; run monitor again')
    require(isinstance(monitor.get('sources'), dict), 'monitor sources')
    for sid, check in monitor['sources'].items():
        require(sid in data['sources'], 'monitor from different source registry')
        require(check['status'] in ('unchanged', 'changed', 'error', 'not_checked', 'unreviewed_baseline'), 'monitor status')
    race_refs = {}
    for rid, target in sorted(targets.items()):
        rows = []
        for original in data['observations']:
            if original['race_id'] != rid:
                continue
            p = deepcopy(original)
            age = (day - date.fromisoformat(p['field_end'])).days
            p['age_days'] = age
            p['freshness'] = 'stale' if age > data['stale_after_days'] else 'recent'
            p['answer_total_pct'] = round(sum(a['pct'] for a in p['answers']), 2)
            p['candidate_identity_status'] = 'reported_names_only'
            p['source_check'] = monitor['sources'].get(p['source_id'], {'status': 'not_checked'})
            p['display_group'] = ('hypothetical' if p['matchup_status'] == 'hypothetical_nominees'
                                  else 'primary' if p['phase'] == 'primary' else 'general')
            # Never silently promote old, hypothetical or changed-source results to a headline.
            p['headline_eligible'] = (p['freshness'] == 'recent' and p['display_group'] == 'general'
                                      and p['population'] == 'likely_voters'
                                      and p['source_check']['status'] not in ('changed', 'error', 'unreviewed_baseline'))
            rows.append(p)
        rows.sort(key=lambda p: (p['field_end'], p['published_on'], p['id']), reverse=True)
        status = ('no_verified_poll' if not rows else 'observed_partial')
        payload = {'schema': 'usa_election_poll_race_v1', 'cycle': cycle, 'as_of': as_of,
                   **target, 'status': status, 'election_schedule_status': 'not_verified_by_this_dataset',
                   'observations': rows, 'independent_survey_count': len({p['survey_id'] for p in rows}),
                   'headline_observation_ids': [p['id'] for p in rows if p['headline_eligible']],
                   'poll_average_pct': None, 'win_probability': None}
        path = asset('races/' + rid.replace(':', '-'), payload)
        race_refs[rid] = {'path': path, 'status': status, 'observation_count': len(rows)}
    states = {}
    for state in data['states']:
        refs = {rid: ref for rid, ref in race_refs.items() if targets[rid]['state'] == state}
        states[state] = {'path': asset('states/' + state, {'schema': 'usa_election_poll_state_v1',
                        'state': state, 'cycle': cycle, 'as_of': as_of, 'races': refs})}
    national = {'schema': 'usa_election_poll_national_v1', 'cycle': cycle, 'as_of': as_of,
                'states': states, 'race_count': len(race_refs),
                'observation_count': len(data['observations']),
                'independent_survey_count': len({p['survey_id'] for p in data['observations']}),
                'covered_race_count': sum(r['observation_count'] > 0 for r in race_refs.values()),
                'sources': data['sources'], 'review_queue': data['review_queue'],
                'monitor': monitor}
    existing_path = public / 'usa_election_polls_index_v1.json'
    existing_cycles = read(existing_path)['cycles'] if existing_path.exists() else {}
    index = {'schema': 'usa_election_polls_index_v1', 'as_of': as_of, 'as_of_timezone': 'UTC',
             'pipeline_role': 'ui_read_model', 'measure': 'reported_vote_intention', 'unit': 'percent',
             'finance_index': 'usa_election_finance_index_v1.json',
             'live_board_file': 'usa_election_live_polls_v1.json',
             'archive_role_ko': 'cycles는 원문 대조 전사 기록, 실시간 지도는 live_board_file을 사용합니다.',
             'cycles': {**existing_cycles, str(cycle): {'path': asset('national', national)}},
             'stale_after_days': data['stale_after_days'],
             'limitations_ko': [
                 '선정된 주·지역구의 검증 완료 자료만 포함합니다. 전국 조사 전체 목록이 아닙니다.',
                 '자료 없음은 지지율 0이나 해당 선거가 없다는 뜻이 아닙니다.',
                 '지역구별 기업 입지·경합도와 선거 일정·최종 후보 명부는 이 자료에서 검증하지 않았습니다.',
                 '경선·가상 대결·조사 대상이 다른 결과는 합산하거나 평균 내지 않습니다.',
                 '신규 원문 감시는 자동화할 수 있으나 결과 편입은 원문 검토 후 수행합니다.',
                 '최근 기준은 조사 종료 후 45일이라는 운영 규칙이며 정확도 등급이 아닙니다.']}
    # Entire input validated first; immutable dependencies written before the entry point.
    for path, payload in assets.items():
        if (public / path).exists():
            require(read(public / path) == payload, 'immutable asset collision')
        else:
            atomic(public / path, payload)
    atomic(public / 'usa_election_polls_index_v1.json', index)
    return national
