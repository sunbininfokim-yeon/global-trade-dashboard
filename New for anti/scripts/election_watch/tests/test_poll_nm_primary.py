import copy,json,unittest
from pathlib import Path
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements,surveyusa_html_fingerprint
from election_watch.poll_quality import corrected_provider_sample
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config/usa_polls';P=ROOT.parent.parent/'public/data';DAY='2026-10-09';read=lambda p:json.loads(p.read_text())
class NewMexicoEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.policy=apply_targets(apply_matchups(read(C/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(C/'targets_2026.json'),read(C/'ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'quality_reviews_2026.json')['reviews'];self.audit=read(P/'usa_election_poll_release_reviews/2026/NM-primary-20261009.json');self.rows=[x['provider_record'] for x in self.audit['records']]
 def test_correct_sample_preserves_original_and_answers(self):
  original=copy.deepcopy(self.rows[1]);obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(self.rows[1],original);sen=next(x for x in obs if x['race_id'].endswith('senate'));self.assertEqual(sen['sample_n'],567);self.assertEqual(sen['provider_sample_correction']['original_provider_sample_n'],576);self.assertEqual([x['pct'] for x in sen['answers']],[54,36])
 def test_changed_import_needs_review(self):
  for field,val in [('sample_size',577),('sponsors',[]),('end_date','2026-10-01'),('url','https://example.org/new')]:
   row=copy.deepcopy(self.rows[1]);row[field]=val;self.assertFalse(normalize([row],self.policy,DAY)[0])
 def test_no_total_sample_or_answer_change(self):
  row=self.rows[1];review=copy.deepcopy(self.policy['quality_reviews'][row['id']]);review['provider_sample_correction']['question_sample_n']=800
  with self.assertRaises(ValueError):corrected_provider_sample(row,review,DAY)
  review=copy.deepcopy(self.policy['quality_reviews'][row['id']]);review['primary_toplines']['Larry Marker']=38
  with self.assertRaises(ValueError):corrected_provider_sample(row,review,DAY)
 def test_exact_alias_and_14d_single_source_not_7d(self):
  obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held)
  for o in obs:
   race=self.policy['races'][o['race_id']];self.assertEqual(o['sample_n'],567);self.assertIsNone(summarize([o],race,DAY,7)['party']);s=summarize([o],race,DAY,14);self.assertEqual(s['pollster_count'],1);self.assertEqual(s['party'],'DEM');self.assertIsNone(s['evidence_quality']['grade'])
  self.assertEqual(obs[0]['answers'][1]['party'],'REP');self.assertEqual(self.policy['races']['USA:NM:governor']['general_from'],'2026-06-03')
 def test_roster_not_official_upgrade_or_unopposed(self):
  self.assertEqual(self.audit['roster_review']['coverage'],'reviewed_secondary_only_official_portal_403');self.assertEqual(self.audit['roster_review']['candidate_count'],10);self.assertFalse(self.audit['roster_review']['unopposed_verified_races']);self.assertTrue(all(r['source_role']=='reviewed_secondary_nominee_listing' for r in read(ROOT/'config/federal_matchups/2026.json')['races'].values() if r['state']=='NM'))
 def html(self,value=47,noise='first'):
  return (f'<html><head><title>Results of SurveyUSA Election Poll #28031</title></head><body><input value="{noise}"><p>About the Research / Filtering: Deb Haaland {value}; Gregg Hull 41. '+'Fixture evidence '*100+f'</p><script>{noise}</script></body></html>').encode()
 def test_report_fingerprint_and_frame_rejection(self):
  self.assertEqual(surveyusa_html_fingerprint(self.html(),'28031'),surveyusa_html_fingerprint(self.html(noise='new'),'28031'));self.assertNotEqual(surveyusa_html_fingerprint(self.html(),'28031'),surveyusa_html_fingerprint(self.html(48),'28031'))
  for body in [b'<html>Access denied</html>',b'<frameset><frame src="main"></frameset>']:
   with self.assertRaises(ValueError):surveyusa_html_fingerprint(body,'28031')
  with self.assertRaises(ValueError):surveyusa_html_fingerprint(self.html(),'99999')
 def merge(self,body,rows=None,url=None):
  s=read(C/'primary_supplements_2026.json');e=copy.deepcopy(next(x for x in s['records'] if x['state']=='NM'));e['documents'][0]['sha256']=surveyusa_html_fingerprint(self.html(),'28031');s['records']=[e]
  if url:e['documents'][0]['url']=url
  class Response:
   status=200
   def geturl(self):return e['documents'][0]['url']
   def read(self,*a):return body
   def __enter__(self):return self
   def __exit__(self,*a):return False
  return merge_primary_supplements(rows or [],s,DAY,['NM'],lambda *a,**kw:Response())
 def test_later_api_duplicate_and_conflict(self):
  row=copy.deepcopy(self.rows[0]);row['id']='later-api';rows,receipts=self.merge(self.html(),[row]);self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['later-api']);row['sample_size']=576
  with self.assertRaises(ValueError):self.merge(self.html(),[row])
 def test_changed_report_preserves_original_and_unknown_url_fails(self):
  rows,receipts=self.merge(self.html(48));self.assertEqual(receipts[0]['status'],'carried_forward_reference_only');self.assertEqual(rows[0]['end_date'],'2026-09-30');self.assertEqual(rows[0]['answers'][0]['pct'],47)
  with self.assertRaises(ValueError):self.merge(self.html(),url='https://results.surveyusa.com/client/PollReport_main.aspx?g=unreviewed')
 def test_source_access_not_money(self):
  access=read(P/'usa_governor_source_access/2026/NM.json');self.assertFalse(access['financial_data_collected']);self.assertFalse(access['candidate_amounts_available']);self.assertEqual(access['status'],'public_endpoint_reachable_mapping_required');self.assertFalse(self.audit['finance_review']['federal_FEC_recollected'])
 def test_house02_historical_preserved(self):
  row=next(x['provider_record'] for x in self.audit['other_provider_records'] if x['provider_record']['id']=='us-202sur44bc5f16');obs,held=normalize([row],self.policy,DAY);self.assertFalse(held);self.assertEqual(obs[0]['sample_n'],554);self.assertIsNone(summarize(obs,self.policy['races']['USA:NM:house:02'],DAY,14)['party'])
if __name__=='__main__':unittest.main()
