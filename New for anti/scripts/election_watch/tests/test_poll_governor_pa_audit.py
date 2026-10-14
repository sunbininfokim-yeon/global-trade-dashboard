import csv,io
from zipfile import ZipFile
import unittest
from election_watch.governor_pa import FILER,EXPENSE,summarize_export
from election_watch.superpac import SourceError

class PennsylvaniaAuditTests(unittest.TestCase):
    def setUp(self):
        self.filer=dict.fromkeys(FILER,'');self.filer.update(CampaignfinanceID='123',FILERID='committee',EYEAR='2026',SubmittedDate='2026-10-01',CYCLE='4',AMMEND='Y',OFFICE='GOV')
        self.expense=dict.fromkeys(EXPENSE,'');self.expense.update(CampaignFinanceID='123',FILERID='committee',EYEAR='2026',SubmittedDate='2026-10-01',CYCLE='4',EXPDATE='20260930',EXPAMT='100.00',EXPDESC='Support Shapiro advertising')
        self.roster=[{'candidate_id':'testDEM','name':'Josh Shapiro','party':'DEM'},{'candidate_id':'testREP','name':'Stacy Garrity','party':'REP'}]
    def archive(self,filers=None,expenses=None,extra=None,headers=None,broken_quote=False):
        out=io.BytesIO()
        with ZipFile(out,'w') as z:
            for kind,cols,rows in [('filer',FILER,[self.filer] if filers is None else filers),('expense',EXPENSE,[self.expense] if expenses is None else expenses)]:
                s=io.StringIO();w=csv.DictWriter(s,fieldnames=headers if kind=='expense' and headers else cols);w.writeheader();w.writerows(rows)
                value=s.getvalue()
                if broken_quote and kind=='expense':value+='123,committee,2026,2026-10-01,4,"broken "quoted" vendor",,,,,20260930,100.00,expense\n'
                z.writestr(kind+'_2026.txt',value)
            for kind in ['contrib','receipt','debt']:z.writestr(kind+'_2026.txt','not read')
            if extra:z.writestr(extra,'unsafe')
        return out.getvalue()
    def audit(self,**kw):return summarize_export(self.archive(**kw),2026,self.roster,'2026-10-08T12:00:00+00:00')
    def test_governor_filer_purpose_and_negative_general_expense_never_become_ie(self):
        a=self.audit(expenses=[self.expense,{**self.expense,'EXPAMT':'-25.00'}])
        self.assertEqual(a['negative_expense_rows'],1);self.assertEqual(a['expenses_in_amended_reports'],2)
        self.assertIsNone(a['current_governor_target_records'])
        self.assertTrue(all(c['support_cents'] is None and c['oppose_cents'] is None for c in a['candidate_audits']))
    def test_invalid_quoting_held_without_permissive_name_repair(self):
        a=self.audit(broken_quote=True);self.assertEqual(a['input_records'],2);self.assertEqual(a['parsed_expense_records'],1)
        self.assertEqual(len(a['sources'][1]['held_csv_rows']),1)
    def test_date_anomalies_remain_held_and_submission_stays_distinct(self):
        a=self.audit(expenses=[self.expense,{**self.expense,'EXPDATE':''},{**self.expense,'EXPDATE':'22660220'},{**self.expense,'EXPDATE':'20260230'}])
        self.assertEqual(a['expense_date_status'],{'valid_date':1,'missing_date':1,'future_date':1,'invalid_date':1})
        self.assertEqual(a['last_reported_submission_on'],'2026-10-01')
    def test_duplicate_report_or_metadata_mismatch_fails_and_unknown_link_held(self):
        with self.assertRaises(SourceError):self.audit(filers=[self.filer,self.filer])
        with self.assertRaises(SourceError):self.audit(expenses=[{**self.expense,'CYCLE':'3'}])
        a=self.audit(expenses=[{**self.expense,'CampaignFinanceID':'999'}]);self.assertEqual(a['expenses_without_valid_filer_report'],1)
    def test_empty_schema_zip_and_invalid_monetary_values_fail(self):
        for kwargs in [dict(expenses=[]),dict(extra='../escape.txt'),dict(expenses=[{**self.expense,'EXPAMT':'NaN'}]),dict(expenses=[{**self.expense,'SubmittedDate':'2027-01-01'}])]:
            with self.assertRaises(SourceError):self.audit(**kwargs)
        with self.assertRaises(SourceError):summarize_export(b'<html>error</html>',2026,self.roster,'2026-10-08T12:00:00+00:00')
        with self.assertRaises(SourceError):summarize_export(self.archive(),2028,self.roster,'2028-10-08T12:00:00+00:00')
