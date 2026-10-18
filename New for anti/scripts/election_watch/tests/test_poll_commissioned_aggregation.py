"""Commissioned polls need exact initial-question review, not a party-wide waiver."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize, summarize
C=Path(__file__).resolve().parents[1]/'config'
class CommissionedAggregationTests(unittest.TestCase):
    def setUp(self):
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),'2026-10-18'),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),'2026-10-18')
        self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
        self.raw=deepcopy(next(e['record']for e in read(C/'usa_polls/primary_supplements_2026.json')['records']if e['record']['id']=='primary-dccc-wi-house01-20260929'))
    def normalize(self, raw=None, policy=None, day='2026-10-18'):
        return normalize([raw or self.raw],policy or self.policy,day)
    def test_exact_internal_initial_question_counts_and_retains_sponsor(self):
        obs,held=self.normalize();self.assertFalse(held)
        self.assertTrue(obs[0]['aggregation_eligibility']['eligible'])
        self.assertTrue(obs[0]['commissioning']['internal'])
        self.assertEqual(obs[0]['commissioning']['aggregation_policy'],'reviewed_commissioned_initial_ballot')
        self.assertEqual(obs[0]['source_quality']['sponsor_review']['commissioner'],'DCCC')
        self.assertEqual(obs[0]['commissioning']['sponsors'],['DCCC'])
        self.assertEqual(obs[0]['commissioning']['provider_sponsors'],[])
    def test_policy_off_and_earlier_snapshot_retain_reference(self):
        p=deepcopy(self.policy);p['commissioned_poll_aggregation']['enabled']=False
        obs,held=self.normalize(policy=p);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
        obs,held=self.normalize(day='2026-10-08');self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
    def test_unreviewed_or_changed_record_does_not_inherit_admission(self):
        for patch in ({'sponsors':['another sponsor']},{'sample_size':501},{'id':'another-wave'}):
            raw={**deepcopy(self.raw),**patch};obs,held=self.normalize(raw)
            self.assertFalse(obs);self.assertTrue(held)
    def test_other_exclusions_and_noninitial_questions_remain_reference(self):
        for patch in ({'ballot_format':'forced_two_candidate_after_undecided_probe'},
                      {'admission':{'signal_exclusion_reasons':['party_internal_reference','methodology_incomplete_reference']}}):
            p=deepcopy(self.policy);r=p['quality_reviews'][self.raw['id']]
            for k,v in patch.items():
                if isinstance(v,dict):r[k].update(v)
                else:r[k]=v
            obs,held=self.normalize(policy=p);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
    def test_count_is_after_same_wave_dedup(self):
        p=deepcopy(self.policy);p['commissioned_poll_aggregation']['reviewed_on']='2026-10-08'
        obs,held=self.normalize(policy=p,day='2026-10-08');self.assertFalse(held)
        result=summarize(obs+deepcopy(obs),p['races']['USA:WI:house:01'],'2026-10-08',30)
        self.assertEqual(result['pollster_count'],1);self.assertEqual(result['commissioned_poll_count'],1)
        obs[0]['aggregation_eligibility']={'eligible':False,'reasons':['primary_source_unavailable_or_changed']}
        result=summarize(obs,p['races']['USA:WI:house:01'],'2026-10-08',30)
        self.assertEqual(result['pollster_count'],0);self.assertEqual(result['commissioned_poll_count'],0)
    def test_published_contract_describes_the_effective_policy(self):
        from election_watch.live_polls import build_live
        board=build_live([self.raw],self.policy,{'schema':'usa_confirmed_results_v1','cycle':2026,'results':[]},'2026-10-18','2026-10-18T22:00:00+00:00','https://api.votehub.com/polls')
        self.assertTrue(board['commissioned_poll_aggregation']['effective'])
        self.assertIn('정당·후보 의뢰 조사도 집계',board['rules_ko'][4])
        self.assertNotIn('내부·정파 조사는 우세 집계 제외',board['rules_ko'][4])
