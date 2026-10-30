"""Montana's official general filing list; excludes contact fields from evidence."""
from datetime import datetime
from html.parser import HTMLParser

URL='https://candidatefiling.mt.gov/candidatefiling/CandidateList.aspx?e=450002987'

class _Rows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag=='td' and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None

def parse_general(html,source_url=URL):
    if source_url!=URL or 'FEDERAL GENERAL 2026' not in html:
        raise ValueError('Not the reviewed Montana general list')
    parser=_Rows();parser.feed(html);races={}
    for row in parser.rows:
        if not any(c in ('UNITED STATES SENATOR','UNITED STATES REPRESENTATIVE') for c in row):continue
        if len(row)!=14 or row[0]!='FILED' or row[13]!='FILED' or row[4]!='REGULAR':
            raise ValueError('Montana federal filing schema/status changed')
        if row[3]=='UNITED STATES SENATOR':
            if row[1:3]!=['Statewide','STATE'] or row[5]!='6':raise ValueError('Montana Senate scope changed')
            rid='USA:MT:senate'
        else:
            if row[1]!='Congressional' or row[2] not in ('1ST CONGRESSIONAL','2ND CONGRESSIONAL') or row[5]!='2':
                raise ValueError('Montana House district changed')
            rid=f'USA:MT:house:0{row[2][0]}'
        write_in='WRITE-IN' in row[8].upper()
        if row[11] not in ('DEM','REP','LIB','IND','NON') or row[11]=='NON' and not write_in:
            raise ValueError('Montana party/write-in requires review')
        name=row[6].lstrip('*').strip().title()
        if not name:raise ValueError('Montana empty name')
        entry={'name':name,'party':'WRI' if write_in else row[11], 'reported_name':row[6],
            'reported_party':row[11],'write_in':write_in,'incumbent':row[6].startswith('*'),
            'agency_status':'FILED','filed_on':datetime.strptime(row[10],'%m/%d/%Y %I:%M:%S %p').date().isoformat(),
            'ballot_access':'write_in' if write_in else 'official_general_filing_listing',
            'candidate_id':None,'source_url':source_url}
        bucket=races.setdefault(rid,[])
        if any(c['name']==name for c in bucket):raise ValueError('Montana duplicate federal candidate')
        bucket.append(entry)
    expected={'USA:MT:senate':5,'USA:MT:house:01':3,'USA:MT:house:02':4}
    if {k:len(v) for k,v in races.items()}!=expected:raise ValueError('Montana federal field changed; review again')
    return races
