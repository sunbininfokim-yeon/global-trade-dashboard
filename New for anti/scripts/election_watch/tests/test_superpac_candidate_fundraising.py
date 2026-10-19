"""Campaign receipts stay separate from outside spending, ballot status and clocks."""
from copy import deepcopy
from pathlib import Path
import io,json,tempfile,unittest,zipfile
from unittest.mock import patch
from election_watch.candidate_fundraising import cents,rows_from_zip,normalize,for_candidate,preserve_previous,collect
import refresh_candidate_fundraising as cli
C=Path(__file__).resolve().parents[1]/'config'

def sample():
 row=['']*30;row[0]='H6OH01001';row[1]='TEST, CANDIDATE';row[4]='DEM';row[5]='1000.01';row[6]='50';row[8]='25';row[10]='123.45';row[11]='10';row[12]='500';row[17]='400';row[18]='OH';row[19]='01';row[27]='09/30/2026'
 master=[row[0],row[1],'DEM','2026','OH','H','01','C','C','C00000001','','','','','']
 return row,master
class FundraisingTests(unittest.TestCase):
 def setUp(self):self.catalog=json.loads((C/'usa_polls/targets_2026.json').read_text());self.row,self.master=sample()
 def doc(self,row=None,master=None):return normalize([row or self.row],[master or self.master],self.catalog,'2026-10-19',{'fixture':'not real data'})
 def test_receipts_individuals_candidate_money_and_loans_are_not_conflated(self):
  d=self.doc();r=d['candidates'][self.row[0]];a=r['amounts'];self.assertEqual(a['receipts_cents'],100001);self.assertEqual(a['individual_contributions_cents'],40000);self.assertEqual(a['candidate_loans_cents'],50000);self.assertIsNone(a['debts_owed_cents']);self.assertTrue(r['transfer_double_count_risk']);self.assertFalse(r['includes_outside_spending']);self.assertEqual(r['coverage_end'],'2026-09-30');self.assertIn('ballot_unverified',r['status'])
 def test_precision_null_and_reported_negative_corrections_are_preserved(self):
  self.assertIsNone(cents(''));self.assertEqual(cents('0'),0);self.assertEqual(cents('-1.23'),-123)
  for bad in ('NaN','Infinity','1.001','oops'):
   with self.assertRaises(ValueError):cents(bad)
 def test_future_dates_old_cycle_district_party_and_duplicate_rows_do_not_join(self):
  for index,value in ((27,'10/20/2026'),(19,'99'),(4,'REP')):
   raw=self.row.copy();raw[index]=value
   with self.assertRaises(ValueError):self.doc(raw)
  master=self.master.copy();master[3]='2028'
  with self.assertRaises(ValueError):self.doc(master=master)
  with self.assertRaises(ValueError):normalize([self.row,self.row],[self.master],self.catalog,'2026-10-19',{})
 def test_missing_master_and_off_cycle_senator_cannot_be_current_2026_candidate(self):
  raw=self.row.copy();raw[0]='S6AZ00001';raw[18]='AZ';raw[19]='00';master=self.master.copy();master[0]=raw[0];master[4]='AZ';master[5]='S';master[6]='00'
  with self.assertRaises(ValueError):self.doc(raw,master)
 def test_at_large_01_is_explicitly_normalized_but_multi_district_00_is_not(self):
  row=self.row.copy();row[18]='AK';master=self.master.copy();master[4]='AK';self.assertEqual(self.doc(row,master)['candidates'][row[0]]['district'],'00')
  row=self.row.copy();row[19]='00';master=self.master.copy();master[6]='00'
  with self.assertRaises(ValueError):self.doc(row,master)
 def test_only_exact_fec_identity_and_office_state_district_match_get_money(self):
  d=self.doc();self.assertEqual(for_candidate(d,self.row[0],'OH','house','01',2026)['amounts']['receipts_cents'],100001)
  self.assertEqual(for_candidate(d,self.row[0],'NY','house','01',2026)['status'],'candidate_identity_scope_conflict')
  self.assertIsNone(for_candidate(d,'unmatched','OH','house','01',2026)['amounts'])
  self.assertIsNone(for_candidate(d,'any-governor','OH','governor',None,2026)['amounts'])
 def test_older_or_missing_report_retains_old_values_and_own_source_day(self):
  old=self.doc();new=deepcopy(old);ident=self.row[0];new['as_of']='2026-10-20';new['candidates'][ident]['coverage_end']='2026-06-30';new['source_receipts']={'new':'request'}
  merged=preserve_previous(new,old);r=for_candidate(merged,ident,'OH','house','01',2026);self.assertEqual(r['coverage_end'],'2026-09-30');self.assertEqual(r['snapshot_as_of'],'2026-10-19');self.assertEqual(r['source_receipts'],old['source_receipts']);self.assertEqual(merged['carried_forward_candidates'],1)
  new=deepcopy(old);new['candidates']={};self.assertIn(ident,preserve_previous(new,old)['candidates'])
 def test_zip_width_missing_member_and_oversized_or_invalid_document_fail(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w')as z:z.writestr('weball26.txt','|'.join(self.row)+'\n')
  self.assertEqual(rows_from_zip(b.getvalue(),'weball26.txt',30),[self.row])
  with self.assertRaises(ValueError):rows_from_zip(b.getvalue(),'weball26.txt',29)
  with self.assertRaises(ValueError):rows_from_zip(b.getvalue(),'other.txt',30)
 def test_cli_source_failure_keeps_last_good_file_and_writes_failure_health(self):
  with tempfile.TemporaryDirectory()as tmp:
   folder=Path(tmp)/'usa_election_finance/2026';folder.mkdir(parents=True);good=folder/'candidate_fundraising_v1.json';good.write_text(json.dumps(self.doc()));before=good.read_bytes()
   with patch('sys.argv',['refresh','--public',tmp]),patch.object(cli,'collect',side_effect=OSError('fixture outage')):self.assertEqual(cli.main(),1)
   self.assertEqual(good.read_bytes(),before);self.assertEqual(json.loads((folder/'candidate_fundraising_status_v1.json').read_text())['status'],'failed_last_good_preserved')
