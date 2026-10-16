"""Florida's forced-choice partisan reference cannot become an ordinary poll signal."""
import copy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize,summarize
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT.parents[1]/'public/data'

class FloridaRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=next(p for p in packets() if p['state']=='FL')
        cls.policy=apply_targets(apply_matchups(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
        cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
        cls.raw=next(r for r in cls.packet['capture']['provider_records'] if r['id']=='gov202chaea67d341')

    def test_primary_lv_result_is_visible_but_not_a_signal_or_full_sample_moe(self):
        rows,held=normalize([self.raw],self.policy,'2026-10-14');self.assertFalse(held)
        row=rows[0]
        self.assertEqual({a['name']:a['pct'] for a in row['answers']},{'Byron Donalds':47,'David Jolly':47})
        self.assertEqual(row['sample_n'],920);self.assertEqual(row['population'],'lv')
        self.assertFalse(row['aggregation_eligibility']['eligible'])
        self.assertIn('forced_choice_after_undecided_probe',row['aggregation_eligibility']['reasons'])
        self.assertIn('party_commissioned_reference',row['aggregation_eligibility']['reasons'])
        self.assertEqual(row['source_quality']['reported_precision']['kind'],'modeled_error')
        self.assertEqual(row['source_quality']['reported_precision']['scope'],'whole_survey_RV1106')
        self.assertIsNone(row['margin_of_error_pp']);self.assertIsNone(row['source_quality']['accuracy_grade'])
        self.assertIsNone(summarize(rows,self.policy['races']['USA:FL:governor'],'2026-10-14',7)['party'])

    def test_changed_sample_or_future_record_has_no_automatic_approval(self):
        changed=copy.deepcopy(self.raw);changed['sample_size']=921
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
        changed=copy.deepcopy(self.raw);changed['id']='unreviewed-fl-next-wave'
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertIn(held[0]['reason'],('pollster_not_selected','unregistered_primary_host','commissioner_not_reviewed','internal_or_partisan'))

    def test_replay_keeps_other_states_history_dates_and_focus(self):
        old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
        new,archive=rebuild(old,history,[self.packet],PUBLIC)
        for rid,race in old['races'].items():
            if race['state']!='FL':
                self.assertEqual(new['races'][rid],race,rid)
                if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
        for key in ('as_of','fetched_at'):self.assertEqual(new[key],old[key])
        for rid,race in old['house_poll_focus']['races'].items():
            if race['state']!='FL':self.assertEqual(new['house_poll_focus']['races'][rid],race,rid)
        self.assertEqual(new['house_poll_focus']['race_count'],104)

if __name__=='__main__':unittest.main()
