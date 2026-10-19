from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class GAWaveTwoTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/GA-wave2-20261019.json');self.rows=[r['provider_record']for r in self.audit['records']];self.packet=read(C/'state_evidence/2026/GA.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_original_pollster_owned_publication_is_individually_reviewed(self):
  obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);o=obs[0];self.assertTrue(o['aggregation_eligibility']['eligible']);self.assertEqual([a['pct']for a in o['answers']],[49,47])
  self.assertEqual(o['source_quality']['disclosure_review']['weighting'],'age_race_gender_political_affiliation')
  for days in (7,14):self.assertEqual(summarize(obs,self.policy['races'][o['race_id']],DAY,days)['party'],'REP')
 def test_direct_source_transport_gap_is_not_claimed_resolved(self):
  review=self.audit['records'][0]['primary_review'];self.assertEqual(review['primary_web_review']['direct_http_status'],'timeout');self.assertIsNone(review['primary_web_review']['raw_response_sha256'])
  self.assertEqual(review['primary_web_review']['status'],'primary_text_read_via_web');self.assertEqual(self.audit['source_receipts'][0]['error'],'<urlopen error timed out>')
 def test_new_wave_and_changed_commissioner_need_new_review(self):
  for patch in ({'id':'unreviewed-james-wave'},{'sponsors':['another funder']},{'sample_size':801}):
   obs,held=normalize([{**deepcopy(self.rows[0]),**patch}],self.policy,DAY);self.assertFalse(obs);self.assertTrue(held)
