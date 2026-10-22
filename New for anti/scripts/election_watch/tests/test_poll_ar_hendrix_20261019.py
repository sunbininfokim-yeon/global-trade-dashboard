from tests.poll_config_fixture import SNAPSHOT_DAY
"""AR exact-release evidence; original rounded API value remains auditable."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.live_polls import normalize,summarize
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';DAY='2026-10-18'
class ARHendrixReleaseTests(unittest.TestCase):
    def setUp(self):
        self.audit=read(ROOT.parent.parent/'public/data/usa_election_poll_release_reviews/2026/AR-hendrix-20261019.json')
        self.raw=self.audit['records'][0]['provider_record']
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
        self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
    def test_primary_values_n_and_both_windows(self):
        obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);o=obs[0]
        self.assertEqual([a['pct']for a in o['answers']],[50,41,4.5]);self.assertEqual(o['sample_n'],709)
        self.assertEqual(o['source_quality']['verification_level'],'primary_toplines_checked')
        self.assertTrue(o['aggregation_eligibility']['eligible'])
        self.assertIsNone(o['source_quality']['accuracy_grade'])
        for days in (7,14):self.assertEqual(summarize(obs,self.policy['races']['USA:AR:senate'],DAY,days)['party'],'REP')
    def test_original_value_is_never_overwritten(self):
        saved=deepcopy(self.raw);obs,_=normalize([self.raw],self.policy,DAY)
        self.assertEqual(self.raw,saved);self.assertEqual(self.raw['answers'][2]['pct'],5)
        self.assertEqual(obs[0]['provider_answer_correction']['provider_values'],{'Jeff Wadlin':5})
    def test_changed_provider_question_or_value_needs_review(self):
        for field,value in [('sample_size',710),('internal',True),('sponsors',[])]:
            raw={**deepcopy(self.raw),field:value};self.assertFalse(normalize([raw],self.policy,DAY)[0])
        raw=deepcopy(self.raw);raw['answers'][0]['pct']=51;self.assertFalse(normalize([raw],self.policy,DAY)[0])
    def test_future_hendrix_release_does_not_inherit_individual_admission(self):
        raw=deepcopy(self.raw);raw['id']='future-other-release';obs,held=normalize([raw],self.policy,DAY)
        self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
    def test_partial_roster_not_upgraded_to_official_or_winner(self):
        self.assertFalse(self.audit['official_full_ballot_obtained']);self.assertFalse(self.audit['finance_recollected'])
        race=self.policy['races']['USA:AR:senate'];self.assertIsNone(race['ballot_competition']['general_unopposed'])
        obs,_=normalize([self.raw],self.policy,DAY);self.assertIsNone(obs[0]['answers'][2]['party'])
