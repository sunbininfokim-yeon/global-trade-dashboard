"""Synthetic fixtures only; no fabricated polls or candidates are published."""
from tests.poll_config_fixture import SNAPSHOT_DAY
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from election_watch.live_polls import apply_watchlist, build_live, close_finished_races, normalize, summarize
from election_watch.poll_ballots import parse_florida
from election_watch.poll_gaps import attach_gaps, refresh_gap_lifecycle
from election_watch.poll_priorities import apply_priorities, attach_coverage
from election_watch.poll_targets import apply_targets, competition
from election_watch.governor_matchups import apply_matchups

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/usa_polls'
DAY = '2026-10-08'

def read(name):
    return json.loads((CONFIG/name).read_text())

def selected(ballots=None):
    if ballots is None:
        return deepcopy(cached_selection())
    policy = apply_priorities(apply_watchlist(read('live_2026.json'), read('watchlist_2026.json')),
        read('priorities_2026.json'), ROOT.parent.parent/'public/data/congressional_districts/USA', DAY)
    policy = apply_matchups(policy, json.loads((ROOT/'config/governor_matchups/2026.json').read_text()), SNAPSHOT_DAY)
    return apply_targets(policy, read('targets_2026.json'), ballots or read('ballot_reviews_2026.json'), SNAPSHOT_DAY)

@lru_cache(maxsize=1)
def cached_selection():
    return selected(read('ballot_reviews_2026.json'))

def synthetic_poll(**changes):
    return dict({'id':'synthetic-only-new-release','subject':'2026 CA-48','poll_type':'us-representative',
        'seat_name':'CA-48','pollster':'SurveyUSA','url':'https://results.surveyusa.com/client/synthetic-only',
        'sponsors':['KGTV (San Diego)','The San Diego Union Tribune'],'population':'lv','sample_size':500,
        'internal':False,'partisan':None,'start_date':'2026-10-09','end_date':'2026-10-13',
        'created_at':'2026-10-14','answers':[{'choice':'Marni von Wilpert','pct':48},
                                               {'choice':'Jim Desmond','pct':43}]}, **changes)

def florida_html():
    rows=[]
    for district in range(1,29):
        rows.append(f'<tr><td>{district}</td><td>Fixture, Candidate{district} (DEM)</td>'
                    '<td>Qualified</td><td>Unopposed</td><td></td></tr>')
        rows.append('<tr><td></td><td>Opponent, Test (REP)</td><td>Qualified</td>'
                    '<td>Won</td><td></td></tr>')
    statewide='<tr><td>Fixture, Statewide (DEM)</td><td>Qualified</td><td>Won</td><td></td></tr>'
    return ('Candidate Listing for 2026 General Election'
        '<b>United States Senator</b><table class="results">'+statewide+'</table>'
        '<b>United States Representative</b><table class="results">'+''.join(rows)+'</table>'
        '<b>Governor</b><table class="results">'+statewide+'</table>')

class PollTargetsTests(unittest.TestCase):
    def test_nationwide_catalog_is_435_35_36_without_non_election_slots(self):
        p=selected()
        self.assertEqual(p['target_catalog']['counts'],{'house':435,'senate':35,'governor':36})
        self.assertEqual(len(p['states']),50)
        self.assertNotIn('USA:NY:senate',p['races'])
        self.assertNotIn('USA:WA:governor',p['races'])
        self.assertEqual(p['races']['USA:FL:house:27']['collection_priority']['order'],1)

    def test_at_large_joins_transport_01_to_map_00(self):
        p=selected()
        r=p['races']['USA:AK:house:00']
        self.assertEqual((r['subject'],r['seat_name']),('2026 AK-01','AK-01'))
        self.assertNotIn('USA:AK:house:01',p['races'])
        self.assertEqual(r['district_transport']['canonical_district'],'00')

    def test_catalog_rejects_impossible_districts_or_future_reviews(self):
        for edit in ('seat_count','review_date','election_cycle'):
            catalog=read('targets_2026.json')
            if edit=='seat_count':catalog['states']['CT']['house_seats']=6
            if edit=='review_date':catalog['reviewed_on']='2027-01-01'
            if edit=='election_cycle':catalog['election_date']='2028-11-03'
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                apply_targets(read('live_2026.json'),catalog,read('ballot_reviews_2026.json'),SNAPSHOT_DAY)

    def test_new_release_automatically_admitted_for_reviewed_matchup_and_source(self):
        p=selected();rows,bad=normalize([synthetic_poll()],p,'2026-10-15')
        self.assertFalse(bad);self.assertEqual(rows[0]['race_id'],'USA:CA:house:48')
        self.assertEqual(rows[0]['source_quality']['verification_level'],'partial')
        self.assertEqual(summarize(rows,p['races']['USA:CA:house:48'],'2026-10-15',7)['party'],'DEM')

    def test_unreviewed_source_commissioner_or_matchup_stays_held(self):
        p=selected()
        # This synthetic fixture deliberately lacks a reviewed field. The
        # production TX-38 roster is now connected and must not be presumed missing.
        p['races']['USA:TX:house:38']['required_candidates']=[]
        for changes,reason in [({'pollster':'Unknown Institution'},'pollster_not_selected'),
                               ({'sponsors':['Unknown sponsor']},'commissioner_not_reviewed'),
                               ({'subject':'2026 TX-38','seat_name':'TX-38'},'matchup_not_reviewed'),
                               ({'population':'a'},'unsupported_population')]:
            with self.subTest(reason=reason):
                rows,bad=normalize([synthetic_poll(**changes)],p,'2026-10-15')
                self.assertFalse(rows);self.assertEqual(bad[0]['reason'],reason)

    def test_explicit_alias_keeps_one_candidate_identity(self):
        p=selected();rid='USA:NM:house:02'
        raw=synthetic_poll(subject='2026 NM-02',seat_name='NM-02',sponsors=['KOB-TV (Albuquerque)'],
            answers=[{'choice':'Gabe Vasquez','pct':48},{'choice':'Greg Cunningham','pct':43}])
        rows,bad=normalize([raw],p,'2026-10-15');self.assertFalse(bad)
        self.assertEqual(summarize(rows,p['races'][rid],'2026-10-15',7)['leader'],'Gabe Vasquez')
        self.assertEqual(rows[0]['answers'][0]['party'],'DEM')
        raw['answers'].append({'choice':'Gabriel Vasquez','pct':1})
        rows,bad=normalize([raw],p,'2026-10-15');self.assertFalse(rows)
        self.assertEqual(bad[0]['reason'],'duplicate_candidate_alias')

    def test_changed_nominee_holds_poll_admission_instead_of_reusing_old_matchup(self):
        ballots=read('ballot_reviews_2026.json');rid='USA:NY:house:17'
        ballots['races'][rid]['candidates'][0]['name']='SYNTHETIC REPLACEMENT'
        ballots['races'][rid]['candidates'][0].pop('poll_name_aliases',None)
        p=selected(ballots)
        self.assertEqual(p['races'][rid]['required_candidates'],[])
        self.assertEqual(p['races'][rid]['schedule_status'],'changed_matchup_review_required')

    def test_reviewed_general_period_does_not_use_arbitrary_september_cutoff(self):
        p=selected()
        self.assertEqual(p['races']['USA:CA:house:48']['general_from'],'2026-06-03')
        self.assertEqual(p['races']['USA:NH:house:01']['general_from'],'2026-09-09')

class BallotCompetitionTests(unittest.TestCase):
    def test_primary_unopposed_is_not_general_unopposed(self):
        data=parse_florida(florida_html(),DAY)
        self.assertEqual(len(data['races']),30)
        for r in data['races'].values():
            self.assertFalse(r['official_general_unopposed'])
            self.assertIsNot(competition(r)['general_unopposed'],True)

    def test_official_single_general_listing_is_not_certified_winner(self):
        r=deepcopy(read('ballot_reviews_2026.json')['races']['USA:FL:house:10'])
        c=competition(r)
        self.assertTrue(c['general_unopposed']);self.assertFalse(c['confirmed_winner'])
        self.assertEqual(c['no_vote_status'],'official_listing_ballot_omission_rule')
        r['coverage']='major_party_only';self.assertIsNone(competition(r)['general_unopposed'])

    def test_same_party_or_independent_or_write_in_does_not_mean_unopposed(self):
        r=deepcopy(read('ballot_reviews_2026.json')['races']['USA:FL:house:10'])
        r['candidates'].append({**r['candidates'][0],'name':'SYNTHETIC OPPONENT','party':'WRI'})
        c=competition(r)
        self.assertFalse(c['general_unopposed']);self.assertEqual(c['write_in_candidates'],['SYNTHETIC OPPONENT'])
        r['candidates'][1]['party']='DEM';self.assertEqual(competition(r)['status'],'same_party_contest')
        self.assertFalse(competition(r)['confirmed_winner'])

    def test_changed_or_empty_agency_table_fails_closed(self):
        for html in (florida_html().replace('Candidate Listing for 2026','Candidate Listing for 2024'),
                     florida_html().replace('<td>28</td>','<td>29</td>'),
                     florida_html().replace('Qualified','New Unknown Status')):
            with self.assertRaises(ValueError):parse_florida(html,DAY)

class GapReportTests(unittest.TestCase):
    def test_api_failure_after_election_cannot_leave_poll_counts_on_audit(self):
        p=selected();board=build_live([synthetic_poll()],p,{'schema':'usa_confirmed_results_v1','results':[]},
            '2026-10-15','2026-10-15T01:00:00+00:00','test')
        attach_coverage(board,[],p,{'status':'hold','races':{}});attach_gaps(board,{'status':'hold','races':{}})
        self.assertEqual(board['data_gaps']['counts_by_office']['house']['with_polls'],1)
        close_finished_races(board,p,{},'2026-11-04');refresh_gap_lifecycle(board)
        gaps=board['data_gaps'];self.assertEqual(gaps['counts_by_office']['house']['with_polls'],0)
        self.assertEqual(gaps['counts_by_office']['house']['closed_elections'],435)
        self.assertEqual(gaps['as_of'],'2026-10-15')
        self.assertEqual(gaps['lifecycle_checked_as_of'],'2026-11-04')
        self.assertEqual(gaps['states']['CA']['house']['polls_without_7d'],[])

    def test_no_observation_is_not_zero_spending_and_governor_ie_is_separate(self):
        p=selected();board=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
        finance={'status':'ok','races':{'USA:FL:governor':{'status':'unsupported'},
            'USA:CA:governor':{'status':'partial','totals_by_category':{
                'state_independent_spending':{'records':2}},'data_file':'fixture.json'}}}
        attach_coverage(board,[],p,finance);attach_gaps(board,finance)
        gaps=board['data_gaps'];fl=gaps['races']['USA:FL:governor'];ca=gaps['races']['USA:CA:governor']
        self.assertIsNone(fl['super_pac']['records']);self.assertIsNone(fl['state_external_spending']['records'])
        self.assertEqual(ca['state_external_spending']['records'],2)
        self.assertEqual(ca['super_pac']['status'],'no_observed_super_pac')
        self.assertFalse(gaps['states']['NY']['senate']['scheduled'])
        self.assertEqual(gaps['states']['NY']['senate']['polls_without_observations'],[])

    def test_bad_review_config_preserves_last_good_and_writes_failure_status(self):
        import refresh_live_polls
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'board.json';output.write_text('{"last_good":true}')
            bad=root/'bad.json';bad.write_text('invalid JSON')
            with patch('sys.argv',['refresh','--output',str(output),'--as-of',DAY,'--ballot-reviews',str(bad)]):
                self.assertEqual(refresh_live_polls.main(),1)
            self.assertEqual(output.read_text(),'{"last_good":true}')
            self.assertEqual(json.loads((root/'usa_election_live_polls_status_v1.json').read_text())['status'],'error')

if __name__=='__main__':unittest.main()
