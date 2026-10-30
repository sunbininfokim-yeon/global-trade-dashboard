"""Nationwide display identities from a reviewed public election directory.

The directory distinguishes authority-confirmed names (normal type), names
without that confirmation (italics), and inactive names (struck through).
These are secondary reports, never our certification or a polling approval.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
import unicodedata


class RosterTable(HTMLParser):
    """Keep cell structure, name prefix, and status markup without dependencies."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.row = None; self.cell = None; self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = []; self.cell = None
        elif tag == 'td' and self.row is not None:
            self.cell = {'attrs': attrs, 'text': [], 'prefix': [], 'links': [],
                         'images': [], 'anchors': [], 'section': False,
                         'italic': False, 'strike': False, 'annotation': False}
            self.row.append(self.cell)
        if self.cell is None: return
        if tag == 'img': self.cell['images'].append(attrs)
        if tag == 'a':
            if attrs.get('name'): self.cell['anchors'].append(attrs['name'])
            self.link = [] if not self.cell['annotation'] else None
        if tag == 'span' and attrs.get('id') == 'heaL': self.cell['section'] = True
        if tag in ('br', 'span'):
            self.cell['text'].append(' ')
            self.cell['annotation'] = True
        if not self.cell['annotation']:
            if tag in ('i', 'em'): self.cell['italic'] = True
            if tag in ('strike', 's', 'del'): self.cell['strike'] = True

    def handle_endtag(self, tag):
        if tag == 'a' and self.cell is not None and self.link is not None:
            value = ' '.join(''.join(self.link).split())
            if value: self.cell['links'].append(value)
            self.link = None
        if tag == 'td': self.cell = None; self.link = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row); self.row = None; self.cell = None

    def handle_data(self, text):
        if self.cell is None: return
        self.cell['text'].append(text)
        if not self.cell['annotation']: self.cell['prefix'].append(text)
        if self.link is not None: self.link.append(text)


def _text(cell, key='text'):
    return ' '.join(''.join(cell[key]).split())


def _name(cell):
    prefix = _text(cell, 'prefix'); links = cell['links']
    # Campaign names follow office-title links; exact source text, not fuzzy IDs.
    if links and prefix.endswith(links[-1]): return links[-1]
    if links and prefix.startswith(links[0]):
        title = links[0]
        if title in ('Member of Congress', 'Senator', 'Governor', 'state Representative',
                     'state Senator', 'state Treasurer', 'Lieutenant Governor'):
            return prefix[len(title):].strip()
    # An unlinked title in this directory is also outside the candidate's name.
    prefix = re.sub(r'^former [\w .,-]+ Council Member ', '', prefix)
    if not prefix or re.search(r'\b(?:TBD|to be determined|primary winner|runoff winner)\b', prefix, re.I):
        raise ValueError('Unresolved candidate identity')
    return prefix


def _party(reported):
    base = reported.split(';')[0].strip()
    mapping = {'Democratic': 'DEM', 'Democratic-Farmer Labor': 'DEM',
               'Democratic-Nonpartisan League': 'DEM', 'Republican': 'REP',
               'Libertarian': 'LIB', 'Green': 'GRN', 'Pacific Green': 'GRN',
               'Wisconsin Green': 'GRN', 'Constitution': 'CST',
               'American Constitution': 'CST', 'U.S. Taxpayers': 'UST',
               'Working Class': 'WCP', 'Natural Law': 'NLP', 'Write-in': 'WRI'}
    independent = {'Independent', 'Unaffiliated', 'Nonpartisan', 'Nonparty',
                   'No Party', 'No Party Affiliation', 'No Party Preference',
                   'No Political Party', 'By Petition'}
    return mapping.get(base, 'IND' if base in independent else 'OTH' if base else 'UNK')


def same_source_name(alias, name):
    """Exact ordered given/surname tokens, source nicknames, optional middle initials."""
    def tokens(value):
        text = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
        return [w for w in re.findall(r'[a-z0-9]+', text) if w not in ('jr', 'sr', 'ii', 'iii', 'iv', 'v', 'mr', 'mrs', 'ms')]
    a = tokens(alias); variants = [name]
    nickname = re.search(r'"([^"]+)"\s*(.+)$', name)
    if nickname: variants.append(f'{nickname[1]} {nickname[2]}')
    for variant in variants:
        b = tokens(variant)
        if len(a) < 2 or len(b) < 2 or a[0] != b[0] or a[-1] != b[-1]: continue
        index = 0
        for word in b:
            if index < len(a) and (a[index] == word or len(a[index]) == 1 and word.startswith(a[index])):
                index += 1
        if index == len(a): return True
    return False


def parse_house_roster(html, state, state_name, seats, reviewed_on):
    day = date.fromisoformat(reviewed_on)
    if day.year != 2026 or not isinstance(seats, int) or not 1 <= seats <= 52:
        raise ValueError('Invalid 2026 House roster universe')
    if f'{state_name} 2026 General Election' not in html \
            or 'Candidates for office appear on this page in' not in html \
            or 'certified to appear on the ballot' not in html:
        raise ValueError('Unknown state/cycle or missing source status legend')
    source_url = f'https://www.thegreenpapers.com/G26/{state}'
    parser = RosterTable(); parser.feed(html)
    races = {}; current = None
    for cells in parser.rows:
        if not cells: continue
        first = cells[0]; label = _text(first)
        if any(c['section'] for c in cells) or first['attrs'].get('class') == 'off':
            current = None
        election = [im.get('alt', '') for c in cells for im in c['images']
                    if 'up for' in im.get('alt', '')]
        if election:
            district = re.match(r'^CD (\d+)\b', label)
            if (district or label.startswith('At-Large')) and not any('special' in e for e in election):
                number = int(district[1]) if district else 0
                if (seats == 1 and number != 0) or (seats > 1 and not 1 <= number <= seats):
                    raise ValueError('Noncanonical/out-of-range House district')
                rid = f'USA:{state}:house:{number:02d}'
                if rid in races: raise ValueError('Duplicate regular House office')
                current = {'race_id': rid, 'state': state, 'office': 'house', 'district': f'{number:02d}',
                    'election_date': '2026-11-03', 'status': 'reported_general_matchup',
                    'coverage': 'reported_active_candidate_listing',
                    'source_role': 'reviewed_secondary_nominee_listing', 'source_url': source_url,
                    'reviewed_on': reviewed_on, 'candidates': [], 'unconfirmed_candidates': [],
                    'excluded_candidates': [], 'absent_parties': [],
                    'limitations_ko': '공개 선거 명부가 선거당국 확인을 보고한 후보만 표시합니다. 공식 투표용지 인증·전체 기명 후보 완결·당선 결과를 뜻하지 않습니다.'}
                if state == 'LA':
                    current['election_system'] = 'all_party_general_with_majority_runoff'
                    current['limitations_ko'] += ' 루이지애나는 11월 전정당 선거이며 정당별 후보가 복수일 수 있습니다.'
                races[rid] = current
            else: current = None
        if current is None: continue
        line = ' '.join(_text(c) for c in cells).strip()
        if 'Candidate list (' in line:
            if current.get('source_candidate_count') is not None:
                raise ValueError('Unexpected nested candidate list')
            match = re.fullmatch(r'Candidate list \((\d+)(?:, (\d+) write-ins?)?\) - 120th Congress', line)
            if not match: raise ValueError('Regular House candidate list contract changed')
            current['source_candidate_count'] = int(match[1]) + int(match[2] or 0)
        if len(cells) != 6 or not any(i.get('alt') == 'Candidate' for i in cells[1]['images']): continue
        name = _name(cells[5]); reported_party = _text(cells[2])
        candidate = {'name': name, 'party': _party(reported_party), 'reported_party': reported_party,
                     'candidate_id': None, 'source_url': source_url,
                     'ballot_access': 'write_in' if reported_party.startswith('Write-in') else 'reported_ballot_candidate'}
        ids = [a for a in cells[0]['anchors'] if re.fullmatch(r'H[0-9A-Z]{8}', a)]
        if len(ids) > 1: raise ValueError('Ambiguous reported candidate ID')
        if ids: candidate['reported_fec_id'] = ids[0]
        if cells[5]['strike']: bucket = 'excluded_candidates'; candidate['source_status'] = 'inactive'
        elif cells[5]['italic']: bucket = 'unconfirmed_candidates'; candidate['source_status'] = 'authority_confirmation_not_reported'
        else: bucket = 'candidates'; candidate['source_status'] = 'authority_confirmation_reported_by_secondary_source'
        if any(c['name'] == name for c in current[bucket]): raise ValueError('Duplicate candidate identity')
        current[bucket].append(candidate)
    expected = {f'USA:{state}:house:{n:02d}' for n in (range(1, seats + 1) if seats > 1 else [0])}
    if set(races) != expected: raise ValueError('Incomplete regular House district universe')
    for race in races.values():
        if not race['candidates']: raise ValueError('No confirmed reported general candidate')
        actual = len(race['candidates']) + len(race['unconfirmed_candidates'])
        if race.get('source_candidate_count') != actual:
            raise ValueError('Candidate count/markup does not reconcile')
        race['unconfirmed_candidate_count'] = len(race['unconfirmed_candidates'])
        # A missing major party in a secondary list is never proof of unopposed election.
        race['unopposed_status'] = 'not_verified'
    modified = re.search(r'Last Modified:.*?new Date\(\s*(\d+)\s*\)', html, re.S)
    updated_at = datetime.fromtimestamp(int(modified[1]) / 1000, timezone.utc).isoformat() if modified else None
    if updated_at and date.fromisoformat(updated_at[:10]) > day:
        raise ValueError('Future source update')
    provenance = {'state': state, 'source_url': source_url, 'source_role': 'reviewed_secondary_nominee_listing',
                  'reviewed_on': reviewed_on, 'source_updated_at': updated_at,
                  'sha256': sha256(html.encode()).hexdigest(), 'house_races': len(races),
                  'confirmed_reported_candidates': sum(len(r['candidates']) for r in races.values()),
                  'unconfirmed_candidates': sum(len(r['unconfirmed_candidates']) for r in races.values())}
    return races, provenance


def merge_national_house(snapshot, catalog, documents, reviewed_on):
    """Require all 50 sources / 435 seats before replacing a display snapshot."""
    from .federal_matchups import validate_snapshot, STATES
    validate_snapshot(snapshot, reviewed_on)
    if catalog.get('cycle') != 2026 or set(catalog['states']) != STATES \
            or set(documents) != STATES or sum(s['house_seats'] for s in catalog['states'].values()) != 435:
        raise ValueError('Incomplete nationwide House collection')
    result = deepcopy(snapshot); sources = []
    for state, row in sorted(catalog['states'].items()):
        races, provenance = parse_house_roster(documents[state], state, row['name'], row['house_seats'], reviewed_on)
        sources.append(provenance)
        for rid, race in races.items():
            previous = result['races'].get(rid)
            if previous and (previous['status'] == 'certified_ballot' \
                    or previous.get('source_role') == 'state_election_agency' \
                    or previous['coverage'] in ('complete_ballot', 'certified_major_party_field', 'complete_active_agency_listing')):
                for candidate in previous['candidates']:
                    matches = [c for c in race['candidates'] if c['party'] == candidate['party']
                               and same_source_name(candidate['name'], c['name'])]
                    if len(matches) == 1 and matches[0].get('reported_fec_id'):
                        candidate['reported_fec_id'] = matches[0]['reported_fec_id']
                        candidate['secondary_identifier_source_url'] = race['source_url']
                continue
            result['races'][rid] = race
    result['reviewed_on'] = reviewed_on
    result['house_universe'] = {s: r['house_seats'] for s, r in catalog['states'].items()}
    result['source_snapshots'] = [s for s in result.get('source_snapshots', [])
                                  if s.get('source_role') != 'reviewed_secondary_nominee_listing'] + sources
    note = '하원 50주·435구 연결. 주별 공식 명부와 The Green Papers의 선거당국 확인 보고 명부를 구분하며 미확인·탈락 후보는 표시 후보에서 제외합니다.'
    if note not in result['limitations_ko']: result['limitations_ko'].append(note)
    validate_snapshot(result, reviewed_on)
    return result


def attach_reviewed_poll_aliases(snapshot, polls):
    """Review existing identities against source names, with no fuzzy surname join.

    Only an exact ordered name contained in the full source name, or the source's
    explicit quoted nickname, can supply an alias. Party and unique identity in
    that race must agree. Changed nominees never inherit a former nominee's poll.
    """
    result = deepcopy(snapshot)
    for rid, race in result['races'].items():
        if race.get('source_role') not in ('reviewed_secondary_nominee_listing', 'state_election_agency'): continue
        poll = polls.get('races', {}).get(rid, {})
        if poll.get('schedule_status') != 'reported_general_matchup': continue
        for name in poll.get('required_candidates', []):
            party = poll.get('candidates', {}).get(name, {}).get('party')
            party = 'REP' if party == 'GOP' else party
            matched = [c for c in race['candidates'] if c['party'] == party and any(same_source_name(name, identity)
                       for identity in [c['name'], c.get('reported_legal_name', '')])]
            if len(matched) == 1 and name != matched[0]['name']:
                candidate = matched[0]
                aliases = candidate.setdefault('poll_name_aliases', [])
                if name not in aliases: aliases.append(name)
                candidate['poll_alias_basis'] = 'existing_reviewed_identity_and_exact_source_name_or_quoted_nickname'
    return result


def merge_official_house_reviews(snapshot, reviews, reviewed_on):
    from .federal_matchups import validate_snapshot
    if reviews.get('schema') != 'usa_official_house_reviews_v1' or reviews.get('cycle') != 2026 \
            or date.fromisoformat(reviews['reviewed_on']) > date.fromisoformat(reviewed_on):
        raise ValueError('Unreviewed official House overrides')
    result = deepcopy(snapshot)
    grouped = {}
    for rid, race in reviews['races'].items():
        if race['office'] != 'house' or race.get('source_role') != 'state_election_agency':
            raise ValueError('Non-agency/non-House override')
        grouped.setdefault(race['state'], set()).add(rid)
        row = deepcopy(race)
        for candidate in row['candidates']:
            matches = [c for c in snapshot['races'][rid]['candidates'] if c['party'] == candidate['party']
                       and same_source_name(candidate['name'], c['name'])]
            if len(matches) == 1 and matches[0].get('reported_fec_id'):
                candidate['reported_fec_id'] = matches[0]['reported_fec_id']
                candidate['secondary_identifier_source_url'] = snapshot['races'][rid]['source_url']
        result['races'][rid] = row
    for state, ids in grouped.items():
        seats = snapshot['house_universe'][state]
        expected = {f'USA:{state}:house:{n:02d}' for n in (range(1, seats + 1) if seats > 1 else [0])}
        if ids != expected: raise ValueError('Partial state agency override')
    result['official_house_review_sources'] = deepcopy(reviews.get('sources', []))
    validate_snapshot(result, reviewed_on)
    return result


def attach_verified_finance_ids(snapshot, finance_races):
    """Source-cited ID plus existing FEC race/name/party; never use finance as nominee list."""
    result = deepcopy(snapshot)
    by_race = {}
    for race in finance_races:
        if race.get('cycle') != 2026 or race.get('office') != 'house': continue
        records = by_race.setdefault(race['race_id'], {})
        for row in race.get('candidates', []):
            record = records.setdefault(row['candidate_id'], {'names': set(), 'parties': set()})
            record['names'].update(row.get('reported_names') or [row['name']])
            record['parties'].update('GRN' if p == 'GRE' else p for p in row.get('reported_parties', []))
    for rid, race in result['races'].items():
        for candidate in race['candidates']:
            reported_id = candidate.get('reported_fec_id')
            if not isinstance(reported_id, str) or not re.fullmatch(r'H[0-9A-Z]{8}', reported_id): continue
            record = by_race.get(rid, {}).get(reported_id)
            if not record or candidate['party'] not in record['parties']: continue
            names = []
            for name in record['names']:
                parts = name.split(',', 1)
                names.append(f'{parts[1].strip()} {parts[0].strip()}' if len(parts) == 2 else name)
            if any(same_source_name(name, identity) for name in names
                   for identity in [candidate['name'], candidate.get('reported_legal_name', ''), *candidate.get('finance_name_aliases', [])]):
                candidate['candidate_id'] = reported_id
                candidate['candidate_id_basis'] = 'source_cited_id_corroborated_by_existing_fec_race_name_party'
    return result


def apply_reviewed_aliases(snapshot, reviews, as_of):
    """Exceptional source-backed spellings; exact race/name/party/cited ID gate."""
    from .federal_matchups import _source_url
    if reviews.get('schema') != 'usa_candidate_identity_aliases_v1' or reviews.get('cycle') != 2026 \
            or date.fromisoformat(reviews['reviewed_on']) > date.fromisoformat(as_of):
        raise ValueError('Unreviewed candidate aliases')
    result = deepcopy(snapshot)
    for review in reviews['records']:
        if date.fromisoformat(review['reviewed_on']) > date.fromisoformat(as_of): raise ValueError('Future candidate alias')
        _source_url(review['official_source_url']); _source_url(review['roster_source_url'])
        race = result['races'][review['race_id']]
        candidates = [c for c in race['candidates'] if c['name'] == review['candidate_name']
                      and c['party'] == review['party'] and c.get('reported_fec_id') == review['reported_fec_id']]
        if len(candidates) != 1: raise ValueError('Changed candidate identity needs alias review')
        candidate = candidates[0]
        for field in ('poll_name_aliases', 'finance_name_aliases'):
            candidate[field] = sorted(set(candidate.get(field, []) + review['aliases']))
        candidate['alias_review_source_url'] = review['official_source_url']
        candidate['alias_reviewed_on'] = review['reviewed_on']
    return result
