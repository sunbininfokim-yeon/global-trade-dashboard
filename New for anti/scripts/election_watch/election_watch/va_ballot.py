"""Virginia agency federal general listing, without publishing contact data."""
from datetime import date
from html.parser import HTMLParser
import re
from .polls import require

URL = 'https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-3-2026-gen-elect-federal-offices/'
PERIOD_URL = 'https://www.elections.virginia.gov/news-releases/supreme-court-of-virginia-voids-april-21-redistricting-referendum-2.html'
PARTIES = {'Democratic':'DEM','Republican':'REP','Independent':'IND','Libertarian':'LIB','Green':'GRN'}

class FederalTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0; self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            require(self.depth==0,'nested Virginia table'); self.depth=1; self.table=[]
        if not self.depth:return
        if tag=='tr':self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:self.table.append(self.row);self.row=None
        if tag=='table' and self.depth:self.tables.append(self.table);self.table=None;self.depth=0
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)

def parse_ballot(html,reviewed_on):
    require(date.fromisoformat(reviewed_on)>=date(2026,8,5),'Virginia review predates primary')
    require('November 3, 2026 - Federal Offices' in html,'Virginia general cycle/page changed')
    parser=FederalTable();parser.feed(html);parser.close()
    tables=[t for t in parser.tables if t and t[0][:5]==['Office Title','District','Candidate Party','Candidate Name','Incumbent']]
    require(len(tables)==1,'Virginia federal table missing/ambiguous')
    found={}
    for cells in tables[0][1:]:
        require(len(cells)==len(tables[0][0]),'Virginia malformed federal row')
        office,district,party,name,incumbent=cells[:5]
        require(office in ('Member, United States Senate','Member, House of Representatives'),'Virginia nonfederal office in federal listing')
        require(name and party in PARTIES and incumbent in ('Yes','No'),'Virginia identity/party/status changed')
        kind='senate' if office=='Member, United States Senate' else 'house'
        if kind=='house':
            m=re.fullmatch(r'(\d+)(?:st|nd|rd|th) District',district)
            require(m and 1<=int(m[1])<=11,'Virginia federal district outside apportionment')
            district=f'{int(m[1]):02d}'
        else:require(district=='Statewide','Virginia Senate district changed');district=None
        rid='USA:VA:'+kind+(':'+district if district else '')
        race=found.setdefault(rid,{'race_id':rid,'state':'VA','office':kind,'district':district,
            'election_date':'2026-11-03','status':'reported_general_matchup',
            'coverage':'complete_active_agency_listing','source_role':'state_election_agency',
            'source_url':URL,'reviewed_on':reviewed_on,'reviewed_general_from':'2026-08-05',
            'period_source_url':PERIOD_URL,'candidates':[],'excluded_candidates':[],
            'unconfirmed_candidates':[],'unopposed_status':'not_verified'})
        require(not any(c['name']==name for c in race['candidates']),'duplicate Virginia candidate')
        race['candidates'].append({'name':name,'party':PARTIES[party],'reported_party':party,
            'reported_name':name,'candidate_id':None,'source_url':URL,
            'ballot_access':'official_general_candidate_listing','agency_incumbent':incumbent=='Yes'})
    expected={'USA:VA:senate'}|{f'USA:VA:house:{n:02d}' for n in range(1,12)}
    require(set(found)==expected and all(r['candidates'] for r in found.values()),'Virginia federal universe incomplete')
    for r in found.values():
        r['absent_parties']=[p for p in ('DEM','REP') if not any(c['party']==p for c in r['candidates'])]
        r['source_candidate_count']=len(r['candidates']);r['unconfirmed_candidate_count']=0
        r['limitations_ko']='주 선거당국 본선 후보 명부. 연락처는 수집 결과에 포함하지 않습니다. 기명투표 가능성과 당선 인증은 별도이며 무투표 당선을 뜻하지 않습니다.'
    return found
