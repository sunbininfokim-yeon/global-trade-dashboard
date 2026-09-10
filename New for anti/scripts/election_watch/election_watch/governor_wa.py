"""Washington PDC C6 candidate allocations, separate from federal Super PACs."""
from collections import Counter
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .superpac import money, now, SourceError

API = 'https://data.wa.gov/resource/67cp-h962.json'
METADATA = 'https://data.wa.gov/api/views/67cp-h962.json'
COLUMNS = 'id,origin,report_number,report_type,report_date,election_year,sponsor_entity_id,sponsor_id,sponsor_name,sponsor_description,candidate_entity_id,candidate_candidacy_id,candidate_name,candidate_office,candidate_party,portion_of_amount,for_or_against,url'
IE_TYPES = {'Independent Expenditure', 'Independent Expenditure Ad', 'Independent Expenditure Ads'}


def fetch_json(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'ElectionWatch/1.0'}), timeout=60) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            if attempt == 3:
                raise SourceError('Washington PDC fetch/JSON failure; old snapshot preserved') from None
            time.sleep(2 ** attempt)


def collect(cycle, fetch=fetch_json):
    metadata = fetch(METADATA)
    revision = metadata.get('rowsUpdatedAt')
    if revision is None:
        raise SourceError('Washington dataset revision missing')
    columns = {c.get('fieldName'): c for c in metadata.get('columns', [])}
    # Amendment handling is a source guarantee, not an inference from report dates.
    if 'original report records are not included' not in columns.get('report_number', {}).get('description', ''):
        raise SourceError('Washington amendment contract changed; review required')
    params = {'$select': COLUMNS, '$where': f"candidate_office='Governor' AND election_year between {cycle-1} and {cycle}", '$order': 'id,origin', '$limit': 1000}
    records, seen, excluded = [], set(), Counter()
    for page in range(100):
        rows = fetch(API + '?' + urlencode(dict(params, **{'$offset': page * 1000})))
        if not isinstance(rows, list):
            raise SourceError('Washington response is not an array')
        for row in rows:
            identity = (row.get('id'), row.get('origin'))
            if not all(identity) or identity in seen:
                raise SourceError('Washington missing/duplicate row identity')
            seen.add(identity)
            if not str(row.get('origin', '')).startswith('C6.3') or row.get('candidate_office') != 'Governor':
                excluded['not_governor_allocation'] += 1
                continue
            if row.get('report_type') not in IE_TYPES:
                excluded['electioneering_or_other_report'] += 1
                continue
            direction = {'For': 'support', 'Against': 'oppose'}.get(row.get('for_or_against'))
            if not direction:
                excluded['unknown_direction'] += 1
                continue
            if not all(row.get(k) for k in ['candidate_candidacy_id', 'candidate_entity_id', 'sponsor_entity_id', 'candidate_name', 'sponsor_name', 'report_date']):
                excluded['unresolved_identity'] += 1
                continue
            try:
                cents = money(row.get('portion_of_amount'))
            except ValueError:
                excluded['invalid_allocation_amount'] += 1
                continue
            url = (row.get('url') or {}).get('url', '')
            if not url.startswith('https://'):
                excluded['missing_filing_url'] += 1
                continue
            party = row.get('candidate_party') or 'UNKNOWN'
            records.append({'candidate_id': 'WA:candidacy:' + row['candidate_candidacy_id'],
                'person_id': 'WA:entity:' + row['candidate_entity_id'], 'candidate_name': row['candidate_name'],
                'party': {'Democratic': 'DEM', 'Republican': 'REP'}.get(party, party), 'reported_party': party,
                'committee_id': 'WA:entity:' + row['sponsor_entity_id'], 'committee_name': row['sponsor_name'],
                'sponsor_description': row.get('sponsor_description'), 'category': 'state_independent_spender_unclassified',
                'office': 'governor', 'state': 'WA', 'district': None, 'cycle': cycle,
                'election_type': 'UNKNOWN', 'reporting_year': int(row['election_year']),
                'source_id': 'WA:C6:' + row['id'], 'report_id': row['report_number'],
                'source_url': url, 'classification_source_url': METADATA,
                'support_cents': cents if direction == 'support' else 0,
                'oppose_cents': cents if direction == 'oppose' else 0, 'records': 1,
                'filing_date': row['report_date'][:10], 'monthly': {}, 'monthly_basis': 'unavailable',
                'provenance': 'PDC current C6.3 candidate allocation; not report/vendor/funding total'})
        if len(rows) < 1000:
            break
    else:
        raise SourceError('Washington page budget exhausted')
    if fetch(METADATA).get('rowsUpdatedAt') != revision:
        raise SourceError('Washington dataset changed during pagination; retry required')
    return {'schema': 'usa_governor_source_v1', 'cycle': cycle, 'state': 'WA', 'generated_at': now(),
        'status': 'partial', 'dataset_revision': revision, 'source_url': API, 'metadata_url': METADATA,
        'last_filing_date': max((r['filing_date'] for r in records), default=None),
        'spending': records, 'quality': {'input_records': len(seen), 'included_records': len(records), 'excluded_records': dict(excluded)},
        'limitations_ko': ['워싱턴 C6 독립지출 후보별 배분액만 포함. C4 등 다른 공시와 선거 관련 통신은 제외하므로 전체 외부지출이 아닙니다.',
            '신고 연도는 선거일의 연도가 아닙니다. 경선·본선과 광고 월별 시점은 이 자료에서 확정하지 않습니다.',
            '지출자 유형은 미분류입니다. 이 자료를 슈퍼팩 지출로 표기하지 마세요.',
            '주지사 등록 후보 전체 명부는 미확보. 지출에서 식별된 후보만 포함합니다.']}
