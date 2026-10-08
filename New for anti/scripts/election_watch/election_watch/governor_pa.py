"""Audit PA official annual filer/expense exports without inferring candidate IE."""
from collections import Counter
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib, io
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile
from .superpac import SourceError

SOURCE='https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/campaign-finance-data'
EXPORT='https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/campaign-finance/campaign-finance-data/2026.zip'
README='https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/campaign-finance/campaign-finance-data/readme-cf-data.txt'
FORM='https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/campaign-finance/dseb_505.pdf'
FILER=['CampaignfinanceID','FILERID','EYEAR','SubmittedDate','CYCLE','AMMEND','TERMINATE','FILERTYPE','FILERNAME','OFFICE','DISTRICT','PARTY','ADDRESS1','ADDRESS2','CITY','STATE','ZIPCODE','COUNTY','PHONE','BEGINNING','MONETARY','INKIND']
EXPENSE=['CampaignFinanceID','FILERID','EYEAR','SubmittedDate','CYCLE','EXPNAME','ADDRESS1','ADDRESS2','CITY','STATE','ZIPCODE','EXPDATE','EXPAMT','EXPDESC']


def summarize_export(raw, cycle, roster, checked_at):
    if cycle!=2026 or not roster or len({c['candidate_id'] for c in roster})!=len(roster):
        raise SourceError('PA unreviewed cycle/roster')
    if not raw or len(raw)>55*1024*1024:raise SourceError('PA empty/oversized ZIP')
    checked=date.fromisoformat(checked_at[:10])
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            expected={f'{kind}_{cycle}.txt' for kind in ('receipt','filer','expense','debt','contrib')}
            if set(archive.namelist())!=expected or len(archive.namelist())!=len(expected):
                raise SourceError('PA ZIP member schema changed')
            tables={};sources=[]
            # Never extract ZIP members or read the large contribution file.
            for kind,columns in [('filer',FILER),('expense',EXPENSE)]:
                name=f'{kind}_{cycle}.txt';info=archive.getinfo(name)
                if info.file_size>25*1024*1024 or info.flag_bits&1:raise SourceError('PA unsafe export member')
                content=archive.read(name)
                lines=content.decode('cp1252').splitlines()
                if not lines or next(csv.reader([lines[0]],strict=True))!=columns:raise SourceError('PA CSV schema changed')
                rows=[];held=[]
                for line_number,line in enumerate(lines[1:],2):
                    try:
                        values=next(csv.reader([line],strict=True))
                    except csv.Error:
                        held.append({'line':line_number,'reason':'invalid_csv_quoting',
                                     'line_sha256':hashlib.sha256(line.encode('cp1252')).hexdigest()})
                        continue
                    if len(values)!=len(columns):raise SourceError('PA CSV column count changed')
                    rows.append(dict(zip(columns,values)))
                if not rows:raise SourceError('PA empty CSV; zero not inferred')
                for row in rows:
                    if set(row)!=set(columns) or any(v is None for v in row.values()):raise SourceError('PA malformed CSV')
                    if row['EYEAR']!=str(cycle) or not row['FILERID'] or not row[columns[0]].isdigit():raise SourceError('PA report identity/year changed')
                    if date.fromisoformat(row['SubmittedDate'])>checked:raise SourceError('PA future submission')
                    if kind=='expense':
                        amount=Decimal(row['EXPAMT'])
                        if not amount.is_finite() or amount!=amount.quantize(Decimal('.01')):raise SourceError('PA invalid amount')
                    elif row['AMMEND'] not in ('Y','N'):raise SourceError('PA amendment flag changed')
                tables[kind]=rows
                sources.append({'export_url':EXPORT,'member':name,'columns':columns,'rows':len(rows),
                                'member_sha256':hashlib.sha256(content).hexdigest(),'encoding':'cp1252',
                                'source_data_lines':len(lines)-1,'held_csv_rows':held})
    except (BadZipFile,UnicodeError,csv.Error,ValueError,InvalidOperation,RuntimeError):
        raise SourceError('PA invalid official export; last audit preserved') from None
    filers=tables['filer'];expenses=tables['expense'];byid={r['CampaignfinanceID']:r for r in filers}
    if len(byid)!=len(filers):raise SourceError('PA duplicated report identity')
    unmatched=[r for r in expenses if r['CampaignFinanceID'] not in byid]
    matched=[r for r in expenses if r['CampaignFinanceID'] in byid]
    if any(any(r[k]!=byid[r['CampaignFinanceID']][k] for k in ['FILERID','EYEAR','SubmittedDate','CYCLE']) for r in matched):
        raise SourceError('PA expense/filer report mismatch')
    date_status=Counter();valid=[]
    for r in expenses:
        try:
            value=datetime.strptime(r['EXPDATE'],'%Y%m%d').date()
            if value>checked:date_status['future_date']+=1
            else:date_status['valid_date']+=1;valid.append(value.isoformat())
        except ValueError:date_status['missing_date' if not r['EXPDATE'] else 'invalid_date']+=1
    return {'schema':'usa_governor_finance_audit_v1','state':'PA','cycle':cycle,'captured_at':checked_at,
        'status':'collected_normalization_held','source_url':SOURCE,'sources':sources,
        'zip_sha256':hashlib.sha256(raw).hexdigest(),'input_records':sources[1]['source_data_lines'],
        'parsed_expense_records':len(expenses),'filer_report_records':len(filers),
        'source_filer_data_lines':sources[0]['source_data_lines'],
        'expenses_without_valid_filer_report':len(unmatched),
        'current_governor_target_records':None,'export_scope':'annual_general_expenses_not_candidate_independent_expenditures',
        'all_state_ie_coverage':'not_established','source_total_count':None,'completeness':'source_export_only_no_filing_universe_reconciliation',
        'last_reported_submission_on':max(r['SubmittedDate'] for r in expenses),
        'report_cycle_counts':dict(Counter(r['CYCLE'] for r in expenses)),
        'amended_filer_reports':sum(r['AMMEND']=='Y' for r in filers),
        'expenses_in_amended_reports':sum(byid[r['CampaignFinanceID']]['AMMEND']=='Y' for r in matched),
        'expense_date_status':dict(date_status),'last_valid_reported_expense_on':max(valid) if valid else None,
        'negative_expense_rows':sum(Decimal(r['EXPAMT'])<0 for r in expenses),
        'identical_row_extra_occurrences':sum(n-1 for n in Counter(tuple(r[k] for k in EXPENSE) for r in expenses).values()),
        'official_field_description_url':README,'candidate_ie_form_url':FORM,
        'candidate_audits':[{'candidate_id':c['candidate_id'],'name':c['name'],'party':c['party'],
            'reported_rows':None,'support_cents':None,'oppose_cents':None,'amount_status':'target_and_direction_not_present'} for c in roster],
        'hold_reasons':['general_expenses_not_ie','target_and_support_oppose_not_present',
                        'transaction_id_and_amendment_lineage_not_established','expense_date_anomalies_held','invalid_csv_quoting_rows_held','unmatched_filer_rows_held'],
        'limitations_ko':['공식2026 연간 ZIP의 신고자·일반 비용 두 표만 대조한 감사. ZIP 연도는 신고 기준이고 본선 지출 범위나 IE 전수 수집을 뜻하지 않습니다.',
            '비용 수취인·목적·신고자의 OFFICE는 지지/반대 대상 후보가 아닙니다. 후보 캠프 일반 지출도 외부 독립지출에 합산하지 않습니다.',
            '정정 신고 건수는 별도 필드입니다. 거래ID/대체 관계가 없어 원신고·정정과 동일 행을 합산하거나 임의 중복 삭제하지 않습니다.',
            '따옴표 문법 오류 행은 엄격한 CSV 검사를 통과하지 못해 해석하지 않고 줄 번호/지문만 보존합니다. 미검증 신고자 연결도 보류합니다.',
            '누락·잘못된 날짜·미래 지출일은 감사 건수만 기록하고 금액을 후보에게 귀속하지 않습니다. 마지막 신고일과 지급일을 분리합니다.',
            '후보·S/O를 담는 DSEB-505 개별 신고 원문과 정정 관계 확보가 후속 과제입니다. 일반 비용 ZIP만으로 후보별 주지사 금액을 계산할 수 없습니다.']}


def collect_audit(cycle, roster, opener=urlopen):
    if cycle!=2026:raise SourceError('PA unreviewed cycle')
    with opener(Request(EXPORT,headers={'User-Agent':'ElectionWatch/1.0 public-source-review'}),timeout=45) as response:
        if response.status!=200 or response.geturl()!=EXPORT:raise SourceError('PA unexpected export redirect/response')
        raw=response.read(55*1024*1024+1)
    return summarize_export(raw,cycle,roster,datetime.now(timezone.utc).isoformat())
