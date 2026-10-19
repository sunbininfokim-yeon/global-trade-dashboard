from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class MOWaveTwoTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/MO-wave2-20261019.json');self.rows=[r['provider_record']for r in self.audit['records']];self.packet=read(C/'state_evidence/2026/MO.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_initial_named_ballot_is_separate_from_informed_and_generic_questions(self):
  obs,held=normalize(self.packet['capture']['primary_records'],self.policy,DAY);self.assertFalse(held);o=obs[0]
  self.assertEqual([a['pct']for a in o['answers']],[41,44]);self.assertEqual(o['source_quality']['disclosure_review']['excluded_informed_question'],{'Fred Wellman':48,'Ann Wagner':41});self.assertEqual(o['sample_n'],600)
 def test_historical_observation_never_becomes_current_lead(self):
  obs,held=normalize(self.packet['capture']['primary_records'],self.policy,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible']);self.assertEqual(obs[0]['display_group'],'historical_matchup_reference')
  for days in (7,14):self.assertEqual(summarize(obs,self.policy['races']['USA:MO:house:02'],DAY,days)['pollster_count'],0)
 def test_source_failure_preserves_original_date_and_conflicting_api_is_held(self):
  from election_watch.poll_primary_supplements import merge_primary_supplements
  entry=next(e for e in read(C/'usa_polls/primary_supplements_2026.json')['records']if e['state']=='MO')
  snap={'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]}
  def fail(req,timeout):raise OSError('synthetic source failure')
  rows,receipts=merge_primary_supplements([],snap,DAY,['MO'],fail);self.assertEqual(rows[0]['end_date'],'2026-05-31');self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
  obs,held=normalize(rows,self.policy,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
  raw=deepcopy(self.rows[0]);raw['id']='later-provider-wave';raw['sample_size']=601
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([raw],snap,DAY,['MO'],fail)
