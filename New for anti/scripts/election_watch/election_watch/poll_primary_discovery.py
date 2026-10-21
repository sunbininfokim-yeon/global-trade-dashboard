"""Bounded official publisher lists. Discovery never approves a poll/question."""
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import hashlib
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .polls import digest, require
from .poll_source_discovery import Node, TableParser, safe_link

SOURCES = {
    'emerson_rss': 'https://emersoncollegepolling.com/feed/',
    'quinnipiac_results': 'https://poll.qu.edu/poll-results/',
    'suffolk_latest': 'https://www.suffolk.edu/academics/research-at-suffolk/political-research-center',
}
LIMIT = 4_000_000


def visible(node):
    if node.tag in ('script','style'):
        return ''
    return ' '.join(' '.join(visible(c) if isinstance(c,Node) else c
                            for c in node.children).split())


def race_hints(title, state_names, catalog):
    """Explicit geographic/office labels only; House generic ballots stay out."""
    found = set()
    for code, district in re.findall(r'\b([A-Z]{2})[-–](\d{1,2}|AL)\b', title):
        if code in state_names:
            seats = catalog['states'][code]['house_seats']
            number = 1 if district == 'AL' else int(district)
            if 1 <= number <= seats and (district != 'AL' or seats == 1):
                found.add(f'USA:{code}:house:'+('00' if seats == 1 else f'{number:02}'))
    states = [s for s, name in state_names.items()
              if re.search(r'\b'+re.escape(name)+r'\b', title, re.I)]
    # Several state names in a roundup cannot define one statewide sample.
    if len(states) != 1:
        prefix = re.match(r'^([A-Z]{2})\s+(?:Governor|Senate)', title)
        states = [prefix[1]] if prefix and prefix[1] in state_names else []
    if len(states) == 1:
        state = states[0]
        district = re.search(re.escape(state_names[state])+r"(?:'s|’s)?\s+(\d{1,2})(?:st|nd|rd|th)\s+(?:Congressional\s+)?District", title, re.I)
        if district:
            seats = catalog['states'][state]['house_seats']; number = int(district[1])
            if 1 <= number <= seats:
                found.add(f'USA:{state}:house:'+('00' if seats == 1 else f'{number:02}'))
        for office, pattern in [('governor', r'(?<!Lt\. )(?<!Lieutenant )\bGovernor(?:[’\']s)?(?:\b|\s)|\bgubernatorial\b'),
                                ('senate', r'\b(?:U\.?S\.?\s+)?Senate\b')]:
            if re.search(pattern, title, re.I) and state in catalog[office+'_states']:
                found.add(f'USA:{state}:{office}')
    return sorted(found)


def record(source, url, label, published, catalog, captured_at, context=None):
    state_names = {s: r['name'] for s, r in catalog['states'].items()}
    hints = race_hints(context or label, state_names, catalog)
    result = []
    for rid in hints or [None]:
        parts = rid.split(':') if rid else []
        item = {'source': source, 'source_url': safe_link(url), 'publisher_url': SOURCES[source],
                'poll_label': label, 'publisher_article_published_on': published,
                'publisher_context_sha256': digest(context) if context else None,
                'captured_at': captured_at, 'race_id': rid,
                'state': parts[1] if parts else None, 'office': parts[2] if parts else None,
                'district': parts[3] if len(parts) == 4 else None,
                'election_phase': 'unclassified', 'status': 'primary_review_required',
                'signal_eligible': False, 'linked_source_role': 'publisher_release_list',
                'missing_fields': ['primary_question', 'fieldwork_dates', 'question_sample_n',
                                   'population', 'methodology', 'commissioner'],
                'note_ko': '공식 발표 목록 발견. 기사 게시일은 조사기간이 아니며 표본·문항·경선/본선·bellwether 범위를 승인하지 않습니다.'}
        item['id'] = 'discovery-primary-'+digest(item)[:24]
        result.append(item)
    return result


def parse_emerson(body, catalog, as_of, captured_at):
    require(b'<!DOCTYPE' not in body.upper() and b'<!ENTITY' not in body.upper(), 'unsafe publisher XML')
    root = ET.fromstring(body); channel = root.find('channel')
    require(root.tag == 'rss' and channel is not None
            and channel.findtext('title') == 'Emerson Polling'
            and channel.findtext('link') == 'https://emersoncollegepolling.com/', 'changed Emerson feed')
    rows = []; skipped = 0
    for item in channel.findall('item')[:40]:
        try:
            published = parsedate_to_datetime(item.findtext('pubDate'))
            require(published.tzinfo is not None, 'publisher timezone missing')
            if published.year != catalog['cycle'] or published.date() > date.fromisoformat(as_of):
                continue
            url = safe_link(item.findtext('link')); title = unescape(item.findtext('title') or '')
            require(urlparse(url).hostname == 'emersoncollegepolling.com', 'changed Emerson article host')
            if not re.search(r'poll|governor|senate|district', title, re.I):
                continue
            intro = TableParser();intro.feed(item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or '')
            context = title+' '+' '.join(visible(p) for p in list(intro.root.nodes('p'))[:8])[:6000]
            # National/generic/presidential articles cannot create a state race.
            if not race_hints(context,{s:r['name'] for s,r in catalog['states'].items()},catalog):
                continue
            rows.extend(record('emerson_rss', url, title, published.date().isoformat(), catalog, captured_at,context))
        except (ValueError, TypeError, KeyError, AttributeError):
            skipped += 1
    require(rows, 'no current Emerson releases')
    return rows, skipped


def parse_index(body, source, catalog, as_of, captured_at):
    parser = TableParser(); parser.feed(body.decode('utf-8')); parser.close()
    parents = {}
    def visit(node):
        for child in node.children:
            if isinstance(child, Node):
                parents[child] = node; visit(child)
    visit(parser.root)
    rows = []; skipped = 0
    for anchor in parser.root.nodes('a'):
        label = visible(anchor)
        url = urljoin(SOURCES[source], anchor.attrs.get('href', '')); parsed = urlparse(url)
        if source == 'quinnipiac_results':
            if parsed.hostname != 'poll.qu.edu' or parsed.path != '/poll-release' or not label or label.startswith('Read More'):
                continue
        elif source == 'suffolk_latest':
            if parsed.hostname != 'www.suffolk.edu' or '/political-research-center/polls/' not in parsed.path or not re.search(r'\b2026\b', label):
                continue
        else:
            raise ValueError('unreviewed primary index')
        try:
            node = anchor; days = []
            for _ in range(5):
                # Select the closest dated card, never a date elsewhere on the page.
                text = visible(node)
                matches = re.findall(r'\b([A-Z][a-z]+\s+\d{1,2},\s*2026)\b', text)
                if matches:
                    days = sorted({datetime.strptime(' '.join(x.split()), '%B %d, %Y').date() for x in matches})
                    break
                node = parents.get(node)
                if node is None or len(visible(node)) > 2500:
                    break
            require(len(days) == 1, 'missing or ambiguous publisher date')
            if days[0] > date.fromisoformat(as_of):
                continue
            # Non-race policy/generic ballots are not put into the race queue.
            hints = race_hints(label, {s:r['name'] for s,r in catalog['states'].items()}, catalog)
            if not hints:
                continue
            rows.extend(record(source, url, label, days[0].isoformat(), catalog, captured_at))
        except (ValueError, TypeError, KeyError):
            skipped += 1
    require(rows, 'no dated primary election releases')
    return list({(r['race_id'],r['source_url'],r['publisher_article_published_on']):r for r in rows}.values()), skipped


def collect_primary(catalog, as_of, captured_at=None, opener=urlopen):
    stamp = captured_at or datetime.now(timezone.utc).isoformat()
    rows = []; health = {}
    for source, url in SOURCES.items():
        try:
            with opener(Request(url, headers={'User-Agent':'ElectionEvidenceReview/1.0 public-release-discovery'}), timeout=20) as response:
                require(response.status == 200 and response.geturl() == url, 'publisher response/redirect')
                body = response.read(LIMIT+1)
            require(len(body) <= LIMIT, 'oversized publisher list')
            found, skipped = (parse_emerson(body,catalog,as_of,stamp) if source == 'emerson_rss'
                              else parse_index(body,source,catalog,as_of,stamp))
            rows.extend(found)
            health[source] = {'status':'partial' if skipped else 'ok', 'url':url,
                'captured_at':stamp, 'sha256':hashlib.sha256(body).hexdigest(),
                'candidate_records':len(found), 'skipped_entries':skipped,
                'scope':'publisher_latest_list_not_complete_cycle'}
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
            health[source] = {'status':'unavailable','url':url,'attempted_at':stamp,'error_type':type(exc).__name__}
    return {'records':rows,'source_health':health}
