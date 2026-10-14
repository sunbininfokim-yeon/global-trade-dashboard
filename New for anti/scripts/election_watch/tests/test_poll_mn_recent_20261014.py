"""Minnesota Q7 primary values, unchanged-release admission and state-only replay."""
import copy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize
from publish_state_packets import rebuild

ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT.parents[1]/'public/data'

class MinnesotaRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=next(p for p in packets() if p['state']=='MN')
        cls.policy=apply_targets(apply_matchups(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),'2026-10-14'),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),'2026-10-14')
        cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
        cls.raw=next(r for r in cls.packet['capture']['provider_records'] if r['id']=='us-202sur83d49b6b')

    def test_q3_values_and_credibility_interval_are_not_fabricated_sampling_error(self):
        observations,held=normalize([self.raw],self.policy,'2026-10-14')
        self.assertFalse(held);row=observations[0]
        self.assertEqual({a['name']:a['pct'] for a in row['answers']},{'Jake Johnson':46,'Brad Finstad':44})
        self.assertEqual(row['sample_n'],565);self.assertEqual(row['field_end'],'2026-10-09')
        self.assertTrue(row['aggregation_eligibility']['eligible'])
        self.assertEqual(self.policy['races']['USA:MN:house:01']['candidates']['Jake Johnson']['canonical_name'],'Jacob \"Jake\" Johnson')
        self.assertEqual(row['source_quality']['reported_precision']['kind'],'credibility_interval')
        self.assertEqual(row['source_quality']['reported_precision']['half_width_pp'],4.6)
        self.assertIsNone(row['margin_of_error_pp']);self.assertIsNone(row['source_quality']['accuracy_grade'])

    def test_changed_metadata_or_new_release_is_not_automatically_reviewed(self):
        changed=copy.deepcopy(self.raw);changed['sample_size']=566
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
        changed=copy.deepcopy(self.raw);changed['id']='new-unreviewed-mn-wave'
        rows,held=normalize([changed],self.policy,'2026-10-14')
        self.assertFalse(rows);self.assertEqual(held[0]['reason'],'commissioner_not_reviewed')

    def test_state_only_replay_keeps_other_races_history_dates_and_house_focus(self):
        old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
        new,archive=rebuild(old,history,[self.packet],PUBLIC)
        for rid,race in old['races'].items():
            if race['state']!='MN':
                self.assertEqual(new['races'][rid],race,rid)
                if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
        for key in ('as_of','fetched_at'):self.assertEqual(new[key],old[key])
        for rid,race in old['house_poll_focus']['races'].items():
            if race['state']!='MN':self.assertEqual(new['house_poll_focus']['races'][rid],race,rid)
        self.assertEqual(new['house_poll_focus']['race_count'],104)
        self.assertEqual(new['state_captures']['MN']['captured_at'],'2026-10-14T05:14:02.840821+00:00')

if __name__=='__main__':unittest.main()
