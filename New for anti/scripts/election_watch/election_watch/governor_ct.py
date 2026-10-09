"""Bounded public SEEC search audit; search rows are not normalized IE totals."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import urlencode, urljoin
from urllib.request import build_opener, HTTPCookieProcessor, Request
from .polls import require

URL='https://seec.ct.gov/eCrisReporting/SearchingIndependentExpenditure.aspx'
HEADERS=['Root Expenditure ID','Committee/Entity Name','Report Type','Document Type','Payee',
    'Received Date','File Year','Period Covered Start Date','Period Covered End Date','Amount',
    'Form Section','Supporting Candidates','Supporting Offices','Opposing Candidates','Opposing Offices','Data Source']


class SearchForm(HTMLParser):
    def __init__(self):
        super().__init__(); self.fields={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs); name=a.get('name'); kind=a.get('type')
        if tag=='input' and name and (kind in ('hidden','text') or
                kind in ('checkbox','radio') and 'checked' in a):
            self.fields[name]=a.get('value','on' if kind=='checkbox' else '')


class SearchGrid(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.rows=[]; self.row=None; self.cell=None; self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='table' and a.get('id')=='ctl00_ContentPlaceHolder1_gvSearchResult':
            require(not self.rows and not self.active,'duplicate CT search grid'); self.active=True
        if not self.active:return
        if tag=='tr':self.row=[];self.links=[]
        if tag in ('td','th'):self.cell=[]
        if tag=='br' and self.cell is not None:self.cell.append(' ')
        if tag=='a' and a.get('href','').startswith('Data/Attachment/'):
            self.links.append(urljoin(URL,a['href']))
    def handle_data(self,text):
        if self.active and self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if not self.active:return
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append((self.row,self.links));self.row=None
        if tag=='table':self.active=False


def summarize_search(html,cycle,roster,captured_at):
    require(cycle==2026 and roster and all(c['state']=='CT' and c['office']=='G' for c in roster),
            'CT audit roster/cycle mismatch')
    require('Filed Year: 2026' in html and 'Office: Governor' in html and 'Records Per Page: 100' in html,
            'CT search criteria changed')
    pages=re.search(r'id="ctl00_ContentPlaceHolder1_lblPageSummary">\s*of (\d+)',html)
    require(pages and int(pages[1])==1,'CT search needs pagination; previous audit preserved')
    grid=SearchGrid();grid.feed(html);grid.close()
    require(len(grid.rows)>1 and grid.rows[0][0]==HEADERS and len(grid.rows)<=101,
            'CT result grid empty/schema changed/budget exceeded')
    records=[];today=date.fromisoformat(captured_at[:10])
    for cells,links in grid.rows[1:]:
        require(len(cells)==len(HEADERS) and len(links)==1,'CT malformed search row')
        row=dict(zip(HEADERS,cells))
        require(row['File Year']=='2026' and row['Root Expenditure ID'].isdigit()
                and row['Document Type'] in ('Original','Amendment'), 'CT filing identity/year changed')
        try:
            received=datetime.strptime(row['Received Date'],'%m/%d/%Y').date()
            start=datetime.strptime(row['Period Covered Start Date'],'%m/%d/%Y').date()
            end=datetime.strptime(row['Period Covered End Date'],'%m/%d/%Y').date()
            amount=Decimal(row['Amount'].removeprefix('$').replace(',',''))
        except (ValueError,InvalidOperation):raise ValueError('CT date/amount invalid') from None
        require(date(2025,1,1)<=received<=today and start<=end and amount.is_finite()
                and amount==amount.quantize(Decimal('.01')), 'CT date/amount outside audit scope')
        records.append({'reported_root_expenditure_id':row['Root Expenditure ID'],
            'committee':row['Committee/Entity Name'],'report_type':row['Report Type'],
            'document_type':row['Document Type'],'received_date':received.isoformat(),
            'file_year':2026,'period_start':start.isoformat(),'period_end':end.isoformat(),
            'reported_amount_cents':int(amount*100),'form_section':row['Form Section'],
            'supporting_candidates':row['Supporting Candidates'],'supporting_offices':row['Supporting Offices'],
            'opposing_candidates':row['Opposing Candidates'],'opposing_offices':row['Opposing Offices'],
            'report_url':links[0],'normalized_candidate_ie_amount':None,
            'hold_reason':'report_type_section_independence_stage_and_amendment_lineage_not_verified'})
    key=lambda s:' '.join(s.casefold().split())
    candidates=[]
    for c in roster:
        names={key(n) for n in [c['name'],*c.get('reported_name_aliases',[])]}
        matched=[r for r in records if any(key(r[direction+'_candidates']) in names
            and r[direction+'_offices']=='Governor' for direction in ('supporting','opposing'))]
        candidates.append({'candidate_id':c['candidate_id'],'name':c['name'],'party':c['party'],
            'reported_rows':len(matched),'support_cents':None,'oppose_cents':None,
            'amount_status':'search_target_match_only_independence_and_amendments_unverified'})
    return {'schema':'usa_governor_finance_audit_v1','state':'CT','cycle':cycle,
        'captured_at':captured_at,'status':'collected_normalization_held','source_url':URL,
        'sources':[{'search_url':URL,'html_sha256':hashlib.sha256(html.encode()).hexdigest(),
            'search':{'filing_year':2026,'office':'Governor','maximum_rows':100,'show_history':False},
            'result_pages':1}], 'input_records':len(records), 'records':records,
        'current_governor_target_records':sum(c['reported_rows'] for c in candidates),
        'candidate_audits':candidates,'candidate_amounts_available':False,
        'last_search_received_date':max(r['received_date'] for r in records),
        'hold_reasons':['search_includes_lieutenant_governor_and_prior_primary_candidates',
            'ordinary_paid_and_unpaid_expense_sections_are_not_proof_of_independent_expenditure',
            'zero_root_ids_and_amendment_lineage_unverified','primary_general_election_stage_not_verified'],
        'limitations_ko':['공식 공개 검색 결과 감사이며 후보별 독립지출 합계가 아닙니다.',
            'Governor 검색에 부지사·과거 경선 후보와 일반 비용도 반환됩니다. 명칭·지지 칼럼만으로 금액을 합산하지 않습니다.',
            '2026 신고연도는 2025 수신 공시도 포함합니다. 검색일은 공시일이 아니며 본선·경선 단계는 미확인입니다.',
            '정정 연결과 독립성 미확인으로 후보별 지지·반대액은 null. FEC Super PAC O 지출과 구분합니다.']}


def collect_audit(cycle,roster,opener=None):
    opener=opener or build_opener(HTTPCookieProcessor()).open
    def fetch(request):
        with opener(request,timeout=30) as response:
            require(response.status==200 and response.geturl()==URL,'CT search response redirected')
            body=response.read(3*1024*1024+1)
        require(len(body)<=3*1024*1024,'CT search response exceeds budget')
        return body.decode('utf-8')
    headers={'User-Agent':'ElectionWatch/1.0 public-filings-audit'}
    form=SearchForm();form.feed(fetch(Request(URL,headers=headers)));form.close()
    require('__VIEWSTATE' in form.fields and '__VIEWSTATEGENERATOR' in form.fields,'CT search state missing')
    fields=form.fields
    require(fields.get('ctl00$ContentPlaceHolder1$rblShowHistory')=='0','CT search history default changed')
    fields.update({'ctl00$ContentPlaceHolder1$lstFILE_YEAR':str(cycle),
        'ctl00$ContentPlaceHolder1$Offices':'Governor','ctl00$ContentPlaceHolder1$lstNoOfRecords':'100',
        'ctl00$ContentPlaceHolder1$lstReportType1':'','ctl00$ContentPlaceHolder1$btnSearch':'Search'})
    html=fetch(Request(URL,data=urlencode(fields).encode(),
        headers={**headers,'Content-Type':'application/x-www-form-urlencoded'}))
    return summarize_search(html,cycle,roster,datetime.now(timezone.utc).isoformat())
