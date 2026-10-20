"""Opted-in co/efficient public release tables; never forecasts or blanket admission."""
from datetime import date,datetime,timezone
import re
import hashlib
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from .polls import require,digest
from .poll_source_discovery import TableParser
from .poll_quality import answer_correction_fingerprint,review_fingerprint
ADAPTER='coefficient_public_html_v1'
INDEX='https://battlegrounds.coefficient.org/'

def validate_contract(entry):
    from .superpac import STATES
    state=entry.get('state','');rid=entry.get('race_id','')
    require(state in STATES and rid in (f'USA:{state}:senate',f'USA:{state}:governor')
        and entry.get('index_url')==INDEX and entry.get('release_url')==INDEX+state.lower()+'/'
        and entry.get('pollster')=='co/efficient' and entry.get('pollster_group')=='coefficient',
        'unreviewed coefficient source contract')

def tree(text):
    p=TableParser();p.feed(text);p.close();return p.root

def document(url,opener):
    u=urlparse(url)
    require(u.scheme=='https' and u.hostname=='battlegrounds.coefficient.org' and not u.query
        and not u.fragment and not u.username and not u.password
        and (u.path=='/' or re.fullmatch('/[a-z]{2}/',u.path)), 'unreviewed coefficient URL')
    with opener(Request(url,headers={'User-Agent':'ElectionPollPipeline/3.0 public-primary-tables'}),timeout=20) as response:
        require(response.status==200 and response.geturl()==url,'coefficient response/redirect')
        body=response.read(3*1024*1024+1)
    require(len(body)<=3*1024*1024,'coefficient document oversized')
    text=body.decode('utf-8');require('<html' in text.lower() and '<body' in text.lower(),'coefficient HTML format')
    return tree(text),{'url':url,'sha256':hashlib.sha256(body).hexdigest(),'status':'unchanged','checked_at':datetime.now(timezone.utc).isoformat()}

def release_date(index,entry,as_of):
    links=[n for n in index.nodes('a') if urljoin(INDEX,n.attrs.get('href',''))==entry['release_url']]
    require(len(links)==1,'coefficient release link missing/ambiguous')
    match=re.search(r'([A-Z][a-z]+ \d{1,2}, 2026)',links[0].text())
    require(match,'coefficient exact release day missing')
    published=datetime.strptime(match[1],'%B %d, %Y').date()
    require(published<=date.fromisoformat(as_of),'future coefficient release')
    return published.isoformat()

def extract(root,entry,race,published,as_of):
    from .superpac import STATES
    # The source contract state must agree with its explicit article heading.
    headings=list(root.nodes('h1')); require(len(headings)==1,'coefficient heading missing')
    require(headings[0].text().split('·')[0].strip()==race['subject'].removeprefix('2026 '), 'coefficient geography mismatch')
    methods=[p.text() for p in root.nodes('p') if 'meth-p' in p.attrs.get('class','').split()]
    require(len(methods)==1,'coefficient methodology missing')
    method=methods[0]
    m=re.search(r'co/efficient surveyed ([\d,]+) likely general election voters in (.+?) on ([A-Z][a-z]+) (\d{1,2})[-–](\d{1,2}), (2026)',method)
    require(m and m[2]==race['subject'].removeprefix('2026 ') and 'mobile text responses and landline interviews' in method
        and 'Results are weighted on age, gender, race, education, congressional district, and community type' in method,
        'coefficient method/population changed')
    n=int(m[1].replace(',',''));month=datetime.strptime(m[3],'%B').month
    start=date(2026,month,int(m[4])).isoformat();end=date(2026,month,int(m[5])).isoformat()
    require(n>0 and start<=end<=published<=as_of and end<'2026-11-03','coefficient field dates invalid')
    vitals=[p for p in root.nodes('p') if 'vitals' in p.attrs.get('class','').split()]
    require(len(vitals)==1,'coefficient header missing')
    header={}
    for span in vitals[0].children:
        if not hasattr(span,'tag') or span.tag!='span':continue
        labels=list(span.nodes('b'));require(len(labels)==1,'coefficient header label changed')
        key=labels[0].text();require(key not in header,'coefficient duplicate header')
        header[key]=span.text()[len(key):].strip()
    require(header.get('Sample','').replace(',','')==f'{n} likely general election voters'
        and header.get('Fielded','').replace('–','-')==f'{m[3]} {m[4]}-{m[5]}, 2026'
        and header.get('Mode')=='Mobile text responses and landline interviews'
        and header.get('Released')==datetime.fromisoformat(published).strftime('%B %Y'),
        'coefficient header/method/index conflict')
    precision=re.search(r'margin of error is ±([\d.]+) percentage points',method)
    require(precision and 0<float(precision[1])<100 and header.get('MoE')==f'±{precision[1]}%', 'coefficient precision missing/conflicting')
    require(any(p.text()=='Independent public polling. Not sponsored by any candidate committee, party committee or other independent expenditure.' for p in root.nodes('p')),
        'coefficient commissioning statement changed')
    office='U.S. Senate' if race['office']=='senate' else 'Governor of '+race['subject'].removeprefix('2026 ')
    expected=f'If the November 3rd general election for {office} were held today, who would you vote for?'
    questions=[q for q in root.nodes('details') if any(re.sub(r'^Q\d+\s*','',s.text())==expected for s in q.nodes('summary'))]
    require(len(questions)==1,'coefficient ordinary ballot question missing/ambiguous')
    q=questions[0];answers=[];other=[];all_values=[]
    for row in q.nodes('div'):
        if 'bar-row' not in row.attrs.get('class','').split():continue
        labels=[s.text() for s in row.nodes('span') if s.attrs.get('class')=='bar-k']
        numbers=[s.text() for s in row.nodes('span') if 'bar-v' in s.attrs.get('class','').split()]
        require(len(labels)==len(numbers)==1 and re.fullmatch(r'\d+(?:\.\d+)?%',numbers[0]),'coefficient answer cell changed')
        value=float(numbers[0][:-1]);require(0<=value<=100,'coefficient percentage invalid');all_values.append(value)
        label=labels[0]
        if label in ('Undecided','Someone else','Other'):other.append({'label':label,'pct':value});continue
        parts=label.split(', ',1);require(len(parts)==2,'coefficient candidate party missing')
        name,party=parts
        require(name in race['candidates'],'coefficient candidate identity needs review')
        parties={'Republican':'REP','Democrat':'DEM','Democratic':'DEM','Nonpartisan':'IND','Independent':'IND',
            'Libertarian':'LIB','Legal Marijuana Now Party':'OTH','Nebraska Working People Party':'OTH','America First Party Nebraska':'OTH'}
        require(party in parties and race['candidates'][name]['party']==parties[party], 'coefficient candidate party mismatch')
        answers.append({'choice':name,'pct':value})
    require(len(answers)>=2 and len({a['choice'] for a in answers})==len(answers)
        and set(race['required_candidates'])<={a['choice'] for a in answers}
        and 98<=sum(all_values)<=102,'coefficient incomplete candidate ballot')
    return start,end,n,answers,other,method,float(precision[1]),expected

def collect_entry(entry,policy,as_of,opener=urlopen):
    index,idoc=document(INDEX,opener);published=release_date(index,entry,as_of)
    root,rdoc=document(entry['release_url'],opener);race=policy['races'][entry['race_id']]
    require(race['state']==entry['state'] and race['office']==entry['race_id'].rsplit(':',1)[1], 'coefficient race mismatch')
    start,end,n,answers,other,method,moe,prompt=extract(root,entry,race,published,as_of)
    docs=[idoc,rdoc];checked=rdoc['checked_at'];rid=entry['race_id']
    raw={'id':'primary-html-coefficient-'+digest({'race_id':rid,'start':start,'end':end,'question':prompt})[:20],
        'subject':race['subject'],'poll_type':race['poll_type'],'seat_name':race.get('seat_name'),
        'pollster':entry['pollster'],'start_date':start,'end_date':end,'created_at':published,'sample_size':n,
        'population':'lv','answers':answers,'url':entry['release_url'],'sponsors':[],'internal':False,'partisan':None}
    review={'reviewed_on':checked[:10],'review_method':'structured_primary_html_table_v1',
        'provider_record_sha256':answer_correction_fingerprint(raw),'primary_supplement_record_sha256':answer_correction_fingerprint(raw),
        'sources':[INDEX,entry['release_url']],'primary_documents':[{'url':d['url'],'sha256':d['sha256']} for d in docs],
        'primary_toplines':{a['choice']:a['pct'] for a in answers},'question_sample_n':n,
        'admission':{'pollster':entry['pollster'],'provider_url':raw['url'],'group':'coefficient','methodology_url':raw['url'],
            'source_role':'pollster_primary','signal_eligible':False,'signal_exclusion_reasons':['automated_release_question_context_review_pending']},
        'ballot_format':'ordinary_named_candidate_ballot','disclosure_review':{'population':'LV','sample_n':n,
            'field_dates':[start,end],'primary_release_date':published,'release_date_source':INDEX,
            'question_wording_checked':True,'question':prompt,'question_scope':rid,'other_responses':other,
            'methodology':method,'publication_date_status':'publisher_index_exact_date'},
        'reported_precision':{'kind':'publisher_reported_margin_of_error','half_width_pp':moe,'scope':'publisher statewide sample'},
        'missing_fields':['commissioner_identity','question_order_context_review','historical_accuracy_rating'],
        'limitations_ko':'기관 공개 목록 날짜와 본문 방법론·후보 표 자동 추출. 새 발표는 문항 순서·의뢰자 검토 전 참고 전용. 정확도·승률 아님.'}
    observation={'id':raw['id'],'race_id':rid,'pollster_group':'coefficient','field_start':start,'field_end':end,
        'population':'lv','sample_n':n,'answers':[{'name':a['choice'],'pct':a['pct'],'party':race['candidates'][a['choice']]['party']} for a in answers]}
    review['snapshot_sha256']=review_fingerprint(observation)
    capture={'status':'primary_documents_rechecked','original_reviewed_on':review['reviewed_on'],'checked_at':checked,
        'documents':docs,'provider_duplicate_ids':[],'reviewed_replaced_provider_ids':[], 'extraction_method':'structured_primary_html_table_v1'}
    raw['primary_source_capture']=capture
    return [{'id':raw['id'],'state':entry['state'],'kind':'html_table','contract_id':entry['id'],'contract_sha256':digest(entry),
        'record':raw,'quality_review':review,**capture}],[]
