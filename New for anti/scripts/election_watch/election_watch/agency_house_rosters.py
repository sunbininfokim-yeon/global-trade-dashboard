"""Reviewed general-candidate adapters; never primary filing lists or FEC registrants."""
import csv
from io import StringIO
import re

from .house_rosters import RosterTable, _text


def _finish(state, seats, rows, url, reviewed_on, certified=False):
    expected = {f'{n:02d}' for n in (range(1, seats + 1) if seats > 1 else [0])}
    if set(rows) != expected or any(not candidates for candidates in rows.values()):
        raise ValueError('Incomplete official general House listing')
    result = {}
    for district, candidates in rows.items():
        rid = f'USA:{state}:house:{district}'
        result[rid] = {'race_id': rid, 'state': state, 'office': 'house', 'district': district,
            'election_date': '2026-11-03', 'reviewed_on': reviewed_on, 'source_url': url,
            'source_role': 'state_election_agency', 'status': 'certified_ballot' if certified else 'reported_general_matchup',
            'coverage': 'complete_ballot' if certified else 'complete_active_agency_listing',
            'candidates': [{'name': c[0], 'party': c[1], 'reported_party': c[2] if len(c) > 2 else c[1],
                            'candidate_id': None, 'source_url': url}
                           for c in sorted(set(candidates))],
            'absent_parties': [party for party in ('DEM', 'REP') if not any(c[1] == party for c in candidates)],
            'limitations_ko': '공식 본선 명부의 현재 후보입니다. 당선 결과 또는 향후 기명 후보까지 완결되었다는 뜻이 아닙니다.'}
    return result


def parse_nc_csv(text, source_url, reviewed_on):
    reader = csv.DictReader(StringIO(text.lstrip('\ufeff')))
    if not {'election_dt', 'contest_name', 'name_on_ballot', 'party_candidate'}.issubset(reader.fieldnames or []):
        raise ValueError('NC official candidate schema changed')
    rows = {}; legal_names = {}
    for row in reader:
        match = re.fullmatch(r'US HOUSE OF REPRESENTATIVES DISTRICT (\d{2})', row['contest_name'])
        if not match or row['election_dt'] != '11/03/2026': continue
        if not row['name_on_ballot'].strip() or not row['party_candidate']: raise ValueError('NC incomplete candidate')
        party = 'GRN' if row['party_candidate'] == 'GRE' else row['party_candidate']
        rows.setdefault(match[1], []).append((row['name_on_ballot'].strip(), party))
        legal = ' '.join(row.get(k, '').strip() for k in ('first_name', 'middle_name', 'last_name', 'name_suffix_lbl')).strip()
        if legal: legal_names[(match[1], row['name_on_ballot'].strip(), party)] = legal
    result = _finish('NC', 14, rows, source_url, reviewed_on)
    for race in result.values():
        for candidate in race['candidates']:
            legal = legal_names.get((race['district'], candidate['name'], candidate['party']))
            if legal: candidate['reported_legal_name'] = legal
    return result


def parse_ia_layout(text, source_url, reviewed_on):
    if 'November 3, 2026 General Election' not in text or 'Candidate List' not in text:
        raise ValueError('Not IA general list')
    rows = {}; district = None
    parties = {'Republican': 'REP', 'Democratic': 'DEM', 'Libertarian': 'LIB', 'No Party': 'IND'}
    for line in text.splitlines():
        match = re.match(r'United States Representative District (\d+)\s{2,}', line.strip())
        if match:
            district = f'{int(match[1]):02d}'; rows.setdefault(district, [])
            line = line.strip()[match.end():]
        elif line.strip().startswith('Governor'): district = None
        if district is None: continue
        cells = re.split(r'\s{2,}', line.strip())
        if len(cells) >= 3 and cells[0] in parties:
            rows[district].append((cells[1], parties[cells[0]]))
    return _finish('IA', 4, rows, source_url, reviewed_on)


def parse_mo_layout(text, source_url, reviewed_on):
    if not all(t in text for t in ('General Election on Tuesday, November 3, 2026', 'certify', 'REPUBLICAN CANDIDATES')):
        raise ValueError('Not MO general certification')
    rows = {}; current_party = None; congress = False
    parties = {'REPUBLICAN': 'REP', 'DEMOCRATIC': 'DEM', 'LIBERTARIAN': 'LIB', 'INDEPENDENT': 'IND'}
    for raw in text.splitlines():
        line = raw.strip()
        party = re.fullmatch(r'(REPUBLICAN|DEMOCRATIC|LIBERTARIAN|INDEPENDENT) CANDIDATES', line)
        if party: current_party = parties[party[1]]; congress = False
        if line == 'For U.S. Representative': congress = True; continue
        if line.startswith('For '): congress = False
        candidate = re.fullmatch(r'District (\d+), (.+)', line)
        if congress and current_party and candidate:
            rows.setdefault(f'{int(candidate[1]):02d}', []).append((candidate[2], current_party))
    return _finish('MO', 8, rows, source_url, reviewed_on, certified=True)


def parse_sd_html(html, source_url, reviewed_on):
    if '11/3/2026' not in html or 'General' not in html: raise ValueError('Not SD general list')
    parser = RosterTable(); parser.feed(html); candidates = []
    for cells in parser.rows:
        if len(cells) >= 16 and _text(cells[0]) == 'United States Representative':
            if _text(cells[13]) != 'Active' or _text(cells[14]) != 'General' or not _text(cells[15]).startswith('11/3/2026 '):
                continue
            candidates.append((_text(cells[1]), _text(cells[2])))
    return _finish('SD', 1, {'00': candidates}, source_url, reviewed_on)


def parse_de_html(html, source_url, reviewed_on):
    if '2026' not in html or 'General' not in html: raise ValueError('Not DE general list')
    parser = RosterTable(); parser.feed(html); candidates = []
    parties = {'Democratic': 'DEM', 'Republican': 'REP', 'Libertarian': 'LIB', 'Green': 'GRN'}
    for cells in parser.rows:
        if len(cells) == 6 and _text(cells[0]) == 'Representative in Congress' and _text(cells[4]) == 'Qualified':
            name = re.split(r'\s+(?:Residential Address:|Mailing Address:|Phone #|Website:)', _text(cells[3]), maxsplit=1)[0]
            if not name or _text(cells[2]) not in parties: raise ValueError('DE candidate schema changed')
            candidates.append((name, parties[_text(cells[2])]))
    return _finish('DE', 1, {'00': candidates}, source_url, reviewed_on)


def parse_nj_layout(text, source_url, reviewed_on):
    if 'Official List' not in text or 'Candidates for House of Representatives' not in text \
            or not re.search(r'For GENERAL ELECTION\s+11/03/202\s*6', text):
        raise ValueError('Not NJ official general list')
    ordinals = dict(zip(('First Second Third Fourth Fifth Sixth Seventh Eighth Ninth Tenth Eleventh Twelfth').split(), range(1, 13)))
    parties = {'Democratic': 'DEM', 'Republican': 'REP', 'Green Party': 'GRN', 'INDEPENDENT': 'IND'}
    rows = {}; district = None
    for raw in text.splitlines():
        heading = re.match(r'(\w+) Congressional District:', raw.strip())
        if heading:
            if heading[1] not in ordinals: raise ValueError('Unknown NJ congressional ordinal')
            district = f'{ordinals[heading[1]]:02d}'; rows.setdefault(district, [])
        cells = re.split(r'\s{2,}', raw.strip())
        if district and len(cells) >= 3 and cells[0].isupper() and re.search('[A-Z]', cells[0]) \
                and not any(w in cells[0] for w in ('CONGRESSIONAL', 'COUNTIES', 'NAME', 'ELECTION')) \
                and re.search(r'\d|P\.?O\.? BOX', cells[1]):
            rows[district].append((cells[0].rstrip(' *'), parties.get(cells[2], 'OTH'), cells[2]))
    return _finish('NJ', 12, rows, source_url, reviewed_on, certified=True)
