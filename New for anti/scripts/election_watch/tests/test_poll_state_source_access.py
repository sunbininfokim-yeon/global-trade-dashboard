import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from election_watch.governor_source_access import collect_access, probe, publish_access, validate_access

ROOT=Path(__file__).resolve().parents[1]
URL='https://peachfile.ethics.ga.gov/'
CHECKED='2026-10-08T10:00:00+00:00'


class Response(io.BytesIO):
    status=200
    def __init__(self, body=b'<html>PeachFile public search</html>', url=URL):
        super().__init__(body);self.url=url
    def geturl(self):return self.url


class GovernorSourceAccessTests(unittest.TestCase):
    def agency(self):
        return json.loads((ROOT/'config/usa_state_campaign_finance_sources_v1.json').read_text())['states']['GA']

    def opener(self):
        return lambda req,timeout:Response(url=req.full_url)

    def test_reachable_endpoint_never_asserts_money_or_record_coverage(self):
        row=collect_access('GA',2026,self.agency(),CHECKED,opener=self.opener())
        self.assertEqual(row['status'],'public_endpoint_reachable_mapping_required')
        self.assertFalse(row['financial_data_collected']);self.assertFalse(row['candidate_amounts_available'])
        self.assertNotIn('records',row);self.assertNotIn('support_cents',row)

    def test_legacy_success_cannot_hide_current_portal_block(self):
        def opener(req,timeout):
            if req.full_url==URL:raise HTTPError(URL,403,'Forbidden',{},None)
            return Response(url=req.full_url)
        row=collect_access('GA',2026,self.agency(),CHECKED,opener=opener)
        self.assertEqual(row['status'],'source_access_blocked')
        self.assertEqual(row['endpoints'][0]['http_status'],403)
        self.assertTrue(all(r['status']=='public_endpoint_reachable' for r in row['endpoints'][1:]))
        self.assertIsNone(row['last_current_endpoint_accessible_at'])

    def test_soft_block_and_redirect_are_not_success(self):
        blocked=probe(URL,lambda req,timeout:Response(b'The request is blocked.'))
        self.assertEqual(blocked['status'],'source_access_blocked')
        redirect=probe(URL,lambda req,timeout:Response(url='https://unreviewed.example/login'))
        self.assertEqual(redirect['status'],'source_response_review_required')
        self.assertFalse(redirect['same_host'])

    def test_network_failure_preserves_last_reachable_time(self):
        old=collect_access('GA',2026,self.agency(),CHECKED,opener=self.opener())
        failing=Mock(side_effect=URLError('synthetic timeout'))
        row=collect_access('GA',2026,self.agency(),'2026-10-08T11:00:00+00:00',old,failing)
        self.assertEqual(row['status'],'source_unavailable')
        self.assertEqual(row['last_current_endpoint_accessible_at'],CHECKED)
        self.assertNotEqual(row['checked_at'],row['last_current_endpoint_accessible_at'])

    def test_future_review_or_wrong_health_scope_does_not_replace_valid_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'GA.json'
            old=publish_access(p,'GA',2026,self.agency(),CHECKED,opener=self.opener())
            original=p.read_bytes()
            agency=self.agency();agency['public_source_review']['reviewed_on']='2026-10-09'
            with self.assertRaises(ValueError):publish_access(p,'GA',2026,agency,CHECKED,old,self.opener())
            self.assertEqual(original,p.read_bytes())
            invalid=copy.deepcopy(old);invalid['state']='TN'
            with self.assertRaises(ValueError):publish_access(p,'GA',2026,self.agency(),CHECKED,invalid,self.opener())
            self.assertEqual(original,p.read_bytes())

    def test_health_cannot_invent_finance_or_conflict_with_current_endpoint(self):
        old=collect_access('GA',2026,self.agency(),CHECKED,opener=self.opener())
        for field,value in [('candidate_amounts_available',True),('status','source_access_blocked')]:
            row=copy.deepcopy(old);row[field]=value
            with self.assertRaises(ValueError):validate_access(row,'GA',2026,'2026-10-08')

    def test_temporary_failure_and_deleted_endpoint_are_distinguished_from_access_denial(self):
        for code,expected in [(403,'source_access_blocked'),(503,'source_unavailable'),
                              (429,'source_unavailable'),(404,'source_response_review_required')]:
            def opener(req,timeout):raise HTTPError(req.full_url,code,'synthetic',{},None)
            row=probe(URL,opener)
            self.assertEqual(row['http_status'],code);self.assertEqual(row['status'],expected)
