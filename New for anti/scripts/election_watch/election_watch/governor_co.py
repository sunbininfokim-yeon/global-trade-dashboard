"""Audit official Colorado bulk expenditures; never infer an IE target/direction.

CandidateName belongs to the filing candidate committee, not the beneficiary
of an independent expenditure. Supplemental notices require a separate join.
"""
from collections import Counter
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
import csv, io, hashlib, re, zipfile
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .superpac import SourceError

DOWNLOAD_PAGE='https://tracer.sos.colorado.gov/PublicSite/DataDownload.aspx'
KEY_URL='https://tracer.sos.colorado.gov/PublicSite/Resources/DownloadDataFileKey.pdf'
CSV_URL='https://Tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/2026_ExpenditureData.csv.zip'
HEADERS=['CO_ID','ExpenditureAmount','ExpenditureDate','LastName','FirstName','MI','Suffix',
    'Address1','Address2','City','State','Zip','Explanation','RecordID','FiledDate','ExpenditureType',
    'PaymentType','DisbursementType','Electioneering','CommitteeType','CommitteeName','CandidateName',
    'Employer','Occupation','Amended','Amendment','AmendedRecordID','Jurisdiction']

def parse_export(raw,as_of):
    if len(raw)>30*1024*1024:raise SourceError('Colorado ZIP exceeded size budget')
    try:
        z=zipfile.ZipFile(io.BytesIO(raw));entries=z.infolist()
        if len(entries)!=1 or entries[0].filename!='2026_ExpenditureData.csv' or entries[0].file_size>100*1024*1024:
            raise SourceError('Colorado ZIP membership/size changed')
        csv_raw=z.read(entries[0]);reader=csv.DictReader(io.StringIO(csv_raw.decode('cp1252')))
        if reader.fieldnames!=HEADERS:raise SourceError('Colorado expenditure schema changed')
        rows=list(reader)
    except (UnicodeError,csv.Error,zipfile.BadZipFile,RuntimeError):
        raise SourceError('Colorado public export invalid') from None
    if not rows or any(set(r)!=set(HEADERS) or any(v is None for v in r.values()) for r in rows):
        raise SourceError('Colorado empty/truncated export; previous audit preserved')
    for row in rows:
        try:
            filed=datetime.strptime(row['FiledDate'],'%Y-%m-%d %H:%M:%S').date()
            amount=Decimal(row['ExpenditureAmount'])
        except (ValueError,InvalidOperation):raise SourceError('Colorado filing date/amount changed') from None
        if filed.year!=2026 or filed>date.fromisoformat(as_of) or not row['RecordID'].isdigit() \
           or not amount.is_finite() or amount!=amount.quantize(Decimal('.01')) \
           or row['Amended'] not in ('Y','N') or row['Amendment'] not in ('Y','N'):
            raise SourceError('Colorado filing identity/year/amendment changed')
    return rows,hashlib.sha256(csv_raw).hexdigest()

def summarize_export(raw,cycle,roster,captured_at,source_as_of,source_last_modified=None):
    if cycle!=2026 or not roster or any(c['state']!='CO' or c['office']!='G' for c in roster):
        raise SourceError('Colorado requires reviewed 2026 governor roster')
    try:
        source_day=datetime.strptime(source_as_of,'%m/%d/%Y %I:%M %p').date()
        captured_day=date.fromisoformat(captured_at[:10])
    except ValueError:raise SourceError('Colorado snapshot date changed') from None
    if source_day.year!=2026 or source_day>captured_day:
        raise SourceError('Colorado snapshot date outside reviewed year/capture')
    rows,csv_sha=parse_export(raw,source_day.isoformat())
    ie=[r for r in rows if r['CommitteeType']=='Independent Expenditure Committee']
    return {'schema':'usa_governor_finance_audit_v1','state':'CO','cycle':cycle,
        'captured_at':captured_at,'status':'collected_normalization_held','source_url':DOWNLOAD_PAGE,
        'sources':[{'report_year':2026,'export_url':CSV_URL,'rows':len(rows),
            'csv_encoding':'cp1252','zip_sha256':hashlib.sha256(raw).hexdigest(),'csv_sha256':csv_sha,
            'source_as_of_text':source_as_of,'source_last_modified':source_last_modified,'file_key_url':KEY_URL}],
        'input_records':len(rows),'independent_expenditure_committee_rows':len(ie),
        'independent_expenditure_committee_count':len({r['CO_ID'] for r in ie}),
        'current_governor_target_records':None,'candidate_amounts_available':False,
        'last_general_bulk_filing_date':max(r['FiledDate'][:10] for r in rows),
        'candidate_audits':[{'candidate_id':c['candidate_id'],'name':c['name'],'party':c['party'],
            'reported_target':None,'reported_rows':None,'support_cents':None,'oppose_cents':None,
            'amount_status':'target_and_direction_unavailable'} for c in roster],
        'reported_committee_types':dict(Counter(r['CommitteeType'] for r in rows)),
        'duplicate_record_ids':sum(n-1 for n in Counter(r['RecordID'] for r in rows).values()),
        'amendment_diagnostics':{'amended_rows':sum(r['Amended']=='Y' for r in rows),
            'amendment_rows':sum(r['Amendment']=='Y' for r in rows),
            'lineage_verified':False},
        'hold_reasons':['bulk_candidate_name_is_filing_owner_not_ie_target','target_support_oppose_columns_missing',
            'supplemental_notice_transaction_and_amendment_join_required','only_2026_reporting_year_collected'],
        'limitations_ko':['공식2026년 일반지출ZIP의 수집 감사. 후보 캠프 비용과 독립지출을 합산하지 않습니다.',
            'Independent Expenditure Committee 행도 후보 대상·지지반대 방향·선거 단계가 없으므로 주지사 금액은null입니다.',
            'CandidateName은신고 캠프 소유자 필드이며 독립지출 수혜후보가 아닙니다. 설명문 이름검색으로 금액을분배하지 않습니다.',
            '전체CSV의 마지막신고일은 주지사 독립지출 마지막공시일이 아닙니다.2025년·미지원공시 전수를 주장하지 않습니다.']}

def collect_audit(cycle,roster,opener=urlopen):
    def fetch(url,budget):
        with opener(Request(url,headers={'User-Agent':'ElectionWatch/1.0 public-source-review'}),timeout=45) as r:
            if urlparse(r.geturl()).hostname.casefold()!='tracer.sos.colorado.gov':
                raise SourceError('Colorado public source redirected')
            body=r.read(budget+1);modified=r.headers.get('Last-Modified')
        if len(body)>budget:raise SourceError('Colorado source exceeded size budget')
        return body,modified
    page,_=fetch(DOWNLOAD_PAGE,1000000);html=unescape(page.decode('utf-8'))
    if '2026_ExpenditureData.csv.zip' not in html:raise SourceError('Colorado reviewed bulk link disappeared')
    match=re.search(r'as of\s*(?:<[^>]+>\s*)*(\d{1,2}/\d{1,2}/2026)\s*(?:<[^>]+>\s*)*(\d{1,2}:\d{2} [AP]M)',html)
    if not match:raise SourceError('Colorado bulk snapshot date unavailable')
    raw,modified=fetch(CSV_URL,30*1024*1024)
    return summarize_export(raw,cycle,roster,datetime.now(timezone.utc).isoformat(),' '.join(match.groups()),modified)
