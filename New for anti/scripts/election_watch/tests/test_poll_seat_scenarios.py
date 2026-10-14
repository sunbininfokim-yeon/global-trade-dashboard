from tests.poll_config_fixture import SNAPSHOT_DAY
import json
from copy import deepcopy
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from election_watch.seat_scenarios import build_scenarios

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent.parent / 'public/data'
POLICY = json.loads((ROOT/'config/usa_polls/seat_scenarios_2026.json').read_text())
ROSTER = json.loads((PUBLIC/'elections_board_v1.json').read_text())


def board():
    return {'cycle': 2026, 'source_status': 'ok', 'as_of': '2026-10-05',
            'fetched_at': '2026-10-05T01:00:00+00:00', 'races': {}}


def build(b=None, p=None, day='2026-10-05', health=None):
    return build_scenarios(b or board(), ROSTER, p or POLICY, day,
                           day+'T02:00:00+00:00', health)


class SeatScenarioTests(unittest.TestCase):
    def test_unknown_races_conserve_national_totals_and_independents(self):
        result = build()
        for office, total in [('house',435),('senate',100),('governor',50)]:
            row = result['chambers'][office]
            self.assertEqual(sum(row['scenario_counts'].values())+row['unresolved_seats'], total)
            self.assertNotIn('seats', row)
            self.assertNotIn('win_prob', row)
        senate = result['chambers']['senate']
        self.assertEqual(senate['buckets']['retained'], {'DEM':32,'GOP':31,'IND':2})
        self.assertEqual(senate['unresolved_seats'], 9)
        self.assertEqual(result['chambers']['house']['unresolved_seats'],43)
        self.assertEqual(result['chambers']['governor']['unresolved_seats'],12)
        self.assertEqual(result['chambers']['governor']['scenario_counts'],{'DEM':19,'GOP':19,'IND':0})

    def test_poll_replaces_one_pending_race_and_windows_stay_separate(self):
        b=board();b['races']['USA:PA:house:07']={'windows':{
            '7':{'status':'poll_lead','party':'REP'},'14':{'status':'poll_lead','party':'DEM'}}}
        result=build(b)
        self.assertEqual(result['chambers']['house']['scenario_counts']['GOP'],196)
        self.assertEqual(result['windows']['14']['chambers']['house']['scenario_counts']['DEM'],198)
        self.assertEqual(result['chambers']['house']['unresolved_seats'],42)
        self.assertEqual(result['chambers']['house']['lead_abbr'],'없음')

    def test_old_failed_or_replay_polls_cannot_add_seats(self):
        for change,health in [({'as_of':'2026-10-01'},None),({'source_status':'replay'},None),({}, {'status':'error'})]:
            b=board();b.update(change);b['races']['USA:PA:house:07']={'windows':{'7':{'status':'poll_lead','party':'DEM'}}}
            self.assertEqual(build(b,health=health)['chambers']['house']['unresolved_seats'],43)

    def test_single_poll_is_separate_and_can_be_excluded_from_counts(self):
        b=board();b['races']['USA:PA:house:07']={'windows':{'7':{
            'status':'single_poll_lead','party':'REP','included_ids':['one'],
            'evidence_quality':{'level':'unrated','grade':None,'coverage':'single_source','independent_pollster_count':1}}}}
        result=build(b);house=result['chambers']['house']
        self.assertEqual(house['scenario_counts']['GOP'],196)
        self.assertEqual(house['single_poll_lead_counts']['GOP'],1)
        self.assertEqual(house['scenario_counts_without_single_polls']['GOP'],195)
        self.assertEqual(house['unresolved_without_single_polls'],43)
        self.assertEqual(house['buckets']['single_poll_lead'],{'GOP':1})
        self.assertEqual(house['buckets']['recent_poll_lead'],{})
        self.assertEqual(house['lead_abbr'],'없음')
        self.assertEqual(sum(house['scenario_counts_without_single_polls'].values())+
                         house['unresolved_without_single_polls'],435)
        row=next(r for r in result['windows']['7']['competitive_conclusions'] if r['race_id']=='USA:PA:house:07')
        self.assertEqual(row['evidence_quality']['coverage'],'single_source')
        self.assertIn('참고',row['conclusion_ko'])
        self.assertEqual(row['included_poll_ids'],['one'])

    def test_failed_source_cannot_publish_single_poll_evidence(self):
        b=board();b['races']['USA:PA:house:07']={'windows':{'7':{
            'status':'single_poll_lead','party':'DEM','evidence_quality':{'level':'unrated','coverage':'single_source'}}}}
        result=build(b,health={'status':'error'})
        row=next(r for r in result['windows']['7']['competitive_conclusions'] if r['race_id']=='USA:PA:house:07')
        self.assertEqual(row['party_abbr'],'없음');self.assertIsNone(row['evidence_quality'])
        self.assertEqual(result['chambers']['house']['single_poll_lead_counts']['DEM'],0)

    def test_election_end_removes_single_poll_signal_and_quality(self):
        b=board();b['races']['USA:PA:house:07']={'windows':{'7':{
            'status':'single_poll_lead','party':'DEM','evidence_quality':{'level':'unrated','coverage':'single_source'}}}}
        result=build(b,day='2026-11-04')
        self.assertEqual(result['chambers']['house']['unresolved_seats'],435)
        row=next(r for r in result['windows']['7']['competitive_conclusions'] if r['race_id']=='USA:PA:house:07')
        self.assertIsNone(row['evidence_quality']);self.assertEqual(row['conclusion_ko'],'판정 보류')

    def test_stale_ratings_are_not_silently_refreshed(self):
        result=build(day='2026-10-20')
        self.assertEqual(result['chambers']['house']['unresolved_seats'],435)
        self.assertEqual(result['chambers']['senate']['unresolved_seats'],35)

    def test_certified_result_overrides_rating_after_election(self):
        b=board();b['races']['USA:GA:senate']={'contest_id':'ga-general','result':{
            'status':'certified','race_id':'USA:GA:senate','contest_id':'ga-general',
            'party':'REP','certified_on':'2026-11-10'}}
        result=build(b,day='2026-11-11')['chambers']['senate']
        self.assertEqual(result['buckets']['certified_result'],{'GOP':1})
        self.assertEqual(result['unresolved_seats'],34)
        self.assertEqual(result['buckets']['rated_baseline_assumption'],{})

    def test_bad_house_partition_fails_closed(self):
        p=deepcopy(POLICY);p['house']['baseline_by_party']['DEM']+=1
        with self.assertRaises(ValueError):build(p=p)

    def test_same_size_wrong_senate_schedule_fails_closed(self):
        p=deepcopy(POLICY)
        p['senate']['ratings']['solid_dem'].remove('CO')
        p['senate']['ratings']['solid_dem'].append('NY')
        with self.assertRaises(ValueError):build(p=p)

    def test_same_size_wrong_governor_schedule_fails_closed(self):
        p=deepcopy(POLICY)
        p['governor']['ratings']['solid_dem'].remove('CA')
        p['governor']['ratings']['solid_dem'].append('DE')
        with self.assertRaises(ValueError):build(p=p)

    def test_lean_direction_never_becomes_a_poll_conclusion(self):
        b=board();b['races']['USA:NC:senate']={'windows':{'7':{'status':'insufficient_pollsters','party':None}}}
        result=build(b)
        conclusions=result['windows']['7']['competitive_conclusions']
        self.assertEqual(len(conclusions),64)
        row=next(r for r in conclusions if r['race_id']=='USA:NC:senate')
        self.assertEqual(row['party_abbr'],'없음')
        self.assertEqual(row['conclusion_ko'],'판정 보류')

    def test_solid_likely_baseline_is_separate_from_competitive_polling(self):
        b=board();b['races']['USA:GA:senate']={'windows':{'7':{'status':'poll_lead','party':'REP'}}}
        result=build(b)
        row=next(r for r in result['chambers']['senate']['races'] if r['race_id']=='USA:GA:senate')
        self.assertEqual(row['basis'],'rated_baseline_assumption')
        self.assertEqual(row['party_abbr'],'DEM')
        self.assertFalse(row['competitive'])

    def test_bad_roster_holds_scenario_without_discarding_fresh_polls(self):
        import refresh_live_polls
        from test_live_polls import poll
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'polls.json'
            with patch('sys.argv',['refresh','--output',str(out),'--as-of',SNAPSHOT_DAY,
                                    '--governor-matchups',str(Path(tmp)/'no-governor-snapshot.json'),
                                    '--election-board',str(Path(tmp)/'missing.json')]),\
                 patch.object(refresh_live_polls,'fetch_polls',return_value=([poll()], 'test')),\
                 patch.object(refresh_live_polls,'merge_primary_supplements',return_value=([poll()], [])),\
                 patch.object(refresh_live_polls,'fetch_florida',side_effect=ValueError('synthetic agency outage')):
                self.assertEqual(refresh_live_polls.main(),1)
            polls=json.loads(out.read_text())
            self.assertEqual(polls['source_status'],'ok')
            self.assertEqual(len(polls['races']['USA:NY:governor']['observations']),1)
            health=json.loads((Path(tmp)/'usa_election_live_polls_status_v1.json').read_text())
            self.assertEqual(health['status'],'ok')
            self.assertEqual(health['seat_scenario']['status'],'hold')
            forecast=json.loads((Path(tmp)/'usa_midterms_forecast_v1.json').read_text())
            self.assertEqual(forecast['status'],'hold')
            self.assertNotIn('scenario_counts',forecast['chambers']['house'])


if __name__ == '__main__':
    unittest.main()
