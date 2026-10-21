"""CA reviewed document versions; old field dates and reference exclusions stay."""
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.state_inputs import validate_packet
from tests.poll_config_fixture import SNAPSHOT_DAY
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';PUBLIC=ROOT.parents[1]/'public/data';DAY='2026-10-21'
IDS={'primary-ppic-ca-governor-20260910','primary-ppic-ca-governor-20260706','primary-ivc-ca-governor-20261002'}
class CASourceRecheckTests(unittest.TestCase):
 def setUp(self):
  self.packet=read(C/'state_evidence/2026/CA.json');self.audit=read(ROOT/'research/2026/CA/source-recheck-20261021.json')
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
  self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def observations(self):
  rows=[r for r in self.packet['capture']['primary_records']if r['id']in IDS];good,bad=normalize(rows,self.policy,DAY)
  self.assertFalse(bad);self.assertEqual(len(good),3);return {r['id']:r for r in good}
 def test_versions_rechecked_but_not_new_polls_or_advanced_field_dates(self):
  obs=self.observations()
  for ident,shares,n,end in [('primary-ppic-ca-governor-20260910',[60,38],1103,'2026-09-10'),('primary-ppic-ca-governor-20260706',[61,36],1003,'2026-07-06'),('primary-ivc-ca-governor-20261002',[48,38],2906,'2026-10-02')]:
   o=obs[ident];self.assertEqual([a['pct']for a in o['answers']],shares);self.assertEqual(o['sample_n'],n);self.assertEqual(o['field_end'],end)
   self.assertEqual(o['source_quality']['reviewed_on'],DAY)
   for w in (7,14):self.assertIsNone(summarize([o],self.policy['races']['USA:CA:governor'],DAY,w)['party'])
 def test_new_exact_fingerprints_match_actual_receipts(self):
  receipts={r['url']:r for r in self.audit['source_receipts']}
  for e in read(C/'usa_polls/primary_supplements_2026.json')['records']:
   if e['record']['id']not in IDS:continue
   self.assertEqual(e['reviewed_on'],DAY)
   for d in e['documents']:
    self.assertEqual(receipts[d['url']]['status'],200)
    if d.get('format')!='reviewed_html_article_v1':self.assertEqual(d['sha256'],receipts[d['url']]['sha256'])
    else:self.assertEqual(d['sha256'],'d7273edcce7efa8e7ca0c70e547471aec726e8f46072b0f5bee506aa0d127510')
  observed=[r for r in self.packet['capture']['receipt']['primary_supplement_receipts']if r['id']in IDS]
  self.assertEqual(len(observed),3);self.assertTrue(all(r['status']=='primary_documents_rechecked'for r in observed))
 def test_ivc_question_and_leaner_gap_does_not_gain_signal_permission(self):
  o=self.observations()['primary-ivc-ca-governor-20261002'];self.assertFalse(o['aggregation_eligibility']['eligible'])
  self.assertFalse(o['source_quality']['disclosure_review']['question_wording_checked'])
 def test_new_capture_retains_prior_receipt_and_no_finance_refresh(self):
  r=self.packet['capture']['receipt'];self.assertTrue(r['new_provider_collection']);self.assertFalse(r['federal_finance_recollected']);self.assertEqual(r['prior_capture_receipt'],self.audit['previous_capture_receipt'])
  self.assertFalse(self.audit['provider_delta']['missing_ids']);self.assertFalse(self.audit['provider_delta']['changed_ids'])
  names={s:v['name']for s,v in read(C/'usa_polls/targets_2026.json')['states'].items()};validate_packet(self.packet,names)
 def test_state_replay_is_idempotent_and_preserves_other_states(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');hist=read(PUBLIC/'usa_election_poll_history_2026.json');new,nh=rebuild(old,hist,[self.packet],PUBLIC);again,ah=rebuild(new,nh,[self.packet],PUBLIC)
  self.assertEqual(new,again);self.assertEqual(nh,ah)
  for rid,r in old['races'].items():
   if not rid.startswith('USA:CA:'):self.assertEqual(new['races'][rid],r)
  for rid,r in hist['races'].items():
   if not rid.startswith('USA:CA:'):self.assertEqual(nh['races'][rid],r)
  for rid,r in old['house_poll_focus']['races'].items():
   if not rid.startswith('USA:CA:'):self.assertEqual(new['house_poll_focus']['races'][rid],r)
  for k in ('as_of','fetched_at'):self.assertEqual(new[k],old[k])
