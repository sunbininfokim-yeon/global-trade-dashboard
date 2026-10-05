"""Synthetic fixtures are never published as election observations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from election_watch.live_polls import (apply_watchlist, normalize, summarize,
                                      validated_results, build_live, poll_history)
ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'config/usa_polls/live_2026.json').read_text())
WATCHLIST=json.loads((ROOT/'config/usa_polls/watchlist_2026.json').read_text())
RID='USA:NY:governor'
DAY='2026-09-30'
def poll(id='a',**changes):
    return dict({'id':id,'subject':'2026 New York','poll_type':'governor','pollster':'Quinnipiac University',
        'sample_size':800,'population':'lv','url':'https://poll.qu.edu/poll-release?releaseid=test',
        'internal':False,'partisan':None,'start_date':'2026-09-24','end_date':'2026-09-25',
        'created_at':'2026-09-26','seat_name':None,'sponsors':[],
        'answers':[{'choice':'Kathy Hochul','pct':48},{'choice':'Bruce Blakeman','pct':44}]},**changes)
def second(**changes):
    return poll('b',pollster='Emerson College',url='https://emersoncollegepolling.com/test/',**changes)
def summary(raw,days=7):
    rows,_=normalize(raw,POLICY,DAY)
    return summarize(rows,POLICY['races'][RID],DAY,days)
class LivePollTests(unittest.TestCase):
    def test_competitive_watchlist_adds_discovery_slots_without_poll_leads(self):
        selected=apply_watchlist(POLICY,WATCHLIST)
        self.assertEqual(selected['watchlist']['priority_race_count'],55)
        self.assertEqual(selected['races']['USA:OH:house:07']['monitor_priority']['tier'],'toss_up')
        self.assertEqual(selected['races']['USA:AK:senate']['required_candidates'],[])
        self.assertIn('OH',selected['states'])
        self.assertEqual(POLICY['states'],['NY','TN','GA','FL','PA','MI','WI','AZ','NV','NC'])
        board=build_live([],selected,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
        self.assertEqual(board['races']['USA:AK:senate']['windows']['7']['status'],'no_recent_poll')
        self.assertIsNone(board['races']['USA:AK:senate']['windows']['7']['party'])
        self.assertEqual(board['watchlist']['priority_race_count'],55)
    def test_watchlist_rejects_duplicate_races(self):
        import copy
        bad=copy.deepcopy(WATCHLIST)
        bad['ratings']['house']['lean_dem'].append('AZ-06')
        with self.assertRaises(ValueError):
            apply_watchlist(POLICY,bad)
    def test_input_guards(self):
        for item in [poll(pollster='Unknown'),poll(url='https://poll.qu.edu.evil.example/test'),
                     poll(internal=True),poll(partisan='REP'),poll(end_date='2026-10-02'),
                     poll(start_date='2026-01-01'),poll(sample_size=None),
                     poll(answers=[{'choice':'Someone Else','pct':51},{'choice':'Bruce Blakeman','pct':49}])]:
            with self.subTest(item=item):
                accepted,rejected=normalize([item],POLICY,DAY)
                self.assertFalse(accepted);self.assertEqual(len(rejected),1)
    def test_seven_days_includes_today_and_six_days_before(self):
        self.assertEqual(summary([poll(start_date='2026-09-23',end_date='2026-09-23')])['pollster_count'],0)
        self.assertEqual(summary([poll(end_date='2026-09-24')])['pollster_count'],1)
    def test_one_pollster_never_colours(self):
        s=summary([poll(),poll('duplicate')]);self.assertEqual(s['status'],'insufficient_pollsters')
        self.assertEqual(s['lead_counts'],{'Kathy Hochul':1});self.assertIsNone(s['party'])
    def test_two_independent_latest_surveys_agree(self):
        s=summary([poll(),second()]);self.assertEqual((s['status'],s['party']),('poll_lead','DEM'))
    def test_latest_per_institution(self):
        old=second(end_date='2026-09-24',answers=[{'choice':'Kathy Hochul','pct':40},{'choice':'Bruce Blakeman','pct':50}]);old['id']='old'
        self.assertEqual(summary([poll(),old,second()])['lead_counts'],{'Kathy Hochul':2})
    def test_conflicting_same_wave_quarantined(self):
        conflict=second(answers=[{'choice':'Kathy Hochul','pct':40},{'choice':'Bruce Blakeman','pct':50}]);conflict['id']='c'
        s=summary([poll(),second(),conflict]);self.assertEqual(s['conflicting_pollsters'],['emerson']);self.assertIsNone(s['party'])
    def test_tie_not_majority(self):
        s=summary([poll(),second(answers=[{'choice':'Kathy Hochul','pct':45},{'choice':'Bruce Blakeman','pct':45}])])
        self.assertEqual(s['tie_count'],1);self.assertIsNone(s['party'])
    def test_rv_lv_not_added(self):
        self.assertEqual(summary([poll(),second(population='rv')])['pollster_count'],1)
        s=summary([poll(population='rv'),second(population='rv')]);self.assertEqual((s['population'],s['party']),('rv','DEM'))
    def test_unknown_leading_candidate(self):
        a=[{'choice':'Kathy Hochul','pct':20},{'choice':'Bruce Blakeman','pct':20},{'choice':'Unmapped Candidate','pct':50}]
        s=summary([poll(answers=a),second(answers=a)]);self.assertEqual(s['status'],'unknown_leader_party');self.assertIsNone(s['party'])
    def test_watch_slot_is_not_general_race(self):
        good,bad=normalize([poll(subject='2026 Tennessee')],POLICY,DAY)
        self.assertFalse(good);self.assertEqual(bad[0]['reason'],'matchup_not_reviewed')
    def test_corrections_replace_snapshot(self):
        result={'schema':'usa_confirmed_results_v1','results':[]}
        a=build_live([poll(),second()],POLICY,result,DAY,DAY,'test')
        b=build_live([poll()],POLICY,result,DAY,DAY,'test')
        self.assertEqual(a['races'][RID]['windows']['7']['status'],'poll_lead')
        self.assertEqual(b['races'][RID]['windows']['7']['status'],'insufficient_pollsters')
    def test_poll_list_accumulates_until_election_then_clears_from_live_board(self):
        results={'schema':'usa_confirmed_results_v1','results':[]}
        rows=[poll(),second()]
        before=build_live(rows,POLICY,results,'2026-11-03',DAY,'test')
        self.assertEqual(before['races'][RID]['phase'],'pre_election')
        self.assertEqual(len(before['races'][RID]['observations']),2)
        after=build_live(rows,POLICY,results,'2026-11-04',DAY,'test')
        closed=after['races'][RID]
        self.assertEqual(closed['phase'],'awaiting_certified_result')
        self.assertEqual(closed['observations'],[])
        self.assertEqual(closed['windows']['7']['status'],'election_closed')
        self.assertIsNone(closed['windows']['14']['party'])
        self.assertEqual(len(poll_history(rows,POLICY,'2026-11-04')['races'][RID]['observations']),2)
    def test_official_result_keeps_poll_display_closed(self):
        result={'race_id':RID,'contest_id':POLICY['races'][RID]['contest_id'],'status':'certified',
                'winner':'Kathy Hochul','party':'DEM','certified_on':'2026-12-01',
                'reviewed_on':'2026-12-02','source_url':'https://elections.ny.gov/certified-results',
                'evidence_note':'SYNTHETIC TEST ONLY'}
        board=build_live([poll()],POLICY,{'schema':'usa_confirmed_results_v1','results':[result]},
                         '2026-12-03',DAY,'test')
        self.assertEqual(board['races'][RID]['phase'],'certified_result')
        self.assertEqual(board['races'][RID]['observations'],[])
        self.assertEqual(board['races'][RID]['result']['winner'],'Kathy Hochul')
    def test_certified_result_guards(self):
        r={'race_id':RID,'contest_id':POLICY['races'][RID]['contest_id'],'status':'certified','winner':'Kathy Hochul',
           'party':'DEM','certified_on':'2026-12-01','reviewed_on':'2026-12-02',
           'source_url':'https://elections.ny.gov/certified-results','evidence_note':'SYNTHETIC TEST ONLY'}
        self.assertEqual(validated_results({'schema':'usa_confirmed_results_v1','results':[r]},POLICY,'2026-12-03')[RID]['party'],'DEM')
        for change in [{'party':'REP'},{'status':'leading'},{'contest_id':'old-election'},
                       {'source_url':'https://example.com'},{'certified_on':'2026-10-01'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                validated_results({'schema':'usa_confirmed_results_v1','results':[{**r,**change}]},POLICY,'2026-12-03')
        with self.assertRaises(ValueError):validated_results({'schema':'usa_confirmed_results_v1','results':[r]},POLICY,DAY)
    def test_failed_refresh_preserves_last_good(self):
        import refresh_live_polls
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'board.json';path.write_text('{"last_good":true}')
            with patch('sys.argv',['refresh','--output',str(path)]),patch.object(refresh_live_polls,'fetch_polls',side_effect=ValueError('bad schema')):
                self.assertEqual(refresh_live_polls.main(),1)
            self.assertEqual(path.read_text(),'{"last_good":true}')
            self.assertEqual(json.loads((Path(d)/'usa_election_live_polls_status_v1.json').read_text())['status'],'error')
    def test_failed_refresh_still_closes_election_poll_display(self):
        import refresh_live_polls
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'board.json'
            existing=build_live([poll()],POLICY,{'schema':'usa_confirmed_results_v1','results':[]},
                                DAY,DAY,'test')
            path.write_text(json.dumps(existing))
            with patch('sys.argv',['refresh','--output',str(path),'--as-of','2026-11-04']),\
                 patch.object(refresh_live_polls,'fetch_polls',side_effect=ValueError('offline')):
                self.assertEqual(refresh_live_polls.main(),1)
            updated=json.loads(path.read_text())
            self.assertEqual(updated['races'][RID]['observations'],[])
            self.assertEqual(updated['races'][RID]['windows']['7']['status'],'election_closed')
            self.assertEqual(updated['source_status'],'error_stale')
            self.assertEqual(json.loads((Path(d)/'usa_election_live_polls_status_v1.json').read_text())['status'],'error')
if __name__=='__main__':unittest.main()
