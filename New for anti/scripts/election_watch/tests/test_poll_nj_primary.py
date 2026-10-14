from election_watch.polls import read as effective_read
import copy,hashlib,json,unittest
from pathlib import Path
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.state_evidence import build_state,load_finance
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config/usa_polls';P=ROOT.parent.parent/'public/data';DAY='2026-10-09'
r=lambda p:effective_read(p)

class NewJerseyEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.ballots=r(C/'ballot_reviews_2026.json');self.policy=apply_targets(apply_matchups(r(C/'live_2026.json'),r(ROOT/'config/governor_matchups/2026.json'),DAY),r(C/'targets_2026.json'),self.ballots,DAY);self.policy['quality_reviews']=r(C/'quality_reviews_2026.json')['reviews'];self.audit=r(P/'usa_election_poll_release_reviews/2026/NJ-primary-20261009.json');self.raw=self.audit['records'][0]['provider_record']
 def test_exact_three_candidate_initial_question_and_leaners(self):
  obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),1);o=obs[0];self.assertEqual([a['pct'] for a in o['answers']],[47,42,1]);self.assertEqual(o['race_id'],'USA:NJ:house:07');self.assertEqual((o['sample_n'],o['population'],o['field_end']),(498,'lv','2026-09-12'));self.assertTrue(o['source_quality']['disclosure_review']['includes_leaners']);self.assertIsNone(o['source_quality']['accuracy_grade'])
 def test_weight_target_conflict_remains_reference_and_no_recent_winner(self):
  obs,_=normalize([self.raw],self.policy,DAY);self.assertFalse(obs[0]['aggregation_eligibility']['eligible']);self.assertIn('weighting_electorate_and_candidate_order_conflict_requires_clarification',obs[0]['aggregation_eligibility']['reasons'])
  for d in (7,14):self.assertIsNone(summarize(obs,self.policy['races']['USA:NJ:house:07'],DAY,d)['party'])
 def test_district_senate_and_2025_governor_recall_not_statewide_polls(self):
  self.assertTrue(self.audit['records'][0]['review']['disclosure_review']['excluded_district_only_senate_poll']['not_statewide']);self.assertTrue(self.audit['official_ballot']['governor_non_election']);self.assertNotIn('USA:NJ:governor',self.policy['races']);self.assertTrue(all(x['provider_record']['poll_type']=='us-representative' for x in self.audit['records']))
 def test_official_39_candidate_scope_and_no_false_unopposed(self):
  races=[v for v in r(ROOT/'config/federal_matchups/2026.json')['races'].values() if v['state']=='NJ'];self.assertEqual(len(races),13);self.assertEqual(sum(len(x['candidates']) for x in races),39);self.assertTrue(all(x['source_role']=='state_election_agency' for x in races));h8=next(x for x in races if x['district']=='08');self.assertEqual(h8['absent_parties'],['REP']);self.assertEqual(len(h8['candidates']),4);self.assertEqual(h8['unopposed_status'],'not_verified');self.assertEqual(self.audit['official_ballot']['unopposed_verified_races'],[])
 def test_special_election_not_converted_to_November_general_poll(self):
  self.assertTrue(self.audit['official_ballot']['special_polling_excluded_from_November']);self.assertEqual(self.policy['races']['USA:NJ:house:11']['general_from'],'2026-06-03');self.assertEqual(self.audit['official_ballot']['special_house_11_election_date'],'2026-04-16');h7=self.ballots['races']['USA:NJ:house:07'];self.assertEqual(h7['excluded_candidates'][0]['name'],'Lana Leguia');self.assertFalse(any(c['name']=='Lana Leguia' for c in h7['candidates']))
 def test_changed_unregistered_release_cannot_inherit_admission(self):
  row=copy.deepcopy(self.raw);row['id']='future-stimsight-release';self.assertFalse(normalize([row],self.policy,DAY)[0]);row=copy.deepcopy(self.raw);row['sample_size']=500;self.assertFalse(normalize([row],self.policy,DAY)[0])
 def test_primary_provider_same_wave_duplicate_conflict_and_preservation(self):
  s=r(C/'primary_supplements_2026.json');e=copy.deepcopy(next(x for x in s['records'] if x['state']=='NJ'));body=b'%PDF-reviewed-fixture';e['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();s['records']=[e]
  class Response:
   status=200
   def __init__(self,url):self.url=url
   def geturl(self):return self.url
   def read(self,*a):return body
   def __enter__(self):return self
   def __exit__(self,*a):return False
  opener=lambda req,**kw:Response(req.full_url);row=copy.deepcopy(self.raw);row['id']='later-provider';rows,receipts=merge_primary_supplements([row],s,DAY,['NJ'],opener);self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['later-provider']);row['answers'][0]['pct']=48
  with self.assertRaises(ValueError):merge_primary_supplements([row],s,DAY,['NJ'],opener)
  e['documents'][0]['sha256']='0'*64;rows,receipts=merge_primary_supplements([],s,DAY,['NJ'],opener);self.assertEqual(rows[0]['end_date'],'2026-09-12');self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
 def test_identifier_provenance_not_falsely_attributed_to_nominee_PDF(self):
  for race in [x for x in r(ROOT/'config/federal_matchups/2026.json')['races'].values() if x['state']=='NJ']:
   for c in race['candidates']:
    if c.get('reported_fec_id'):self.assertEqual(c['secondary_identifier_source_url'],'https://www.thegreenpapers.com/G26/NJ');self.assertNotEqual(c['source_url'],c['secondary_identifier_source_url'])
  reviews=r(C/'state_finance_identities_2026.json')['races'];self.assertEqual({x['candidate_id'] for x in reviews['USA:NJ:house:08']},{'H2NJ08232'});self.assertFalse(any(x['candidate_id']=='H2NJ13075' for x in reviews['USA:NJ:house:08']))

if __name__=='__main__':unittest.main()
