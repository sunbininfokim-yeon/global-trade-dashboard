import copy,hashlib,io,json,unittest
from pathlib import Path
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.governor_source_access import collect_access
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-09'
read=lambda p:json.loads(p.read_text())
class AlaskaPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/AK-primary-20261009.json')
  self.policy=apply_targets(apply_matchups(read(C/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(C/'targets_2026.json'),read(C/'ballot_reviews_2026.json'),DAY)
  self.policy['quality_reviews']=read(C/'quality_reviews_2026.json')['reviews'];self.rows=[r['provider_record'] for r in self.audit['records']]
 def current(self):
  obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),6);return obs
 def test_all_four_candidates_and_two_sullivans_keep_separate_identities(self):
  for rid in ['USA:AK:house:00','USA:AK:senate','USA:AK:governor']:
   r=self.policy['races'][rid];self.assertEqual(len(r['required_candidates']),4);self.assertEqual(r['ballot_system'],'ranked_choice');self.assertEqual(r['schedule_status'],'reported_general_matchup');self.assertFalse(r['ballot_competition']['general_unopposed'])
  r=self.policy['races']['USA:AK:senate'];self.assertEqual(r['candidates']['Dan Sullivan']['party'],'REP');self.assertEqual(r['candidates']['Daniel J. Sullivan Jr.']['party'],'OTH')
  r=self.policy['races']['USA:AK:house:00'];self.assertEqual(r['district_transport']['canonical_district'],'00');self.assertEqual(r['candidates']['Bill Hill']['party'],'IND')
 def test_first_choice_and_forced_pair_are_not_final_simulations(self):
  obs=self.current();q=next(o for o in obs if o['id'].startswith('primary-ak-quantus'));p=next(o for o in obs if o['id']=='us-202qua198b0338')
  self.assertEqual(q['ballot_question']['kind'],'first_preference');self.assertEqual(len(q['answers']),4);self.assertEqual(q['sample_n'],758);self.assertEqual(q['source_quality']['question_sample_n'],737)
  self.assertEqual({a['name']:a['pct'] for a in q['answers']},{'Dan Sullivan':46.1,'Mary Peltola':45.5,'Daniel J. Sullivan Jr.':1.6,'Gerald Heikes':1.3})
  self.assertEqual(p['ballot_question']['kind'],'forced_two_candidate');self.assertEqual({a['name']:a['pct'] for a in p['answers']},{'Mary Peltola':47.2,'Dan Sullivan':47.8})
  self.assertEqual(p['source_quality']['disclosure_review']['conditional_leaner_sample_n'],35)
 def test_verified_senate_ids_reach_display_and_finance_without_confusing_sullivans(self):
  federal=read(ROOT/'config/federal_matchups/2026.json');roster=federal['races']['USA:AK:senate']
  ids={c['name']:c.get('candidate_id') for c in roster['candidates']}
  self.assertEqual(ids,{'Mary Peltola':'S6AK00276','Dan S. Sullivan':'S4AK00214','Gerald L. Heikes':'S8AK00140','Daniel J. Sullivan Jr.':None})
  self.assertEqual(self.policy['races']['USA:AK:senate']['candidates']['Dan Sullivan']['candidate_id'],'S4AK00214')
  self.assertIsNone(self.policy['races']['USA:AK:senate']['candidates']['Daniel J. Sullivan Jr.']['candidate_id'])
  from election_watch.state_evidence import load_finance,candidate_finance
  asset=load_finance(PUBLIC/'usa_election_finance_index_v1.json',2026)['races']['USA:AK:senate']
  for c in roster['candidates']:
   result=candidate_finance(c,asset,'senate')
   self.assertEqual(result['join_status'],'same_reviewed_candidate_id' if c['candidate_id'] else 'candidate_finance_not_linked')
 def test_rcv_reference_never_votes_in_ordinary_lead_count_or_winner(self):
  obs=self.current();self.assertTrue(all(not o['aggregation_eligibility']['eligible'] and not o['ballot_question']['election_result'] for o in obs))
  for rid,r in self.policy['races'].items():
   if r['state']!='AK':continue
   for days in [7,14]:
    s=summarize([o for o in obs if o['race_id']==rid],r,DAY,days);self.assertEqual(s['pollster_count'],0);self.assertIsNone(s['party']);self.assertIsNone(s['leader']);self.assertEqual(s['status'],'no_recent_poll')
  s=summarize([o for o in obs if o['race_id']=='USA:AK:senate'],self.policy['races']['USA:AK:senate'],DAY,14);self.assertEqual(s['reference_poll_count'],2)
 def test_unreviewed_full_field_and_changed_pair_still_require_question_review(self):
  raw=copy.deepcopy(next(r for r in self.rows if r['id'].startswith('primary-ak-quantus')));raw['id']='new-unreviewed-poll';self.policy['pollsters'][raw['pollster']]={'group':'quantus','hosts':['quantusinsights.org'],'methodology_url':raw['url']}
  obs,held=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'ranked_choice_question_not_reviewed')
  raw=copy.deepcopy(next(r for r in self.rows if r['id']=='us-202qua198b0338'));raw['answers'][0]['pct']=47.3
  obs,held=normalize([raw],self.policy,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
 def test_partial_first_choice_or_eligible_simulation_is_rejected(self):
  p=copy.deepcopy(self.policy);p['quality_reviews']['us-202qua198b0338']['ranked_choice_question']['kind']='first_preference'
  obs,held=normalize([next(r for r in self.rows if r['id']=='us-202qua198b0338')],p,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'ranked choice field mismatch')
  p=copy.deepcopy(self.policy);p['quality_reviews']['us-202qua198b0338']['admission']['signal_eligible']=True
  obs,held=normalize([next(r for r in self.rows if r['id']=='us-202qua198b0338')],p,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'RCV requires exact reference review')
 def test_final_round_denominator_not_inferred_from_study_sample(self):
  for o in self.current():
   if o['ballot_question']['kind']=='simulated_final_round':
    self.assertEqual(o['sample_n'],800);self.assertIsNone(o['source_quality']['question_sample_n']);self.assertIsNone(o['source_quality']['disclosure_review']['active_final_round_denominator']);self.assertIsNone(o['source_quality']['accuracy_grade'])
 def test_separate_question_guard_later_api_dedup_and_changed_source(self):
  snapshot=read(C/'primary_supplements_2026.json');entry=copy.deepcopy(next(e for e in snapshot['records'] if e['state']=='AK'));body=b'%PDF-reviewed';entry['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();url=entry['documents'][0]['url'];snap={**snapshot,'records':[entry]}
  class Response(io.BytesIO):
   status=200
   def geturl(self):return url
  provider=next(r for r in self.rows if r['id']=='us-202qua198b0338')
  rows,checks=merge_primary_supplements([provider],snap,DAY,['AK'],lambda req,timeout:Response(body));self.assertEqual(len(rows),2);self.assertEqual(checks[0]['separate_question_provider_ids'],[provider['id']]);self.assertFalse(checks[0]['provider_duplicate_ids'])
  self.assertEqual(checks[0]['status'],'primary_documents_rechecked');self.assertEqual(checks[0]['documents'][0]['status'],'unchanged')
  first=copy.deepcopy(entry['record']);first['id']='later-full-first-choice-api'
  rows,checks=merge_primary_supplements([provider,first],snap,DAY,['AK'],lambda req,timeout:Response(body));self.assertEqual(len(rows),2);self.assertEqual(checks[0]['provider_duplicate_ids'],[first['id']])
  changed=copy.deepcopy(provider);changed['answers'][0]['pct']=47.3
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):merge_primary_supplements([changed],snap,DAY,['AK'],lambda req,timeout:Response(body))
  rows,checks=merge_primary_supplements([provider],snap,DAY,['AK'],lambda req,timeout:Response(b'%PDF-changed'));self.assertEqual(checks[0]['status'],'carried_forward_reference_only');self.assertEqual(rows[-1]['end_date'],'2026-09-30')
 def test_supplement_receipt_requires_unchanged_reviewed_document(self):
  row=copy.deepcopy(next(r for r in self.rows if r['id'].startswith('primary-ak-quantus')));review=self.policy['quality_reviews'][row['id']];doc=review['primary_documents'][0]
  row['primary_source_capture']={'original_reviewed_on':DAY,'status':'primary_documents_rechecked','documents':[{'url':doc['url'],'status':'unchanged','sha256':'0'*64}]}
  obs,held=normalize([row],self.policy,DAY);self.assertFalse(obs);self.assertEqual(held[0]['reason'],'primary_document_receipt_mismatch')
 def test_governor_access_failure_is_not_zero_financial_coverage(self):
  from urllib.error import URLError
  def unavailable(req,timeout):raise URLError('timed out')
  agency=read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')['states']['AK'];a=collect_access('AK',2026,agency,'2026-10-09T00:00:00+00:00',opener=unavailable)
  self.assertEqual(a['status'],'source_unavailable');self.assertFalse(a['financial_data_collected']);self.assertFalse(a['candidate_amounts_available']);self.assertNotIn('support_cents',a)
 def test_pre_primary_and_unverified_current_releases_remain_held(self):
  rows=[h['provider_record'] for h in self.audit['held_records']];obs,held=normalize(rows,self.policy,DAY);self.assertFalse(obs);self.assertEqual(len(held),32)
if __name__=='__main__':unittest.main()
