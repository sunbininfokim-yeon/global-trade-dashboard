"""Colorado certified general ballot; state legislative contests stay separate."""
from html.parser import HTMLParser
from datetime import date
import re
from .polls import require

URL = 'https://www.sos.state.co.us/pubs/elections/vote/generalCandidates.html'
PARTIES = {'Democratic Party':'DEM', 'Republican Party':'REP', 'Libertarian Party':'LIB',
    'American Constitution Party':'CST', 'Unity Party':'OTH', 'Unaffiliated':'IND',
    'Forward Party':'FWD', 'Approval Voting Party':'APV'}

class BallotTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0; self.selected=False; self.tables=0; self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':
            if 'w3-cmsTable' in attrs.get('class','').split():
                require(not self.selected,'nested candidate table'); self.selected=True; self.tables+=1
            if self.selected:self.depth+=1
        if not self.selected:return
        if tag=='tr':self.row=[]
        if tag in ('td','th') and self.row is not None:
            self.cell={'text':[],'withdrawn':False};self.row.append(self.cell)
        if self.cell is not None and (tag in ('s','strike','del') or 'line-through' in attrs.get('style','')):
            self.cell['withdrawn']=True
    def handle_endtag(self,tag):
        if not self.selected:return
        if tag in ('td','th'):self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
        if tag=='table':
            self.depth-=1
            if self.depth==0:self.selected=False
    def handle_data(self,data):
        if self.cell is not None:self.cell['text'].append(data)

def parse_ballot(html,reviewed_on):
    require(date.fromisoformat(reviewed_on)>=date(2026,9,4),'Colorado certification is after review')
    require('2026 General Election Official Candidate List' in html
        and 'certified to the counties on September 4' in html,'Colorado cycle/certification changed')
    parser=BallotTable();parser.feed(html);parser.close()
    require(parser.tables==1 and parser.rows,'Colorado candidate table missing/ambiguous')
    text=lambda c:' '.join(''.join(c['text']).split())
    require([text(c) for c in parser.rows[0]]==['Candidate name','Office','District','Party','Write in?'],
            'Colorado ballot columns changed')
    found={}
    for cells in parser.rows[1:]:
        require(len(cells)==5,'Colorado malformed candidate row')
        name,office,district,party,write_in=map(text,cells)
        if office not in ('US Senate','US House of Representatives','Governor'):continue
        require(name and party in PARTIES and write_in in ('Y','N'),'Colorado unknown candidate identity/party')
        kind={'US Senate':'senate','US House of Representatives':'house','Governor':'governor'}[office]
        if kind=='house':
            require(district.isdigit() and 1<=int(district)<=8,'Colorado district outside federal apportionment')
            district=f'{int(district):02d}'
        else:require(district=='State','Colorado statewide district changed');district=None
        rid='USA:CO:'+kind+(':'+district if district else '')
        race=found.setdefault(rid,{'race_id':rid,'state':'CO','office':kind,'district':district,
            'election_date':'2026-11-03','status':'certified_ballot','coverage':'complete_ballot',
            'reviewed_on':reviewed_on,'source_url':URL,'source_role':'state_election_agency',
            'candidates':[],'excluded_candidates':[],'absent_parties':[],
            'reviewed_general_from':'2026-07-01',
            'period_source_url':'https://www.sos.state.co.us/pubs/elections/calendars/2026ElectionCalendar.pdf'})
        candidate={'name':name,'party':'WRI' if write_in=='Y' else PARTIES[party],
            'reported_party':party,'write_in':write_in=='Y','candidate_id':None,'source_url':URL,
            'reported_name':name,'ballot_access':'write_in' if write_in=='Y' else 'certified_general_ballot'}
        bucket='excluded_candidates' if any(c['withdrawn'] for c in cells) else 'candidates'
        require(not any(c['name']==name for c in race[bucket]),'duplicate Colorado ballot candidate')
        if bucket=='excluded_candidates':candidate['agency_status']='withdrawn'
        race[bucket].append(candidate)
    expected={'USA:CO:senate','USA:CO:governor'}|{f'USA:CO:house:{n:02d}' for n in range(1,9)}
    require(set(found)==expected and all(r['candidates'] for r in found.values()),'Colorado federal/governor universe incomplete')
    for r in found.values():r['absent_parties']=[p for p in ('DEM','REP') if not any(c['party']==p for c in r['candidates'])]
    return found
