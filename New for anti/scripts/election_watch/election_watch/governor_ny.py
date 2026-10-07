"""NY official daily data: reviewed IE filers, uniquely linked R allocations to F payments.

Unlinked Schedule R totals are cumulative and must never be summed as payments.
Unknown filers, ambiguous report versions and multi-target payments are excluded.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .superpac import SourceError, money, now

API = 'https://data.ny.gov/resource/e9ss-239a.json'
METADATA = 'https://data.ny.gov/api/views/e9ss-239a.json'
NOTICE_URL = 'https://publicreporting.elections.ny.gov/IndependentExpenditure/IndependentExpenditure'
FIELDS = {'filer_id', 'cand_comm_name', 'election_year', 'filing_abbrev',
          'filing_sched_abbrev', 'trans_number', 'trans_mapping', 'sched_date',
          'org_amt', 'election_year_r', 'office_desc', 'r_support_oppose',
          'filing_trans_id', 'r_amend', 'r_subcontractor', 'r_liability',
          'flng_ent_first_name', 'flng_ent_last_name'}


def fetch_json(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'ElectionWatch/1.0'}), timeout=60) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise SourceError('New York official API fetch/JSON failure; old snapshot preserved') from None


def _key(row):
    return (row.get('filer_id'), row.get('election_year'), row.get('election_type'),
            row.get('county_desc'), row.get('filing_abbrev'))


def _name(row):
    return ' '.join(row.get(k, '').strip() for k in
                    ('flng_ent_first_name', 'flng_ent_middle_name', 'flng_ent_last_name')
                    if row.get(k, '').strip())


def normalize(cycle, allocations, linked_rows, revision, roster, filers):
    registry = {}
    for candidate in roster:
        for alias in [candidate['name'], *candidate.get('reported_name_aliases', [])]:
            key = ' '.join(alias.split()).casefold()
            if key in registry and registry[key]['candidate_id'] != candidate['candidate_id']:
                raise SourceError('New York ambiguous reviewed candidate alias')
            registry[key] = candidate
    payments, targets = defaultdict(list), defaultdict(list)
    for row in linked_rows:
        if row.get('filing_sched_abbrev') == 'F':
            payments[(row.get('filer_id'), row.get('trans_number'))].append(row)
        elif row.get('filing_sched_abbrev') == 'R':
            targets[(row.get('filer_id'), row.get('trans_mapping'))].append(row)
    seen, records, excluded = set(), [], Counter()
    unknown_filers = set()
    for row in allocations:
        ident = row.get('filing_trans_id')
        if not ident or ident in seen:
            raise SourceError('New York missing/duplicate allocation row identity')
        seen.add(ident)
        if row.get('office_desc') != 'Governor' or str(row.get('election_year_r')) != str(cycle):
            excluded['not_governor_election'] += 1
            continue
        filer = row.get('filer_id')
        reviewed = filers.get(filer)
        if not reviewed or reviewed['name'].casefold() != row.get('cand_comm_name', '').casefold():
            unknown_filers.add(filer)
            excluded['unreviewed_independent_spender'] += 1
            continue
        parent = row.get('trans_mapping')
        if not parent:
            excluded['unlinked_cumulative_allocation'] += 1
            continue
        key = (filer, parent)
        if len(targets[key]) != 1 or len(payments[key]) != 1:
            excluded['ambiguous_version_or_multiple_targets'] += 1
            continue
        payment = payments[key][0]
        if _key(row) != _key(payment) or row.get('r_amend') != payment.get('r_amend'):
            excluded['report_version_mismatch'] += 1
            continue
        if row.get('r_amend') not in ('Y', 'N'):
            raise SourceError('New York amendment flag changed')
        # These flags mean the payment was subcontracted / paid an outstanding
        # liability (NYSBOE handbook p.93), not that it is a second payment or an
        # unpaid balance. Count its F paid amount once; never add detail/N balances.
        if any(payment.get(k) not in ('Y', 'N') for k in ('r_subcontractor', 'r_liability')):
            excluded['unresolved_payment_flags'] += 1
            continue
        candidate = registry.get(_name(row).casefold())
        direction = {'S': 'support', 'O': 'oppose'}.get(row.get('r_support_oppose'))
        if not candidate or not direction:
            excluded['unresolved_candidate_or_direction'] += 1
            continue
        try:
            cents, paid = money(row.get('org_amt')), money(payment.get('org_amt'))
            spent = date.fromisoformat(payment['sched_date'][:10]).isoformat()
        except (ValueError, KeyError, TypeError):
            excluded['invalid_amount_or_date'] += 1
            continue
        # Only one target and exactly the paid amount: no allocations or cumulative
        # totals are guessed from a partial/overlapping parent expenditure.
        if cents != paid or not f'{cycle-1}-01-01' <= spent <= f'{cycle}-12-31':
            excluded['allocation_payment_mismatch_or_outside_cycle'] += 1
            continue
        support, oppose = (cents, 0) if direction == 'support' else (0, cents)
        records.append({
            'candidate_id': candidate['candidate_id'], 'candidate_name': candidate['name'],
            'party': candidate['party'], 'party_basis': 'reviewed_certified_general_ballot',
            'candidate_identity_status': 'reviewed_exact_name_alias_office_cycle',
            'committee_id': 'NY:filer:' + filer, 'committee_name': row['cand_comm_name'],
            'category': 'state_independent_spender_unclassified',
            'office': 'governor', 'state': 'NY', 'district': None, 'cycle': cycle,
            'election_type': 'UNKNOWN', 'source_id': f'NY:F:{filer}:{parent}',
            'report_id': ':'.join(str(k or '') for k in _key(row)),
            'source_url': API + '?' + urlencode({'$where': f"filing_trans_id='{ident}'"}),
            'classification_source_url': reviewed['source_url'],
            'allocation_row_id': ident, 'payment_row_id': payment['filing_trans_id'],
            'support_cents': support, 'oppose_cents': oppose, 'records': 1,
            'filing_date': None, 'expenditure_date': spent,
            'monthly': {spent[:7]: {'support_cents': support, 'oppose_cents': oppose}},
            'monthly_basis': 'parent_payment_date',
            'provenance': 'Reviewed NY IE filer; unique Schedule R target with S/O linked to equal Schedule F payment',
        })
    if len({r['source_id'] for r in records}) != len(records):
        raise SourceError('New York duplicate parent expenditure identity')
    return {
        'schema': 'usa_governor_source_v1', 'cycle': cycle, 'state': 'NY',
        'generated_at': now(), 'status': 'partial', 'dataset_revision': revision,
        'source_url': API, 'metadata_url': METADATA, 'last_filing_date': None,
        'source_data_updated_at': datetime.fromtimestamp(revision, timezone.utc).isoformat(),
        'spending': records, 'candidates': roster,
        'amount_basis': 'gross_disclosed_payments_refunds_not_netted',
        'quality': {'input_records': len(allocations), 'included_records': len(records),
                    'excluded_records': dict(excluded), 'unreviewed_filer_ids': sorted(unknown_filers)},
        'limitations_ko': [
            '공식 IE 통지에서 확인한 지출자만 포함하며 새 지출자는 검토 전 제외합니다. 연방 슈퍼팩 유형과 동일하지 않습니다.',
            '주지사 후보별 Schedule R 배분이 단일 Schedule F 실제 지출과 같은 금액으로 연결된 건만 집계합니다. 연결 없는 누적 배분액·복수 후보·모호한 정정 버전은 제외합니다.',
            '2025~2026 지출만 포함합니다. 4년 선거기간 전체 외부지출 총액이나 실시간 24시간 통지 총액이 아닙니다.',
            '실제 지급액을 집계하며 하도급 세부 내역·미지급 잔액을 더하지 않습니다. 환불은 차감하지 않은 공시 지출액입니다.',
            'API의 현재 공개 스냅샷을 매번 다시 집계합니다. 정정본은 날짜나 숫자 ID로 추측하지 않으며 모호한 연결은 제외합니다. 신고일·경선/본선 용도는 미확보입니다.',
        ],
    }


def collect(cycle, roster, filer_registry, fetch=fetch_json):
    if filer_registry.get('cycle') != cycle or not roster:
        raise SourceError('New York reviewed cycle-specific roster/IE filer registry required')
    filers = {r['filer_id']: r for r in filer_registry['filers']}
    if len(filers) != len(filer_registry['filers']):
        raise SourceError('New York duplicate reviewed filer')
    metadata = fetch(METADATA)
    revision = metadata.get('rowsUpdatedAt')
    columns = {c.get('fieldName') for c in metadata.get('columns', [])}
    if not isinstance(revision, int) or not FIELDS <= columns:
        raise SourceError('New York dataset revision/schema changed')

    def query(where):
        result, seen = [], set()
        for page in range(100):
            rows = fetch(API + '?' + urlencode({'$where': where, '$order': 'filing_trans_id',
                                               '$limit': 1000, '$offset': page * 1000}))
            if not isinstance(rows, list):
                raise SourceError('New York response is not an array')
            for row in rows:
                ident = row.get('filing_trans_id')
                if not ident or ident in seen:
                    raise SourceError('New York missing/duplicate paginated identity')
                seen.add(ident)
            result.extend(rows)
            if len(rows) < 1000:
                return result
        raise SourceError('New York page budget exhausted')

    base = f"election_year between '{cycle-1}' and '{cycle}'"
    allocations = query(base + f" AND filing_sched_abbrev='R' AND office_desc='Governor' AND election_year_r='{cycle}'")
    parents = sorted({r['trans_mapping'] for r in allocations if r.get('trans_mapping') and r.get('filer_id') in filers})
    linked = []
    # API-returned identifiers are validated before insertion into SoQL.
    for start in range(0, len(parents), 40):
        batch = parents[start:start+40]
        if any(not all(c.isalnum() or c in '-_' for c in ident) for ident in batch):
            raise SourceError('New York unexpected transaction identifier')
        quoted = ','.join("'" + ident + "'" for ident in batch)
        linked.extend(query(base + f" AND ((filing_sched_abbrev='F' AND trans_number in ({quoted})) OR (filing_sched_abbrev='R' AND trans_mapping in ({quoted})))"))
    if fetch(METADATA).get('rowsUpdatedAt') != revision:
        raise SourceError('New York dataset changed during collection; retry required')
    payload = normalize(cycle, allocations, linked, revision, roster, filers)
    payload['reviewed_filer_registry_as_of'] = filer_registry['verified_on']
    return payload
