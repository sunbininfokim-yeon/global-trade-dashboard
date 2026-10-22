"""MS source review: one wave, distinct initial questions and original receipts."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.state_inputs import validate_packet
from tests.poll_config_fixture import SNAPSHOT_DAY
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';PUBLIC=ROOT.parents[1]/'public/data';DAY='2026-10-21';ID='primary-dfp-ms-senate-20260815'
class MSQuestionReviewTests(unittest.TestCase):
 def setUp(self):
  self.packet=read(C/'state_evidence/2026/MS.json');self.audit=read(ROOT/'research/2026/MS/source-recheck-20261021.json')
  self.entry=next(e for e in read(C/'usa_polls/primary_supplements_2026.json')['records']if e['record']['id']==ID)
  self.api=next(r for r in self.packet['capture']['provider_records']if r['id']=='us-202dat084dfba9')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
  self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_current_q3_keeps_original_field_values_and_actual_publication(self):
  row=next(r for r in self.packet['capture']['primary_records']if r['id']==ID)
  good,bad=normalize([row],self.policy,DAY);self.assertFalse(bad);self.assertEqual(len(good),1)
  o=good[0];self.assertEqual((o['provider_record_date'],o['field_start'],o['field_end']),('2026-08-28','2026-08-05','2026-08-15'))
  self.assertEqual({a['name']:a['pct']for a in o['answers']},{'Scott Colom':38,'Cindy Hyde-Smith':44,'Ty Pinkins':7})
  self.assertEqual(row['sponsors'],['Way to Lead PAC','Democracy Alliance','Democracy Strategy Partners'])
  self.assertEqual(o['source_quality']['disclosure_review']['wave_id'],'ms-dfp-20260805-20260815')
  self.assertFalse(o['aggregation_eligibility']['eligible'])
  for w in (7,14):self.assertIsNone(summarize(good,self.policy['races']['USA:MS:senate'],DAY,w)['party'])
 def test_exact_api_q4_is_distinct_but_incomplete_general_ballot_is_held(self):
  def offline(*a,**kw):raise OSError('synthetic source outage')
  rows,receipts=merge_primary_supplements([self.api],{'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[self.entry]},DAY,opener=offline,reviewed_entries=[self.entry])
  self.assertEqual(len(rows),2);self.assertEqual(receipts[0]['separate_question_provider_ids'],[self.api['id']])
  self.assertNotIn('conflict_reason',receipts[0]);good,bad=normalize(rows,self.policy,DAY)
  self.assertEqual(len(good),1);self.assertEqual([(r['id'],r['reason'])for r in bad],[(self.api['id'],'reviewed_initial_two_candidate_question_omits_ballot_minor_candidate')])
  self.assertEqual(self.api['created_at'],'2026-08-29');self.assertEqual(self.api['sponsors'],['Way to Lead PAC'])
 def test_changed_api_does_not_inherit_question_approval(self):
  api=deepcopy(self.api);api['answers'][0]['pct']+=1
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
   merge_primary_supplements([api],{'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[self.entry]},DAY)
 def test_state_scope_original_receipt_and_no_finance_collection(self):
  names={s:v['name']for s,v in read(C/'usa_polls/targets_2026.json')['states'].items()};validate_packet(self.packet,names)
  r=self.packet['capture']['receipt'];self.assertTrue(r['new_provider_collection']);self.assertFalse(r['federal_finance_recollected'])
  self.assertEqual(r['prior_capture_receipt'],self.audit['previous_capture_receipt'])
  self.assertEqual(self.audit['source_receipts'][0]['sha256'],self.entry['documents'][0]['sha256'])
 def test_replay_preserves_other_races_history_and_focus(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');hist=read(PUBLIC/'usa_election_poll_history_2026.json');new,nh=rebuild(old,hist,[self.packet],PUBLIC)
  for rid,r in old['races'].items():
   if not rid.startswith('USA:MS:'):self.assertEqual(new['races'][rid],r)
  for rid,r in hist['races'].items():
   if not rid.startswith('USA:MS:'):self.assertEqual(nh['races'][rid],r)
  self.assertEqual(set(new['house_poll_focus']['races']),set(old['house_poll_focus']['races']))
  for rid,r in old['house_poll_focus']['races'].items():
   if not rid.startswith('USA:MS:'):self.assertEqual(new['house_poll_focus']['races'][rid],r)
  for k in ('as_of','fetched_at'):self.assertEqual(new[k],old[k])
