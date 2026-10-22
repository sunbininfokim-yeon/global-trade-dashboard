from tests.poll_config_fixture import SNAPSHOT_DAY
"""Reviewed MS source admission; incomplete evidence is never a fresh win."""
from copy import deepcopy
from pathlib import Path
import hashlib,io,unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class MSSourceExpansionTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/MS-source-expansion-20261019.json');self.raw=self.audit['records'][0]['provider_record'];self.packet=read(C/'state_evidence/2026/MS.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews'];self.policy['quality_reviews'][self.raw['id']]=deepcopy(self.audit['records'][0]['primary_review'])
 def test_reviewed_source_values_and_metadata_remain_exact(self):
  rows=[self.raw];obs,held=normalize(rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),1)
  self.assertEqual(obs[0]['sample_n'],self.raw['sample_size']);self.assertEqual({a['name']:a['pct']for a in obs[0]['answers']},{a['choice']:a['pct']for a in self.raw['answers']})
  self.assertEqual(obs[0]['source_quality']['verification_level'],'primary_toplines_checked');self.assertIsNone(obs[0]['source_quality']['accuracy_grade'])
 def test_changed_sample_or_commissioner_needs_recheck(self):
  for patch in ({'sample_size':9999},{'sponsors':['unknown commissioner']}):
   raw={**deepcopy(self.raw),**patch};obs,held=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertTrue(held)
 def test_capture_provenance_and_finance_not_refreshed(self):
  self.assertFalse(self.audit['new_provider_collection']);self.assertFalse(self.audit['finance_recollected']);self.assertFalse(self.audit['new_provider_collection'])
 def test_old_or_incomplete_source_never_generates_current_lead(self):
  obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
  for window in (7,14):self.assertIsNone(summarize(obs,self.policy['races'][obs[0]['race_id']],DAY,window)['party'])
 def test_source_outage_preserves_original_record_and_provider_conflict_is_held(self):
  entry={'state':'MS','reviewed_on':DAY,'record':deepcopy(self.raw),'record_sha256':self.policy['quality_reviews'][self.raw['id']]['primary_supplement_record_sha256'],'documents':deepcopy(self.policy['quality_reviews'][self.raw['id']]['primary_documents'])}
  def fail(req,timeout):raise OSError('synthetic source outage')
  rows,receipts=merge_primary_supplements([],{'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]},DAY,['MS'],fail,reviewed_entries=[entry])
  self.assertEqual(rows[0]['end_date'],self.raw['end_date']);self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
  obs,held=normalize(rows,self.policy,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
  changed=deepcopy(self.raw);changed['id']='later-api-same-wave';changed['answers'][0]['pct']+=1
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([changed],{'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]},DAY,['MS'],fail,reviewed_entries=[entry])
