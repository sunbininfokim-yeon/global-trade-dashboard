"""FEC campaign summaries. These are neither outside spending nor personal wealth."""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import re
from urllib.request import Request, urlopen
import zipfile

from .polls import require

BASE = 'https://www.fec.gov/files/bulk-downloads/{cycle}/'
DOCS = 'https://www.fec.gov/campaign-finance-data/all-candidates-file-description/'
METRICS = {'receipts': 5, 'transfers_from_authorized': 6, 'disbursements': 7,
    'transfers_to_authorized': 8, 'beginning_cash': 9, 'cash_on_hand': 10,
    'candidate_contributions': 11, 'candidate_loans': 12, 'other_loans': 13,
    'candidate_loan_repayments': 14, 'other_loan_repayments': 15, 'debts_owed': 16,
    'individual_contributions': 17, 'other_committee_contributions': 25,
    'party_committee_contributions': 26, 'individual_refunds': 28, 'committee_refunds': 29}


def cents(raw):
    if raw == '':
        return None
    try:
        value = Decimal(raw)
        require(value.is_finite() and value * 100 == (value * 100).to_integral_value(),
                'invalid candidate finance precision')
        return int(value * 100)
    except (InvalidOperation, OverflowError):
        raise ValueError('invalid candidate finance amount') from None


def rows_from_zip(body, filename, width):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        require(archive.namelist() == [filename], 'changed FEC ZIP members')
        info = archive.getinfo(filename)
        require(info.file_size <= 30_000_000 and not info.flag_bits & 1, 'oversized/encrypted FEC member')
        text = archive.read(filename).decode('utf-8-sig')
    rows = list(csv.reader(io.StringIO(text), delimiter='|'))
    require(rows and all(len(r) == width for r in rows), 'empty/changed FEC row layout')
    return rows


def normalize(summary_rows, master_rows, catalog, as_of, receipts):
    day = date.fromisoformat(as_of); cycle = catalog['cycle']
    require(cycle == 2026 and len(catalog['states']) == 50, 'unreviewed fundraising universe')
    master = {}; seen = set(); output = {}; held = Counter()
    for row in master_rows:
        require(len(row) == 15 and re.fullmatch(r'[HSP][A-Z0-9]{8}', row[0]), 'invalid FEC candidate master')
        require(row[0] not in master, 'duplicate FEC master identity')
        master[row[0]] = row
    for row in summary_rows:
        require(len(row) == 30 and row[0] not in seen, 'changed/duplicate FEC financial summary')
        seen.add(row[0]); candidate = master.get(row[0])
        if not candidate or candidate[3] != str(cycle) or candidate[5] not in ('H', 'S'):
            held['outside_2026_house_senate_or_master_missing'] += 1; continue
        ident, state, office = candidate[0], candidate[4], {'H': 'house', 'S': 'senate'}[candidate[5]]
        if state not in catalog['states'] or (office == 'senate' and state not in catalog['senate_states']):
            held['outside_reviewed_election_universe'] += 1; continue
        if row[18] != state or row[4] != candidate[2] or ident[0] != candidate[5]:
            held['summary_master_state_party_office_conflict'] += 1; continue
        district = None
        if office == 'house':
            seats = catalog['states'][state]['house_seats']
            if row[19] != candidate[6] or not re.fullmatch(r'\d{2}', row[19]):
                held['summary_master_district_conflict'] += 1; continue
            reported = int(row[19])
            if seats == 1 and reported in (0, 1):
                district = '00'
            elif seats > 1 and 1 <= reported <= seats:
                district = row[19]
            else:
                held['district_outside_current_universe'] += 1; continue
        try:
            covered = datetime.strptime(row[27], '%m/%d/%Y').date()
            require(date(cycle-1, 1, 1) <= covered <= day, 'outside or future report period')
            amounts = {name+'_cents': cents(row[index]) for name, index in METRICS.items()}
        except (ValueError, TypeError):
            held['invalid_amount_or_coverage_date'] += 1; continue
        rid = f'USA:{state}:{office}' + (f':{district}' if district else '')
        output[ident] = {'candidate_id': ident, 'name': row[1], 'reported_party': row[4],
            'state': state, 'office': office, 'district': district, 'reported_district': row[19],
            'race_id': rid, 'election_year': cycle, 'fec_candidate_status': candidate[8],
            'principal_committee_id': candidate[9] or None,
            'status': 'reported_campaign_summary_ballot_unverified',
            'coverage_end': covered.isoformat(), 'currency': 'USD', 'amount_unit': 'cents',
            'amounts': amounts, 'source_url': f'https://www.fec.gov/data/candidate/{ident}/?cycle={cycle}',
            'source_snapshot_as_of': as_of, 'source_receipts': receipts,
            'transfer_double_count_risk': all((amounts[k] or 0) > 0 for k in
                ('transfers_from_authorized_cents', 'transfers_to_authorized_cents')),
            'includes_outside_spending': False}
    require(output, 'no valid candidate fundraising summaries; preserve previous snapshot')
    return {'schema': 'usa_candidate_fundraising_v1', 'cycle': cycle, 'as_of': as_of,
        'source_receipts': receipts, 'source_documentation': DOCS,
        'scope': 'FEC_two_year_reporting_period_2026_House_Senate_scheduled_states',
        'candidate_count': len(output), 'excluded': dict(held), 'candidates': output,
        'limitations_ko': ['캠프 총수입에는 차입·후보 본인 출연·이체 등이 포함되며 순수 후원금과 다릅니다.',
            '개인 후원금은 individual_contributions_cents, 캠프 총수입은 receipts_cents로 구분합니다.',
            '여러 수권 위원회 간 이체는 중복 위험이 있어 원문 이체 금액과 경고를 보존하며 임의 순모금을 계산하지 않습니다.',
            '후보별 coverage_end가 다릅니다. 수집일을 공시 기준일로 바꾸지 않습니다.',
            'FEC 등록은 본선 인증·현재 출마 확정이 아닙니다. 후보 ID로만 연결하며 과거/경선 후보도 포함될 수 있습니다.',
            '상원 6년 선거주기 전체가 아닌 FEC 2026 이년 보고주기 자료입니다.',
            '주지사 캠프 모금은 주별 공시가 필요하며 이 연방 자료에 포함되지 않습니다.',
            '슈퍼팩·독립지출·후보 개인 재산과 합산하지 않습니다.']}


def preserve_previous(doc, previous):
    require(previous['schema'] == doc['schema'] and previous['cycle'] == doc['cycle'],
            'fundraising previous snapshot scope')
    require(previous['as_of'] <= doc['as_of'], 'older candidate fundraising capture')
    carried = 0
    for ident, old in previous['candidates'].items():
        new = doc['candidates'].get(ident)
        if new is None or new['coverage_end'] < old['coverage_end']:
            doc['candidates'][ident] = {**old, 'carried_forward_reason':
                'missing_in_new_bulk' if new is None else 'new_bulk_has_older_coverage_date'}
            carried += 1
    doc['candidate_count'] = len(doc['candidates']); doc['carried_forward_candidates'] = carried
    return doc


def collect(cycle, as_of, captured_at, catalog, opener=urlopen):
    require(cycle == catalog['cycle'] == 2026, 'unreviewed fundraising cycle')
    suffix = str(cycle)[-2:]; parsed = {}; receipts = {}
    for key, file, member, width in [('summary', f'weball{suffix}.zip', f'weball{suffix}.txt', 30),
                                      ('master', f'cn{suffix}.zip', 'cn.txt', 15)]:
        url = BASE.format(cycle=cycle) + file
        with opener(Request(url, headers={'User-Agent': 'ElectionEvidenceReview/1.0'}), timeout=45) as response:
            require(response.url == url, 'unexpected FEC bulk redirect')
            body = response.read(15_000_001)
            require(len(body) <= 15_000_000, 'oversized FEC response')
            modified = response.headers.get('Last-Modified')
        try:
            parsed[key] = rows_from_zip(body, member, width)
        except zipfile.BadZipFile:
            raise ValueError('invalid FEC ZIP; preserve last good snapshot') from None
        receipts[key] = {'url': url, 'captured_at': captured_at,
            'sha256': hashlib.sha256(body).hexdigest(), 'last_modified': modified}
    return normalize(parsed['summary'], parsed['master'], catalog, as_of, receipts)


def for_candidate(snapshot, candidate_id, state, office, district, cycle):
    if office == 'governor':
        return {'status': 'state_campaign_fundraising_adapter_not_connected', 'amounts': None}
    if not snapshot:
        return {'status': 'not_collected', 'amounts': None}
    require(snapshot['schema'] == 'usa_candidate_fundraising_v1' and snapshot['cycle'] == int(cycle),
            'invalid fundraising snapshot')
    found = snapshot['candidates'].get(candidate_id)
    if not found:
        return {'status': 'no_matched_summary', 'amounts': None}
    if (found['state'], found['office'], found['district']) != (state, office, district):
        return {'status': 'candidate_identity_scope_conflict', 'amounts': None}
    return {**found, 'snapshot_as_of': found.get('source_snapshot_as_of', snapshot['as_of']),
            'source_receipts': found.get('source_receipts', snapshot['source_receipts'])}
