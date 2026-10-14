import csv, io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from election_watch.governor_co import HEADERS, CSV_URL, DOWNLOAD_PAGE, parse_export, summarize_export, collect_audit
from election_watch.superpac import SourceError
from refresh_governor_finance_audit import main

class ColoradoFinanceAuditTests(unittest.TestCase):
    def row(self,**updates):
        r={k:'' for k in HEADERS};r.update(CO_ID='1',RecordID='100',ExpenditureAmount='10.25',
            FiledDate='2026-10-08 00:00:00',CommitteeType='Independent Expenditure Committee',
            CommitteeName='Committee',CandidateName='',Amended='N',Amendment='N')
        r.update(updates);return r
    def export(self,rows=None,name='2026_ExpenditureData.csv',headers=HEADERS):
        text=io.StringIO();w=csv.DictWriter(text,fieldnames=headers,extrasaction="ignore");w.writeheader();w.writerows(rows or [self.row()])
        body=io.BytesIO()
        with zipfile.ZipFile(body,'w') as z:z.writestr(name,text.getvalue().encode('cp1252'))
        return body.getvalue()
    def roster(self):return [dict(state='CO',office='G',candidate_id='CO:1',name='Candidate',party='DEM')]
    def audit(self,raw):return summarize_export(raw,2026,self.roster(),'2026-10-09T00:00:00+00:00','10/8/2026 2:00 AM')
    def test_campaign_owner_not_ie_target_and_amendments_not_summed(self):
        raw=self.export([self.row(CommitteeName='Comité',CandidateName='Candidate'),
            self.row(CommitteeType='Candidate Committee',Amended='Y'),self.row(Amendment='Y')])
        audit=self.audit(raw)
        self.assertEqual(audit['input_records'],3)
        self.assertEqual(audit['independent_expenditure_committee_rows'],2)
        self.assertEqual(audit['duplicate_record_ids'],2)
        self.assertFalse(audit['candidate_amounts_available'])
        self.assertFalse(audit['amendment_diagnostics']['lineage_verified'])
        for key in ('support_cents','oppose_cents','reported_rows'):self.assertIsNone(audit['candidate_audits'][0][key])
        self.assertIsNone(audit['current_governor_target_records'])
        self.assertEqual(audit['sources'][0]['csv_encoding'],'cp1252')
    def test_changed_schema_archive_amount_date_and_amendment_fail_closed(self):
        for raw in [b'blocked',self.export(name='2025_ExpenditureData.csv'),
                    self.export(headers=HEADERS[:-1]),self.export([self.row(ExpenditureAmount='NaN')]),
                    self.export([self.row(ExpenditureAmount='1.001')]),self.export([self.row(RecordID='')]),
                    self.export([self.row(FiledDate='2026-10-10 00:00:00')]),
                    self.export([self.row(FiledDate='2025-10-08 00:00:00')]),self.export([self.row(Amendment='?')])]:
            with self.assertRaises(SourceError):self.audit(raw)
    def test_future_snapshot_or_wrong_state_not_a_valid_co_audit(self):
        with self.assertRaises(SourceError):summarize_export(self.export(),2026,self.roster(),'2026-10-09','10/10/2026 2:00 AM')
        with self.assertRaises(SourceError):summarize_export(self.export(),2026,[dict(state='CA',office='G')],'2026-10-09','10/8/2026 2:00 AM')
    def test_public_html_date_entities_and_exact_zip_link(self):
        page=('<html>as of&nbsp;<span>10/8/2026&nbsp;&nbsp;2:00 AM</span><a href="'+CSV_URL+'">Download</a></html>').encode()
        raw=self.export()
        class Response:
            headers={}
            def __init__(self,url):self.url=url
            def geturl(self):return self.url
            def read(self,*a):return page if self.url==DOWNLOAD_PAGE else raw
            def __enter__(self):return self
            def __exit__(self,*a):return False
        result=collect_audit(2026,self.roster(),lambda req,**kw:Response(req.full_url))
        self.assertEqual(result['sources'][0]['source_as_of_text'],'10/8/2026 2:00 AM')
    def test_refresh_failure_keeps_existing_audit_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            public=Path(td);path=public/'usa_governor_finance_audits/2026/CO.json';path.parent.mkdir(parents=True)
            original=b'{"prior":"valid"}\n';path.write_bytes(original)
            with patch('refresh_governor_finance_audit.collect_co',side_effect=SourceError('source failed')), \
                 patch('sys.argv',['refresh_governor_finance_audit.py','--state','CO','--public',td]):
                self.assertEqual(main(),1)
            self.assertEqual(path.read_bytes(),original)
