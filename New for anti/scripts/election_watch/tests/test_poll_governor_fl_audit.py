import copy
import csv,io
import unittest
from election_watch.governor_fl import HEADERS,LIMIT,parse_export,summarize_export,validate_form,collect_audit
from election_watch.superpac import SourceError


def encoded(rows,headers=HEADERS):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=headers,delimiter='\t')
    writer.writeheader();writer.writerows(rows);return out.getvalue().encode('windows-1252')


class FloridaPublicAuditTests(unittest.TestCase):
    def fixture(self):
        row=dict.fromkeys(HEADERS,'');row.update({'Candidate/Committee':'Synthetic Test (ECO)',
            'Date':'09/10/2026','Amount':'-10.00','Payee Name':'Fixture Vendor',
            'Purpose':'support Candidate Alpha','Type':'REF'})
        roster=[{'candidate_id':'FL:test','name':'Candidate Alpha','party':'DEM'}]
        return row,roster

    def test_eco_expenses_purpose_and_refund_never_imply_candidate_ie(self):
        row,roster=self.fixture();result=summarize_export(2026,encoded([row,row]),roster,'2026-10-08T00:00:00Z')
        self.assertEqual(result['input_records'],2);self.assertEqual(result['identical_row_occurrences'],2)
        self.assertIsNone(result['current_governor_target_records'])
        for c in result['candidate_audits']:
            self.assertIsNone(c['reported_rows']);self.assertIsNone(c['support_cents']);self.assertIsNone(c['oppose_cents'])
        self.assertEqual(result['all_state_ie_coverage'],'not_established')
        self.assertEqual(result['last_reported_expenditure_on'],'2026-09-10')

    def test_empty_html_and_row_cap_are_failures_not_zero_coverage(self):
        row,_=self.fixture()
        for raw in [b'',b'<HTML>Invalid Date Range Entered</HTML>',encoded([]),encoded([row]*LIMIT)]:
            with self.assertRaises(SourceError):parse_export(raw,2026,'2026-10-08T00:00:00Z')

    def test_schema_extra_columns_and_truncated_records_fail(self):
        row,_=self.fixture()
        for raw in [encoded([row],HEADERS+['new']),encoded([row])+b'bad\trow\n']:
            with self.assertRaises(SourceError):parse_export(raw,2026,'2026-10-08T00:00:00Z')

    def test_historical_outside_cycle_future_and_nonfinite_values_fail(self):
        row,_=self.fixture()
        for key,value in [('Date','01/01/2024'),('Date','10/09/2026'),('Amount','NaN'),('Amount','Infinity'),
                          ('Amount','10.001'),('Candidate/Committee','Candidate Campaign')]:
            changed={**row,key:value}
            with self.assertRaises(SourceError):parse_export(encoded([changed]),2026,'2026-10-08T00:00:00Z')

    def test_unreviewed_cycle_roster_and_form_fail_closed(self):
        row,roster=self.fixture()
        for cycle,candidates in [(2024,roster),(2026,[]),(2026,roster*2)]:
            with self.assertRaises(SourceError):summarize_export(cycle,encoded([row]),candidates,'2026-10-08T00:00:00Z')
        with self.assertRaises(SourceError):validate_form('<form action="/login">Sign in</form>',2026)

    def test_export_redirect_does_not_become_public_finance_data(self):
        _,roster=self.fixture()
        class Response:
            status=200
            def geturl(self):return 'https://example.org/login'
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with self.assertRaises(SourceError):collect_audit(2026,roster,lambda *args,**kw:Response())
