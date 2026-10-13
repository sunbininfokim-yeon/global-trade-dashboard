"""Read the statewide VoteWA general listing, without contact details."""
from html.parser import HTMLParser
import re

URL = 'https://voter.votewa.gov/CandidateList.aspx?c=99&e=899'


def parse_general(html):
    class Listing(HTMLParser):
        def __init__(self):
            super().__init__(); self.rows = []; self.row = None; self.cell = None
            self.select = None; self.selected = {}
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'select': self.select = attrs.get('id')
            if tag == 'option' and self.select and 'selected' in attrs:
                self.selected[self.select] = attrs.get('value')
            if tag == 'tr': self.row = []
            if tag in ('td', 'th'): self.cell = []
        def handle_data(self, text):
            if self.cell is not None: self.cell.append(text)
        def handle_endtag(self, tag):
            if tag == 'select': self.select = None
            if tag in ('td', 'th') and self.cell is not None:
                if self.row is not None:
                    self.row.append(' '.join(' '.join(self.cell).split()))
                self.cell = None
            if tag == 'tr' and self.row is not None:
                self.rows.append(self.row); self.row = None
    parser = Listing(); parser.feed(html)
    if parser.selected.get('ddlElection') != '899' or parser.selected.get('ddlCounty') != '99':
        raise ValueError('Not the statewide 2026 general election listing')
    result = {}
    for row in parser.rows:
        if not row or row[0].casefold() != 'congressional': continue
        if len(row) != 14 or row[2:5] != ['U.S. Representative', 'Regular', '2'] or row[11] != 'Active':
            raise ValueError('WA congressional listing schema/status changed')
        district = re.fullmatch(r'Congressional District (\d+)', row[1], re.I)
        party = {'DEMOCRATIC': 'DEM', 'REPUBLICAN': 'REP'}.get(row[10])
        if not district or not party or not row[5] or row[13] not in ('1', '2'):
            raise ValueError('WA candidate/district/party requires review')
        key = f'USA:WA:house:{int(district[1]):02d}'
        result.setdefault(key, []).append({'name': row[5], 'party': party,
            'ballot_order': int(row[13]), 'source_url': URL})
    if set(result) != {f'USA:WA:house:{n:02d}' for n in range(1, 11)}:
        raise ValueError('WA ten-district universe changed')
    for candidates in result.values():
        if len(candidates) != 2 or {c['ballot_order'] for c in candidates} != {1, 2} or len({c['name'] for c in candidates}) != 2:
            raise ValueError('WA top-two field changed')
        candidates.sort(key=lambda c: c['ballot_order'])
    return result
