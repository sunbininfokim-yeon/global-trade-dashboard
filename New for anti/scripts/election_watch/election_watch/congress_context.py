"""Official House roster/vacancies and explicitly evidenced swing-seat rules."""
from collections import Counter
from datetime import datetime
from html import unescape
import re
import xml.etree.ElementTree as ET

MEMBERS_URL = 'https://clerk.house.gov/xml/lists/MemberData.xml'
VACANCIES_URL = 'https://clerk.house.gov/Members/ViewVacancies'
PARTIES = {'R': ('GOP', 'Republican'), 'D': ('DEM', 'Democratic'), 'I': ('IND', 'Independent')}
DELEGATES = {'AS', 'DC', 'GU', 'MP', 'PR', 'VI'}


def house_context(xml, vacancy_html):
    root = ET.fromstring(xml)
    members, vacancies, seen = [], [], set()
    for entry in root.findall('./members/member'):
        seat = entry.findtext('statedistrict') or ''
        if not re.fullmatch(r'[A-Z]{2}\d{2}', seat):
            raise ValueError('Unexpected House seat code')
        if seat in seen:
            raise ValueError('Duplicate House seat')
        seen.add(seat)
        state, district = seat[:2], seat[2:]
        info = entry.find('member-info')
        state = info.find('state').get('postal-code')
        name = info.findtext('namelist')
        if name:
            party = info.findtext('party')
            if party not in PARTIES:
                raise ValueError('Unknown House party code')
            abbr, label = PARTIES[party]
            members.append({'bioguideId': info.findtext('bioguideID'), 'name': name,
                'party': label, 'abbr': abbr, 'state': info.findtext('state/state-fullname'),
                'state_abbr': state, 'district': int(district), 'chamber': 'house',
                'is_delegate': state in DELEGATES})
        else:
            pred = entry.find('predecessor-info')
            if pred is None:
                raise ValueError('Vacancy predecessor unavailable')
            date = pred.find('pred-vacate-date').get('date')
            # Match the exact vacancy link, then its own Special Election block.
            # Never borrow a date from another district or from a filled vacancy.
            block = re.search(r'href="/members/' + seat + r'/vacancy"(.*?)(?=<p class="border_bottom"|$)', vacancy_html, re.S | re.I)
            special, date_status = None, 'not_verified'
            if block:
                text = unescape(re.sub(r'<[^>]+>', ' ', block[1]))
                match = re.search(r'Special Election\s+(Date TBD|[A-Za-z]+\s+\d{1,2},\s+\d{4})', text)
                if match:
                    date_status = 'unannounced' if match[1] == 'Date TBD' else 'announced'
                    if date_status == 'announced':
                        special = datetime.strptime(match[1], '%B %d, %Y').date().isoformat()
            vacancies.append({'chamber': 'house', 'state': state, 'district': district,
                'prior_party_abbr': PARTIES[pred.findtext('pred-party')][0],
                'prior_member': pred.findtext('pred-official-name'),
                'vacated_on': datetime.strptime(date, '%Y%m%d').date().isoformat(),
                'special_election_date': special, 'special_election_date_status': date_status,
                'note_ko': '공식 하원 공석. 보궐선거일 미발표.' if date_status == 'unannounced' else '공식 하원 공석. 일정 출처 상태를 확인하세요.',
                'source_urls': [MEMBERS_URL, VACANCIES_URL]})
    voting = [m for m in members if not m['is_delegate']]
    if len(voting) + len([v for v in vacancies if v['state'] not in DELEGATES]) != 435:
        raise ValueError('House seats do not reconcile to 435')
    return {'members': members, 'vacancies': vacancies,
        'house_source_published_on': datetime.strptime(root.get('publish-date'), '%B %d, %Y').date().isoformat(),
        'house_summary': {'house_voting_seats': 435, 'house_voting_members': len(voting),
            'house_vacancies': len([v for v in vacancies if v['state'] not in DELEGATES]),
            'house_by_party': dict(Counter(m['abbr'] for m in voting)),
            'house_delegates_by_party': dict(Counter(m['abbr'] for m in members if m['is_delegate'])),
            'house_roster_rows_including_delegates': len(members)}}


def swing_seats(history):
    result = []
    for seat in history['seats']:
        elections = sorted(seat['elections'], key=lambda e: e['year'])
        evidence, basis = None, None
        last = elections[-1]
        if seat.get('geography_comparable') and len(elections) >= 3:
            recent = elections[-3:]
            flips = sum(a['party_abbr'] != b['party_abbr'] for a,b in zip(recent,recent[1:]))
            if flips >= 2:
                evidence = 'two_party_changes_last_three_general_elections'
                basis = '최근 3회 본선 당선 정당: ' + ' → '.join(f"{e['year']} {e['party_abbr']}" for e in recent) + ' (2회 교체·동일 주 전체 경계)'
        presidential = last.get('presidential_party_abbr')
        if presidential and {presidential,last['party_abbr']} == {'DEM','GOP'}:
            evidence = 'presidential_congressional_split_ticket'
            basis = f"{last['year']} 대선 {presidential} 우세 · {seat['chamber']} {last['party_abbr']} 당선 (동일 주 전체 공식 결과)"
        if evidence:
            result.append({k:seat[k] for k in ('chamber','state','district')} | {
                'party_abbr': last['party_abbr'], 'basis_ko': basis, 'criterion': evidence,
                'party_basis': 'last_verified_general_election_winner', 'evidence': elections,
                'history_through': last['year'], 'prediction': False})
    return result
