import copy,hashlib,io,json,unittest
from pathlib import Path
from urllib.error import URLError
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.state_evidence import build_state,load_finance
from election_watch.governor_source_access import collect_access
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-08'
read=lambda p:json.loads(p.read_text())
class WisconsinPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/WI-primary-20261009.json');self.gov=read(ROOT/'config/governor_matchups/2026.json')
  self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),self.gov,DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews'];self.rows=[e['provider_record'] for e in self.audit['records']]
 def current(self):
  obs,rejected=normalize(self.rows,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),6);return obs
 def test_marquette_total_and_lv_samples_are_distinct(self):
  obs=self.current();s=[o for o in obs if o['field_end']=='2026-09-23' and o['race_id']=='USA:WI:governor'];self.assertEqual(sorted(o['sample_n'] for o in s),[692,843])
  for o in s:
   q=o['source_quality'];self.assertEqual(q['disclosure_review']['sampling_frame'],{'L2_registration_sample':627,'SSRS_probability_address_panel':216});self.assertEqual(q['disclosure_review']['mode_n'],{'online':749,'telephone':94});self.assertIsNone(q['question_sample_n']);self.assertIsNone(q['accuracy_grade']);self.assertTrue(q['disclosure_review']['question_sample_n_not_inferred_from_weighted_frequency'])
 def test_initial_vote_not_undecided_only_lean_question(self):
  obs=self.current();o=next(o for o in obs if o['id']=='gov202mar6e84a0e7');self.assertEqual({a['name']:a['pct'] for a in o['answers']},{'David Crowley':49.0,'Tom Tiffany':46.0});self.assertEqual(o['source_quality']['ballot_format'],'two_candidate_initial_with_undecided');self.assertIn('D2',o['source_quality']['disclosure_review']['question'])
 def test_historical_and_partial_platform_not_current_forecast(self):
  obs=self.current();g=[o for o in obs if o['race_id']=='USA:WI:governor']
  for w in [7,14]:self.assertEqual(summarize(g,self.policy['races']['USA:WI:governor'],DAY,w)['pollster_count'],0)
  p=next(o for o in obs if o['id']=='gov202plab53c0b38');self.assertFalse(p['aggregation_eligibility']['eligible']);self.assertEqual(p['sample_n'],500);self.assertEqual(p['source_quality']['disclosure_review']['additional_state_assembly_battleground_oversample_n'],50)
 def test_dccc_original_typo_is_held_correct_primary_internal_reference(self):
  obs=self.current();o=next(o for o in obs if o['race_id']=='USA:WI:house:01');self.assertFalse(o['aggregation_eligibility']['eligible']);self.assertEqual([a['name'] for a in o['answers']],['Bryan Steil','Mitchell Berman']);self.assertTrue(o['source_quality']['sponsor_review']['primary_internal']);self.assertEqual(o['source_quality']['reported_precision']['confidence_level_pct'],95);self.assertEqual(o['source_quality']['reported_precision']['half_width_pp'],4.4)
  old=next(e['replaced_provider_record'] for e in self.audit['records'] if 'replaced_provider_record' in e);accepted,rejected=normalize([old],self.policy,DAY);self.assertFalse(accepted);self.assertTrue(rejected)
 def test_no_senate_race_or_forecast_is_created(self):
  self.assertNotIn('USA:WI:senate',self.policy['races']);i=read(PUBLIC/'usa_election_state_evidence_index_v1.json');s=read(PUBLIC/i['states']['WI']['data_file']);self.assertTrue(s['office_coverage']['senate']['non_election']);self.assertEqual(s['office_coverage']['senate']['scheduled_races'],0)
 def test_same_wave_exact_replacement_and_later_corrected_api_deduplicate(self):
  snap=read(CONFIG/'primary_supplements_2026.json');entry=copy.deepcopy(next(e for e in snap['records'] if e['record']['id']=='primary-dccc-wi-house01-20260929'));body=b'%PDF-test';entry['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();test={**snap,'records':[entry]};url=entry['documents'][0]['url']
  class Response(io.BytesIO):
   status=200
   def geturl(self):return url
  opener=lambda req,timeout:Response(body)
  old=next(e['replaced_provider_record'] for e in self.audit['records'] if 'replaced_provider_record' in e);rows,checks=merge_primary_supplements([old],test,DAY,['WI'],opener);self.assertEqual(len(rows),1);self.assertEqual(checks[0]['reviewed_replaced_provider_ids'],[old['id']])
  fixed=copy.deepcopy(entry['record']);fixed['id']=old['id'];rows,checks=merge_primary_supplements([fixed],test,DAY,['WI'],opener);self.assertEqual(len(rows),1);self.assertEqual(checks[0]['provider_duplicate_ids'],[old['id']])
  changed=copy.deepcopy(old);changed['answers'][0]['pct']=47
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([changed],test,DAY,['WI'],opener)
 def test_moore_finance_identity_remains_reviewed_same_party_id(self):
  i=read(PUBLIC/'usa_election_state_evidence_index_v1.json');s=read(PUBLIC/i['states']['WI']['data_file']);r=next(r for r in s['races'] if r['race_id']=='USA:WI:house:04');c=next(c for c in r['candidates'] if c['party']=='DEM');self.assertEqual(c['finance_candidate_id'],'H4WI04183');self.assertEqual(c['finance_identity_evidence']['finance_reported_names'],['MOORE, GWEN S']);self.assertEqual(c['finance']['by_election_type']['P2026']['support_cents'],4256); self.assertEqual(c['finance']['by_election_type']['G2026']['support_cents'],12233)
 def test_unavailable_current_portal_never_asserts_zero_money(self):
  agency=read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')['states']['WI'];opener=lambda req,timeout:(_ for _ in ()).throw(URLError('synthetic DNS failure'));a=collect_access('WI',2026,agency,'2026-10-08T19:40:00+00:00',opener=opener);self.assertEqual(a['status'],'source_unavailable');self.assertFalse(a['candidate_amounts_available']);self.assertFalse(a['financial_data_collected']);self.assertNotIn('support_cents',a)
if __name__=='__main__':unittest.main()
