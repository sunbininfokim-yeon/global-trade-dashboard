import unittest
from election_watch.governor_ca import normalize, RemoteZip
from election_watch.superpac import SourceError

class CaliforniaTests(unittest.TestCase):
    def cover(self, **changes):
        return dict(FILING_ID='1',AMEND_ID='0',FORM_TYPE='F496',OFFICE_CD='GOV',CAND_NAML='Candidate',CAND_NAMF='Test',CAND_NAMS='',SUP_OPP_CD='S',FILER_ID='12',FILER_NAML='Committee',ENTITY_CD='RCP',RPT_DATE='6/2/2026 12:00:00 AM',**changes)
    def line(self, **changes):
        row=dict(FILING_ID='1',AMEND_ID='0',LINE_ITEM='1',FORM_TYPE='F496',EXP_DATE='6/1/2026 12:00:00 AM',MEMO_CODE='',AMOUNT='10.25')
        row.update(changes);return row
    def test_full_amendment_replacement_including_deleted_lines(self):
        old=self.cover();new=dict(old,AMEND_ID='1')
        p=normalize(2026,[old,new],[self.line(),self.line(AMEND_ID='1',AMOUNT='-0.25')])
        self.assertEqual(p['spending'][0]['support_cents'],-25)
        self.assertEqual(p['quality']['included_records'],1)
        self.assertEqual(normalize(2026,[old,new],[self.line()])['spending'],[])
    def test_exact_roster_identity_no_fuzzy_party_inference(self):
        roster=[dict(name='Test Candidate',candidate_id='CA:certified:1',party='DEM',source_url='https://example.gov/list')]
        p=normalize(2026,[self.cover()],[self.line()],roster)
        self.assertEqual(p['spending'][0]['party'],'DEM')
        with self.assertRaises(SourceError):normalize(2026,[self.cover()],[self.line()],roster+roster)
        p=normalize(2026,[dict(self.cover(),CAND_NAMF='T.')],[self.line()],roster)
        self.assertEqual(p['spending'][0]['party'],'UNKNOWN')
        self.assertEqual(p['spending'][0]['category'],'state_independent_spender_unclassified')
        with self.assertRaises(SourceError):normalize(2026,[self.cover()],[self.line(),self.line()])
    def test_outside_cycle_and_memo_excluded(self):
        p=normalize(2026,[self.cover()],[self.line(EXP_DATE='1/1/2024'),self.line(LINE_ITEM='2',MEMO_CODE='X')])
        self.assertEqual(p['spending'],[])
        self.assertEqual(p['quality']['input_records'],sum(p['quality']['excluded_records'].values()))
    def test_range_must_pin_etag_and_be_partial(self):
        class Response:
            status=200
            headers={'Content-Length':'100','ETag':'version1'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
        r=RemoteZip(opener=lambda *a,**k:Response())
        with self.assertRaises(SourceError):r.read(1)
