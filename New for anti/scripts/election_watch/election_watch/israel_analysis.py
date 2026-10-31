"""Publish reviewed Knesset observations without a polling average or live claims."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
import re
from .israel_results import validate_results
from .israel_translation import collect_input_texts, validate_translations

CORE_FILES = ('sources.json', 'election_calendar.json', 'lists.json',
         'poll_observations.jsonl', 'coalition_positions.jsonl', 'review_receipts.json')
FILES = CORE_FILES + ('coalition_context.json', 'ko_translations.json')
STATUSES = {'accepted', 'partial', 'held'}
SEATS = 120


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def read_inputs(root):
    result = {}
    for name in FILES:
        text = (root / name).read_text(encoding='utf-8')
        result[name] = ([json.loads(line) for line in text.splitlines() if line.strip()]
                        if name.endswith('.jsonl') else json.loads(text))
    post = root / 'post_election.json'
    if post.exists():
        result[post.name] = json.loads(post.read_text(encoding='utf-8'))
    recorded = result['review_receipts.json']['input_sha256']
    for name in CORE_FILES[:-1]:
        if recorded.get(name) != hashlib.sha256((root / name).read_bytes()).hexdigest():
            raise ValueError('review receipt does not match input: ' + name)
    return result


def safe_url(url):
    parsed = urlparse(url or '')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('source_url must be an HTTPS source')


def validate_day(value, as_of):
    if value is None:
        return
    if date.fromisoformat(value) > date.fromisoformat(as_of):
        raise ValueError('observation date is after evidence date')


def validate_observations(rows, known, as_of):
    identities = set()
    for row in rows:
        if row.get('record_type') != 'observation':
            continue
        # Some draft subquestion rows omit the cycle; they inherit the explicitly
        # checked Knesset-26 input container, never a cycle from a numeric value.
        if row.get('cycle', 'knesset-26') != 'knesset-26' or row.get('review_status') not in STATUSES:
            raise ValueError('wrong election cycle or missing review status')
        key = (row.get('poll_id'), row.get('question_id'), row.get('scenario'))
        if not all(key) or key in identities:
            raise ValueError('duplicate or incomplete observation identity')
        identities.add(key)
        safe_url(row.get('source_url'))
        for field in ('field_start', 'field_end'):
            validate_day(row.get(field), as_of)
        if row.get('field_start') and row.get('field_end') and row['field_start'] > row['field_end']:
            raise ValueError('reversed fieldwork dates')
        for field in ('published_at', 'revised_at', 'collected_at'):
            if row.get(field):
                value = datetime.fromisoformat(row[field].replace('Z', '+00:00'))
                if value.tzinfo is None:
                    raise ValueError('timestamp needs timezone')
                validate_day(value.date().isoformat(), as_of)
        if row.get('average_eligible') is not False:
            raise ValueError('this snapshot has no reviewed averaging policy')
        values = row.get('values') or []
        if row.get('question_id') == 'reported_seats':
            if row['review_status'] == 'held':
                if any(value.get('seats') is not None for value in values):
                    raise ValueError('held seat row must not publish numbers')
                continue
            seen = set()
            for value in values:
                seat, lid = value.get('seats'), value.get('list_id')
                if lid not in known or lid in seen:
                    raise ValueError('unknown or duplicate list in seat poll')
                seen.add(lid)
                if type(seat) is not int or not 0 <= seat <= SEATS:
                    raise ValueError('missing or invalid reported seat number')
            if not values or sum(value['seats'] for value in values) != SEATS or row.get('seat_sum') != SEATS:
                raise ValueError('reported seat poll must total 120')
            if row['review_status'] == 'accepted' and (not row.get('field_end') or
                    not row.get('pollster') or type(row.get('n_respondents')) is not int or row['n_respondents'] <= 0):
                raise ValueError('accepted seat poll requires methodology and field date')
        elif row.get('unit') == 'percent':
            for value in values:
                pct = value.get('pct')
                if pct is not None and (type(pct) not in (int, float) or not 0 <= pct <= 100):
                    raise ValueError('invalid reported percentage')
                if value.get('list_id') is not None and value['list_id'] not in known:
                    raise ValueError('unknown list in percentage row')



def validate_context(context, known):
    if context.get('schema') != 'israel_coalition_context_v1':
        raise ValueError('coalition context schema mismatch')
    date.fromisoformat(context['reviewed_on'])
    groups = context.get('groups', [])
    group_ids = {row['id'] for row in groups}
    if len(group_ids) != len(groups) or not groups:
        raise ValueError('duplicate or missing coalition group')
    if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', row.get('color', '')) for row in groups):
        raise ValueError('invalid coalition color')
    families = context.get('ideology_groups', [])
    family_ids = {row['id'] for row in families}
    if not families or len(family_ids) != len(families):
        raise ValueError('duplicate or missing ideology group')
    if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', row.get('color', '')) for row in families):
        raise ValueError('invalid ideology color')
    sources = context.get('sources', {})
    for source in sources.values():
        safe_url(source['url'])
    profiles = context.get('parties', [])
    if len({row['list_id'] for row in profiles}) != len(profiles):
        raise ValueError('duplicate party context')
    for row in profiles:
        if row['list_id'] not in known or row['group'] not in group_ids:
            raise ValueError('unknown party or coalition group')
        if not row.get('source_ids') or not set(row['source_ids']) <= sources.keys():
            raise ValueError('party context source missing')
        if row.get('ideology_group') not in family_ids or not row.get('ideology_note'):
            raise ValueError('unknown or missing ideology group')
        if not row.get('ideology_source_ids') or not set(row['ideology_source_ids']) <= sources.keys():
            raise ValueError('ideology source missing')
    pairs = context.get('cooperation_pairs', [])
    if len({row['id'] for row in pairs}) != len(pairs):
        raise ValueError('duplicate cooperation pair')
    profile_groups = {row['list_id']: row['group'] for row in profiles}
    for pair in pairs:
        if (len(set(pair.get('parties', []))) != 2 or not set(pair['parties']) <= known
                or any(profile_groups.get(id) != pair.get('group') for id in pair['parties'])):
            raise ValueError('invalid cooperation pair')
        if not pair.get('source_ids') or not set(pair['source_ids']) <= sources.keys():
            raise ValueError('cooperation source missing')
        date.fromisoformat(pair['event_date'])

    kinds = {'electoral_cooperation', 'reported_bloc', 'conditional', 'joint_platform',
             'refusal', 'external_support', 'unknown', 'electoral_refusal'}
    relations = context.get('relationships', [])
    if len({row['id'] for row in relations}) != len(relations):
        raise ValueError('duplicate coalition relationship')
    for row in relations:
        if row.get('kind') not in kinds or not row.get('parties') or not set(row['parties']) <= known:
            raise ValueError('invalid coalition relationship')
        if not row.get('source_ids') or not set(row['source_ids']) <= sources.keys():
            raise ValueError('relationship source missing')
        if row.get('target_group') and row['target_group'] not in group_ids:
            raise ValueError('unknown relationship target group')
        if row['kind'] == 'refusal' and (row.get('anchor') not in known or
                not row.get('targets') or not set(row['targets']) <= known or not row.get('target_person')):
            raise ValueError('refusal needs a person, anchor and targets')
        date.fromisoformat(row['event_date'])
    for preset in context.get('presets', []):
        if not preset.get('list_ids') or not set(preset['list_ids']) <= known:
            raise ValueError('unknown coalition preset party')
    return context


def build(inputs, as_of, built_at):
    date.fromisoformat(as_of)
    clock = datetime.fromisoformat(built_at.replace('Z', '+00:00'))
    if clock.tzinfo is None:
        raise ValueError('build timestamp needs timezone')
    receipt = inputs['review_receipts.json']
    if receipt.get('evidence_as_of') != as_of or receipt.get('mode') != 'reviewed_snapshot':
        raise ValueError('cannot advance research date by rebuilding')
    lists = inputs['lists.json']
    if lists.get('cycle') != 'knesset-26':
        raise ValueError('wrong list cycle')
    ids = [row['id'] for row in lists['lists']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate list identities')
    rows = inputs['poll_observations.jsonl']
    validate_observations(rows, set(ids), as_of)
    context = validate_context(inputs['coalition_context.json'], set(ids))
    translations = validate_translations(inputs['ko_translations.json'], collect_input_texts(inputs, context))
    observations = [row for row in rows if row.get('record_type') == 'observation']
    seat_rows = [row for row in observations if row['question_id'] == 'reported_seats']
    counts = Counter(row['review_status'] for row in seat_rows)
    sources = inputs['sources.json']['sources']
    source_ids = [row['id'] for row in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('duplicate source IDs')
    for row in sources:
        safe_url(row['url'])
    post = inputs.get('post_election.json')
    if post is not None:
        validate_results(post, set(ids))
    return {
        **({'post_election': post} if post is not None else {}),
        'schema': 'israel_election_analysis_v1', 'iso3': 'ISR', 'cycle': 'knesset-26',
        'evidence_as_of': as_of, 'built_at': built_at, 'draft': True,
        'collection_mode': 'reviewed_snapshot', 'automatic_refresh': False,
        'coverage_complete': False, 'window': inputs['poll_observations.jsonl'][0].get('window'),
        'assembly_seats': SEATS, 'arithmetic_majority': SEATS // 2 + 1,
        'rules': {'threshold_pct': None, 'threshold_reported_pct': 3.25,
                  'threshold_status': 'held', 'threshold_note_ko': '보도상 3.25% · 선거법 81조 원문 확인 보류',
                  'allocation_status': 'held', 'allocation_note_ko': '득표율·위원회 접수 협약 미확보 · 의석 배분 계산 보류'},
        'current_seats': None, 'current_seats_status': 'held',
        'list_review_status': lists['review_status'], 'list_source': lists['list_source'],
        'lists': lists['lists'], 'list_missing': lists['missing'],
        'judgment_copy': lists.get('followup_judgment_evidence'),
        'calendar': inputs['election_calendar.json']['events'],
        'observations': observations,
        'research_notes': [row for row in rows if row.get('record_type') not in ('meta', 'observation')],
        'coalition_positions': [row for row in inputs['coalition_positions.jsonl'] if row.get('record_type') != 'meta'],
        'sources': sources,
        'coalition_context': context, 'localization': translations,
        'coverage': {'accepted_seat_polls': counts['accepted'], 'partial_seat_polls': counts['partial'],
                     'held_seat_polls': counts['held'], 'reported_lists': len(ids), 'sources': len(sources)},
        'input_digests': {name: digest(inputs[name]) for name in (*FILES, *(('post_election.json',) if post is not None else ()))},
        'limitations_ko': ['검토 입력 재생성 · 자동 수집 미설치', '최근 30일 전수 조사 미완료',
                           '현직 의석·후보 순위·공식 명부 원문 보류', '평균·총리 승률·연정 성립 확률 없음'],
    }


def health(board):
    content = json.dumps(board, ensure_ascii=False, indent=2) + '\n'
    return {'schema': 'israel_election_analysis_status_v1', 'status': 'reviewed_snapshot',
            'evidence_as_of': board['evidence_as_of'], 'built_at': board['built_at'],
            'board_sha256': hashlib.sha256(content.encode()).hexdigest(), 'automatic_refresh': False,
            'coverage_complete': False, 'coverage': board['coverage']}
