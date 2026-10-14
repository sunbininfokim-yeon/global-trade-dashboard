"""Public Florida agency listing adapter; primary and general status are distinct."""
from datetime import date
import hashlib
from html import unescape
import re
from urllib.request import Request, urlopen

from .polls import require

URL = 'https://dos.elections.myflorida.com/candidates/CanList.asp?elecid=20261103-GEN&status=All'
LAW_URL = 'https://leg.state.fl.us/STATUTES/index.cfm?App_mode=Display_Statute&URL=0100-0199%2F0101%2FSections%2F0101.151.html'


def cell_text(html):
    return ' '.join(unescape(re.sub(r'<[^>]*>', '', html)).split())


def parse_florida(html, as_of):
    require('Candidate Listing for 2026 General Election' in cell_text(html), 'Florida election changed')
    require(date.fromisoformat(as_of).year == 2026, 'Florida adapter cycle must be reviewed')
    races = {}
    for heading, office in [('United States Senator', 'senate'),
                            ('United States Representative', 'house'), ('Governor', 'governor')]:
        # Search the visible office heading, not the same text in form options.
        pattern = r'<(?:h[1-6]|b|strong)\b[^>]*>\s*' + heading + r'\s*</(?:h[1-6]|b|strong)>'
        match = re.search(pattern, html, re.I)
        require(match is not None, 'Florida office heading changed')
        table = re.search(r'<table\b[^>]*class="results"[^>]*>(.*?)</table>', html[match.end():], re.S | re.I)
        require(table is not None, 'Florida result table changed')
        district = None
        seen = set()
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table.group(1), re.S | re.I):
            if re.search(r'<th\b', row, re.I):
                continue
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
            if not cells:
                continue
            require(len(cells) == (5 if office == 'house' else 4), 'Florida columns changed')
            if office == 'house':
                reported = cell_text(cells.pop(0))
                if reported:
                    require(re.fullmatch(r'\d{1,2}', reported) is not None, 'Florida district changed')
                    district = f'{int(reported):02}'
                require(district is not None and 1 <= int(district) <= 28, 'Florida district universe')
            name, status, primary, general = map(cell_text, cells)
            require(status in ('Qualified', 'Unopposed', 'Defeated', 'Withdrawn',
                               'Did Not Qualify', 'Transferred to Local', 'Elected'), 'Florida candidate status changed')
            if status not in ('Qualified', 'Unopposed'):
                continue
            match = re.match(r'(.+?),\s*(.+?)\s*\(([A-Z]+)\)', name)
            require(match is not None, 'Florida candidate name changed')
            last, first, party = match.groups()
            display = f'{first} {last}'
            party = {'NPA': 'IND', 'LPF': 'LIB'}.get(party, party)
            identity = (district, display, party)
            require(identity not in seen, 'Florida duplicate candidate')
            seen.add(identity)
            rid = f'USA:FL:{office}' + (f':{district}' if district else '')
            race = races.setdefault(rid, {'race_id': rid, 'state': 'FL', 'office': office,
                'district': district, 'election_date': '2026-11-03',
                'reviewed_on': as_of, 'source_url': URL, 'source_role': 'state_election_agency',
                'coverage': 'complete_active_agency_listing', 'candidates': [],
                'official_general_unopposed': False,
                'limitations_ko': '주 선관위 후보 추적 명부의 현재 Qualified/Unopposed 전체. 선관위 자체가 참고 명부로 안내하며 결과 인증 문서가 아닙니다.'})
            race['candidates'].append({'name': display, 'party': party, 'candidate_id': None,
                'source_url': URL, 'agency_status': status,
                'primary_status': primary, 'general_status': general})
            if general == 'Unopposed':
                race['official_general_unopposed'] = True
                race['no_vote_law_url'] = LAW_URL
        require(seen, 'Florida empty office listing')
    require(len(races) == 30 and {r['district'] for r in races.values() if r['office'] == 'house'}
            == {f'{i:02}' for i in range(1, 29)}, 'Florida incomplete race listing')
    for race in races.values():
        require(not race['official_general_unopposed'] or len(race['candidates']) == 1,
                'Florida contradictory general unopposed listing')
    return {'races': races, 'source_url': URL,
            'source_sha256': hashlib.sha256(html.encode()).hexdigest(), 'checked_on': as_of}


def fetch_florida(as_of):
    with urlopen(Request(URL, headers={'User-Agent': 'ElectionWatch/2.0'}), timeout=25) as response:
        require(response.url == URL, 'Florida unexpected redirect')
        raw = response.read(4_000_001)
    require(len(raw) <= 4_000_000, 'Florida response exceeds budget')
    return parse_florida(raw.decode('utf-8'), as_of)
