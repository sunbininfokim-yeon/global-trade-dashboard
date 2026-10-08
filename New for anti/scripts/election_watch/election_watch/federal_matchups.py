"""Reviewed ballot identities for display, independent of polling admission."""
from copy import deepcopy
from datetime import date
from html.parser import HTMLParser
import re
from urllib.parse import urlparse

PARTIES = {'Democratic': 'DEM', 'Republican': 'REP', 'No Party Preference': 'IND'}
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
        if race['coverage'] not in ('complete_ballot', 'certified_major_party_field', 'reported_major_party_field'):
            raise ValueError('Unknown federal ballot coverage')
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


def attach_matchups(states, snapshot, as_of):
    validate_snapshot(snapshot, as_of)
    result = deepcopy(states)
    for state in result:
        state['election_matchups'] = {key: deepcopy(r) for key, r in snapshot['races'].items() if r['state'] == state['id']}
        for member in state.get('federal_delegation', {}).get('senators', []):
            review = snapshot.get('incumbents', {}).get(member.get('bioguideId'))
            if review: member['senate_election_history'] = deepcopy(review)
    return result
