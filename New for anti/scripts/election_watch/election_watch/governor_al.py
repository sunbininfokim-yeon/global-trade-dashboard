"""Audit Alabama's public annual expenditures; beneficiary/direction stay null.

The export key identifies CandidateName as the candidate MAKING the expenditure.
Neither a PAC row nor a candidate committee's costs establish candidate-targeted
independent spending. Raw payee/contact records are never published by this audit.
"""
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import csv, hashlib, io, json, shutil, subprocess, tempfile, zipfile
from urllib.parse import urlencode, urlparse
from pathlib import Path
from .superpac import SourceError

HOST='https://fcpa.alabamavotes.gov/'
DOWNLOAD_PAGE=HOST+'page.request.do?page=page.acfPublicDownloadData'
MANIFEST_URL=HOST+'page.request.do?'+urlencode({'page':'com.acf.common.page.transactiondatadownloadsresults',
    'pageSize':100,'pageNumber':1,'sortDirection':'ASC','sortBy':'year'})
KEY_URL=HOST+'page.request.do?page=getResource&resource=expendituresExportLayout'
HEADERS=['CommitteeId','ExpenditureAmount','ExpenditureDate','LastName','FirstName','MI','Suffix',
    'Address1','City','State','Zip','Explanation','ExpenditureID','FiledDate','Purpose',
    'ExpenditureType','CommitteeType','CommitteeName','CandidateName','Amended']


def fetch_public(url,budget):
    """Read-only HTTPS GET with system certificate validation, including macOS.

    The server's chain fails with this desktop's bundled Python CA store. Curl
    uses the system trust store; TLS verification is never disabled or downgraded.
    No login, reset, report submission, browser cookie, or API key is used.
    """
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='fcpa.alabamavotes.gov' or parsed.username or parsed.password:
        raise SourceError('Alabama source outside reviewed HTTPS host')
    binary=shutil.which('curl')
    if not binary:raise SourceError('Alabama verified HTTPS transport unavailable')
    with tempfile.TemporaryDirectory(prefix='al-public-audit-') as folder:
        target=Path(folder)/'response'
        try:
            result=subprocess.run([binary,'--fail','--silent','--show-error','--proto','=https',
                '--max-redirs','0','--connect-timeout','15','--max-time','45',
                '--max-filesize',str(budget),'--output',str(target),url],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=50,check=False)
        except (OSError,subprocess.TimeoutExpired):raise SourceError('Alabama source unavailable') from None
        if result.returncode or not target.exists() or target.stat().st_size>budget:
            raise SourceError('Alabama source unavailable or exceeded size budget')
        return target.read_bytes()


def select_export(raw,cycle,as_of):
    try:
        data=json.loads(raw);rows=data['data']['list'];total=data['data']['totalRecords']
        if data['success'] is not True or type(total) is not int or not 0<total<=100 or len(rows)!=total:
            raise SourceError('Alabama manifest incomplete/paginated')
        matches=[r for r in rows if r['YEAR']==cycle and r['DATATYPE']=='Expenditure']
        if len(matches)!=1:raise SourceError('Alabama annual expenditure selection ambiguous')
        chosen=matches[0];ident=chosen['DOWNLOAD']
        updated=datetime.strptime(chosen['LASTUPDATEDRAW'],'%b %d, %Y, %I:%M:%S %p').date()
        if type(ident) is not int or ident<=0 or updated.year!=cycle or updated>date.fromisoformat(as_of):
            raise SourceError('Alabama manifest ID/date changed')
        return {**chosen,'source_as_of':updated.isoformat(),
                'export_url':HOST+'page.request.do?'+urlencode({'page':'getTransactionData','id':ident})}
    except (KeyError,TypeError,ValueError):raise SourceError('Alabama manifest schema/date changed') from None


def summarize_export(raw,cycle,roster,captured_at,selected,manifest_sha256,key_sha256):
    if cycle!=2026 or not roster or any(c['state']!='AL' or c['office']!='G' for c in roster):
        raise SourceError('Alabama requires reviewed 2026 governor roster')
    if selected['YEAR']!=cycle or selected['DATATYPE']!='Expenditure' or selected['source_as_of']>captured_at[:10]:
        raise SourceError('Alabama export year/snapshot changed')
    if len(raw)>30*1024*1024:raise SourceError('Alabama ZIP exceeded size budget')
    try:
        archive=zipfile.ZipFile(io.BytesIO(raw));members=archive.infolist()
        if len(members)!=1 or members[0].filename!='2026_ExpendituresExtract1.csv' or members[0].file_size>100*1024*1024:
            raise SourceError('Alabama ZIP membership/size changed')
        body=archive.read(members[0]);reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
        if reader.fieldnames!=HEADERS:raise SourceError('Alabama expenditure schema changed')
        records=list(reader)
    except (UnicodeError,csv.Error,zipfile.BadZipFile,RuntimeError):
        raise SourceError('Alabama expenditure archive invalid') from None
    if not records:raise SourceError('Alabama empty export; previous audit preserved')
    valid=[];rejected=Counter()
    for row in records:
        if set(row)!=set(HEADERS) or any(v is None for v in row.values()):
            rejected['ragged_source_csv_record']+=1;continue
        try:
            filed=datetime.strptime(row['FiledDate'],'%m/%d/%Y').date()
            spent=datetime.strptime(row['ExpenditureDate'],'%m/%d/%Y').date()
            amount=Decimal(row['ExpenditureAmount'])
        except (ValueError,InvalidOperation):
            rejected['invalid_or_missing_date_amount']+=1;continue
        if filed.year!=cycle or filed.isoformat()>selected['source_as_of'] or spent>filed \
                or not amount.is_finite() or amount!=amount.quantize(Decimal('.01')) \
                or not row['CommitteeId'].isdigit() or not row['ExpenditureID'].isdigit() \
                or row['Amended'] not in ('Y','N') \
                or row['CommitteeType'] not in ('Principal Campaign Committee','Political Action Committee'):
            rejected['invalid_identity_date_amount_or_status']+=1;continue
        valid.append(row)
    if not valid:raise SourceError('Alabama no structurally valid records; previous audit preserved')
    return {'schema':'usa_governor_finance_audit_v1','state':'AL','cycle':cycle,'captured_at':captured_at,
        'status':'collected_normalization_held','source_url':DOWNLOAD_PAGE,
        'sources':[{'report_year':cycle,'manifest_url':MANIFEST_URL,'manifest_sha256':manifest_sha256,
            'export_url':selected['export_url'],'file_key_url':KEY_URL,'file_key_sha256':key_sha256,
            'source_as_of':selected['source_as_of'],'source_as_of_text':selected['LASTUPDATEDRAW'],
            'source_timezone':'not_disclosed','zip_sha256':hashlib.sha256(raw).hexdigest(),
            'csv_sha256':hashlib.sha256(body).hexdigest(),'csv_encoding':'utf-8-sig',
            'rows':len(records),'valid_structure_and_dates_rows':len(valid)}],
        'input_records':len(records),'valid_structure_and_dates_records':len(valid),
        'source_parse_status':'partial_rejected_source_records' if rejected else 'all_records_structurally_checked',
        'rejected_source_records':dict(rejected),'candidate_amounts_available':False,
        'current_governor_target_records':None,'reported_committee_types':dict(Counter(r['CommitteeType'] for r in valid)),
        'last_valid_general_bulk_filing_date':max(datetime.strptime(r['FiledDate'],'%m/%d/%Y').date().isoformat() for r in valid),
        'duplicate_valid_record_ids':sum(n-1 for n in Counter(r['ExpenditureID'] for r in valid).values()),
        'amendment_diagnostics':{'amended_valid_rows':sum(r['Amended']=='Y' for r in valid),
            'lineage_verified':False,'monetary_deduplication_performed':False},
        'candidate_audits':[{'candidate_id':c['candidate_id'],'name':c['name'],'party':c['party'],
            'reported_target':None,'reported_rows':None,'support_cents':None,'oppose_cents':None,
            'amount_status':'target_and_direction_unavailable'} for c in roster],
        'hold_reasons':['bulk_candidate_name_is_filing_owner_not_ie_target','target_support_oppose_columns_missing',
            'amendment_lineage_not_verified','only_2026_reporting_year_collected'],
        'limitations_ko':['공식 일반지출ZIP 수집 감사이며 주지사 독립지출 금액 수집 완료가 아닙니다.',
            'CSV 파손·필수값 미확보 행은 제외 진단에 보존. 행 수를 완전한 고유 공시 건수로 표시하지 않습니다.',
            'CandidateName은 지출한 캠프 소유자입니다. PAC 비용·후보 캠프 비용을 독립지출 수혜후보에게 배분하지 않습니다.',
            '지지/반대·선거 단계·정정 계보 미확보로 모든 후보 금액은null. 일반지출 최신일은 주지사 IE 최신일이 아닙니다.']}


def collect_audit(cycle,roster,fetcher=fetch_public):
    captured_at=datetime.now(timezone.utc).isoformat()
    manifest=fetcher(MANIFEST_URL,1024*1024)
    selected=select_export(manifest,cycle,captured_at[:10])
    key=fetcher(KEY_URL,1024*1024)
    if not key.startswith(b'%PDF-'):raise SourceError('Alabama export key changed format')
    raw=fetcher(selected['export_url'],30*1024*1024)
    return summarize_export(raw,cycle,roster,captured_at,selected,
        hashlib.sha256(manifest).hexdigest(),hashlib.sha256(key).hexdigest())
