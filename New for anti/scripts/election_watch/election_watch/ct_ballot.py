"""Read reviewed CT guide sections; fusion ballot lines are one person."""
from datetime import date
import re
from .polls import require

URL = 'https://portal.ct.gov/-/media/sots/electionservices/voter_guide/2026/2026_voter_guide_final.pdf?rev=4eaa300798fe46f9a5722765c5e7226d&hash=59A37CA0EF6C8402D58E1E37B12DE510'
PERIOD_URL = 'https://portal.ct.gov/-/media/sots/electionservices/calendars/2026-elections/2026-election-calendar-122325.pdf?rev=340f2bcacc9748c1a2ed8f49d1774f52&hash=471ECCC3D26999C2D53BB5636927C0EB'
PARTIES = {'D':'DEM', 'R':'REP', 'I':'OTH', 'WFP':'OTH', 'Green Party':'GRN'}


def parse_sections(cover, house, governor, reviewed_on):
    """Explicit PDF section extraction, not an installed candidate API adapter."""
    house='\n'.join(line.strip() for line in house.splitlines())
    governor='\n'.join(line.strip() for line in governor.splitlines())
    require('2026' in cover and 'Connecticut' in cover,
            'Connecticut guide year/state changed')
    require(date.fromisoformat(reviewed_on) >= date(2026,8,12),
            'Connecticut review predates general period')
    require('Connecticut has five' in house and 'Lt. Governor' in governor,
            'Connecticut guide section boundary changed')
    found = {}; district = None
    for line in house.splitlines():
        line = line.strip()
        m = re.fullmatch(r'District (\d+)',line)
        if m:
            require(1 <= int(m[1]) <= 5, 'Connecticut federal district changed')
            district = f'{int(m[1]):02d}'
        elif re.fullmatch(r'.+?\s+\([^()]+\)(?:\s*\([^()]+\))*',line):
            require(district is not None, 'Connecticut candidate outside district')
            _add(found, 'house', district, line, reviewed_on)
    section = governor.split('Governor\n',1)
    require(len(section)==2, 'Connecticut governor heading missing')
    section = section[1].split('Lt. Governor',1)[0]
    for line in section.splitlines():
        line=line.strip()
        if re.fullmatch(r'.+?\s+\([^()]+\)(?:\s*\([^()]+\))*',line):
            _add(found,'governor',None,line,reviewed_on)
    expected={f'USA:CT:house:{n:02d}' for n in range(1,6)}|{'USA:CT:governor'}
    require(set(found)==expected and sum(len(r['candidates']) for r in found.values())==15
            and len(found['USA:CT:governor']['candidates'])==2,
            'Connecticut reviewed guide universe changed')
    for race in found.values():
        race.update(source_candidate_count=len(race['candidates']), unconfirmed_candidate_count=0,
                    absent_parties=[p for p in ('DEM','REP') if not any(c['party']==p for c in race['candidates'])])
    return found


def _add(found, office, district, line, reviewed_on):
    name=line[:line.index('(')].strip(); labels=re.findall(r'\(([^()]+)\)',line)
    require(name and labels and len(set(labels))==len(labels) and set(labels)<=set(PARTIES),
            'Connecticut ballot party changed')
    major=[PARTIES[x] for x in labels if x in ('D','R')]
    require(len(major)<=1, 'Connecticut cross-major-party endorsement requires review')
    party=major[0] if major else PARTIES[labels[0]]
    rid=f'USA:CT:{office}'+(':'+district if district else '')
    race=found.setdefault(rid,{'race_id':rid,'state':'CT','office':office,'district':district,
        'election_date':'2026-11-03','status':'reported_general_matchup',
        'coverage':'complete_active_agency_listing','source_role':'state_election_agency',
        'source_url':URL,'reviewed_on':reviewed_on,'reviewed_general_from':'2026-08-12',
        'period_source_url':PERIOD_URL,'candidates':[],'unconfirmed_candidates':[],
        'excluded_candidates':[],'unopposed_status':'not_verified',
        'limitations_ko':'주 선거당국 안내서의 현재 후보 명부. 교차추천은 한 후보로 유지. 기명 후보 전수·무투표 당선·당선 인증은 별도 확인 대상입니다.'})
    require(not any(c['name']==name for c in race['candidates']), 'duplicate Connecticut candidate')
    race['candidates'].append({'name':name,'party':party,'reported_name':name,
        'reported_party':'; '.join(labels),'reported_ballot_parties':labels,
        'candidate_id':None,'source_url':URL,'ballot_access':'official_general_candidate_listing'})
