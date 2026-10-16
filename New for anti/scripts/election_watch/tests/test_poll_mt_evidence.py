from pathlib import Path
import unittest
from election_watch.polls import read
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1]; PUBLIC=ROOT.parents[1]/'public/data'
class MontanaEvidenceTests(unittest.TestCase):
 def test_official_four_way_senate_and_separate_writein(self):
  r=read(ROOT/'config/federal_matchups/2026.json')['races']['USA:MT:senate']
  self.assertEqual({c['name']:c['party'] for c in r['candidates']},{'Kurt Alme':'REP','Kyle Austin':'LIB','Alani Bankhead':'DEM','Seth Bodnar':'IND'})
  self.assertEqual(len(r['declared_write_ins']),1)
  self.assertEqual(r['declared_write_ins'][0]['name'],'Jami Dee Woodman')
  self.assertEqual({c['candidate_id'] for c in r['candidates']},{'S6MT00295','S6MT00261','S6MT00253','S6MT00287'})
 def test_house_universe_and_no_governor_contest(self):
  rs=read(ROOT/'config/usa_polls/ballot_reviews_2026.json')['races']
  mt=[r for r in rs.values() if r['state']=='MT']
  self.assertEqual(len(mt),3); self.assertEqual(sum(len(r['candidates']) for r in mt),11)
  self.assertNotIn('USA:MT:governor',rs)
 def test_state_replay_keeps_other_states_and_global_dates(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');hist=read(PUBLIC/'usa_election_poll_history_2026.json');p=read(ROOT/'config/state_evidence/2026/MT.json')
  new,archive=rebuild(old,hist,[p],PUBLIC)
  for rid,r in old['races'].items():
   if r['state']!='MT':self.assertEqual(new['races'][rid],r)
  for key in ('as_of','fetched_at'):self.assertEqual(old[key],new[key])
  for rid,r in hist['races'].items():
   if not rid.startswith('USA:MT:'):self.assertEqual(archive['races'][rid],r)

from copy import deepcopy
from unittest.mock import Mock
from urllib.error import URLError
from election_watch.state_inputs import packets
from election_watch.live_polls import normalize,apply_watchlist
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
class MontanaPrimaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.packet=next(p for p in packets() if p['state']=='MT')
  cls.policy=apply_targets(apply_matchups(apply_watchlist(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/usa_polls/watchlist_2026.json')),read(ROOT/'config/governor_matchups/2026.json'),'2026-10-16'),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),'2026-10-16')
  cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
 def test_initial_question_subsamples_and_whole_survey_error_remain_distinct(self):
  rows,held=normalize(self.packet['capture']['primary_records'],self.policy,'2026-10-16');self.assertFalse(held)
  expected={'USA:MT:senate':(804,'Kurt Alme',38.148375),'USA:MT:house:01':(377,'Aaron Flint',42.184196),'USA:MT:house:02':(421,'Troy Downing',46.745154)}
  for rid,(n,name,pct) in expected.items():
   row=next(r for r in rows if r['race_id']==rid and r['pollster_group']=='rutgers_eagleton_mtfp')
   self.assertEqual((row['sample_n'],row['population']),(n,'rv'));self.assertTrue(row['aggregation_eligibility']['eligible'])
   self.assertAlmostEqual(next(a['pct'] for a in row['answers'] if a['name']==name),pct,places=5)
   self.assertIsNone(row['margin_of_error_pp']);self.assertEqual(row['source_quality']['reported_precision']['kind'],'whole_survey_margin_of_error')
   self.assertTrue(row['source_quality']['disclosure_review']['separate_leaner_rows_not_used'])
  concord=next(r for r in rows if 'concord' in r['id']);self.assertFalse(concord['aggregation_eligibility']['eligible'])
  self.assertIn('commissioner_not_disclosed_reference',concord['aggregation_eligibility']['reasons'])
  leader=max(concord['answers'],key=lambda a:a['pct']);self.assertEqual((leader['name'],leader['party']),('Seth Bodnar','IND'))
 def test_new_known_source_poll_connects_without_admitting_retired_or_incomplete_field(self):
  # Synthetic transport fixture only, never saved as a production observation.
  raw={'id':'test-only-new-mt-wave','subject':'2026 Montana','poll_type':'us-senator','pollster':'Emerson College','url':'https://emersoncollegepolling.com/test-only-mt-fixture','start_date':'2026-10-14','end_date':'2026-10-15','created_at':'2026-10-15','population':'lv','sample_size':500,'answers':[{'choice':n,'pct':p} for n,p in [('Kurt Alme',40),('Alani Bankhead',20),('Seth Bodnar',30),('Kyle Austin',3)]],'seat_name':None,'sponsors':[],'internal':False,'partisan':None}
  rows,held=normalize([raw],self.policy,'2026-10-16');self.assertFalse(held);self.assertTrue(rows[0]['aggregation_eligibility']['eligible'])
  for retired in (False,True):
   bad=deepcopy(raw)
   if retired:bad['answers'][0]['choice']='Steve Daines'
   else:bad['answers'].pop()
   rows,held=normalize([bad],self.policy,'2026-10-16');self.assertFalse(rows);self.assertEqual(held[0]['reason'],'unreviewed_matchup')
 def test_exact_later_api_duplicate_and_conflict_or_source_failure(self):
  catalog=read(ROOT/'config/usa_polls/primary_supplements_2026.json');entry=next(e for e in catalog['records'] if e['state']=='MT')
  subset={**catalog,'records':[entry]};provider=deepcopy(entry['record']);provider['id']='test-only-later-api-id'
  rows,receipts=merge_primary_supplements([provider],subset,'2026-10-16',['MT'],opener=Mock(side_effect=URLError('test-only-offline')))
  self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['test-only-later-api-id'])
  self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
  accepted,held=normalize(rows,self.policy,'2026-10-16');self.assertFalse(held);self.assertFalse(accepted[0]['aggregation_eligibility']['eligible'])
  provider['sample_size']=845
  with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
   merge_primary_supplements([provider],subset,'2026-10-16',['MT'])
 def test_fec_scope_missing_identity_and_no_current_poll_winners(self):
  audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/MT-primary-20261016.json')
  self.assertEqual(audit['finance_quality'],{'included_records':212,'excluded_records':{'memo':6}})
  self.assertEqual(sum(r['records'] for r in audit['finance_spending_audit']),212)
  from election_watch.superpac import build_snapshot
  capture=self.packet['federal_finance_review'];replayed=build_snapshot(2026,capture['candidates'],capture['raw_records'])
  self.assertEqual(replayed['spending'],capture['spending']);self.assertEqual(replayed['quality'],capture['quality'])
  self.assertNotIn('api_key',str(capture['sources']))
  self.assertTrue(all(r['state']=='MT' for r in audit['finance_spending_audit']))
  self.assertEqual((audit['finance_current_ballot_aggregates'],audit['finance_other_candidate_aggregates']),(23,6))
  sheedy=next(c for r in audit['official_rosters'].values() for c in r['candidates'] if c['name']=='Nick Sheedy');self.assertIsNone(sheedy['candidate_id'])
  old=read(PUBLIC/'usa_election_live_polls_v1.json');hist=read(PUBLIC/'usa_election_poll_history_2026.json');new,_=rebuild(old,hist,[self.packet],PUBLIC)
  for rid in ('USA:MT:senate','USA:MT:house:01','USA:MT:house:02'):
   self.assertTrue(new['races'][rid]['observations'])
   for days in ('7','14'):self.assertEqual(new['races'][rid]['windows'][days]['pollster_count'],0)
  for rid,r in old['house_poll_focus']['races'].items():
   if r['state']!='MT':self.assertEqual(new['house_poll_focus']['races'][rid],r)
  self.assertEqual(new['house_poll_focus']['race_count'],104)

from election_watch.ballot_mt import parse_general,URL
class MontanaParserTests(unittest.TestCase):
 def test_official_federal_rows_require_valid_status_district_and_no_duplicates(self):
  audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/MT-primary-20261016.json');rows=[]
  for r in audit['official_rosters'].values():
   for c in r['candidates']+r.get('declared_write_ins',[]):
    senate=r['office']=='senate';cells=['FILED','Statewide' if senate else 'Congressional','STATE' if senate else ('1ST CONGRESSIONAL' if r['district']=='01' else '2ND CONGRESSIONAL'),'UNITED STATES SENATOR' if senate else 'UNITED STATES REPRESENTATIVE','REGULAR','6' if senate else '2',c['reported_name'],'','WRITE-IN' if c['write_in'] else '', '', '7/10/2026 11:00:00 AM',c['reported_party'],'','FILED']
    rows.append('<tr>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
  body='FEDERAL GENERAL 2026<table>'+''.join(rows)+'</table>'
  self.assertEqual(sum(map(len,parse_general(body,URL).values())),12)
  for bad in [body.replace('FILED','WITHDRAWN',1),body.replace('2ND CONGRESSIONAL','22ND CONGRESSIONAL'),body+rows[0]]:
   with self.assertRaises(ValueError):parse_general(bad,URL)
