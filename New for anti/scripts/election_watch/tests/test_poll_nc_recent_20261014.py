"""North Carolina Q3 primary values, unchanged-release admission and state-only replay."""
import copy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY

ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT.parents[1]/'public/data'

class NorthCarolinaRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=next(p for p in packets() if p['state']=='NC')
        cls.policy=apply_targets(apply_matchups(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
        cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
        cls.raw=next(r for r in cls.packet['capture']['provider_records'] if r['id']=='us-202surbcf9e1be')

    def test_q3_values_and_credibility_interval_are_not_fabricated_sampling_error(self):
        observations,held=normalize([self.raw],self.policy,'2026-10-14')
        self.assertFalse(held);row=observations[0]
        self.assertEqual({a['name']:a['pct'] for a in row['answers']},{'Roy Cooper':54,'Michael Whatley':40})
        self.assertEqual(row['sample_n'],643);self.assertEqual(row['field_end'],'2026-10-11')
        self.assertTrue(row['aggregation_eligibility']['eligible'])
        self.assertEqual(row['source_quality']['reported_precision']['kind'],'credibility_interval')
        self.assertEqual(row['source_quality']['reported_precision']['half_width_pp'],5)
        self.assertIsNone(row['margin_of_error_pp']);self.assertIsNone(row['source_quality']['accuracy_grade'])

    def test_changed_metadata_or_new_release_is_not_automatically_reviewed(self):
        changed=copy.deepcopy(self.raw);changed['sample_size']=644
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
        changed=copy.deepcopy(self.raw);changed['id']='new-unreviewed-nc-wave'
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertEqual(held[0]['reason'],'commissioner_not_reviewed')

    def test_state_only_replay_keeps_other_races_history_dates_and_house_focus(self):
        old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
        new,archive=rebuild(old,history,[self.packet],PUBLIC)
        for rid,race in old['races'].items():
            if race['state']!='NC':
                self.assertEqual(new['races'][rid],race,rid)
                if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
        for key in ('as_of','fetched_at'):self.assertEqual(new[key],old[key])
        for rid,race in old['house_poll_focus']['races'].items():
            if race['state']!='NC':self.assertEqual(new['house_poll_focus']['races'][rid],race,rid)
        self.assertEqual(new['house_poll_focus']['race_count'],104)
        self.assertEqual(new['state_captures']['NC']['captured_at'],'2026-10-14T05:14:02.840821+00:00')

if __name__=='__main__':unittest.main()
