from tests.poll_config_fixture import SNAPSHOT_DAY
import copy,hashlib,io,json,unittest
from pathlib import Path
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config/usa_polls';P=ROOT.parent.parent/'public/data';DAY='2026-10-08';read=lambda p:json.loads(p.read_text())
class IowaSuffolkTests(unittest.TestCase):
 def setUp(self):
  self.policy=apply_targets(apply_matchups(read(C/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'targets_2026.json'),read(C/'ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(C/'quality_reviews_2026.json')['reviews'];self.audit=read(P/'usa_election_poll_release_reviews/2026/IA-suffolk-20261009.json');self.raw=[r['provider_record'] for r in self.audit['records']]
 def current(self):
  obs,rejected=normalize(self.raw,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),2);return obs
 def test_statewide500_not_county300_or_second_choice11(self):
  for o in self.current():
   self.assertEqual(o['sample_n'],500);self.assertEqual(o['source_quality']['question_sample_n'],500);self.assertEqual(o['population'],'lv');self.assertEqual(o['field_end'],'2026-10-04');self.assertIn('Muscatine',o['source_quality']['disclosure_review']['excluded_geographies'][0]);self.assertEqual(o['source_quality']['reported_precision']['confidence_level_pct'],95);self.assertEqual(o['source_quality']['reported_precision']['half_width_pp'],4.4);self.assertIn('not registered',o['source_quality']['disclosure_review']['registration_disclosure_conflict'])
 def test_initial_senate_preserves_decimal_minor_party_and_unallocated(self):
  o=next(o for o in self.current() if o['race_id'].endswith('senate'));self.assertEqual([(a['pct'],a['party']) for a in o['answers']],[(43.6,'REP'),(48.0,'DEM'),(2.2,'LIB')]);self.assertEqual(o['source_quality']['ballot_format'],'multi_candidate');self.assertEqual(o['source_quality']['disclosure_review']['non_candidate_responses'],{'undecided':5.6,'refused':0.6});self.assertLess(sum(a['pct'] for a in o['answers']),100)
 def test_governor_leaners_question_and_decimal_values(self):
  o=next(o for o in self.current() if o['race_id'].endswith('governor'));self.assertEqual([a['pct'] for a in o['answers']],[42.8,54.8]);self.assertEqual(o['source_quality']['ballot_format'],'two_candidate_with_leaners');self.assertEqual(o['source_quality']['disclosure_review']['non_candidate_responses'],{'undecided':2.2,'refused':0.2})
 def test_7d_senate_tie_14d_poll_count_lead_not_winner_or_grade(self):
  b=read(P/'usa_election_live_polls_v1.json');r=b['races']['USA:IA:senate'];s=summarize(r['observations'],self.policy['races']['USA:IA:senate'],DAY,7);self.assertEqual(s['status'],'tie');self.assertIsNone(s['party']);self.assertEqual(s['pollster_count'],2);s=summarize(r['observations'],self.policy['races']['USA:IA:senate'],DAY,14);self.assertEqual(s['status'],'poll_lead');self.assertEqual(s['party'],'DEM');self.assertEqual(s['pollster_count'],3);self.assertEqual(s['lead_counts'],{'Josh Turek':2,'Ashley Hinson':1});self.assertIsNone(s['evidence_quality']['grade']);self.assertNotIn('us-202marf54f428e',s['included_ids']);self.assertTrue(all(d['significance']=='not_evaluated' for d in s['poll_details']))
 def test_late_provider_duplicate_exact_and_conflict_fail(self):
  snapshot=read(C/'primary_supplements_2026.json');entries=[e for e in snapshot['records'] if e['state']=='IA'];body=b'%PDF-1.7 reviewed synthetic Iowa source'
  for e in entries:
   for d in e['documents']:d['sha256']=hashlib.sha256(body).hexdigest()
  class Response(io.BytesIO):
   status=200
   def __init__(self,url):super().__init__(body);self.url=url
   def geturl(self):return self.url
  opener=lambda req,timeout:Response(req.full_url);s={**snapshot,'records':entries};raw=copy.deepcopy(entries[0]['record']);raw['id']='later-api-ia';rows,receipts=merge_primary_supplements([raw],s,DAY,['IA'],opener);self.assertEqual(len(rows),2);self.assertEqual(receipts[0]['provider_duplicate_ids'],['later-api-ia']);self.assertEqual(receipts[0]['status'],'primary_documents_rechecked');raw['sample_size']=300
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([raw],s,DAY,['IA'],opener)
 def test_changed_primary_carries_original_dates_and_excludes_signal(self):
  snapshot=read(C/'primary_supplements_2026.json')
  class Response(io.BytesIO):
   status=200
   def __init__(self,url):super().__init__(b'%PDF-1.7 changed');self.url=url
   def geturl(self):return self.url
  rows,receipts=merge_primary_supplements([],snapshot,DAY,['IA'],lambda req,timeout:Response(req.full_url));obs,rejected=normalize(rows,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),2);self.assertTrue(all(not o['aggregation_eligibility']['eligible'] for o in obs));self.assertTrue(all(o['field_end']=='2026-10-04' for o in obs));self.assertTrue(all(r['status']=='carried_forward_reference_only' for r in receipts))
 def test_snapshot_change_does_not_admit_new_release(self):
  for key,value in [('sample_size',300),('sponsors',['campaign']),('end_date','2026-10-05')]:
   raw=copy.deepcopy(self.raw[0]);raw[key]=value;obs,rejected=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertEqual(rejected[0]['reason'],'primary_review_provider_metadata_changed')
 def test_house_still_missing_and_report_index_not_zero_spending(self):
  b=read(P/'usa_election_live_polls_v1.json')
  for d in ['01','02','03','04']:
   r=b['races']['USA:IA:house:'+d];self.assertFalse(r['observations']);self.assertIsNone(r['windows']['7']['party']);self.assertEqual(r['windows']['7']['status'],'no_recent_poll')
  idx=read(P/'usa_governor_ie_report_indexes/2026/IA.json');self.assertFalse(idx['cycle_discovery_complete']);self.assertFalse(idx['candidate_amounts_available']);self.assertTrue(all(r['support_cents'] is None and r['oppose_cents'] is None for r in idx['records']))
if __name__=='__main__':unittest.main()
