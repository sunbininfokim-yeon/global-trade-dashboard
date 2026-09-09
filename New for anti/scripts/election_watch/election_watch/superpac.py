"""Public campaign-finance facts only; no candidate ranking or persuasion model."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = 'https://api.open.fec.gov/v1/'
STATES = 'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split()
OFFICES = {'H': 'house', 'S': 'senate', 'P': 'president'}
CATEGORIES = {'O': 'super_pac', 'U': 'single_candidate_ie', 'V': 'hybrid_pac', 'W': 'hybrid_pac'}
LIMITS = [
    'FEC 등록은 투표용지 등재·경선 참가·현재 출마 상태의 확정 증거가 아닙니다. 탈락·사퇴 후보도 공시 내역에 남습니다.',
    '정기보고의 most_recent=true 행만 집계합니다. 24/48시간 긴급보고는 중복 합산을 피하기 위해 제외하므로 최근 지출이 늦게 반영될 수 있습니다.',
    '지원·반대 금액은 해당 후보를 대상으로 한 독립지출입니다. 반대 지출을 다른 후보 또는 정당의 지원액으로 전환하지 않습니다.',
    '정당은 지출 대상 후보의 신고 정당입니다. 슈퍼팩의 당 소속이나 후보와의 관계를 추정하지 않습니다.',
    '대선은 전국 단위입니다. 공시의 주 코드를 실제 광고 집행 지역으로 해석하지 않습니다.',
    '상원은 주·선거유형 단위이며 seat class 미확보 시 같은 유형의 동시 선거를 의석별로 구분할 수 없습니다.',
    '전체 외부자금·광고 노출·후원금의 최종 실소유자·득표 영향·당선 확률을 측정하지 않습니다.',
]


def now():
    return datetime.now(timezone.utc).isoformat()


def money(value):
    if value is None or isinstance(value, bool):
        raise ValueError('missing_amount')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.quantize(Decimal('.01')):
            raise ValueError('invalid_amount')
        return int(amount * 100)
    except InvalidOperation as exc:
        raise ValueError('invalid_amount') from exc


class SourceError(RuntimeError):
    pass


class FecClient:
    def __init__(self, key, fetch=None, pause=time.sleep, max_pages=10000):
        self.key, self.fetch, self.pause = key, fetch or self._fetch, pause
        self.max_pages = max_pages
        self.requests = 0
        self.sources = []

    def _fetch(self, url):
        for attempt in range(4):
            try:
                with urlopen(Request(url, headers={'User-Agent': 'ElectionWatch/1.0'}), timeout=45) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    # Never include the URL: it contains the API key.
                    raise SourceError(f'FEC HTTP {exc.code}') from None
                self.pause(min(30, 2 ** (attempt + 1)))
            except (URLError, TimeoutError, OSError, ValueError):
                if attempt == 3:
                    raise SourceError('FEC network/JSON failure') from None
                self.pause(2 ** attempt)

    def rows(self, endpoint, **params):
        if not self.key:
            raise SourceError('FEC_API_KEY is required; no full run with DEMO_KEY')
        safe_params = dict(params, per_page=100)
        self.sources.append({'url': API + endpoint + '?' + urlencode(safe_params, doseq=True), 'retrieved_at': now()})
        query = dict(safe_params, api_key=self.key)
        seek = endpoint == 'schedules/schedule_e/'
        if not seek:
            query['page'] = 1
        seen = set()
        for page in range(1, self.max_pages + 1):
            self.requests += 1
            result = self.fetch(API + endpoint + '?' + urlencode(query, doseq=True))
            rows, pagination = result.get('results'), result.get('pagination')
            if not isinstance(rows, list) or not isinstance(pagination, dict):
                raise SourceError('Invalid FEC response contract')
            yield from rows
            if not rows:
                return
            if seek:
                cursor = pagination.get('last_indexes')
                if not cursor:
                    if len(rows) < 100:
                        return
                    raise SourceError('FEC missing continuation cursor')
                token = json.dumps(cursor, sort_keys=True)
                if token in seen:
                    raise SourceError('FEC repeated continuation cursor')
                seen.add(token)
                query.update(cursor)
            else:
                pages = pagination.get('pages')
                if not isinstance(pages, int):
                    raise SourceError('FEC missing page count')
                if page >= pages:
                    return
                query['page'] = page + 1
            self.pause(3.7)  # under the standard 1,000 requests/hour budget
        raise SourceError('FEC page budget exhausted; refusing incomplete snapshot')


def candidates_from_bulk(data, cycle):
    """Cycle-specific FEC master; never infer candidate identity from a name."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        with archive.open('cn.txt') as file:
            reader = csv.reader(io.TextIOWrapper(file, encoding='utf-8-sig', errors='replace'), delimiter='|')
            for row in reader:
                if len(row) != 15:
                    raise SourceError('FEC candidate master schema changed')
                if row[5] not in OFFICES or row[3] not in (str(cycle - 1), str(cycle)):
                    continue
                yield {'candidate_id': row[0], 'name': row[1], 'party': row[2] or 'UNKNOWN',
                       'election_year': int(row[3]), 'office': row[5], 'state': row[4],
                       'district': row[6], 'candidate_status': row[8], 'incumbent_challenge': row[7]}


def fetch_candidates(cycle):
    url = f'https://www.fec.gov/files/bulk-downloads/{cycle}/cn{str(cycle)[-2:]}.zip'
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'ElectionWatch/1.0'}), timeout=60) as response:
                data = response.read()
            return list(candidates_from_bulk(data, cycle)), {'url': url, 'retrieved_at': now(), 'sha256': hashlib.sha256(data).hexdigest()}
        except (HTTPError, URLError, TimeoutError, OSError):
            if attempt == 2:
                raise SourceError('FEC candidate master download failed') from None
            time.sleep(2 ** attempt)


def normalize(row, cycle):
    if row.get('is_notice') is not False:
        raise ValueError('notice_or_unknown')
    if row.get('most_recent') is not True:
        raise ValueError('amendment_status_unverified')
    if row.get('memoed_subtotal') or row.get('memo_code') == 'X':
        raise ValueError('memo')
    if row.get('action_code') == 'D':
        raise ValueError('deleted')
    office = OFFICES.get(row.get('candidate_office'))
    if not office:
        raise ValueError('out_of_scope_office')
    candidate_id, committee_id = row.get('candidate_id'), row.get('committee_id')
    if not re.fullmatch(r'[HSP][A-Z0-9]{8}', candidate_id or '') or not committee_id:
        raise ValueError('unresolved_id')
    if candidate_id[0] != row['candidate_office']:
        raise ValueError('candidate_office_conflict')
    state = 'US' if office == 'president' else row.get('candidate_office_state')
    if state not in STATES + ['US', 'DC', 'AS', 'GU', 'MP', 'PR', 'VI']:
        raise ValueError('unresolved_state')
    district = str(row.get('candidate_office_district') or '').zfill(2) if office == 'house' else None
    if office == 'house' and (row.get('candidate_office_district') in (None, '') or not re.fullmatch(r'\d{2}', district)):
        raise ValueError('unresolved_district')
    election = str(row.get('election_type') or 'UNKNOWN')
    if not re.fullmatch(r'[A-Z0-9_-]{1,20}', election):
        raise ValueError('invalid_election_code')
    support = {'S': 'support', 'O': 'oppose'}.get(row.get('support_oppose_indicator'))
    if not support:
        raise ValueError('unresolved_support_oppose')
    if not row.get('sub_id'):
        raise ValueError('missing_transaction_identity')
    committee = row.get('committee') or {}
    kind = CATEGORIES.get(committee.get('committee_type'), 'other_independent_spender' if committee.get('committee_type') else 'unclassified')
    return {'source_id': str(row['sub_id']), 'cycle': cycle, 'office': office, 'state': state, 'district': district,
            'election_type': election, 'election_type_label': row.get('election_type_full'),
            'candidate_id': candidate_id, 'candidate_name': row.get('candidate_name') or candidate_id,
            'party': row.get('candidate_party') or 'UNKNOWN', 'committee_id': committee_id,
            'committee_name': committee.get('name') or committee_id, 'committee_type': committee.get('committee_type'),
            'category': kind, 'direction': support, 'amount_cents': money(row.get('expenditure_amount')),
            'date': str(row.get('dissemination_date') or row.get('expenditure_date') or '')[:10] or None,
            'filing_date': row.get('filing_date'), 'source_url': f'https://www.fec.gov/data/independent-expenditures/?data_type=processed&committee_id={committee_id}&candidate_id={candidate_id}&cycle={cycle}'}


def governor_coverage():
    return {state: {'status': 'unsupported', 'amount_cents': None,
                   'reason_ko': '주 선거자금 공시 어댑터 미연결. FEC 자료로 주지사 선거를 집계할 수 없습니다.'} for state in STATES}


def build_snapshot(cycle, candidates, expenditures, sources=None):
    issues, seen = Counter(), set()
    totals = defaultdict(int)
    groups = {}
    last_filing = None
    for raw in expenditures:
        try:
            item = normalize(raw, cycle)
        except ValueError as exc:
            issues[str(exc)] += 1
            continue
        if item['source_id'] in seen:
            issues['duplicate_sub_id'] += 1
            continue
        seen.add(item['source_id'])
        key = tuple(item[field] for field in ('office', 'state', 'district', 'election_type', 'candidate_id', 'party', 'committee_id', 'category'))
        if key not in groups:
            groups[key] = {k: v for k, v in item.items() if k not in ('source_id', 'date', 'direction', 'amount_cents', 'filing_date')}
            groups[key].update(support_cents=0, oppose_cents=0, records=0, monthly={})
        group = groups[key]
        group[item['direction'] + '_cents'] += item['amount_cents']
        group['records'] += 1
        month = (item['date'] or 'unknown')[:7]
        group['monthly'].setdefault(month, {'support_cents': 0, 'oppose_cents': 0})[item['direction'] + '_cents'] += item['amount_cents']
        totals[f"{item['category']}_{item['direction']}_cents"] += item['amount_cents']
        if item['filing_date']:
            last_filing = max(last_filing or '', item['filing_date'])
    important = set(issues) - {'notice_or_unknown', 'memo', 'deleted', 'duplicate_sub_id', 'out_of_scope_office'}
    return {'schema': 'usa_superpac_v1', 'cycle': cycle, 'generated_at': now(),
            'status': 'partial' if important else 'ready', 'currency': 'USD', 'amount_unit': 'cents',
            'coverage': {'federal': 'processed_regular_reports', 'governor': governor_coverage(),
                         'candidate_roster': 'FEC registrations; ballot/withdrawal status unverified',
                         'last_filing_date': last_filing, 'notices_included': False},
            'candidates': candidates, 'spending': sorted(groups.values(), key=lambda x: (x['state'], x['office'], x['district'] or '', x['election_type'], x['candidate_id'], x['committee_id'], x['party'])),
            'summary': dict(totals), 'quality': {'included_records': len(seen), 'excluded_records': dict(sorted(issues.items()))},
            'sources': sources or [], 'limitations_ko': LIMITS}


def import_governor(snapshot, payload):
    """Reviewed normalized state data; not an automatic 50-state collector."""
    if payload.get('schema') != 'usa_governor_ie_import_v1' or payload.get('cycle') != snapshot['cycle']:
        raise ValueError('Governor import schema/cycle mismatch')
    records, seen = [], set()
    state = payload.get('state')
    if state not in STATES or payload.get('coverage') != 'partial':
        raise ValueError('Governor imports require state and partial coverage')
    for row in payload.get('records', []):
        required = ['source_id', 'candidate_id', 'candidate_name', 'party', 'committee_id', 'committee_name', 'election_type', 'source_url', 'classification_source_url', 'as_of']
        if row.get('office') != 'governor' or row.get('state') != state or not all(row.get(k) for k in required):
            raise ValueError('Incomplete governor record or out-of-scope office')
        if row.get('reviewed') is not True or row.get('is_current') is not True:
            raise ValueError('Governor records require reviewed current filings')
        if row.get('category') not in ('state_independent_expenditure_committee', 'hybrid_pac', 'other_independent_spender'):
            raise ValueError('Do not label state entities as FEC Super PACs')
        for field in ('source_url', 'classification_source_url'):
            if not re.match(r'^https://[^/]+/', row[field]):
                raise ValueError('Governor source must use HTTPS')
        if row['source_id'] in seen:
            raise ValueError('Duplicate governor source_id; resolve amendments before import')
        seen.add(row['source_id'])
        direction = row.get('direction')
        if direction not in ('support', 'oppose'):
            raise ValueError('Invalid governor direction')
        record = {key: row[key] for key in required + ['office', 'state', 'category']}
        record.update(cycle=snapshot['cycle'], district=None, support_cents=0, oppose_cents=0, records=1, monthly={})
        record[direction + '_cents'] = money(row.get('amount_usd'))
        records.append(record)
    snapshot['spending'].extend(records)
    snapshot['coverage']['governor'][state] = {'status': 'partial', 'records': len(records), 'reason_ko': '검토된 주 공시만 포함. 주 전체 및 후보 명단의 완전성은 미검증.'}
    return snapshot
