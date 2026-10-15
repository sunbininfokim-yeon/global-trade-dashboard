"""Bounded secondary discovery. Aggregator rows are never eligible poll votes.

270toWin's public latest-polls pages load the HTML endpoint below. Its date is
not a fieldwork date, and its table lacks question n/population/methodology.
Keep those unknown until a primary release is independently reviewed.
"""
from collections import Counter
from datetime import date
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .polls import digest, require

BASE = 'https://www.270towin.com'
OFFICES = {'house': 'H', 'senate': 'S', 'governor': 'G'}
MAX_BYTES = 1024 * 1024


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def nodes(self, tag):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.nodes(tag)

    def text(self):
        return ' '.join(''.join(c.text() if isinstance(c, Node) else c
                                for c in self.children).split())


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'source'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def endpoint(office, cycle):
    require(office in OFFICES and type(cycle) is int, 'discovery office/cycle')
    query = [('election_year', str(cycle)), ('election_types[]', OFFICES[office]),
             *[('election_subtypes[]', x) for x in ('PE', 'PR', 'GE', 'GR')], ('limit', '40')]
    return BASE + '/polls/php/get-polls-list-v2.php?' + urlencode(query)


def safe_link(value):
    parsed = urlparse(value)
    require(parsed.scheme in ('https', 'http') and parsed.hostname
            and not parsed.username and not parsed.password, 'invalid discovery source link')
    return value


def parse_270(html, office, cycle, as_of, state_names):
    parser = TableParser()
    parser.feed(html)
    tables = [t for t in parser.root.nodes('table') if t.attrs.get('id') == 'polls-list']
    require(len(tables) == 1, 'missing or changed 270toWin poll table')
    bodies = [b for b in tables[0].children if isinstance(b, Node) and b.tag == 'tbody']
    require(len(bodies) == 1, 'changed 270toWin table body')
    rows = [r for r in bodies[0].children if isinstance(r, Node) and r.tag == 'tr']
    require(0 < len(rows) <= 200, 'empty or oversized 270toWin table')
    slug_states = {name.lower().replace(' ', '-'): state for state, name in state_names.items()}
    records, skipped, context, remaining = [], [], None, 0
    for position, row in enumerate(rows):
        try:
            cells = [c for c in row.children if isinstance(c, Node) and c.tag == 'td']
            if len(cells) == 1 and cells[0].text() == 'Advertisement':
                continue
            if len(cells) == 7:
                require(remaining == 0, 'incomplete discovery rowspan')
                spans = [int(c.attrs.get('rowspan', '1')) for c in cells[:4]]
                require(len(set(spans)) == 1 and 1 <= spans[0] <= 8, 'changed discovery rowspan')
                remaining = spans[0]
                m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', cells[0].text())
                require(m is not None, 'discovery date format')
                month, day, year = map(int, m.groups())
                shown_date = date(year, month, day).isoformat()
                require(year == cycle and shown_date <= as_of, 'future or different cycle discovery')
                source = list(cells[2].nodes('a'))
                location = list(cells[3].nodes('a'))
                require(len(source) == len(location) == 1, 'ambiguous discovery source/location')
                location_url = urljoin(BASE, location[0].attrs.get('href', ''))
                parsed = urlparse(location_url)
                require(parsed.hostname == 'www.270towin.com' and parsed.scheme == 'https', 'discovery location host')
                match = re.fullmatch(fr'/{cycle}-{office}-polls/([a-z-]+)(?:/district-(\d+))?/?', parsed.path)
                require(match is not None and match[1] in slug_states, 'unknown discovery race')
                state, district = slug_states[match[1]], match[2]
                if office == 'house':
                    # The at-large location link omits district-N; the displayed
                    # code must explicitly say AL. Never map a missing number to 00.
                    if district is None:
                        require(location[0].text() == state+'-AL', 'ambiguous at-large discovery')
                        district = '00'
                    else:
                        district = district.zfill(2)
                        require(location[0].text() == state+'-'+district, 'discovery district label mismatch')
                else:
                    require(district is None, 'district on statewide discovery')
                phase = {'General Election': 'general', 'General Runoff': 'general_runoff',
                         'Primary Election': 'primary', 'Primary Runoff': 'primary_runoff',
                         'Democratic Primary': 'democratic_primary', 'Republican Primary': 'republican_primary'}.get(cells[1].text(), 'unclassified')
                require(source[0].attrs.get('href') and not source[0].attrs['href'].startswith('#'),
                        'missing discovery source link')
                context = {'race_id': f'USA:{state}:{office}' + (f':{district}' if district else ''),
                    'state': state, 'office': office, 'district': district,
                    'aggregator_date': shown_date, 'aggregator_date_meaning': 'not_verified_as_fieldwork_or_release_date',
                    'displayed_election_type': cells[1].text(), 'election_phase': phase,
                    'pollster_label': source[0].text(),
                    'source_url': safe_link(urljoin(BASE, source[0].attrs.get('href', ''))),
                    'linked_source_role': 'unverified_aggregator_link',
                    'aggregator_race_url': location_url}
                result_cell = cells[4]
            else:
                require(len(cells) == 3 and remaining > 0 and context, 'orphan discovery continuation')
                result_cell = cells[0]
            remaining -= 1
            answers = []
            for candidate in result_cell.nodes('tr'):
                parts = [c for c in candidate.children if isinstance(c, Node) and c.tag == 'td']
                if len(parts) != 2:
                    continue
                pct = re.fullmatch(r'(\d+(?:\.\d+)?)%', parts[1].text())
                require(pct is not None, 'changed discovery percentage')
                value = float(pct[1])
                require(math.isfinite(value) and 0 <= value <= 100, 'invalid discovery percentage')
                party = {'fill-D': 'DEM', 'fill-R': 'REP', 'fill-I': 'IND'}.get(candidate.attrs.get('class'))
                answers.append({'name_label': parts[0].text(), 'party_label': party, 'pct': value})
            require(len(answers) >= 2 and all(a['name_label'] for a in answers), 'missing discovery candidates')
            record = {**context, 'answers': answers, 'field_start': None, 'field_end': None,
                'population': None, 'sample_n': None, 'ballot_format': 'not_reviewed',
                'source': '270toWin', 'status': 'primary_review_required', 'signal_eligible': False,
                'missing_fields': ['primary_question', 'fieldwork_dates', 'question_sample_n', 'population', 'methodology', 'commissioner'],
                'note_ko': '취합 사이트에서 발견한 조사. 원문·문항 검증 전 우세 집계와 중복 조사 수에 포함하지 않음.'}
            record['id'] = 'discovery-270-' + digest({**context, 'answers': answers})[:20]
            records.append(record)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            skipped.append({'row': position, 'reason': str(exc)[:160]})
            context, remaining = None, 0
    require(records, 'no usable 270toWin discovery records')
    if remaining:
        skipped.append({'row': len(rows), 'reason': 'incomplete discovery rowspan'})
    unique = {r['id']: r for r in records}
    return list(unique.values()), skipped


def collect_270(cycle, as_of, captured_at, state_names, opener=urlopen):
    date.fromisoformat(as_of)
    sources, records = {}, []
    for office in OFFICES:
        url = endpoint(office, cycle)
        try:
            with opener(Request(url, headers={'User-Agent': 'ElectionPollPipeline/2.0'}), timeout=30) as response:
                require(response.url == url, 'unexpected discovery redirect')
                body = response.read(MAX_BYTES+1)
            require(len(body) <= MAX_BYTES, 'oversized discovery response')
            found, skipped = parse_270(body.decode('utf-8'), office, cycle, as_of, state_names)
            records.extend(found)
            import hashlib
            sources[office] = {'status': 'partial' if skipped else 'ok', 'request_url': url,
                'captured_at': captured_at, 'sha256': hashlib.sha256(body).hexdigest(),
                'record_count': len(found), 'skipped_rows': skipped,
                'scope': 'latest_40_list_entries_not_complete_cycle'}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            sources[office] = {'status': 'unavailable', 'attempted_at': captured_at,
                'request_url': url, 'error_type': type(exc).__name__}
    return {'schema': 'usa_poll_source_discovery_v1', 'cycle': cycle, 'as_of': as_of,
        'captured_at': captured_at, 'status': 'ok' if all(s['status']=='ok' for s in sources.values()) else 'partial',
        'source_health': sources, 'records': records,
        'summary': {'discovered_records': len(records), 'races': len({r['race_id'] for r in records}),
                    'by_office': dict(Counter(r['office'] for r in records)), 'signal_eligible_records': 0},
        'limitations_ko': '최신 목록 탐색용. 원문 수치·기간·표본·모집단·의뢰자·후보 신원·파동 중복 검증 전 여론조사 본 데이터에 편입하지 않음. 과거 전체 조사 또는 현재 조사 존재의 완전한 목록이 아님.'}


def annotate_provider_links(report, provider_rows, captured_at):
    """Exact source-link hints for review, never wave deduplication/admission."""
    links = Counter(row.get('url') for row in provider_rows if isinstance(row.get('url'), str))
    for row in report['records']:
        row['provider_source_url_matches'] = links[row['source_url']]
    report['provider_comparison'] = {'status': 'exact_url_hints_only', 'captured_at': captured_at,
        'records_without_same_source_url': sum(r['provider_source_url_matches']==0 for r in report['records']),
        'note_ko': 'URL 일치 여부는 수집 누락 검토용 단서이며 동일 조사 파동·후보·기간이 검증됐다는 뜻이 아님.'}
