from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class FLWaveTwoTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/FL-wave2-20261019.json');self.rows=[r['provider_record']for r in self.audit['records']];self.packet=read(C/'state_evidence/2026/FL.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_precise_toplines_question_samples_and_current_windows(self):
  obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),2)
  self.assertEqual([[a['pct']for a in o['answers']]for o in obs],[[45.9,43.8],[47.6,42.4]])
  for o in obs:
   self.assertEqual(o['sample_n'],2351);self.assertTrue(o['aggregation_eligibility']['eligible']);self.assertIsNone(o['source_quality']['accuracy_grade'])
   self.assertIsNone(summarize([o],self.policy['races'][o['race_id']],DAY,7)['party'])
   self.assertEqual(summarize([o],self.policy['races'][o['race_id']],DAY,14)['party'],'REP')
 def test_staged_corrections_preserve_original_answers_and_sample(self):
  obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);sen=next(o for o in obs if o['race_id']=='USA:FL:senate')
  self.assertEqual(sen['provider_answer_correction']['provider_values'],{'Ashley Moody':48.0,'Angie Nixon':42.0})
  self.assertEqual(sen['provider_metadata_correction']['provider_values'],{'sample_size':800});self.assertEqual(sen['provider_metadata_correction']['primary_values_used'],{'sample_size':2351})
 def test_corrupt_intermediate_binding_does_not_waive_correction_guards(self):
  p=deepcopy(self.policy);p['quality_reviews']['us-202mdwe9967dcc']['provider_metadata_correction']['provider_snapshot_sha256']='0'*64
  obs,held=normalize([self.rows[1]],p,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'provider_correction_snapshot_changed')
 def test_changed_sample_sponsor_answers_or_wave_do_not_inherit_review(self):
  for patch in ({'sample_size':801},{'sponsors':['other']},{'answers':[{'choice':'Ashley Moody','pct':49},{'choice':'Angie Nixon','pct':42}]}):
   raw={**deepcopy(self.rows[1]),**patch};obs,held=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertTrue(held)
  raw={**deepcopy(self.rows[1]),'id':'future-unreviewed-mdw-wave'};obs,held=normalize([raw],self.policy,DAY)
  self.assertFalse(held);self.assertEqual(len(obs),1);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
  self.assertEqual(obs[0]['sample_n'],800);self.assertNotIn('provider_answer_correction',obs[0]);self.assertNotIn('provider_metadata_correction',obs[0])
 def test_fresh_request_and_old_primary_receipts_are_distinct(self):
  self.assertTrue(self.audit['new_provider_collection']);self.assertFalse(self.audit['provider_payload_changed_since_previous_request']);self.assertFalse(self.audit['finance_recollected'])
  self.assertNotEqual(self.packet['capture']['receipt']['previous_capture_at'],self.packet['capture']['fetched_at']);self.assertTrue(all(r['primary_source_capture']['checked_at']<self.packet['capture']['fetched_at']for r in self.packet['capture']['primary_records']))
