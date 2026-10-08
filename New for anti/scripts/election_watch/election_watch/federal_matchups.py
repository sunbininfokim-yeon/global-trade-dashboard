"""Reviewed ballot identities for display, independent of polling admission."""
from copy import deepcopy
from datetime import date
from html.parser import HTMLParser
import re
from urllib.parse import urlparse

PARTIES = {'Democratic': 'DEM', 'Republican': 'REP', 'No Party Preference': 'IND'}
MI_GENERAL_URL = 'https://mi-boe.entellitrak.com/etk-mi-boe-prod/page.request.do?electionType=GEN&electionYear=2026&page=page.miboePublicReport'
MI_PARTIES = {'Democratic Party': 'DEM', 'Republican Party': 'REP',
              'Libertarian Party': 'LIB', 'U.S. Taxpayers Party': 'UST',
              'Green Party': 'GRN', 'Working Class Party': 'WCP',
              'Natural Law Party': 'NLP', 'No Party Affiliation': 'IND'}
STATES = set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split())
SENATE_2026_STATES = set('AL AK AR CO DE FL GA ID IL IA KS KY LA ME MA MI MN MS MT NE NH NJ NM NC OH OK OR RI SC SD TN TX VA WV WY'.split())


def _source_url(value):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid federal ballot source')


def parse_ca_house(text, source_url, reviewed_on):
    """The certified general list, never the primary/registration list."""
    if not re.search(r'General Election\s*-\s*November 3, 2026', text):
        raise ValueError('Not the 2026 California general ballot')
    found = {}
    pattern = r'United States Representative District (\d+)\s*(.*?)(?=United States Representative District \d+|State Senate District|State Senator District|Member of the State Assembly District|\Z)'
    for district, body in re.findall(pattern, text, re.S):
        candidates = []
        for line in body.splitlines():
            match = re.fullmatch(r'\s*(.+?)\s+(Democratic|Republican|No Party Preference)\s*', line)
            if match:
                candidates.append({'name': match[1].rstrip('*').strip(), 'party': PARTIES[match[2]],
                                   'source_url': source_url, 'candidate_id': None})
        key = f'USA:CA:house:{int(district):02d}'
        if key in found or len(candidates) != 2:
            raise ValueError('California general candidate count/district changed')
        found[key] = {'race_id': key, 'state': 'CA', 'office': 'house', 'district': f'{int(district):02d}',
                      'election_date': '2026-11-03', 'status': 'certified_ballot', 'coverage': 'complete_ballot',
                      'reviewed_on': reviewed_on, 'source_url': source_url, 'candidates': candidates,
                      'absent_parties': [p for p in ('DEM', 'REP') if not any(c['party'] == p for c in candidates)]}
    if set(found) != {f'USA:CA:house:{n:02d}' for n in range(1, 53)}:
        raise ValueError('California 52-district universe changed')
    return found


def parse_michigan_general(text, reviewed_on):
    """Readable official listing; federal offices only, no state legislature.

    A public candidate listing is not an election result or a separately
    certified ballot. DISQ candidates are retained as exclusions, not nominees.
    """
    if not all(s in text for s in ('Michigan Department of State', 'Official Candidate Listing',
                                  'General Election', 'Tuesday, November 3, 2026')):
        raise ValueError('Not the Michigan 2026 official general listing')
    if date.fromisoformat(reviewed_on).year != 2026:
        raise ValueError('Michigan adapter needs a reviewed cycle')
    found = {}; current = None
    parties = '|'.join(re.escape(p) for p in MI_PARTIES)
    pattern = re.compile(rf'(?:(DISQ)\s+)?({parties})\s+(.+?)\s+(\d{{2}}/\d{{2}}/\d{{4}})\s+(Petitions|Convention)')
    for line in text.splitlines():
        line = ' '.join(line.split())
        district = re.fullmatch(r'(\d+)(?:st|nd|rd|th) District Representative in Congress 2 Year Term \(1\) Position(?: Files In [A-Z ]+ County)?', line)
        if line == 'U.S. Senate 6 Year Term (1) Position' or district:
            number = int(district[1]) if district else None
            if number is not None and not 1 <= number <= 13:
                raise ValueError('Michigan federal district outside apportionment')
            rid = 'USA:MI:senate' if number is None else f'USA:MI:house:{number:02d}'
            if rid in found: raise ValueError('Duplicate Michigan federal office')
            current = {'race_id': rid, 'state': 'MI', 'office': 'senate' if number is None else 'house',
                'district': None if number is None else f'{number:02d}', 'election_date': '2026-11-03',
                'reviewed_on': reviewed_on, 'status': 'reported_general_matchup',
                'coverage': 'complete_active_agency_listing', 'source_role': 'state_election_agency',
                'source_url': MI_GENERAL_URL, 'candidates': [], 'excluded_candidates': [],
                'limitations_ko': '공식 본선 후보 추적 명부. 별도 투표용지 인증·당선 결과가 아니며 향후 기명 후보 등록까지 완결되었다고 보지 않습니다.'}
            found[rid] = current
            continue
        if re.search(r'\d Year Term \(\d+\) Position', line):
            current = None
            continue
        if current is None or not line:
            continue
        match = pattern.fullmatch(line)
        if not match: raise ValueError('Michigan candidate row/status changed')
        status, party, reported_name, filed, method = match.groups()
        if reported_name.count(',') != 1: raise ValueError('Michigan candidate name schema changed')
        last, first = (part.strip() for part in reported_name.split(','))
        if not first or not last: raise ValueError('Michigan empty candidate name')
        candidate = {'name': f'{first} {last}', 'party': MI_PARTIES[party],
                     'candidate_id': None, 'source_url': MI_GENERAL_URL,
                     'reported_name': reported_name, 'reported_party': party,
                     'agency_status': status or 'listed_active', 'filed_on': filed,
                     'filing_method': method}
        bucket = 'excluded_candidates' if status else 'candidates'
        if any(c['name'].casefold() == candidate['name'].casefold() for c in current[bucket]):
            raise ValueError('Michigan duplicate candidate')
        current[bucket].append(candidate)
    expected = {'USA:MI:senate'} | {f'USA:MI:house:{n:02d}' for n in range(1, 14)}
    if set(found) != expected or any(not r['candidates'] for r in found.values()):
        raise ValueError('Incomplete Michigan federal listing')
    for race in found.values():
        race['absent_parties'] = [p for p in ('DEM', 'REP') if not any(c['party'] == p for c in race['candidates'])]
    return found


def merge_ballot_reviews(snapshot, reviews, as_of):
    """Reuse reviewed identities for display; never use FEC registrations.

    Rich certified rosters remain authoritative. A reviewed agency listing can
    replace a reported field; missing rosters can be filled from either source.
    This does not itself approve a polling observation.
    """
    validate_snapshot(snapshot, as_of)
    if reviews.get('schema') != 'usa_poll_ballot_reviews_v1' or reviews.get('cycle') != 2026 \
            or date.fromisoformat(reviews['reviewed_on']) > date.fromisoformat(as_of):
        raise ValueError('Invalid reviewed ballot catalog')
    result = deepcopy(snapshot)
    for key, review in reviews['races'].items():
        if review['office'] == 'governor': continue
        official = review.get('source_role') == 'state_election_agency'
        if not official and review.get('source_role') != 'reviewed_secondary_nominee_listing':
            continue
        previous = result['races'].get(key)
        if previous and (previous['status'] == 'certified_ballot'
                         or not official
                         or previous['reviewed_on'] > review['reviewed_on']):
            continue
        row = deepcopy(review)
        row['status'] = 'reported_general_matchup'
        if row['coverage'] == 'complete_active_agency_listing':
            row['absent_parties'] = [p for p in ('DEM', 'REP') if not any(c['party'] == p for c in row['candidates'])]
        else:
            row.setdefault('absent_parties', [])
        result['races'][key] = row
    validate_snapshot(result, as_of)
    return result


class _Table(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.row = None; self.cell = None; self.depth = 0
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.depth += 1
        if self.depth and tag == 'tr': self.row = []
        if self.depth and tag in ('td', 'th'): self.cell = []
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        if tag == 'tr' and self.row is not None: self.rows.append(self.row); self.row = None
        if tag == 'table': self.depth -= 1
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)


def parse_reported_field(html, office, state_names, source_url, reviewed_on):
    """Public reported nominees, not state certification or poll verification."""
    table = _Table(); table.feed(html)
    expected = 35 if office == 'senate' else 45
    header = ['State' if office == 'senate' else 'District', 'Incumbent / Seat Status' if office == 'senate' else 'Seat Status / Incumbent',
              'Democratic Candidate', 'Republican Candidate', 'Cook Rating']
    if not table.rows or table.rows[0] != header or len(table.rows) != expected + 1:
        raise ValueError('Reported nominee table schema/universe changed')
    found = {}
    for label, incumbent, dem, rep, _rating in table.rows[1:]:
        if office == 'house':
            match = re.fullmatch(r'(.+) (\d+)', label)
            if not match: raise ValueError('Reported district changed')
            label, district = match[1], f'{int(match[2]):02d}'
        else: district = None
        state = state_names[label]; key = f'USA:{state}:{office}' + (f':{district}' if district else '')
        if key in found: raise ValueError('Duplicate reported contest')
        candidates = []; absent = []
        for party, names in [('DEM', dem), ('REP', rep)]:
            if names == 'No Democratic nominee' and party == 'DEM': absent.append(party); continue
            for name in names.split(';'):
                name = name.strip()
                if not name or re.search(r'TBD|pending|primary|runoff|winner', name, re.I):
                    raise ValueError('Unresolved reported nominee')
                candidates.append({'name': name, 'party': party, 'source_url': source_url, 'candidate_id': None})
        found[key] = {'race_id': key, 'state': state, 'office': office, 'district': district,
                      'election_date': '2026-11-03', 'status': 'reported_general_matchup',
                      'coverage': 'reported_major_party_field', 'reviewed_on': reviewed_on,
                      'source_url': source_url, 'candidates': candidates, 'absent_parties': absent,
                      'incumbent_ballot_status': 'not_running' if re.search(r'retiring|not seeking|not running|defeated|Open', incumbent, re.I) else 'running'}
    return found


def validate_snapshot(snapshot, as_of):
    if snapshot.get('schema') != 'usa_federal_matchups_v1' or snapshot.get('cycle') != 2026:
        raise ValueError('Federal ballot snapshot schema/cycle')
    if date.fromisoformat(snapshot['reviewed_on']) > date.fromisoformat(as_of):
        raise ValueError('Future federal ballot snapshot')
    senate_ids = {key for key, race in snapshot['races'].items() if race['office'] == 'senate'}
    if senate_ids != {f'USA:{state}:senate' for state in SENATE_2026_STATES}:
        raise ValueError('Incomplete 2026 Senate contest universe')
    for key, race in snapshot['races'].items():
        expected = f"USA:{race['state']}:{race['office']}" + (f":{race['district']}" if race['office'] == 'house' else '')
        if key != expected or race['race_id'] != key or race['office'] not in ('house', 'senate') or race['state'] not in STATES:
            raise ValueError('Federal ballot race scope mismatch')
        if race['office'] == 'house' and not re.fullmatch(r'\d{2}', str(race['district'])):
            raise ValueError('Noncanonical federal ballot district')
        if race['office'] == 'senate' and race['district'] is not None:
            raise ValueError('Senate district must be statewide')
        if race['election_date'] != '2026-11-03' or date.fromisoformat(race['reviewed_on']) > date.fromisoformat(as_of):
            raise ValueError('Federal ballot date mismatch')
        if race['status'] not in ('certified_ballot', 'reported_general_matchup') or not race['candidates']:
            raise ValueError('Unreviewed federal ballot')
        if race['coverage'] not in ('complete_ballot', 'certified_major_party_field', 'reported_major_party_field',
                                    'complete_active_agency_listing'):
            raise ValueError('Unknown federal ballot coverage')
        if race['coverage'] == 'complete_active_agency_listing' and race.get('source_role') != 'state_election_agency':
            raise ValueError('Agency listing lacks agency provenance')
        _source_url(race['source_url'])
        seen = set()
        for candidate in race['candidates']:
            identity = (candidate['name'].strip().casefold(), candidate['party'])
            _source_url(candidate['source_url'])
            if identity in seen or not all(identity):
                raise ValueError('Invalid/duplicate federal ballot identity/source')
            seen.add(identity)
        if any(c['party'] in race['absent_parties'] for c in race['candidates']):
            raise ValueError('Contradictory absent party')
    for bio, review in snapshot.get('incumbents', {}).items():
        years = review['election_years']
        _source_url(review['source_url'])
        if review.get('corroborating_source_url'):
            _source_url(review['corroborating_source_url'])
        if date.fromisoformat(review['reviewed_on']) > date.fromisoformat(as_of) or review['bioguide_id'] != bio or len(set(years)) != len(years) or years != sorted(years) or any(type(y) is not int or y < 1788 or y > int(as_of[:4]) for y in years):
            raise ValueError('Invalid Senate election history')


def attach_matchups(states, snapshot, as_of, ballot_reviews=None):
    if ballot_reviews is not None:
        snapshot = merge_ballot_reviews(snapshot, ballot_reviews, as_of)
    validate_snapshot(snapshot, as_of)
    result = deepcopy(states)
    for state in result:
        state['election_matchups'] = {key: deepcopy(r) for key, r in snapshot['races'].items() if r['state'] == state['id']}
        for member in state.get('federal_delegation', {}).get('senators', []):
            review = snapshot.get('incumbents', {}).get(member.get('bioguideId'))
            if review: member['senate_election_history'] = deepcopy(review)
    return result
