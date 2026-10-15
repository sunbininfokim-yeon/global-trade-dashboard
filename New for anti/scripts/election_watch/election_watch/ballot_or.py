"""Read the official candidate-list page, never the optional campaign statements."""
import re


def parse_list_page(text, source_url):
    if not re.fullmatch(r'https://sos\.oregon\.gov/elections/Voters-Pamphlet/Documents/VP_G26-Book\d+_web\.pdf', source_url):
        raise ValueError('Not an Oregon 2026 general pamphlet')
    text = text.replace('\u00ad', '').replace('\u00a0', ' ')
    if not all(s in text for s in ('List of Candidates & Measures', 'Partisan Candidates',
            'complete listing of federal and state candidates', 'November 3, 2026')):
        raise ValueError('Not the complete official general candidate-list page')
    lines = [' '.join(s.split()) for s in text.splitlines() if s.strip()]
    start = lines.index('US Senator') + 1
    stop = next(i for i in range(start, len(lines)) if lines[i] in
                ('State Senator', 'State Representative', 'Nonpartisan Candidates'))
    office = 'senate'; district = None; result = {}; pending = None
    for line in lines[start:stop]:
        if line == 'US Representative':
            office = 'house'; district = None; continue
        if line == 'Governor':
            office = 'governor'; district = None; continue
        number = re.fullmatch(r'([1-6])(?:st|nd|rd|th) District', line)
        if number:
            if office != 'house' or pending: raise ValueError('Changed Oregon district section')
            district = f'{int(number[1]):02d}'; continue
        affiliations = [s.strip() for s in line.split(',')]
        if all(s in {'Democrat', 'Republican', 'Working Families', 'Independent',
                     'Libertarian', 'Pacific Green', 'Progressive'} for s in affiliations):
            if not pending or office == 'house' and district is None:
                raise ValueError('Missing Oregon candidate/district')
            party = ('DEM' if 'Democrat' in affiliations else 'REP' if 'Republican' in affiliations
                     else 'LIB' if affiliations[0] == 'Libertarian' else 'PRO'
                     if affiliations[0] == 'Progressive' else 'IND' if affiliations[0] == 'Independent'
                     else ('GRE' if office == 'governor' else 'GRN') if affiliations[0] == 'Pacific Green' else None)
            if party is None: raise ValueError('Unreviewed Oregon party affiliation')
            rid = f'USA:OR:{office}' + (f':{district}' if office == 'house' else '')
            result.setdefault(rid, []).append({'name': pending.rstrip('*').strip(), 'party': party,
                'reported_party': line, 'source_url': source_url,
                'pamphlet_statement_submitted': not pending.endswith('*')})
            pending = None
        else:
            if pending: raise ValueError('Changed Oregon candidate/party layout')
            pending = line
    if pending or len(result.get('USA:OR:senate', [])) != 4 or len(result.get('USA:OR:governor', [])) != 3:
        raise ValueError('Changed Oregon statewide field')
    return result


def merge_lists(pages):
    combined = {}
    for page in pages:
        parsed = parse_list_page(page['text'], page['source_url'])
        for rid, candidates in parsed.items():
            if rid in combined:
                identities = lambda rows: [(c['name'], c['party'], c['reported_party']) for c in rows]
                if identities(combined[rid]) != identities(candidates):
                    raise ValueError('Conflicting official Oregon county books')
            else:
                combined[rid] = candidates
    expected = {'USA:OR:senate', 'USA:OR:governor'} | {f'USA:OR:house:{n:02d}' for n in range(1, 7)}
    if set(combined) != expected or sum(len(c) for rid, c in combined.items() if ':house:' in rid) != 14:
        raise ValueError('Incomplete Oregon six-district official universe')
    return combined
