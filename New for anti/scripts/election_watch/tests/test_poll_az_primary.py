from tests.poll_config_fixture import SNAPSHOT_DAY
import copy,hashlib,io,json,unittest
from pathlib import Path
from urllib.error import HTTPError
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.governor_source_access import collect_access
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-08'
read=lambda p:json.loads(p.read_text())
class ArizonaPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/AZ-primary-20261009.json');self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews'];self.rows=[e['provider_record'] for e in self.audit['records']]
 def current(self):
  obs,rejected=normalize(self.rows,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),3);return obs
 def test_publisher_rv_not_api_lv_and_weighted_model_not_lv_screen(self):
  o=next(o for o in self.current() if o['race_id']=='USA:AZ:house:01');self.assertEqual(o['population'],'rv');self.assertEqual(o['sample_n'],400);self.assertEqual(o['source_quality']['disclosure_review']['provider_population'],'LV');self.assertEqual(o['source_quality']['reported_precision']['half_width_pp'],5.4);self.assertEqual(o['source_quality']['reported_precision']['confidence_level_pct'],95);self.assertTrue(o['source_quality']['reported_precision']['design_effect_included']);self.assertIsNone(o['source_quality']['accuracy_grade']);self.assertEqual({a['name']:a['pct'] for a in o['answers']},{'Amish Shah':44.4,'Jay Feely':41.6})
 def test_original_population_conflict_not_double_counted(self):
  old=self.audit['records'][0]['replaced_population_provider_record'];accepted,rejected=normalize([old],self.policy,DAY);self.assertFalse(accepted);self.assertTrue(rejected)
 def test_7d_missing_and_14d_single_rv_not_certified_winner(self):
  obs=[o for o in self.current() if o['race_id']=='USA:AZ:house:01'];r=self.policy['races']['USA:AZ:house:01'];self.assertEqual(summarize(obs,r,DAY,7)['status'],'no_recent_poll');s=summarize(obs,r,DAY,14);self.assertEqual(s['status'],'single_poll_lead');self.assertEqual(s['pollster_count'],1);self.assertEqual(s['population'],'rv');self.assertIsNone(s['evidence_quality']['grade']);self.assertEqual(s['poll_details'][0]['significance'],'not_evaluated')
 def test_governor_august_observations_do_not_generate_current_lead(self):
  obs=[o for o in self.current() if o['race_id']=='USA:AZ:governor'];self.assertEqual(len(obs),2)
  for days in [7,14]:self.assertEqual(summarize(obs,self.policy['races']['USA:AZ:governor'],DAY,days)['pollster_count'],0)
 def test_bsp_and_informed_hmp_stay_held(self):
  h={x['provider_record']['id']:x for x in self.audit['held_records']};self.assertIn('sample',h['gov202bsp579091db']['reason']);self.assertIn('52/44',h['us-202nor8d5759fc']['note_ko']);obs,rejected=normalize([x['provider_record'] for x in h.values()],self.policy,DAY);self.assertFalse(obs);self.assertEqual(len(rejected),5)
 def test_exact_primary_pdf_guard_and_future_corrected_api_dedup(self):
  snap=read(CONFIG/'primary_supplements_2026.json');entry=copy.deepcopy(next(e for e in snap['records'] if e['state']=='AZ'));body=b'%PDF-test';entry['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();url=entry['documents'][0]['url'];s={**snap,'records':[entry]}
  class Response(io.BytesIO):
   status=200
   def geturl(self):return url
  r=copy.deepcopy(entry['record']);r['id']='later-corrected-api';rows,checks=merge_primary_supplements([r],s,DAY,['AZ'],lambda req,timeout:Response(body));self.assertEqual(len(rows),1);self.assertEqual(checks[0]['provider_duplicate_ids'],['later-corrected-api'])
  r['answers'][0]['pct']=45
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([r],s,DAY,['AZ'],lambda req,timeout:Response(body))
  rows,checks=merge_primary_supplements([],s,DAY,['AZ'],lambda req,timeout:Response(b'%PDF-changed'));self.assertEqual(checks[0]['status'],'carried_forward_reference_only');self.assertEqual(rows[0]['end_date'],'2026-10-01')
 def test_non_election_senate_and_no_zero_from_403(self):
  self.assertNotIn('USA:AZ:senate',self.policy['races']);i=read(PUBLIC/'usa_election_state_evidence_index_v1.json');s=read(PUBLIC/i['states']['AZ']['data_file']);self.assertTrue(s['office_coverage']['senate']['non_election']);self.assertEqual(s['office_coverage']['senate']['scheduled_races'],0);self.assertEqual(s['work_status'],'live_poll_sources_reviewed_finance_blocked')
  def blocked(req,timeout):raise HTTPError(req.full_url,403,'Forbidden',None,None)
  a=collect_access('AZ',2026,read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')['states']['AZ'],'2026-10-08T20:05:00+00:00',opener=blocked);self.assertEqual(a['status'],'source_access_blocked');self.assertFalse(a['financial_data_collected']);self.assertFalse(a['candidate_amounts_available']);self.assertNotIn('support_cents',a)
if __name__=='__main__':unittest.main()
