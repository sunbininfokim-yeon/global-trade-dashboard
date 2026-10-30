from tests.poll_config_fixture import SNAPSHOT_DAY
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class KYWaveTwoTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/KY-wave2-20261019.json');self.rows=[r['provider_record']for r in self.audit['records']];self.packet=read(C/'state_evidence/2026/KY.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_commissioned_questions_from_distinct_institutions_count_once_each(self):
  rows=self.packet['capture']['provider_records']+self.packet['capture']['primary_records'];obs,held=normalize(rows,self.policy,DAY);race=self.policy['races']['USA:KY:house:06']
  self.assertEqual({o['pollster_group']for o in obs},{'change_research','dccc_analytics'})
  signal=summarize(obs,race,DAY,14);self.assertEqual(signal['party'],'DEM');self.assertEqual(signal['pollster_count'],2);self.assertEqual(signal['commissioned_poll_count'],2)
  self.assertEqual(summarize(obs,race,DAY,7)['pollster_count'],0)
 def test_html_evidence_region_and_finite_release_are_bound(self):
  entry=next(e for e in read(C/'usa_polls/primary_supplements_2026.json')['records']if e['record']['id']==self.rows[0]['id']);doc=entry['documents'][0]
  self.assertEqual(doc['format'],'reviewed_html_region_v1');self.assertEqual(doc['selector'],{'tag':'div','id':'site-canvas'});self.assertEqual(len(doc['sha256']),64)
  self.assertTrue(self.rows[0]['internal']);self.assertEqual(self.rows[0]['sponsors'],['DCCC'])
 def test_source_failure_and_later_provider_duplicate_keep_boundaries(self):
  from election_watch.poll_primary_supplements import merge_primary_supplements
  entry=next(e for e in read(C/'usa_polls/primary_supplements_2026.json')['records']if e['record']['id']==self.rows[0]['id']);snap={'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]}
  def fail(req,timeout):raise OSError('synthetic source failure')
  api=deepcopy(self.rows[0]);api['id']='later-provider-id';rows,receipts=merge_primary_supplements([api],snap,DAY,['KY'],fail);self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['later-provider-id'])
  obs,held=normalize(rows,self.policy,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible']);self.assertEqual(obs[0]['field_end'],'2026-10-05')
  api['answers'][0]['pct']=47
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([api],snap,DAY,['KY'],fail)
