"""Florida public ECO expenditure audit; no candidate IE totals are inferred."""
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import hashlib
import io
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .superpac import SourceError

SEARCH = 'https://dos.elections.myflorida.com/campaign-finance/expenditures/'
EXPORT = 'https://dos.elections.myflorida.com/cgi-bin/expend.exe'
HEADERS = ['Candidate/Committee', 'Date', 'Amount', 'Payee Name', 'Address',
           'City State Zip', 'Purpose', 'Type']
LIMIT = 1000


def query_fields(cycle):
    if cycle != 2026:
        raise SourceError('Florida only reviewed 2026 public query supported')
    # This is the public read-only expenditure form, never EFS filing/login.
    return {'election':'20261103-GEN','search_on':'4','ComName':'','ComNameSrch':'2',
        'committee':'ECO','CanFName':'','CanLName':'','CanNameSrch':'2','office':'All',
        'cdistrict':'','cgroup':'','party':'All','cfname':'','clname':'','namesearch':'2',
        'ccity':'','cstate':'','czipcode':'','cpurpose':'','cdollar_minimum':'',
        'cdollar_maximum':'','rowlimit':str(LIMIT),'csort1':'DAT','csort2':'CAN',
        'cdatefrom':'','cdateto':'','queryformat':'2','Submit':'Submit'}


class PublicForm(HTMLParser):
    def __init__(self):
        super().__init__();self.forms=[];self.fields=set();self.options=set()
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='form':self.forms.append((attrs.get('method','').lower(),attrs.get('action')))
        if tag in ('input','select'):self.fields.add(attrs.get('name'))
        if tag=='option':self.options.add(attrs.get('value'))


def validate_form(html, cycle):
    fields=query_fields(cycle);form=PublicForm();form.feed(html)
    if ('post','/cgi-bin/expend.exe') not in form.forms or not set(fields)<=form.fields or not {'ECO',fields['election']}<=form.options:
        raise SourceError('Florida public form schema changed; last audit preserved')


def parse_export(raw, cycle, checked_at):
    if not raw or len(raw)>3*1024*1024 or raw.lstrip().startswith(b'<'):
        raise SourceError('Florida empty/error/oversized export; zero not inferred')
    try:
        # The official legacy form/export contains Windows-1252 text.
        reader=csv.DictReader(io.StringIO(raw.decode('windows-1252')), delimiter='\t')
        if reader.fieldnames != HEADERS:
            raise SourceError('Florida public TSV schema changed')
        rows=list(reader)
        if not rows or len(rows)>=LIMIT:
            raise SourceError('Florida missing or potentially row-limited export; last audit preserved')
        for row in rows:
            if set(row)!=set(HEADERS) or any(v is None for v in row.values()):
                raise SourceError('Florida malformed TSV row')
            day=datetime.strptime(row['Date'],'%m/%d/%Y').date()
            if day.year not in (cycle-1,cycle) or day.isoformat()>checked_at[:10]:
                raise SourceError('Florida outside reviewed expenditure period')
            value=Decimal(row['Amount'])
            if not value.is_finite() or value!=value.quantize(Decimal('.01')):
                raise SourceError('Florida invalid reported monetary value')
            if not row['Candidate/Committee'].endswith(' (ECO)') or not row['Type']:
                raise SourceError('Florida changed committee scope/type')
    except (UnicodeError,csv.Error,ValueError,InvalidOperation):
        raise SourceError('Florida invalid public TSV') from None
    return rows


def summarize_export(cycle, raw, roster, checked_at):
    fields=query_fields(cycle)
    if not roster or len({c['candidate_id'] for c in roster})!=len(roster):
        raise SourceError('Florida reviewed governor roster missing/ambiguous')
    rows=parse_export(raw,cycle,checked_at)
    dates=[datetime.strptime(r['Date'],'%m/%d/%Y').date().isoformat() for r in rows]
    return {'schema':'usa_governor_finance_audit_v1','state':'FL','cycle':cycle,
        'captured_at':checked_at,'status':'collected_normalization_held','source_url':SEARCH,
        'sources':[{'export_url':EXPORT,'query':fields,'columns':HEADERS,'rows':len(rows),
            'tsv_sha256':hashlib.sha256(raw).hexdigest(),'encoding':'windows-1252'}],
        'input_records':len(rows),'current_governor_target_records':None,
        'export_scope':'ECO_general_expenditures_only_not_verified_independent_expenditures',
        'all_state_ie_coverage':'not_established', 'row_limit':LIMIT,
        'source_total_count':None,'completeness':'no_source_total_or_filing_reconciliation',
        'first_reported_expenditure_on':min(dates),'last_reported_expenditure_on':max(dates),
        'report_year_counts':dict(Counter(d[:4] for d in dates)),
        'reported_types':dict(Counter(r['Type'] for r in rows)),
        'reported_committees':dict(Counter(r['Candidate/Committee'] for r in rows)),
        'identical_row_occurrences':sum(n for n in Counter(tuple(r[h] for h in HEADERS) for r in rows).values() if n>1),
        'candidate_audits':[{'candidate_id':c['candidate_id'],'name':c['name'],'party':c['party'],
            'reported_rows':None,'support_cents':None,'oppose_cents':None,
            'amount_status':'target_and_direction_not_present'} for c in roster],
        'hold_reasons':['eco_export_not_independent_expenditure_classification',
            'target_candidate_office_and_support_oppose_not_present',
            'transaction_identity_and_amendment_lineage_missing','full_public_filing_reconciliation_required'],
        'limitations_ko':['공식 공개 ECO 지출 검색 TSV의 제한 범위 수집 감사입니다. PAC·독립지출 신고자 전체나 주지사 지출 전수 수집이 아닙니다.',
            'ECO 조직의 일반 지출을 후보별 독립지출로 간주하지 않습니다. 후보 대상·지지/반대·거래ID·정정 관계가 없어 금액과 대상 건수는 null입니다.',
            '목적 문구·단체 이름·금액·Type(MON/ECC/REF)으로 후보 지지·반대를 추정하지 않습니다. 음수 반환도 일반 지출 자료에 보존하고 합산하지 않습니다.',
            '날짜는 지급 내역 날짜이며 최신 신고일·본선 기준일이 아닙니다. 검색 선거 선택만으로 경선·본선 구분을 확정하지 않습니다.',
            '1000행 제한 도달·빈 응답·HTML 오류·스키마 변경·조회 실패 시 기존 감사와 금융 파일의 원래 기준일을 보존합니다.']}


def collect_audit(cycle, roster, opener=urlopen):
    fields=query_fields(cycle)
    def request(url,data=None):
        with opener(Request(url,data=data,headers={'User-Agent':'ElectionWatch/1.0 public-source-review'}),timeout=30) as response:
            if response.status!=200 or response.geturl()!=url:
                raise SourceError('Florida unexpected public source response/redirect')
            raw=response.read(3*1024*1024+1)
            if len(raw)>3*1024*1024:
                raise SourceError('Florida export exceeded size budget')
            return raw
    validate_form(request(SEARCH).decode('windows-1252'),cycle)
    raw=request(EXPORT,urlencode(fields).encode())
    return summarize_export(cycle,raw,roster,datetime.now(timezone.utc).isoformat())
