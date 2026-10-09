import copy,csv,io,json,zipfile,hashlib
from pathlib import Path
import unittest
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.governor_al import HEADERS,select_export,summarize_export
from election_watch.superpac import SourceError
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-09'
read=lambda p:json.loads(p.read_text())

class AlabamaPollTests(unittest.TestCase):
 def setUp(self):
  self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
  self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews'];self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/AL-primary-20261009.json');self.raw=[r['provider_record'] for r in self.audit['records']]
 def test_original_dates_population_and_reference_only(self):
  obs,rejected=normalize(self.raw,self.policy,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),5);self.assertTrue(all(not o['aggregation_eligibility']['eligible'] for o in obs));self.assertTrue(all(o['source_quality']['accuracy_grade'] is None for o in obs))
  for o in obs:
   self.assertEqual(o['source_quality']['verification_level'],'primary_toplines_checked')
   if o['pollster']=='RMG Research':self.assertEqual((o['population'],o['sample_n'],o['field_end']),('rv',800,'2026-09-25'))
   if o['pollster']=='yes. every kid.':self.assertEqual((o['population'],o['sample_n'],o['field_end']),('lv',601,'2026-07-11'));self.assertEqual(o['source_quality']['disclosure_review']['mode'],{'text_to_web_pct':57,'online_pct':43})
 def test_internal_historical_house_not_statewide_governor(self):
  obs,_=normalize(self.raw,self.policy,DAY);o=next(o for o in obs if o['race_id']=='USA:AL:house:02');self.assertEqual([a['pct'] for a in o['answers']],[46,46]);self.assertEqual(o['display_group'],'historical_matchup_reference');self.assertIn('party_internal_reference',o['aggregation_eligibility']['reasons']);self.assertEqual(o['sample_n'],421);self.assertTrue(o['source_quality']['disclosure_review']['excluded_subdistrict_governor_poll']['not_statewide'])
 def test_old_reference_records_cannot_create_current_signal(self):
  obs,_=normalize(self.raw,self.policy,DAY)
  for rid in ('USA:AL:house:02','USA:AL:senate','USA:AL:governor'):
   for days in (7,14):
    s=summarize([o for o in obs if o['race_id']==rid],self.policy['races'][rid],DAY,days);self.assertFalse(s['included_ids']);self.assertIsNone(s['party'])
 def test_hmp_missing_sample_and_informed_ballot_separate(self):
  hmp=self.audit['discovered_held_releases'][0];self.assertIsNone(hmp['sample_n']);self.assertIsNone(hmp['population']);self.assertEqual(hmp['initial_toplines']['Shomari Figures'],47);self.assertEqual(hmp['excluded_informed_toplines']['Shomari Figures'],50);self.assertFalse(any(r['pollster']=='Tulchin Research' for r in self.raw))
 def test_changed_snapshot_and_unreviewed_release_cannot_inherit_review(self):
  row=copy.deepcopy(self.raw[0]);row['sample_size']+=1;self.assertFalse(normalize([row],self.policy,DAY)[0]);row=copy.deepcopy(self.raw[0]);row['id']='future-unregistered-al-release';self.assertFalse(normalize([row],self.policy,DAY)[0])
 def test_primary_recheck_and_later_provider_deduplicate_or_fail_conflict(self):
  snap=read(CONFIG/'primary_supplements_2026.json');entry=copy.deepcopy(next(e for e in snap['records'] if e['state']=='AL'));body=b'%PDF-reviewed-test';entry['documents'][0]['sha256']=hashlib.sha256(body).hexdigest();snap['records']=[entry]
  class Response:
   status=200
   def __init__(self,url):self.url=url
   def geturl(self):return self.url
   def read(self,*args):return body
   def __enter__(self):return self
   def __exit__(self,*args):return False
  opener=lambda req,**kw:Response(req.full_url)
  original=copy.deepcopy(entry['record']);original['id']='later-provider-id';rows,receipts=merge_primary_supplements([original],snap,DAY,['AL'],opener);self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['later-provider-id'])
  conflict=copy.deepcopy(original);conflict['answers'][0]['pct']+=1
  with self.assertRaises(ValueError):merge_primary_supplements([conflict],snap,DAY,['AL'],opener)
  entry['documents'][0]['sha256']='0'*64;rows,receipts=merge_primary_supplements([],snap,DAY,['AL'],opener);self.assertEqual(receipts[0]['status'],'carried_forward_reference_only');self.assertEqual(rows[0]['end_date'],'2026-07-11')
 def test_official_nine_races_and_special_primary_dates(self):
  federal=read(ROOT/'config/federal_matchups/2026.json')['races'];rows=[r for r in federal.values() if r['state']=='AL'];self.assertEqual(len(rows),8);self.assertEqual(sum(len(r['candidates']) for r in rows),16);self.assertTrue(all(r['source_role']=='state_election_agency' for r in rows));self.assertTrue(all(c['candidate_id'] for r in rows for c in r['candidates']))
  for district in ('01','02','06','07'):self.assertEqual(self.policy['races']['USA:AL:house:'+district]['general_from'],'2026-08-12')
  self.assertEqual(self.policy['races']['USA:AL:senate']['general_from'],'2026-06-17');self.assertTrue(self.audit['official_ballot']['independent_certification_contains_only_state_legislature']);self.assertEqual(self.audit['official_ballot']['unopposed_verified_races'],[])

class AlabamaExpenditureAuditTests(unittest.TestCase):
 roster=[{'candidate_id':'AL:jones','name':'Doug Jones','party':'DEM','state':'AL','office':'G'},{'candidate_id':'AL:tuberville','name':'Tommy Tuberville','party':'REP','state':'AL','office':'G'}]
 selected={'YEAR':2026,'DATATYPE':'Expenditure','DOWNLOAD':55,'source_as_of':'2026-10-08','LASTUPDATEDRAW':'Oct 8, 2026, 2:34:00 AM','export_url':'https://fcpa.alabamavotes.gov/page.request.do?page=getTransactionData&id=55'}
 def archive(self,rows=None,headers=None,filename='2026_ExpendituresExtract1.csv'):
  s=io.StringIO();w=csv.writer(s);w.writerow(headers or HEADERS);w.writerows(rows or [self.row()]);b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr(filename,s.getvalue())
  return b.getvalue()
 def row(self):
  r=dict.fromkeys(HEADERS,'');r.update(CommitteeId='100',ExpenditureAmount='10.00',ExpenditureDate='10/01/2026',ExpenditureID='200',FiledDate='10/07/2026',Purpose='Advertising',ExpenditureType='Itemized',CommitteeType='Principal Campaign Committee',CandidateName='Doug Jones',Amended='N');return [r[k] for k in HEADERS]
 def audit(self,raw):return summarize_export(raw,2026,self.roster,'2026-10-09T05:00:00+00:00',self.selected,'a'*64,'b'*64)
 def test_owner_name_and_pac_cost_never_become_candidate_ie_money(self):
  rows=[self.row(),self.row()];rows[1][HEADERS.index('CommitteeType')]='Political Action Committee';rows[1][HEADERS.index('ExpenditureID')]='201';a=self.audit(self.archive(rows));self.assertEqual(a['input_records'],2);self.assertIsNone(a['current_governor_target_records']);self.assertFalse(a['candidate_amounts_available']);self.assertTrue(all(c['support_cents'] is None and c['oppose_cents'] is None for c in a['candidate_audits']));self.assertNotIn('records',a);self.assertEqual(a['last_valid_general_bulk_filing_date'],'2026-10-07')
 def test_ragged_or_missing_source_values_counted_explicitly_not_zero_filled(self):
  rows=[self.row(),['broken'],self.row()];rows[2][HEADERS.index('FiledDate')]='';a=self.audit(self.archive(rows));self.assertEqual(a['valid_structure_and_dates_records'],1);self.assertEqual(a['rejected_source_records'],{'ragged_source_csv_record':1,'invalid_or_missing_date_amount':1});self.assertEqual(a['source_parse_status'],'partial_rejected_source_records')
 def test_changed_schema_year_or_empty_valid_universe_fails(self):
  headers=HEADERS.copy();headers[0]='ChangedID'
  for raw in (self.archive(headers=headers),self.archive(filename='2024_ExpendituresExtract1.csv'),self.archive([['broken']])):
   with self.assertRaises(SourceError):self.audit(raw)
 def test_manifest_must_be_complete_unique_and_not_future(self):
  manifest={'success':True,'data':{'list':[self.selected],'totalRecords':1}};selected=select_export(json.dumps(manifest),2026,DAY);self.assertEqual(selected['DOWNLOAD'],55)
  for change in ('pagination','duplicate','future'):
   m=copy.deepcopy(manifest)
   if change=='pagination':m['data']['totalRecords']=2
   if change=='duplicate':m['data']['list']*=2;m['data']['totalRecords']=2
   if change=='future':m['data']['list'][0]['LASTUPDATEDRAW']='Oct 10, 2026, 2:34:00 AM'
   with self.assertRaises(SourceError):select_export(json.dumps(m),2026,DAY)

if __name__=='__main__':unittest.main()
