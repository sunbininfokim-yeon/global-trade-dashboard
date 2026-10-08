"""Focus the real UI universe without altering official ratings or inventing polls."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from election_watch.poll_house_focus import apply_house_focus, attach_house_focus, caution_reasons, refresh_house_focus_lifecycle
from test_poll_targets_and_gaps import selected, read, ROOT, DAY

DATA = ROOT.parent.parent/'public/data'


def focus(policy=None, ratings=None, board=None, day=DAY):
    return apply_house_focus(policy or selected(), ratings or json.loads((DATA/'usa_election_ratings_review_v1.json').read_text()),
        board or json.loads((DATA/'elections_board_v1.json').read_text()), read('house_focus_2026.json'), day)


class HouseFocusTests(unittest.TestCase):
    def test_focus_matches_ui_including_alaska_history(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable for cross-language UI contract')
        js = """import fs from 'node:fs';import {electionRatingSummary} from './js/elections/data/election-overview.js';
const board=JSON.parse(fs.readFileSync('public/data/elections_board_v1.json'));
const ratings=JSON.parse(fs.readFileSync('public/data/usa_election_ratings_review_v1.json'));
const summary=electionRatingSummary(ratings,'house',board.countries.find(c=>c.iso3==='USA'),null,Date.parse('2026-10-08'));
console.log(JSON.stringify(summary.races.filter(r=>['toss_up','lean_dem','lean_rep'].includes(r.effective_rating)).map(r=>[r.race_id,r.rating,r.effective_rating,r.additional]).sort()));"""
        actual=json.loads(subprocess.check_output([node,'--input-type=module','-e',js],cwd=ROOT.parent.parent,text=True))
        expected=sorted([[rid,r['cook_rating'],r['effective_rating'],r['classification']=='user_added_caution']
                        for rid,r in focus()['house_poll_focus']['races'].items()])
        self.assertEqual(expected,actual)
        self.assertIn('USA:AK:house:00',focus()['house_poll_focus']['races'])

    def test_focus_takes_priority_over_requested_stable_seats_without_erasing_reason(self):
        original=selected();p=focus(original)
        self.assertEqual(p['races']['USA:NY:house:17']['collection_priority']['order'],0)
        self.assertIn('requested_state',p['races']['USA:NY:house:17']['collection_priority']['reasons'])
        self.assertEqual(p['races']['USA:NY:house:17']['collection_priority']['within_focus_order'],1)
        self.assertEqual(p['races']['USA:NY:house:10']['collection_priority']['order'],1)
        self.assertNotIn('house_poll_focus',original)
        self.assertEqual(original['races']['USA:NY:house:17']['collection_priority']['order'],1)

    def test_official_rating_remains_separate_from_user_caution(self):
        p=focus();f=p['house_poll_focus']
        self.assertEqual(f['race_count'],f['cook_competitive_count']+f['user_added_count'])
        self.assertEqual(f['races']['USA:NY:house:11']['cook_rating'],'solid_rep')
        self.assertEqual(f['races']['USA:NY:house:11']['effective_rating'],'toss_up')
        self.assertEqual(f['races']['USA:NY:house:11']['classification'],'user_added_caution')
        self.assertEqual(f['races']['USA:PA:house:07']['classification'],'cook_toss_up_or_lean')

    def test_invalid_district_duplicate_future_or_wrong_country_rejects(self):
        for edit in ('district','duplicate','future','country'):
            ratings=json.loads((DATA/'usa_election_ratings_review_v1.json').read_text());board=json.loads((DATA/'elections_board_v1.json').read_text())
            if edit=='district':ratings['offices']['house']['races'][0]['district']='99'
            if edit=='duplicate':ratings['offices']['house']['races'][0]=deepcopy(ratings['offices']['house']['races'][1])
            if edit=='future':ratings['offices']['house']['as_of']='2026-10-09'
            if edit=='country':board['countries']=[c for c in board['countries'] if c.get('iso3')!='USA']
            with self.subTest(edit=edit),self.assertRaises(ValueError):focus(ratings=ratings,board=board)

    def test_boundary_history_requires_verified_lineage_for_numbered_district(self):
        config=read('house_focus_2026.json')
        record={'chamber':'house','state':'PA','district':'07','criterion':'two_party_changes_last_three_general_elections',
            'evidence':[{'year':y,'party_abbr':p,'source_url':'https://example.org/synthetic'} for y,p in [(2020,'DEM'),(2022,'GOP'),(2024,'DEM')]]}
        race={'state':'PA','district':'07','cook_held_party':'DEM'};country={'ui_ready':{'congress':{'swing_seats':[record]}}}
        self.assertFalse(caution_reasons(race,country,config))
        record['boundary_lineage_verified']=True
        self.assertEqual(caution_reasons(race,country,config)[0]['criterion'],record['criterion'])
        record['evidence'][0]['source_url']='http://example.org/synthetic'
        self.assertFalse(caution_reasons(race,country,config))

    def test_stale_ratings_are_preserved_but_not_claimed_current(self):
        f=focus(day='2026-10-25')['house_poll_focus']
        self.assertEqual(f['ratings_status'],'stale_reviewed_snapshot')
        self.assertEqual(f['rating_as_of'],'2026-09-25')

    def test_missing_poll_is_a_review_route_not_zero_or_winner(self):
        from election_watch.live_polls import build_live
        from election_watch.poll_priorities import attach_coverage
        p=focus();board=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
        attach_coverage(board,[],p,{"races":{}});attach_house_focus(board,p)
        f=board['house_poll_focus'];r=f['races']['USA:NY:house:17']
        self.assertEqual(r['next_action'],'discover_original_release')
        self.assertEqual(r['coverage_status'],'no_provider_record')
        self.assertNotIn('winner',r)
        unopposed=f['races']['USA:FL:house:10']
        self.assertFalse(unopposed['poll_comparison_required'])
        self.assertEqual(unopposed['next_action'],'not_required_official_general_unopposed')
        self.assertEqual(f['summary']['with_observations'],0)
        self.assertEqual(len(f['without_observations']),f['race_count'])

    def test_closed_election_clears_focus_even_if_api_failed(self):
        from election_watch.live_polls import build_live, close_finished_races
        from election_watch.poll_priorities import attach_coverage
        p=focus();board=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
        attach_coverage(board,[],p,{'races':{}});attach_house_focus(board,p)
        original=board['fetched_at']
        close_finished_races(board,p,{},'2026-11-04')
        refresh_house_focus_lifecycle(board)
        self.assertEqual(board['house_poll_focus']['summary']['closed_elections'],board['house_poll_focus']['race_count'])
        self.assertEqual(board['house_poll_focus']['without_observations'],[])
        self.assertEqual(board['house_poll_focus']['summary']['without_observations'],0)
        self.assertEqual(board['fetched_at'],original)

if __name__=='__main__':unittest.main()
