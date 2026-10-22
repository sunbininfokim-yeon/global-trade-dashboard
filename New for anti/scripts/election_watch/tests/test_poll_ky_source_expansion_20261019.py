from tests.poll_config_fixture import SNAPSHOT_DAY
"""Reviewed KY source admission; incomplete evidence is never a fresh win."""
from copy import deepcopy
from pathlib import Path
import hashlib,io,unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class KYSourceExpansionTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/KY-source-expansion-20261019.json');self.raw=self.audit['records'][0]['provider_record'];self.packet=read(C/'state_evidence/2026/KY.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_reviewed_source_values_and_metadata_remain_exact(self):
  obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),1)
  self.assertEqual(obs[0]['sample_n'],self.raw['sample_size']);self.assertEqual({a['name']:a['pct']for a in obs[0]['answers']},{a['choice']:a['pct']for a in self.raw['answers']})
  self.assertEqual(obs[0]['source_quality']['verification_level'],'primary_toplines_checked');self.assertIsNone(obs[0]['source_quality']['accuracy_grade'])
 def test_changed_sample_or_commissioner_needs_recheck(self):
  for patch in ({'sample_size':9999},{'sponsors':['unknown commissioner']}):
   raw={**deepcopy(self.raw),**patch};obs,held=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertTrue(held)
 def test_capture_provenance_and_finance_not_refreshed(self):
  self.assertFalse(self.audit['new_provider_collection']);self.assertFalse(self.audit['finance_recollected'])
  followup=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/KY-wave2-20261019.json')
  self.assertTrue(followup['new_provider_collection']);self.assertFalse(followup['finance_recollected']);self.assertTrue(self.packet['capture']['receipt']['new_provider_collection'])
 def test_middle_initial_alias_and_commissioning_policy_are_explicit(self):
  race=self.policy['races']['USA:KY:house:06'];self.assertEqual(race['candidates']['Ralph Alvarado']['canonical_name'],'Ralph A. Alvarado')
  obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);self.assertEqual(obs[0]['commissioning']['partisan'],'DEM');self.assertEqual(obs[0]['commissioning']['sponsors'],['Kentuckians Not Corruption'])
  enabled=self.policy.get('commissioned_poll_aggregation',{}).get('enabled',False);self.assertEqual(obs[0]['aggregation_eligibility']['eligible'],enabled)
  self.assertEqual(summarize(obs,race,DAY,7)['pollster_count'],0)
  self.assertEqual(summarize(obs,race,DAY,14)['pollster_count'],int(enabled))
