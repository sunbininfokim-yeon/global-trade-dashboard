"""California current Form 496 allocations from the official daily CAL-ACCESS ZIP."""
from collections import Counter
import csv
from datetime import datetime
import hashlib
import io
from urllib.request import Request, urlopen
import zipfile
from .superpac import money, now, SourceError

URL = 'https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip'
DOCS = 'https://campaignfinance.cdn.sos.ca.gov/calaccess-documentation.zip'
COVER = 'CVR_CAMPAIGN_DISCLOSURE_CD'
LINES = 'S496_CD'


class RemoteZip(io.RawIOBase):
    """Pin every byte range to one ETag; refuse full-file or mixed-version responses."""
    def __init__(self, opener=urlopen, url=URL):
        self.opener = opener
        self.url = url
        with opener(Request(self.url, method='HEAD'), timeout=60) as response:
            self.size = int(response.headers['Content-Length'])
            self.etag = response.headers['ETag']
            self.modified = response.headers.get('Last-Modified')
        self.pos = 0
    def seekable(self): return True
    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos
    def tell(self): return self.pos
    def read(self, size=-1):
        size = self.size - self.pos if size < 0 else size
        if size == 0: return b''
        if size > 80_000_000 or self.pos < 0:
            raise SourceError('California ZIP range exceeds budget')
        end = self.pos + size - 1
        request = Request(self.url, headers={'Range': f'bytes={self.pos}-{end}', 'If-Match': self.etag})
        with self.opener(request, timeout=60) as response:
            if response.status != 206 or response.headers.get('ETag') != self.etag:
                raise SourceError('California ZIP range/revision contract changed')
            if response.headers.get('Content-Range') != f'bytes {self.pos}-{end}/{self.size}':
                raise SourceError('California ZIP returned wrong byte range')
            data = response.read(size + 1)
        if len(data) != size:
            raise SourceError('California ZIP truncated range')
        self.pos += size
        return data


def table(data):
    # The official export is tab-delimited, not quote-escaped CSV. NUL is padding.
    text = data.decode('cp1252').replace('\x00', '')
    yield from csv.DictReader(io.StringIO(text, newline=""), delimiter='\t', quoting=csv.QUOTE_NONE)


def iso_date(value):
    return datetime.strptime(value.split(' ')[0], '%m/%d/%Y').date().isoformat()


def name_key(value):
    return ' '.join(value.split()).casefold()


def target_id(name, cycle):
    return f'CA:reported-name:{cycle}:' + hashlib.sha256(name_key(name).encode()).hexdigest()[:16]


def normalize(cycle, covers, lines, roster=None, ballot_dates=None):
    latest, excluded, seen, records = {}, Counter(), set(), []
    input_records = 0
    for cover in covers:
        if cover['FORM_TYPE'] != 'F496': continue
        filing, amendment = cover['FILING_ID'], int(cover['AMEND_ID'])
        if filing not in latest or amendment > int(latest[filing]['AMEND_ID']):
            latest[filing] = cover
        elif amendment == int(latest[filing]['AMEND_ID']):
            raise SourceError('California duplicate cover identity')
    registry = {name_key(c['name']): c for c in roster or []}
    if len(registry) != len(roster or []):
        raise SourceError('California ambiguous certified candidate names')
    for row in lines:
        input_records += 1
        cover = latest.get(row['FILING_ID'])
        if not cover or row['AMEND_ID'] != cover['AMEND_ID']:
            excluded['superseded_or_missing_cover'] += 1; continue
        if cover['OFFICE_CD'] != 'GOV' or row['FORM_TYPE'] != 'F496':
            excluded['not_governor_f496'] += 1; continue
        try: spent = iso_date(row['EXP_DATE'])
        except (ValueError, AttributeError):
            excluded['missing_expenditure_date'] += 1; continue
        if not f'{cycle-1}-01-01' <= spent <= f'{cycle}-12-31':
            excluded['outside_spending_cycle'] += 1; continue
        identity = ':'.join(row[k] for k in ('FILING_ID','AMEND_ID','LINE_ITEM'))
        if identity in seen: raise SourceError('California duplicate allocation identity')
        seen.add(identity)
        if row['MEMO_CODE'].strip():
            excluded['memo'] += 1; continue
        name = ' '.join(filter(None, [cover['CAND_NAMF'],cover['CAND_NAML'],cover['CAND_NAMS']])).strip()
        direction = {'S':'support','O':'oppose'}.get(cover['SUP_OPP_CD'])
        if not name or not direction or not cover['FILER_ID']:
            excluded['unresolved_target_direction_or_filer'] += 1; continue
        try: cents = money(row['AMOUNT'])
        except ValueError:
            excluded['invalid_amount'] += 1; continue
        candidate = registry.get(name_key(name))
        party = candidate['party'] if candidate else 'UNKNOWN'
        filing_date = iso_date(cover['RPT_DATE']) if cover.get('RPT_DATE') else None
        try:
            ballot_date = iso_date(cover['ELECT_DATE']) if cover.get('ELECT_DATE') else None
        except (ValueError, AttributeError):
            ballot_date = None
        election_type = (ballot_dates or {}).get(ballot_date, 'UNKNOWN')
        if election_type not in ('UNKNOWN', f'P{cycle}', f'G{cycle}'):
            raise SourceError('California reviewed election-date mapping changed')
        records.append({'candidate_id': candidate['candidate_id'] if candidate else target_id(name,cycle),
            'candidate_name': candidate['name'] if candidate else name,
            'reported_candidate_name': name,
            'candidate_identity_status': 'exact_name_office_cycle_match_to_reviewed_roster' if candidate else 'reported_name_only_unverified',
            'candidate_identity_source_url': candidate['source_url'] if candidate else DOCS,
            'party': party, 'party_basis': candidate.get('registration_status', 'certified_primary_ballot') if candidate else 'unavailable',
            'committee_id': 'CA:filer:' + cover['FILER_ID'], 'committee_name': cover['FILER_NAML'],
            'category': 'state_independent_spender_unclassified', 'reported_entity_code': cover['ENTITY_CD'],
            'office': 'governor','state': 'CA','district': None,'cycle': cycle,
            'election_type': election_type, 'reported_election_date': ballot_date,
            'election_type_basis': 'CVR_ELECT_DATE_exact_match_to_reviewed_ballot_calendar' if election_type != 'UNKNOWN' else 'unavailable',
            'source_id': 'CA:F496:' + identity,
            'report_id': row['FILING_ID'], 'amendment_id': int(row['AMEND_ID']),
            'source_url': URL,
            'classification_source_url': DOCS,
            'support_cents': cents if direction=='support' else 0,'oppose_cents': cents if direction=='oppose' else 0,
            'records': 1,'filing_date': filing_date,'expenditure_date': spent,
            'monthly': {spent[:7]: {'support_cents': cents if direction=='support' else 0,'oppose_cents': cents if direction=='oppose' else 0}},
            'monthly_basis': 'reported_expenditure_date', 'provenance': 'Latest entire F496 amendment; S496 AMOUNT, not cover/cumulative total'})
    return {'schema':'usa_governor_source_v1','cycle':cycle,'state':'CA','generated_at':now(),
        'status':'partial','source_url':URL,'metadata_url':DOCS,
        'last_filing_date':max((r['filing_date'] for r in records if r['filing_date']),default=None),
        'spending':records,'candidates':roster or [],
        'quality': {'input_records':input_records, 'current_governor_records':len(seen),'included_records':len(records),'excluded_records':dict(excluded)},
        'limitations_ko':['CA Form 496 최신 정정본의 주지사 독립지출 항목만 포함. Form 460·465 및 다른 형태의 외부지출은 제외합니다.',
            'CVR Elect_Date가 검토한 주지사 선거일과 정확히 같은 공시만 경선·본선으로 분리합니다. 지출일·신고일만으로 추정하지 않으며 빈값·1900년 기본값·다른 선거일은 미확인으로 유지합니다.',
            '주 지출자 유형은 미분류이며 연방 슈퍼팩으로 간주하지 않습니다.',
            '후보 ID가 없는 신고는 같은 회기·직위의 검토 명부와 전체 이름이 정확히 일치할 때만 연결합니다. 별명·중간이름 차이는 미확인 대상으로 유지합니다.',
            '정당의 출처는 후보별 party_basis에 보존합니다. 공식 경선 명부의 정당은 지출 당시 신고 정당 또는 본선 진출을 뜻하지 않습니다.']}


def collect(cycle, roster=None, local_tables=None, ballot_dates=None):
    try:
        if local_tables:
            covers = table((local_tables / COVER).read_bytes())
            lines = table((local_tables / LINES).read_bytes())
            payload = normalize(cycle,covers,lines,roster,ballot_dates)
            payload['source_table_sha256'] = {name: hashlib.sha256((local_tables / name).read_bytes()).hexdigest() for name in (COVER, LINES)}
            payload['dataset_revision'] = 'sha256:' + hashlib.sha256(str(sorted(payload['source_table_sha256'].items())).encode()).hexdigest()
            return payload
        remote = RemoteZip()
        with zipfile.ZipFile(remote) as archive:
            covers = table(archive.read('CalAccess/DATA/'+COVER+'.TSV'))
            lines = table(archive.read('CalAccess/DATA/'+LINES+'.TSV'))
        payload = normalize(cycle,covers,lines,roster,ballot_dates)
        payload.update(dataset_revision=remote.etag, source_last_modified=remote.modified)
        return payload
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, zipfile.BadZipFile):
        raise SourceError('California official ZIP/table fetch or schema failure; old snapshot preserved') from None
