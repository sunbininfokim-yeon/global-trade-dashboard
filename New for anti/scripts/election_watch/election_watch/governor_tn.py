"""Tennessee public IE export audit. Transaction totals remain held for review."""
from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
import http.cookiejar
import io
import re
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import build_opener, HTTPCookieProcessor, Request

from .superpac import SourceError

SEARCH = 'https://apps.tn.gov/tncamp/public/cesearch.htm'
HEADERS = ['Type','Adj','Amount','Date','Election Year','Report Name','Candidate/PAC Name',
           'Vendor Name','Purpose','Candidate For','S/O']


def parse_export(raw, expected, encoding='utf-8-sig'):
    if encoding.lower() not in ('utf-8','utf-8-sig','iso-8859-1','windows-1252'):
        raise SourceError('Tennessee unreviewed CSV encoding')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode(encoding)))
        if reader.fieldnames != HEADERS:
            raise SourceError('Tennessee public CSV schema changed')
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise SourceError('Tennessee public CSV invalid') from None
    if len(rows) != expected or any(set(r) != set(HEADERS) or any(v is None for v in r.values()) for r in rows):
        raise SourceError('Tennessee truncated or changed CSV; last audit preserved')
    if any(r['Type'] != 'Independent' for r in rows):
        raise SourceError('Tennessee export is not independent expenditure search')
    return rows


def summarize_exports(cycle, snapshots, roster, captured_at):
    if not roster or set(snapshots) != {cycle-1, cycle}:
        raise SourceError('Tennessee requires reviewed roster and both report years')
    aliases = {}
    for candidate in roster:
        # Exact reversed source name only; no surname or description matching.
        words = candidate['name'].split()
        key = words[-1].upper() + ', ' + ' '.join(words[:-1]).upper()
        if key in aliases:
            raise SourceError('Tennessee ambiguous reviewed target')
        aliases[key] = candidate
    rows = []
    sources = []
    for year, snapshot in sorted(snapshots.items()):
        parsed = parse_export(snapshot['csv'], snapshot['expected_count'],snapshot.get('encoding','utf-8-sig'))
        sources.append({'report_year':year,'source_url':SEARCH,'export_url':snapshot['export_url'],
            'rows':len(parsed),'csv_encoding':snapshot.get('encoding','utf-8-sig'),
            'csv_sha256':hashlib.sha256(snapshot['csv']).hexdigest()})
        rows.extend({**r,'report_year':year} for r in parsed)
    keys = Counter(tuple(str(r.get(h,'')) for h in [*HEADERS,'report_year']) for r in rows)
    targets = [r for r in rows if r['Candidate For'].upper() in aliases]
    by_candidate = []
    for key,candidate in aliases.items():
        selected = [r for r in targets if r['Candidate For'].upper() == key]
        by_candidate.append({'candidate_id':candidate['candidate_id'],'name':candidate['name'],
            'party':candidate['party'],'reported_target':key,'reported_rows':len(selected),
            'support_rows':sum(r['S/O']=='S' for r in selected),
            'oppose_rows':sum(r['S/O']=='O' for r in selected),
            'ambiguous_identical_rows':sum(keys[tuple(str(r.get(h,'')) for h in [*HEADERS,'report_year'])]>1 for r in selected),
            'support_cents':None,'oppose_cents':None,'amount_status':'normalization_held'})
    return {'schema':'usa_governor_finance_audit_v1','state':'TN','cycle':cycle,
        'captured_at':captured_at,'status':'collected_normalization_held','source_url':SEARCH,
        'sources':sources,'input_records':len(rows),'current_governor_target_records':len(targets),
        'candidate_audits':by_candidate,'reported_candidates':dict(Counter(r['Candidate For'] for r in rows)),
        'hold_reasons':['transaction_identity_missing','report_amendment_lineage_unverified',
                        'target_office_and_election_year_not_present_in_export'],
        'limitations_ko':[
            '공식 공개 Independent 검색의 CSV 전량과 페이지 표시 건수를 대조한 수집 감사입니다. 후보별 총액은 공개하지 않습니다.',
            '검색 CSV에는 거래 고유번호·정정 전후 관계·대상 직위가 없고 선거연도가 빈칸인 행이 있습니다. 신고 원문·정정 목록 검증 전 금액은 null입니다.',
            '동일한 지급 내역이 실제 복수 지급인지 중복/정정인지 추정하지 않습니다. 적힌 후보 이름은 검토된 주지사 명부와 정확히 대조한 발견 대상입니다.',
            '주 독립지출은 연방 Super PAC과 다르며 수집 시점은 마지막 신고일이나 본선 지출 기준일이 아닙니다.']}


def collect_audit(cycle, roster, client=None):
    if type(cycle) is not int or cycle < 2010 or cycle % 2:
        raise SourceError('Tennessee even reporting cycle required')
    client = client or build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client.addheaders = [('User-Agent','ElectionWatch/1.0')]
    snapshots = {}
    def request(url, data=None):
        with client.open(Request(url,data=data),timeout=30) as response:
            if urlparse(response.url).hostname != 'apps.tn.gov' or urlparse(response.url).path.startswith('/paams'):
                raise SourceError('Tennessee public source redirected; last audit preserved')
            raw = response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:
                raise SourceError('Tennessee export exceeded size budget')
            return raw,response.headers.get_content_charset() or 'utf-8'
    for year in [cycle-1,cycle]:
        # Only ASCII form/link/count markers are parsed here; the legacy portal
        # includes non-UTF8 decorative text. CSV candidate names remain strict.
        initial = request(SEARCH)[0].decode('utf-8','replace')
        if 'name="typeOf"' not in initial or 'value="independent"' not in initial or f'value="{year}"' not in initial:
            raise SourceError('Tennessee public search schema/year changed')
        fields={'searchType':'expenditures','toType':'both','toCandidate':'true','toPac':'true','toOther':'true',
            'yearSelection':str(year),'electionYearSelection':'','typeOf':'independent','amountSelection':'equal',
            'amountDollars':'','amountCents':'','_continue':'Search'}
        for key in ['typeField','adjustmentField','amountField','dateField','electionYearField','reportNameField',
                    'candidatePACNameField','vendorNameField','purposeField','candidateForField','soField']:
            fields[key]='true'
        html = request(SEARCH,urlencode(fields).encode())[0].decode('utf-8','replace')
        count=re.search(r'([\d,]+) results? found',html)
        if not count:
            raise SourceError('Tennessee missing result count; zero not inferred')
        links=[urljoin(SEARCH,x.replace('&amp;','&')) for x in re.findall(r'href="([^"]+)"',html)
               if 'd-1341904-e=1' in x and '6578706f7274=1' in x]
        if len(links)!=1 or urlparse(links[0]).hostname!='apps.tn.gov' or urlparse(links[0]).path!='/tncamp/public/ceresults.htm':
            raise SourceError('Tennessee CSV export link changed')
        raw,encoding=request(links[0])
        snapshots[year]={'csv':raw,'encoding':encoding,'expected_count':int(count.group(1).replace(',','')),
                         'export_url':links[0]}
    return summarize_exports(cycle,snapshots,roster,datetime.now(timezone.utc).isoformat())
