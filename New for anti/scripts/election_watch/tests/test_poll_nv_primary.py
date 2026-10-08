import copy,hashlib,io,json,unittest
from pathlib import Path
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.governor_source_access import collect_access
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-08';read=lambda p:json.loads(p.read_text())
class NevadaPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/NV-primary-20261009.json');self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews'];self.rows=[e['provider_record'] for e in self.audit['records']]
 def current(self):
  o,e=normalize(self.rows,self.policy,DAY);self.assertFalse(e);self.assertEqual(len(o),3);return o
 def test_noble_rv_and_lv_values_and_samples_distinct(self):
  o=self.current();r=next(x for x in o if x['population']=='rv');l=next(x for x in o if x['id'].startswith('primary-'));self.assertEqual((r['sample_n'],l['sample_n']),(800,708));self.assertEqual({a['name']:a['pct'] for a in r['answers']},{'Joe Lombardo':38.0,'Aaron Ford':37.0,'Danielle Ford':7.0});self.assertEqual({a['name']:a['pct'] for a in l['answers']},{'Joe Lombardo':42.0,'Aaron Ford':40.0,'Danielle Ford':7.0});self.assertEqual(l['source_quality']['reported_precision']['half_width_pp'],3.68);self.assertEqual(r['source_quality']['reported_precision']['half_width_pp'],3.46);self.assertIsNone(l['source_quality']['question_sample_n'])
 def test_single_wave_one_group_prefers_lv_and_keeps_rv_observation(self):
  o=self.current();s=summarize(o,self.policy['races']['USA:NV:governor'],DAY,14);self.assertEqual(s['pollster_count'],1);self.assertEqual(s['population'],'lv');self.assertEqual(s['included_ids'],['primary-noble-nv-governor-lv-20261006']);self.assertEqual(len([x for x in o if x['pollster_group']=='noble']),2)
 def test_7d_missing_14d_single_lead_not_election_winner(self):
  o=self.current();r=self.policy['races']['USA:NV:governor'];self.assertEqual(summarize(o,r,DAY,7)['status'],'no_recent_poll');s=summarize(o,r,DAY,14);self.assertEqual(s['status'],'single_poll_lead');self.assertEqual(s['party'],'REP');self.assertIsNone(s['evidence_quality']['grade']);self.assertEqual(s['poll_details'][0]['significance'],'not_evaluated')
 def test_emerson_initial_decimal_values_not_approval_or_integer_headline(self):
  o=next(x for x in self.current() if x['pollster_group']=='emerson');self.assertEqual({a['name']:a['pct'] for a in o['answers']},{'Joe Lombardo':42.0,'Aaron Ford':44.2,'Danielle Ford':2.4});self.assertEqual(o['sample_n'],680);self.assertEqual(o['source_quality']['reported_precision']['kind'],'credibility_interval');self.assertIsNone(o['source_quality']['question_sample_n']);self.assertTrue(o['source_quality']['disclosure_review']['question_sample_n_not_inferred_from_weighted_frequency'])
 def test_unmatched_future_xlsx_wave_conflict_and_verified_duplicate(self):
  snapshot=read(CONFIG/'primary_supplements_2026.json');e=copy.deepcopy(next(x for x in snapshot['records'] if x['state']=='NV'));body=b'PK\x03\x04-reviewed-xlsx';e['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();url=e['documents'][0]['url'];s={**snapshot,'records':[e]}
  class Response(io.BytesIO):
   status=200
   def geturl(self):return url
  raw=copy.deepcopy(e['record']);raw['id']='later-api';rows,checks=merge_primary_supplements([raw],s,DAY,['NV'],lambda req,timeout:Response(body));self.assertEqual(len(rows),1);self.assertEqual(checks[0]['provider_duplicate_ids'],['later-api']);raw['sample_size']=800
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([raw],s,DAY,['NV'],lambda req,timeout:Response(body))
  e['documents'][0]['url']='https://unreviewed.example/release.xlsx'
  with self.assertRaisesRegex(ValueError,'unreviewed primary document'):merge_primary_supplements([],{**snapshot,'records':[e]},DAY,['NV'],lambda req,timeout:Response(body))
 def test_changed_xlsx_keeps_original_date_reference_only(self):
  s=read(CONFIG/'primary_supplements_2026.json');e=next(x for x in s['records'] if x['state']=='NV');url=e['documents'][0]['url']
  class Response(io.BytesIO):
   status=200
   def geturl(self):return url
  rows,checks=merge_primary_supplements([],s,DAY,['NV'],lambda req,timeout:Response(b'PK\x03\x04-changed'));o,rejected=normalize(rows,self.policy,DAY);self.assertFalse(rejected);self.assertFalse(o[0]['aggregation_eligibility']['eligible']);self.assertEqual(o[0]['field_end'],'2026-09-26');self.assertEqual(checks[0]['status'],'carried_forward_reference_only')
 def test_http200_incapsula_not_public_financial_coverage(self):
  class Response(io.BytesIO):
   status=200
   def geturl(self):return 'https://www.nvsos.gov/SOSCandidateServices/AnonymousAccess/CEFDSearchUU/Search.aspx'
  a=collect_access('NV',2026,read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')['states']['NV'],'2026-10-08T21:10:00+00:00',opener=lambda req,timeout:Response(b'<iframe>Request unsuccessful. Incapsula incident ID: synthetic</iframe>'));self.assertEqual(a['status'],'source_access_blocked');self.assertFalse(a['financial_data_collected']);self.assertFalse(a['candidate_amounts_available']);self.assertIsNone(a['last_current_endpoint_accessible_at'])
 def test_house_missing_poll_not_zero_and_senate_non_election(self):
  i=read(PUBLIC/'usa_election_state_evidence_index_v1.json');s=read(PUBLIC/i['states']['NV']['data_file']);self.assertEqual(s['work_status'],'live_poll_sources_reviewed_finance_blocked');self.assertTrue(s['office_coverage']['senate']['non_election']);self.assertEqual(s['office_coverage']['senate']['scheduled_races'],0);self.assertEqual(s['office_coverage']['house']['with_poll_observations'],0);self.assertEqual(s['office_coverage']['house']['scheduled_races'],4);self.assertNotIn('USA:NV:senate',self.policy['races']);self.assertEqual(self.audit['house_discovery_status']['provider_house_records'],0)
if __name__=='__main__':unittest.main()
