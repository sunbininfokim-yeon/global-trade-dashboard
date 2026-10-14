"""Synthetic source contracts, never synthetic published candidate data."""
from tests.poll_config_fixture import SNAPSHOT_DAY
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from election_watch.house_rosters import (parse_house_roster, merge_national_house,
    merge_official_house_reviews, attach_reviewed_poll_aliases, attach_verified_finance_ids, apply_reviewed_aliases)
from election_watch.agency_house_rosters import parse_nc_csv, parse_ia_layout, parse_mo_layout, parse_sd_html, parse_de_html, parse_nj_layout
from election_watch.federal_matchups import validate_snapshot
from refresh_house_candidate_rosters import refresh

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-10-08'


def source(name, seats, extra=''):
    rows = [f'<title>{name} 2026 General Election</title>',
            '<p>Candidates for office appear on this page in italics until certified to appear on the ballot.</p>']
    for n in range(1, seats + 1):
        label = 'At-Large' if seats == 1 else f'CD {n}'
        rows += [f'<tr><td class="on">{label}<br><img alt="Seat up for regular election"></td></tr>',
                 '<tr><td></td><td>Candidate list (2) - 120th Congress</td></tr>']
        for party, candidate, fec in [('Democratic', f'Dem Person{n}', 'H6AA00001'), ('Republican', f'Rep Person{n}', 'H6AA00002')]:
            rows.append(f'<tr><td><a name="{fec}"></a></td><td><img alt="Candidate"></td><td>{party}</td><td></td><td></td><td>{candidate}<span>Annotations are not names</span></td></tr>')
    return '\n'.join(rows) + extra


class NationalCandidateTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT/'config/federal_matchups/2026.json').read_text())
        self.catalog = json.loads((ROOT/'config/usa_polls/targets_2026.json').read_text())

    def test_special_and_statewide_candidates_do_not_leak_into_regular_house(self):
        extra = '<tr><td class="on">CD 1<br><img alt="Seat up for special election"></td></tr>'
        extra += '<tr><td></td><td>Candidate list (1)</td></tr><tr><td></td><td><img alt="Candidate"></td><td>Democratic</td><td></td><td></td><td>Wrong Special</td></tr>'
        extra += '<tr><td><span id="heaL">Secretary of State</span></td></tr><tr><td class="off"></td></tr>'
        extra += '<tr><td></td><td>Candidate list (1)</td></tr><tr><td></td><td><img alt="Candidate"></td><td>Republican</td><td></td><td></td><td>Wrong Statewide</td></tr>'
        races, _ = parse_house_roster(source('Alaska',1,extra),'AK','Alaska',1,DAY)
        self.assertEqual([c['name'] for c in races['USA:AK:house:00']['candidates']], ['Dem Person1','Rep Person1'])

    def test_italic_unconfirmed_and_struck_names_are_not_display_nominees(self):
        html = source('Alaska',1).replace('Candidate list (2)', 'Candidate list (3, 1 write-in)')
        html += '<tr><td></td><td><img alt="Candidate"></td><td>Green</td><td></td><td></td><td><i>Unconfirmed Person</i></td></tr>'
        html += '<tr><td></td><td><img alt="Candidate"></td><td>Write-in; (Independent)</td><td></td><td></td><td>Registered Writer</td></tr>'
        html += '<tr><td></td><td><img alt="Candidate"></td><td>Democratic</td><td></td><td></td><td><strike>Lost Primary</strike></td></tr>'
        races, _ = parse_house_roster(html,'AK','Alaska',1,DAY)
        r = races['USA:AK:house:00']
        self.assertEqual(len(r['candidates']),3)
        self.assertEqual(r['candidates'][-1]['ballot_access'],'write_in')
        self.assertEqual(r['unconfirmed_candidates'][0]['name'],'Unconfirmed Person')
        self.assertEqual(r['excluded_candidates'][0]['name'],'Lost Primary')
        self.assertEqual(r['absent_parties'],[])
        self.assertEqual(r['unopposed_status'],'not_verified')

    def test_source_year_count_district_and_future_metadata_changes_hold(self):
        html = source('Alaska',1)
        for bad in (html.replace('2026 General','2024 General'),html.replace('Candidate list (2)','Candidate list (3)'),
                    html.replace('At-Large','CD 1'),html+'Last Modified: new Date( 1833494400000 )'):
            with self.subTest(bad=bad[-100:]),self.assertRaises(ValueError):
                parse_house_roster(bad,'AK','Alaska',1,DAY)

    def test_50_sources_required_and_agency_rosters_preserved(self):
        documents = {s:source(r['name'],r['house_seats']) for s,r in self.catalog['states'].items()}
        updated = merge_national_house(self.snapshot,self.catalog,documents,SNAPSHOT_DAY)
        self.assertEqual(sum(r['office']=='house' for r in updated['races'].values()),435)
        self.assertEqual(updated['races']['USA:MI:house:01']['candidates'],self.snapshot['races']['USA:MI:house:01']['candidates'])
        del documents['WY']
        with self.assertRaises(ValueError):merge_national_house(self.snapshot,self.catalog,documents,SNAPSHOT_DAY)
        broken = deepcopy(updated);del broken['races']['USA:GA:house:01']
        with self.assertRaises(ValueError):validate_snapshot(broken,SNAPSHOT_DAY)

    def test_failed_refresh_preserves_last_valid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'last-good.json';output.write_text('{"original_as_of":"2026-10-07"}')
            with self.assertRaises(FileNotFoundError):
                refresh(ROOT/'config/federal_matchups/2026.json',ROOT/'config/usa_polls/targets_2026.json',
                        ROOT/'config/usa_polls/ballot_reviews_2026.json',output,DAY,directory)
            self.assertEqual(json.loads(output.read_text()),{'original_as_of':'2026-10-07'})

    def test_poll_alias_uses_source_nickname_not_changed_candidate(self):
        rid='USA:GA:house:01'
        snap={'races':{rid:{'source_role':'reviewed_secondary_nominee_listing','candidates':[
            {'name':'James Morris "Jim" Kingston','party':'REP'}, {'name':'Amanda Hollowell','party':'DEM'}]}}}
        polls={'races':{rid:{'schedule_status':'reported_general_matchup','required_candidates':['Jim Kingston','Wrong Nominee'],
            'candidates':{'Jim Kingston':{'party':'REP'},'Wrong Nominee':{'party':'DEM'}}}}}
        out=attach_reviewed_poll_aliases(snap,polls)
        self.assertEqual(out['races'][rid]['candidates'][0]['poll_name_aliases'],['Jim Kingston'])
        self.assertNotIn('poll_name_aliases',out['races'][rid]['candidates'][1])

    def test_finance_id_needs_exact_race_cited_id_name_and_party(self):
        rid='USA:GA:house:14';name='Clayton McLean "Clay" Fuller'
        snap={'races':{rid:{'candidates':[{'name':name,'party':'REP','reported_fec_id':'H0GA14030','candidate_id':None}]}}}
        row={'cycle':2026,'office':'house','race_id':rid,'candidates':[{'candidate_id':'H0GA14030','name':'FULLER, CLAY',
             'reported_names':['FULLER, CLAY','FULLER, CLAYTON'],'reported_parties':['REP']}]}
        self.assertEqual(attach_verified_finance_ids(snap,[row])['races'][rid]['candidates'][0]['candidate_id'],'H0GA14030')
        for key,value in [('race_id','USA:GA:house:13'),('cycle',2024)]:
            bad=deepcopy(row);bad[key]=value
            self.assertIsNone(attach_verified_finance_ids(snap,[bad])['races'][rid]['candidates'][0]['candidate_id'])
        bad=deepcopy(row);bad['candidates'][0]['reported_names']=['DIFFERENT, PERSON']
        self.assertIsNone(attach_verified_finance_ids(snap,[bad])['races'][rid]['candidates'][0]['candidate_id'])

    def test_nc_general_csv_excludes_primary_and_deduplicates_counties(self):
        io=StringIO();writer=csv.DictWriter(io,fieldnames=['election_dt','contest_name','name_on_ballot','party_candidate']);writer.writeheader()
        for n in range(1,15):
            row={'election_dt':'11/03/2026','contest_name':f'US HOUSE OF REPRESENTATIVES DISTRICT {n:02d}','name_on_ballot':f'Nominee{n}','party_candidate':'DEM'}
            writer.writerow(row);writer.writerow(row)
        writer.writerow({'election_dt':'03/03/2026','contest_name':'US HOUSE OF REPRESENTATIVES DISTRICT 01','name_on_ballot':'Lost Primary','party_candidate':'DEM'})
        result=parse_nc_csv(io.getvalue(),'https://example.gov/general.csv',DAY)
        self.assertEqual(len(result),14);self.assertEqual(len(result['USA:NC:house:01']['candidates']),1)

    def test_ia_and_mo_federal_sections_exclude_state_legislature(self):
        ia='Candidate List November 3, 2026 General Election\n'
        for n in range(1,5):ia+=f'United States Representative District {n}  Democratic  Nominee{n}  ADDRESS\n'
        ia+='Governor  Democratic  Wrong State\n'
        self.assertEqual(len(parse_ia_layout(ia,'https://example.gov/general.pdf',DAY)),4)
        mo='General Election on Tuesday, November 3, 2026 certify REPUBLICAN CANDIDATES\nREPUBLICAN CANDIDATES\nFor U.S. Representative\n'
        mo+='\n'.join(f'District {n}, Nominee{n}' for n in range(1,9))
        mo+='\nFor State Representative\nDistrict 1, Wrong State'
        rs=parse_mo_layout(mo,'https://example.gov/certification.pdf',DAY)
        self.assertEqual(rs['USA:MO:house:01']['status'],'certified_ballot')
        self.assertEqual(rs['USA:MO:house:01']['candidates'][0]['name'],'Nominee1')

    def test_de_withdrawal_is_not_active_general_nominee(self):
        html='2026 General'
        for name,status in [('Real Nominee','Qualified'),('Lost Nominee','Withdrawn')]:
            html+=f'<tr><td>Representative in Congress</td><td>Statewide</td><td>Democratic</td><td>{name}<br>Website: https://example.gov</td><td>{status}</td><td>date</td></tr>'
        result=parse_de_html(html,'https://example.gov/general',DAY)
        self.assertEqual([c['name'] for c in result['USA:DE:house:00']['candidates']],['Real Nominee'])

    def test_sd_current_active_general_is_distinct_from_primary_or_withdrawn(self):
        html='11/3/2026 General'
        for name,status,phase in [('General Nominee','Active','General'),('Lost Primary','Active','Primary'),('Withdrawn Nominee','Withdrawn','General')]:
            cells=['United States Representative',name,'DEM','date','','','','','','','','','',status,phase,'11/3/2026 12:00:00 AM']
            html+='<tr>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>'
        result=parse_sd_html(html,'https://example.gov/general',DAY)
        self.assertEqual([c['name'] for c in result['USA:SD:house:00']['candidates']],['General Nominee'])

    def test_reviewed_spelling_does_not_apply_after_source_identity_changes(self):
        rid='USA:TX:house:15'
        snap={'races':{rid:{'candidates':[{'name':'Named Person-Other','party':'REP','reported_fec_id':'H0TX15124'}]}}}
        catalog={'schema':'usa_candidate_identity_aliases_v1','cycle':2026,'reviewed_on':DAY,'records':[
            {'race_id':rid,'candidate_name':'Named Person-Other','party':'REP','reported_fec_id':'H0TX15124',
             'official_source_url':'https://example.house.gov/about','roster_source_url':'https://example.org/general',
             'aliases':['Named Person'],'reviewed_on':DAY}]}
        result=apply_reviewed_aliases(snap,catalog,DAY)
        self.assertEqual(result['races'][rid]['candidates'][0]['finance_name_aliases'],['Named Person'])
        broken=deepcopy(snap);broken['races'][rid]['candidates'][0]['reported_fec_id']='H0TX11111'
        with self.assertRaises(ValueError):apply_reviewed_aliases(broken,catalog,DAY)

    def test_nj_official_ordinal_and_other_party_names(self):
        text='Official List Candidates for House of Representatives For GENERAL ELECTION 11/03/202 6\n'
        for ordinal in 'First Second Third Fourth Fifth Sixth Seventh Eighth Ninth Tenth Eleventh Twelfth'.split():
            text+=f'{ordinal} Congressional District:\n{ordinal.upper()} NOMINEE *  P.O. BOX 1  Democratic\n'
        text+='OTHER NOMINEE  P.O. BOX 2  INDEPENDENT\n'
        result=parse_nj_layout(text,'https://example.gov/official.pdf',DAY)
        self.assertEqual(len(result),12);self.assertEqual(len(result['USA:NJ:house:12']['candidates']),2)

    def test_partial_agency_override_cannot_claim_complete_state(self):
        race=self.snapshot['races']['USA:NC:house:01']
        reviews={'schema':'usa_official_house_reviews_v1','cycle':2026,'reviewed_on':DAY,'races':{race['race_id']:race}}
        with self.assertRaises(ValueError):merge_official_house_reviews(self.snapshot,reviews,SNAPSHOT_DAY)


if __name__ == '__main__':unittest.main()
