import copy
import hashlib
import json
from pathlib import Path
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs
from election_watch.ct_ballot import parse_sections
from election_watch.governor_matchups import apply_matchups, apply_ballot_reviews
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize, summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.governor_ct import collect_audit, summarize_search, HEADERS, URL
from election_watch.superpac import SourceError
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-09'
read=lambda p:json.loads(p.read_text())

class ConnecticutPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
  self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews'];self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/CT-primary-20261009.json');self.raw=[x['provider_record'] for x in self.audit['records']]
 def observations(self):
  obs,rejected=normalize(self.raw,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),2);return {o['pollster_group']:o for o in obs}
 def test_quinnipiac_lv_question_funding_and_precision(self):
  o=self.observations()['quinnipiac'];self.assertEqual([a['pct'] for a in o['answers']],[55,38]);self.assertEqual(o['population'],'lv');self.assertEqual(o['sample_n'],1288);self.assertTrue(o['aggregation_eligibility']['eligible'])
  d=o['source_quality']['disclosure_review'];self.assertTrue(d['includes_leaners']);self.assertEqual(d['non_candidate_responses']['refused'],2);self.assertIsNone(o['source_quality']['accuracy_grade']);self.assertIsNone(o['margin_of_error_pp']);self.assertEqual(o['source_quality']['reported_precision']['half_width_pp'],3.8)
 def test_greatblue_initial_rv_not_followup_or_july(self):
  o=self.observations()['greatblue_research'];self.assertEqual([a['pct'] for a in o['answers']],[48.2,33.9]);self.assertEqual(o['population'],'rv');self.assertEqual(o['sample_n'],1000);self.assertFalse(o['aggregation_eligibility']['eligible']);self.assertEqual(o['source_quality']['disclosure_review']['excluded_followup_ballot']['Ned Lamont'],52.2);self.assertEqual(o['field_end'],'2026-09-08')
 def test_old_polls_never_create_current_7_or_14_day_winner(self):
  for days in (7,14):
   s=summarize(list(self.observations().values()),self.policy['races']['USA:CT:governor'],DAY,days);self.assertFalse(s['included_ids']);self.assertIsNone(s['party'])
 def test_blocked_unh_and_preprimary_held_not_verified(self):
  self.assertEqual(len(self.audit['held_records']),4);self.assertFalse(normalize([x['provider_record'] for x in self.audit['held_records']],self.policy,DAY)[0]);self.assertNotIn('USA:CT:senate',self.policy['races']);self.assertEqual(self.policy['races']['USA:CT:governor']['general_from'],'2026-08-12')
 def test_exact_review_cannot_admit_changed_or_future_release(self):
  for field,value in [('sample_size',1289),('sponsors',['Other']),('answers',[{'choice':'Ned Lamont','pct':54.},{'choice':'Ryan Fazio','pct':39.}])]:
   row=copy.deepcopy(self.raw[0]);row[field]=value;self.assertFalse(normalize([row],self.policy,DAY)[0],field)
  row=copy.deepcopy(self.raw[0]);row['id']='future-registered-provider-release'
  obs,rejected=normalize([row],self.policy,DAY)
  self.assertFalse(rejected);self.assertEqual(obs[0]['source_quality']['verification_level'],'partial')
  row['primary_source_capture']={'status':'primary_documents_rechecked','original_reviewed_on':DAY}
  self.assertFalse(normalize([row],self.policy,DAY)[0])
 def test_primary_recheck_changed_document_and_later_api_conflict(self):
  snap=read(CONFIG/'primary_supplements_2026.json');entry=copy.deepcopy(next(x for x in snap['records'] if x['record']['id']==self.raw[0]['id']));body=b'%PDF-reviewed-test'
  for d in entry['documents']:d['sha256']=hashlib.sha256(body).hexdigest()
  snap['records']=[entry]
  class Response:
   status=200
   def __init__(self,url):self.url=url
   def geturl(self):return self.url
   def read(self,*a):return body
   def __enter__(self):return self
   def __exit__(self,*a):return False
  opener=lambda req,**kw:Response(req.full_url)
  rows,receipts=merge_primary_supplements([entry['record']],snap,DAY,['CT'],opener);self.assertEqual(len(rows),1);self.assertEqual(len(receipts[0]['provider_duplicate_ids']),1)
  for d in entry['documents']:d['sha256']='0'*64
  rows,receipts=merge_primary_supplements([],snap,DAY,['CT'],opener);self.assertEqual(receipts[0]['status'],'carried_forward_reference_only');self.assertEqual(rows[0]['end_date'],'2026-09-14')
  conflict=copy.deepcopy(entry['record']);conflict['answers'][0]['pct']=56
  with self.assertRaises(ValueError):merge_primary_supplements([conflict],snap,DAY,['CT'])
 def test_shared_publisher_new_pdf_not_blanket_approved(self):
  snap=read(CONFIG/'primary_supplements_2026.json');entry=copy.deepcopy(next(x for x in snap['records'] if x['state']=='CT' and 'greatblue' in x['record']['id']));entry['documents'][0]['url']='https://www.sacredheart.edu/new-poll.pdf';snap['records']=[entry]
  with self.assertRaises(ValueError):merge_primary_supplements([],snap,DAY,['CT'])
 def test_governor_listing_scope_not_complete_writein_ballot(self):
  snap=read(ROOT/'config/governor_matchups/2026.json');reviews=read(ROOT/'config/governor_matchups/2026_ballot_reviews.json');out=apply_ballot_reviews(snap,reviews,DAY);self.assertEqual(out['contests']['CT']['coverage'],'complete_active_agency_listing');self.assertEqual(out,apply_ballot_reviews(out,reviews,DAY));reviews['contests']['CT']['coverage']='official_winner'
  with self.assertRaises(SourceError):apply_ballot_reviews(snap,reviews,DAY)

class ConnecticutGuideTests(unittest.TestCase):
 def setUp(self):self.sections=read(ROOT/'tests/fixtures/ct_guide_sections_2026.json')
 def parse(self,sections=None):return parse_sections(**(sections or self.sections),reviewed_on=DAY)
 def test_fusion_one_person_and_independent_party_not_unaffiliated(self):
  r=self.parse();self.assertEqual(len(r),6);self.assertEqual(sum(len(x['candidates']) for x in r.values()),15);a=r['USA:CT:house:02']['candidates'][0];self.assertEqual(a['name'],'George Austin');self.assertEqual(a['party'],'REP');self.assertEqual(a['reported_ballot_parties'],['R','I']);self.assertEqual(next(c for c in r['USA:CT:house:03']['candidates'] if c['name']=='Thomas Egan')['party'],'OTH');self.assertEqual({c['name'] for c in r['USA:CT:governor']['candidates']},{'Ryan Fazio','Ned Lamont'})
 def test_wrong_cycle_party_universe_duplicate_or_boundary_fails(self):
  for field,a,b in [('cover','2026','2024'),('house','District 5','District 6'),('house','(R)','(UNKNOWN)'),('house','Luke Bronin (D)','Luke Bronin (D)\nLuke Bronin (D)'),('governor','Lt. Governor','State Senate')]:
   s=copy.deepcopy(self.sections);s[field]=s[field].replace(a,b)
   with self.assertRaises(ValueError):self.parse(s)
 def test_current_house_alias_ids_and_unconfirmed_writein_preserved(self):
  federal=read(ROOT/'config/federal_matchups/2026.json')['races'];house=[r for r in federal.values() if r['state']=='CT'];self.assertEqual(len(house),5);self.assertEqual(sum(len(r['candidates']) for r in house),13);self.assertEqual(sum(bool(c['candidate_id']) for r in house for c in r['candidates']),10);self.assertIsNone(next(c for c in federal['USA:CT:house:01']['candidates'] if c['name']=='Amy Chai')['candidate_id']);self.assertTrue(federal['USA:CT:house:04']['unconfirmed_candidates'])

class ConnecticutFinanceAuditTests(unittest.TestCase):
 roster=[{'name':'Ryan Fazio','candidate_id':'CT:fazio','party':'REP','state':'CT','office':'G'},{'name':'Ned Lamont','candidate_id':'CT:lamont','party':'DEM','state':'CT','office':'G'}]
 def html(self):
  row=['0','Committee','January 10 Filing','Amendment','Bank','12/19/2025','2026','10/27/2025','12/31/2025','$247.93','G. Expenses Paid by Committee','Ryan  Fazio','Governor','','','eFile'];cells=''.join('<td>'+s+('</td>' if i!=1 else '<a href="Data/Attachment/Unassigned/report.PDF">PDF</a></td>') for i,s in enumerate(row));return 'Filed Year: 2026 Office: Governor Records Per Page: 100<span id="ctl00_ContentPlaceHolder1_lblPageSummary"> of 1</span><table id="ctl00_ContentPlaceHolder1_gvSearchResult"><tr>'+''.join('<th>'+h+'</th>' for h in HEADERS)+'</tr><tr>'+cells+'</tr></table>'
 def test_target_match_and_2025_received_in2026_not_candidate_ie_amount(self):
  r=summarize_search(self.html(),2026,self.roster,'2026-10-09T05:00:00+00:00');self.assertEqual(r['current_governor_target_records'],1);self.assertEqual(r['records'][0]['reported_amount_cents'],24793);self.assertEqual(r['records'][0]['received_date'],'2025-12-19');self.assertIsNone(r['candidate_audits'][0]['support_cents']);self.assertIsNone(r['records'][0]['normalized_candidate_ie_amount'])
 def test_pagination_schema_year_or_invalid_amount_fails(self):
  for a,b in [(' of 1',' of 2'),('File Year</th>','Year</th>'),('Filed Year: 2026','Filed Year: 2024'),('$247.93','$NaN'),('12/19/2025','12/19/2027')]:
   with self.assertRaises(ValueError):summarize_search(self.html().replace(a,b),2026,self.roster,'2026-10-09T05:00:00+00:00')
 def test_only_readonly_search_no_clear_or_reset(self):
  calls=[];outer=self
  class Response:
   status=200
   def __init__(self,text):self.body=text.encode()
   def geturl(self):return URL
   def read(self,*a):return self.body
   def __enter__(self):return self
   def __exit__(self,*a):return False
  def opener(req,**kw):
   calls.append(req)
   if not req.data:return Response('<input type="hidden" name="__VIEWSTATE" value="state"><input type="hidden" name="__VIEWSTATEGENERATOR" value="g"><input type="radio" name="ctl00$ContentPlaceHolder1$rblShowHistory" value="0" checked>')
   payload=parse_qs(req.data.decode(),keep_blank_values=True);self.assertEqual(payload['ctl00$ContentPlaceHolder1$btnSearch'],['Search']);self.assertEqual(payload['ctl00$ContentPlaceHolder1$lstNoOfRecords'],['100']);self.assertFalse(any('Clear' in k or 'Reset' in k for k in payload));return Response(outer.html())
  self.assertEqual(collect_audit(2026,self.roster,opener)['input_records'],1);self.assertEqual(len(calls),2)
  with self.assertRaises(URLError):collect_audit(2026,self.roster,lambda *a,**kw:(_ for _ in ()).throw(URLError('offline')))
