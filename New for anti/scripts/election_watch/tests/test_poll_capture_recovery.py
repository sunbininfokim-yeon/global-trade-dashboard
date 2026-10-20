"""A conflicting primary wave is isolated, never silently admitted or zero-filled."""
from copy import deepcopy
from unittest import TestCase
from tests.test_poll_html_evidence import HTMLEvidenceTests,Response,HTML
from tests.test_live_polls import poll
from tests.poll_config_fixture import SNAPSHOT_DAY
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.polls import read
from election_watch.live_polls import normalize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config/usa_polls'
class CaptureRecoveryTests(TestCase):
 def fixture(self):
  entry=HTMLEvidenceTests().entry();api=deepcopy(entry['record']);api['id']='synthetic-conflicting-provider';api['answers'][0]['pct']+=1
  snapshot={'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]}
  return entry,api,snapshot
 def merge(self,entry,rows,snapshot,isolated):
  return merge_primary_supplements(rows,snapshot,SNAPSHOT_DAY,opener=lambda req,**kw:Response(req.full_url,HTML),reviewed_entries=[entry],isolate_conflicts=isolated)
 def test_default_strict_behavior_still_rejects_unreviewed_conflict(self):
  e,a,s=self.fixture()
  with self.assertRaisesRegex(ValueError,'wave_conflict'):self.merge(e,[a],s,False)
 def test_capture_isolates_conflict_and_preserves_both_versions(self):
  e,a,s=self.fixture();healthy=poll(id='synthetic-healthy-other-race');rows,receipts=self.merge(e,[a,healthy],s,True)
  self.assertEqual(len(rows),2);receipt=receipts[0]
  self.assertEqual(receipt['status'],'primary_provider_conflict_reference_only')
  self.assertEqual(receipt['conflicting_provider_records'],[a]);self.assertEqual(rows[-1]['answers'],e['record']['answers'])
  policy=apply_targets(apply_matchups(read(C/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'targets_2026.json'),read(C/'ballot_reviews_2026.json'),SNAPSHOT_DAY)
  policy['quality_reviews']=read(C/'quality_reviews_2026.json')['reviews'];policy['quality_reviews'][e['record']['id']]['primary_documents']=e['documents']
  good,bad=normalize(rows,policy,SNAPSHOT_DAY);self.assertFalse(bad)
  primary=next(r for r in good if r['id']==e['record']['id']);self.assertFalse(primary['aggregation_eligibility']['eligible'])
  self.assertIn('primary_and_provider_wave_conflict',primary['aggregation_eligibility']['reasons'])
  self.assertTrue(next(r for r in good if r['id']==healthy['id'])['aggregation_eligibility']['eligible'])
 def test_identical_wave_still_deduplicates_without_quarantine(self):
  e,a,s=self.fixture();a['answers']=deepcopy(e['record']['answers']);rows,receipts=self.merge(e,[a],s,True)
  self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')
