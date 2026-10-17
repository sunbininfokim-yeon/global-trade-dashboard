"""Opted-in publisher HTML tables -> existing audited poll observation contract.

Contracts are state inputs; transport/parser code is shared. No JS execution,
challenge bypass, inferred values or aggregator averages. Failed sources retain
last valid rows at their ORIGINAL evidence dates as reference only.
"""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import hashlib
import math
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from .polls import digest, require
from .poll_quality import answer_correction_fingerprint, review_fingerprint
from .poll_source_discovery import TableParser, Node

MAX_BYTES=3*1024*1024
ADAPTER='cnu_wason_public_html_v1'


def contracts(snapshot, as_of, states=None):
    require(snapshot['schema']=='usa_poll_html_table_sources_v1' and snapshot['cycle']==2026,
            'HTML source catalog schema/cycle')
    seen=set(); selected=[]
    for entry in snapshot['records']:
        require(entry['id'] not in seen, 'duplicate HTML source contract');seen.add(entry['id'])
        require(entry['adapter']==ADAPTER and entry['state']=='VA' and
                re.fullmatch(r'USA:VA:house:\d{2}',entry['race_id']) and
                entry['index_url']=='https://cnu.edu/wason/surveys/' and
                entry['pollster']=='Christopher Newport University' and
                entry['pollster_group']=='cnu_wason', 'unreviewed HTML source contract')
        # A newly approved source must not deadlock an older capture/replay.
        # It is unavailable before approval, not permission to advance dates.
        if date.fromisoformat(entry['reviewed_on'])>date.fromisoformat(as_of):continue
        if states is None or entry['state'] in states:selected.append(entry)
    return selected


def document(url, opener=urlopen):
    # URLs come only from the verified institution and its directly linked
    # PUBLIC spreadsheet document. Never fetch arbitrary aggregator links.
    u=urlparse(url)
    allowed=(u.scheme=='https' and not u.username and not u.password and not u.fragment and (
        u.hostname=='cnu.edu' and u.path.startswith('/wason/surveys/') or
        u.hostname=='docs.google.com' and re.fullmatch(r'/spreadsheets/d/e/[A-Za-z0-9_-]+/pubhtml(?:/sheet)?',u.path)))
    require(allowed,'unreviewed HTML document URL')
    with opener(Request(url,headers={'User-Agent':'ElectionPollPipeline/3.0 public-primary-tables'}),timeout=20) as response:
        require(response.status==200 and response.geturl()==url,'HTML source response/redirect')
        body=response.read(MAX_BYTES+1)
    require(len(body)<=MAX_BYTES,'HTML source oversized')
    text=body.decode('utf-8');require('<html' in text.lower() and '<body' in text.lower(),'HTML source format')
    return text,{'url':url,'sha256':hashlib.sha256(body).hexdigest(),'status':'unchanged',
                 'checked_at':datetime.now(timezone.utc).isoformat()}


def parser(text):
    result=TableParser();result.feed(text);result.close();return result


def article_links(text, entry, as_of):
    root=parser(text).root; links=set()
    for node in root.nodes('a'):
        url=urljoin(entry['index_url'],node.attrs.get('href',''));u=urlparse(url)
        m=re.fullmatch(r'/wason/surveys/archive/(2026-\d{2}-\d{2})\.html',u.path)
        if u.scheme=='https' and u.hostname=='cnu.edu' and m:
            if date.fromisoformat(as_of)-timedelta(days=60)<=date.fromisoformat(m[1])<=date.fromisoformat(as_of):links.add(url)
    require(links,'no current dated HTML source links')
    return sorted(links,reverse=True)[:2]


def article_metadata(text, url, entry):
    root=parser(text).root;mains=list(root.nodes('main'));require(len(mains)==1,'missing primary article')
    main=mains[0]
    require(not re.search(r'commissioned|sponsored|funded|on behalf|client',main.text(),re.I),'new commissioning disclosure needs review')
    paragraphs=[p.text() for p in main.nodes('p')]
    methods=[p for p in paragraphs if 'interviews of registered' in p and 'likely general election voters' in p]
    require(len(methods)==1,'missing or changed HTML methodology')
    method=methods[0]
    district=int(entry['race_id'].rsplit(':',1)[1]);ordinal={1:'first',2:'second',3:'third',4:'fourth',5:'fifth',6:'sixth',7:'seventh',8:'eighth',9:'ninth',10:'tenth',11:'eleventh'}.get(district)
    require(ordinal and f'registered {ordinal} congressional district voters' in method,
            'HTML population geography mismatch')
    n=re.search(r'based on (\d+) interviews',method);parts=re.search(r'including (\d+) on landline and (\d+) on cell phone',method)
    require(n and parts and int(n[1])==int(parts[1])+int(parts[2]),'HTML sample size/mode mismatch')
    dates=re.search(r'conducted ([A-Z][a-z]+)\.? (\d{1,2})[-–](\d{1,2}), (2026)',method)
    require(dates,'unsupported HTML field dates')
    month=datetime.strptime(dates[1][:3],'%b').month
    start=date(2026,month,int(dates[2])).isoformat();end=date(2026,month,int(dates[3])).isoformat()
    published=url.rsplit('/',1)[1].removesuffix('.html');require(start<=end<=published,'HTML field/release date order')
    precision=re.search(r'margin of error for the whole survey is \+/-([\d.]+)% at the (\d+)% level',method)
    require(precision and 'Live calling was conducted' in method and 'weighted' in method,'incomplete primary methods')
    frames=[n.attrs['src'] for n in main.nodes('iframe') if n.attrs.get('title')=='Survey Questions' and n.attrs.get('src')]
    require(len(frames)==1,'missing/ambiguous published question table')
    return {'sample_n':int(n[1]),'start':start,'end':end,'published':published,'method':method,
            'moe':float(precision[1]),'confidence':int(precision[2]),'question_index':frames[0]}


def question_links(text, index_url):
    # Decode string escapes, never execute publisher/Google scripts.
    links=[]
    for name, value in re.findall(r'items\.push\(\{name: "([^"]+)", pageUrl: "([^"]+)"',text):
        value=value.replace('\\x3d','=')
        while '\\/' in value:value=value.replace('\\/','/')
        original=urlparse(index_url);u=urlparse(value)
        require(u.scheme=='https' and u.hostname=='docs.google.com' and
                u.path==original.path+'/sheet' and re.fullmatch(r'headers=false&gid=-?\d+',u.query),
                'unreviewed published table link')
        links.append((name,value))
    require(0<len(links)<=20,'missing/oversized published question tabs')
    # Only the ordinary House ballot, not the Q4a Senate district subsample.
    return [(name,url) for name,url in links if name=='Q4']


def question(text, race):
    root=parser(text).root
    tables=[t for t in root.nodes('table') if 'waffle' in t.attrs.get('class','').split()]
    require(len(tables)==1,'missing/ambiguous published HTML table')
    cells=[[c.text() for c in r.children if isinstance(c,Node) and c.tag in ('td','th')]
           for r in tables[0].nodes('tr')]
    titles=[r[1] for r in cells if len(r)==2 and r[1].startswith('Q4:')]
    require(len(titles)==1 and 'Congressional District' in titles[0] and 'held TODAY' in titles[0]
            and 'RANDOMIZE' in titles[0] and 'Senate' not in titles[0], 'unreviewed HTML ballot question')
    require(not re.search(r'ask if|only those|among |after hearing|informed|leaner|if q\d',titles[0],re.I),
            'conditional/informed HTML ballot needs review')
    district=re.search(r'\b(\d+)(?:st|nd|rd|th) Congressional District',titles[0])
    require(district and int(district[1])==int(race['district']),'HTML ballot district mismatch')
    headers=[r for r in cells if len(r)>3 and r[1]=='' and r[2]=='All']
    require(len(headers)==1,'missing primary All column')
    answers=[];other={}
    for r in cells:
        if len(r)<3:continue
        match=re.fullmatch(r'(.+), the (Democrat|Republican|Independent)',r[1])
        if match:
            name=match[1];require(name in race['candidates'],'unreviewed HTML candidate identity')
            party={'Democrat':'DEM','Republican':'REP','Independent':'IND'}[match[2]]
            require(race['candidates'][name]['party']==party,'HTML candidate party mismatch')
            value=float(r[2]);require(0<=value<=100,'invalid HTML percentage')
            answers.append({'choice':name,'pct':value})
        elif r[1] in ('Someone else','Undecided (vol)','Don’t know/ref (vol)'):
            require(r[1] not in other,'duplicate HTML response category')
            other[r[1]]=float(r[2]);require(math.isfinite(other[r[1]]) and 0<=other[r[1]]<=100,'invalid HTML response percentage')
    canonical=lambda n:race['candidates'].get(n,{}).get('canonical_name',n)
    require(len(answers)>=2 and len({canonical(a['choice'])for a in answers})==len(answers)
            and {canonical(n)for n in race['required_candidates']}<={canonical(a['choice'])for a in answers},
            'HTML full reviewed field missing')
    require(set(other)=={'Someone else','Undecided (vol)','Don’t know/ref (vol)'},'missing HTML response categories')
    require(98<=sum(a['pct']for a in answers)+sum(other.values())<=102,'HTML response totals changed')
    return answers,titles[0],other


def collect_entry(entry, policy, as_of, opener=urlopen):
    race=policy['races'][entry['race_id']]
    index,index_doc=document(entry['index_url'],opener);records=[];failures=[]
    for url in article_links(index,entry,as_of):
        try:
            article,article_doc=document(url,opener);meta=article_metadata(article,url,entry)
            qindex,qindex_doc=document(meta['question_index'],opener)
            links=question_links(qindex,meta['question_index']);require(len(links)==1,'ordinary House Q4 not available')
            qurl=links[0][1];qtext,qdoc=document(qurl,opener);answers,title,other=question(qtext,race)
            checked=qdoc['checked_at'];docs=[index_doc,article_doc,qindex_doc,qdoc]
            raw={'id':'primary-html-wason-'+digest({'race_id':entry['race_id'],'end':meta['end'],'question':'Q4'})[:20],
                'subject':race['subject'],'poll_type':race['poll_type'],'seat_name':race.get('seat_name'),
                'pollster':entry['pollster'],'start_date':meta['start'],'end_date':meta['end'],
                'created_at':meta['published'],'sample_size':meta['sample_n'],'population':'lv',
                'answers':answers,'url':url,'sponsors':[],'internal':False,'partisan':None}
            review={'reviewed_on':checked[:10],'review_method':'structured_primary_html_table_v1',
                'provider_record_sha256':answer_correction_fingerprint(raw),
                'primary_supplement_record_sha256':answer_correction_fingerprint(raw),
                'sources':[url,qurl],'primary_documents':[{'url':d['url'],'sha256':d['sha256']}for d in docs],
                'primary_toplines':{a['choice']:a['pct'] for a in answers},'question_sample_n':meta['sample_n'],
                'admission':{'pollster':entry['pollster'],'provider_url':url,'group':entry['pollster_group'],
                    'methodology_url':url,'source_role':'pollster_primary','signal_eligible':True},
                'ballot_format':'ordinary_named_candidate_ballot',
                'disclosure_review':{'population':'LV','sample_n':meta['sample_n'],
                    'field_dates':[meta['start'],meta['end']],'primary_release_date':meta['published'],
                    'question_wording_checked':True,'question_number':'Q4','question_scope':entry['race_id'],
                    'unconditional_full_sample_question':True,'other_responses':other,
                    'sampling_method':'live landline and cellphone interviews; primary methods checked',
                    'weighting':'weighting disclosed in primary methodology; no inferred weights'},
                'reported_precision':{'kind':'publisher_reported_margin_of_sampling_error','half_width_pp':meta['moe'],
                    'confidence_level_pct':meta['confidence'],'scope':f'question LV n{meta["sample_n"]} full interviewed district population'},
                'sponsor_review':{'primary_internal':False,'primary_sponsors':[]},
                'missing_fields':['historical_accuracy_rating'],
                'limitations_ko':'검토된 조사기관 HTML+공개 표 형식을 자동 대조한 관측. 원문 날짜·All 열·현재 후보·기관·방법론 검사이며 수기 전사나 정확도 등급·당선확률이 아닙니다. 다른 지역·상원 문항·정당 선호도를 이 레이스로 전환하지 않습니다.'}
            # Compute the same normalized fingerprint that production admission uses.
            observed={'id':raw['id'],'race_id':race['race_id'] if 'race_id'in race else entry['race_id'],
                'pollster_group':entry['pollster_group'],'field_start':raw['start_date'],'field_end':raw['end_date'],
                'population':'lv','sample_n':raw['sample_size'],
                'answers':[{'name':a['choice'],'pct':a['pct'],'party':race['candidates'][a['choice']]['party']}for a in answers]}
            review['snapshot_sha256']=review_fingerprint(observed)
            raw['primary_source_capture']={'status':'primary_documents_rechecked','original_reviewed_on':review['reviewed_on'],
                'checked_at':checked,'documents':docs,'provider_duplicate_ids':[],'reviewed_replaced_provider_ids':[],
                'extraction_method':'structured_primary_html_table_v1'}
            records.append({'id':raw['id'],'state':entry['state'],'kind':'html_table',
                'contract_id':entry['id'],'contract_sha256':digest(entry),'record':raw,'quality_review':review,
                **deepcopy(raw['primary_source_capture'])})
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:
            failures.append({'url':url,'error_type':type(error).__name__,'reason':str(error)[:120]})
    require(records,'no valid primary HTML table release')
    return records,failures


def saved_html_receipts(previous, state_packets=()):
    # A newly merged packet can be the only last-good primary observation
    # before the first daily publication. Import source receipts, never old API rows.
    receipts=deepcopy(previous.get('primary_supplement_receipts',[]))
    for capture in previous.get('state_captures',{}).values():
        receipts.extend(deepcopy(capture.get('primary_supplement_receipts',[])))
    for packet in state_packets:
        receipts.extend(deepcopy(packet['capture']['receipt'].get('primary_supplement_receipts',[])))
    return [r for r in receipts if r.get('kind')=='html_table']


def merge_html_tables(rows, snapshot, policy, as_of, previous_receipts=(), states=None, opener=urlopen):
    output=deepcopy(rows);receipts=[]
    for entry in contracts(snapshot,as_of,states):
        old={}
        for r in previous_receipts:
            if r.get('kind')=='html_table' and r.get('contract_id')==entry['id'] and r.get('contract_sha256')==digest(entry):
                if r['id'] not in old or r['checked_at']>old[r['id']]['checked_at']:old[r['id']]=r
        previous=deepcopy(list(old.values()))
        try:
            current,failures=collect_entry(entry,policy,as_of,opener)
            seen={r['id']for r in current}
            for old in previous:
                if old['id'] not in seen:
                    old['record']['primary_source_capture']['status']='carried_forward_reference_only'
                    old['status']='carried_forward_reference_only'
                    current.append(old)
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:
            current=previous;failures=[{'error_type':type(error).__name__,'reason':str(error)[:120]}]
            for item in current:
                item['record']['primary_source_capture']['status']='carried_forward_reference_only'
                item['status']='carried_forward_reference_only'
        if not current:
            receipts.append({'kind':'html_table_health','state':entry['state'],'contract_id':entry['id'],
                'status':'unavailable_no_previous_data','failures':failures});continue
        for item in current:
            raw=item['record'];item['failures']=failures
            # Later API duplicates must agree, regardless of API source spelling.
            same=[r for r in output if r.get('subject')==raw['subject'] and r.get('poll_type')==raw['poll_type']
                  and r.get('start_date')==raw['start_date'] and r.get('end_date')==raw['end_date']
                  and r.get('population')==raw['population'] and
                  (r.get('pollster')==entry['pollster'] or r.get('url')==raw['url'])]
            race=policy['races'][entry['race_id']]
            values=lambda r:sorted((race['candidates'].get(a['choice'],{}).get('canonical_name',a['choice']),a['pct'])for a in r['answers'])
            if any(r.get('sample_size')!=raw['sample_size'] or values(r)!=values(raw) or
                   r.get('internal')!=raw['internal'] or r.get('partisan')!=raw['partisan'] or
                   (r.get('sponsors')or[])!=raw['sponsors'] for r in same):
                item['record']['primary_source_capture']['status']='carried_forward_reference_only'
                item['status']='provider_wave_conflict_reference_only'
                # Do not count the disagreeing API record as another institution.
            output=[r for r in output if r not in same and r.get('id')!=raw['id']]
            item['record']['primary_source_capture']['provider_duplicate_ids']=[r['id']for r in same]
            output.append(deepcopy(item['record']));receipts.append(item)
    return output,receipts


def bind_html_reviews(policy, rows, receipts, snapshot, as_of):
    result=deepcopy(policy)
    if not any(r.get('kind')=='html_table' for r in receipts):return result
    allowed={e['id']:e for e in contracts(snapshot,as_of)}
    by_id={r['id']:r for r in rows}; reviews=result.setdefault('quality_reviews',{})
    for receipt in receipts:
        if receipt.get('kind')!='html_table':continue
        entry=allowed.get(receipt.get('contract_id'))
        require(entry and receipt['contract_sha256']==digest(entry),'HTML source contract changed during replay')
        raw=by_id.get(receipt['id']);require(raw is not None,'missing captured HTML row')
        review=receipt['quality_review']
        require(receipt['state']==entry['state'] and review['review_method']=='structured_primary_html_table_v1'
                and review['provider_record_sha256']==answer_correction_fingerprint(raw)
                and receipt['record']==raw,'HTML capture/review mismatch')
        require(raw['pollster']==entry['pollster'] and raw['subject']==result['races'][entry['race_id']]['subject'],
                'HTML capture race/source mismatch')
        existing=reviews.get(raw['id']);require(existing is None or existing==review,'conflicting HTML review')
        reviews[raw['id']]=deepcopy(review)
    return result
