"""Exact university-linked sheet admission; both questions have n=650."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';DAY='2026-10-18'
class IAEmersonSourceTests(unittest.TestCase):
    def setUp(self):
        self.audit=read(ROOT.parent.parent/'public/data/usa_election_poll_release_reviews/2026/IA-source-expansion-20261019.json')
        self.rows=[r['provider_record']for r in self.audit['records'] if r['provider_record']['id'].startswith(('gov202eme','us-202eme'))]
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY)
        self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
    def test_both_primary_questions_eligible_and_precise_values_retained(self):
        obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),2)
        for o in obs:
            self.assertTrue(o['aggregation_eligibility']['eligible']);self.assertEqual(o['sample_n'],650)
            self.assertEqual(o['source_quality']['reported_precision']['kind'],'credibility_interval')
            self.assertEqual(o['source_quality']['verification_level'],'primary_toplines_checked')
            self.assertIsNone(summarize([o],self.policy['races'][o['race_id']],DAY,7)['party'])
            self.assertIn(summarize([o],self.policy['races'][o['race_id']],DAY,14)['party'],('DEM','REP'))
        self.assertEqual(obs[1]['answers'][1]['pct'],46.6)
    def test_changed_api_record_requires_individual_recheck(self):
        for changes in ({'sample_size':651},{'sponsors':[]},{'population':'rv'}):
            raw={**deepcopy(self.rows[0]),**changes};self.assertFalse(normalize([raw],self.policy,DAY)[0])
    def test_new_sheet_wave_is_reference_not_blanket_primary_approval(self):
        raw=deepcopy(self.rows[0]);raw['id']='different-emerson-wave'
        obs,held=normalize([raw],self.policy,DAY);self.assertFalse(held)
        self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
    def test_original_evidence_clocks_and_money_unchanged(self):
        self.assertFalse(self.audit['new_provider_collection']);self.assertTrue(self.audit['preserved_primary_records'])
        self.assertFalse(self.audit['finance_recollected'])

    def test_existing_suffolk_observations_are_preserved_with_their_original_dates(self):
        packet=read(C/'state_evidence/2026/IA.json')
        rows=packet['capture']['primary_records']
        self.assertEqual({r['id']for r in rows},{'primary-suffolk-ia-senate-20261007','primary-suffolk-ia-governor-20261007'})
        self.assertTrue(all(r['end_date']=='2026-10-04'for r in rows))

    def test_yougov_question_n_is_not_the_study_sample(self):
        raw=next(r['provider_record']for r in self.audit['records']if r['provider_record']['id']=='gov202youbb5e2c57')
        obs,held=normalize([raw],self.policy,DAY);self.assertFalse(held);self.assertEqual(obs[0]['sample_n'],2244)
        self.assertEqual(obs[0]['provider_sample_correction']['original_provider_sample_n'],2245)
        self.assertIsNone(obs[0]['source_quality']['reported_precision'])
        for days in (7,14):self.assertEqual(summarize(obs,self.policy['races']['USA:IA:governor'],DAY,days)['party'],'DEM')
