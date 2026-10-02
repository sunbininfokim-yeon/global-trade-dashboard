"""Texas TEC direct-campaign-expenditure candidate rows: governor support only.

The official CAND record identifies a candidate benefiting from an expenditure.
It does not identify opposition, and a multi-candidate expenditure has no
published allocation per target, so neither is inferred here.
"""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import io
import zipfile

from .governor_ca import RemoteZip
from .superpac import SourceError, money, now

ARCHIVE = 'https://prd.tecprd.ethicsefile.com/public/cf/public/TEC_CF_CSV.zip'
SCHEMA = 'https://www.ethics.state.tx.us/data/search/cf/CFS-ReadMe.txt'
CODES = 'https://www.ethics.state.tx.us/data/search/cf/CFS-Codes.txt'
EXPECTED_COLUMNS = 40


def _date(raw):
    return datetime.strptime(raw, '%Y%m%d').date().isoformat()


def _candidate_name(row):
    return ' '.join(part.strip() for part in (row[25], row[23]) if part.strip())


def normalize(cycle, lines, revision, roster=None):
    grouped, excluded = defaultdict(list), Counter()
    roster = roster or []
    registry = {' '.join(c['name'].split()).casefold(): c for c in roster}
    if len(registry) != len(roster):
        raise SourceError('Texas ambiguous certified candidate names')
    input_records = 0
    for row in csv.reader(lines):
        if not row or row[0] == 'recordType':
            continue
        input_records += 1
        if len(row) != EXPECTED_COLUMNS or row[0] != 'CAND':
            raise SourceError('Texas CAND schema changed; old snapshot preserved')
        if row[1] != 'DCE':
            excluded['not_direct_campaign_expenditure'] += 1
            continue
        if row[5] == 'Y':
            excluded['superseded_report'] += 1
            continue
        if row[5] not in ('', 'N'):
            raise SourceError('Texas correction flag changed; old snapshot preserved')
        if not row[9] or not row[3] or not row[6]:
            raise SourceError('Texas missing expenditure/report/filer identity')
        try:
            date = _date(row[11])
        except ValueError:
            excluded['invalid_expenditure_date'] += 1
            continue
        if not f'{cycle-1}-01-01' <= date <= f'{cycle}-12-31':
            excluded['outside_spending_cycle'] += 1
            continue
        grouped[(row[3], row[9])].append(row)

    records = []
    for (report_id, expenditure_id), targets in grouped.items():
        # A CAND row repeats the full expenditure amount, not a target share.
        if len(targets) != 1:
            excluded['multi_target_or_duplicate_expenditure'] += len(targets)
            continue
        row = targets[0]
        if row[34] != 'GOVERNOR':
            excluded['not_governor'] += 1
            continue
        name = _candidate_name(row)
        if not name or not row[8].strip():
            excluded['unresolved_candidate_or_spender'] += 1
            continue
        try:
            cents = money(row[12])
            received = _date(row[4])
            spent = _date(row[11])
        except ValueError:
            excluded['invalid_amount_or_filing_date'] += 1
            continue
        name_key = ' '.join(name.split()).casefold()
        target_id = hashlib.sha256(name_key.encode()).hexdigest()[:16]
        certified = registry.get(name_key)
        records.append({
            'candidate_id': certified['candidate_id'] if certified else f'TX:reported-name:{cycle}:{target_id}',
            'candidate_name': certified['name'] if certified else name,
            'candidate_identity_status': 'exact_name_office_cycle_match_to_certified_roster' if certified else 'reported_name_only_unverified',
            'party': certified['party'] if certified else 'UNKNOWN',
            'party_basis': 'certified_general_ballot' if certified else 'unavailable',
            'committee_id': 'TX:filer:' + row[6], 'committee_name': row[8].strip(),
            'category': 'state_independent_spender_unclassified',
            'office': 'governor', 'state': 'TX', 'district': None, 'cycle': cycle,
            'election_type': 'UNKNOWN', 'source_id': f'TX:DCE:{report_id}:{expenditure_id}',
            'report_id': report_id, 'source_url': ARCHIVE,
            'classification_source_url': SCHEMA,
            'support_cents': cents, 'oppose_cents': 0, 'records': 1,
            'filing_date': received, 'expenditure_date': spent,
            'monthly': {spent[:7]: {'support_cents': cents, 'oppose_cents': 0}},
            'monthly_basis': 'reported_expenditure_date',
            'provenance': 'TEC CAND row linked to one DCE expenditure; candidate benefiting; not all independent spending',
        })
    if len({r['source_id'] for r in records}) != len(records):
        raise SourceError('Texas duplicate expenditure identity')
    if input_records != len(records) + sum(excluded.values()):
        raise SourceError('Texas CAND accounting mismatch')
    return {
        'schema': 'usa_governor_source_v1', 'cycle': cycle, 'state': 'TX',
        'generated_at': now(), 'status': 'partial', 'dataset_revision': revision,
        'source_url': ARCHIVE, 'metadata_url': SCHEMA,
        'last_filing_date': max((r['filing_date'] for r in records), default=None),
        'spending': records, 'candidates': roster,
        'quality': {'input_records': input_records, 'included_records': len(records),
                    'excluded_records': dict(excluded)},
        'limitations_ko': [
            '텍사스 CAND 행에서 단일 주지사 후보가 수혜자로 명시된 DCE 지출만 포함합니다. 반대 지출·일반 PAC 지출·복수 후보 대상 지출은 포함하지 않습니다.',
            '후보 정당은 공식 본선 명부와 이름이 정확히 일치할 때만 붙입니다. 지출 당시 후보 정당이나 경선·본선 용도는 추정하지 않습니다.',
            '지출자 슈퍼팩 유형은 이 파일만으로 확인할 수 없습니다.',
            '단체 전체 지출 또는 주지사 선거 외부지출 총액이 아닙니다.',
        ],
    }


def collect(cycle, archive=None, roster=None):
    try:
        remote = None if archive else RemoteZip(url=ARCHIVE)
        source = archive or remote
        with zipfile.ZipFile(source) as bundle:
            if 'cand.csv' not in bundle.namelist():
                raise SourceError('Texas CAND table missing; old snapshot preserved')
            info = bundle.getinfo('cand.csv')
            if info.file_size > 150_000_000:
                raise SourceError('Texas CAND table exceeds size budget')
            data = bundle.read('cand.csv')
        revision = remote.etag if remote else 'local:' + hashlib.sha256(data).hexdigest()
        return normalize(cycle, io.StringIO(data.decode('utf-8-sig'), newline=''), revision, roster)
    except (OSError, ValueError, UnicodeError, csv.Error, zipfile.BadZipFile, KeyError):
        raise SourceError('Texas official ZIP/table fetch or schema failure; old snapshot preserved') from None
