import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from build_superpac import atomic_json
from build_governor_finance import main as collect_state
from election_watch.governor_ca import normalize, RemoteZip
from election_watch.governor_matchups import parse
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
    def test_ballot_phase_only_explicit_cover_election_date(self):
        dates={'2026-06-02':'P2026','2026-11-03':'G2026'}
        for value,phase in [('6/2/2026 12:00:00 AM','P2026'),('11/3/2026','G2026'),
                            ('','UNKNOWN'),('1/1/1900','UNKNOWN'),('6/2/2024','UNKNOWN')]:
            cover=dict(self.cover(),ELECT_DATE=value)
            p=normalize(2026,[cover],[self.line(EXP_DATE='10/1/2026')],ballot_dates=dates)
            self.assertEqual(p['spending'][0]['election_type'],phase)
        # The same date is not assigned a phase without a reviewed calendar.
        p=normalize(2026,[dict(self.cover(),ELECT_DATE='11/3/2026')],[self.line()])
        self.assertEqual(p['spending'][0]['election_type'],'UNKNOWN')
    def test_range_must_pin_etag_and_be_partial(self):
        class Response:
            status=200
            headers={'Content-Length':'100','ETag':'version1'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
        r=RemoteZip(opener=lambda *a,**k:Response())
        with self.assertRaises(SourceError):r.read(1)
    def test_general_nominee_does_not_downgrade_state_certified_identity(self):
        certified = {'candidate_id':'CA:certified:1','name':'Test Candidate','party':'DEM',
            'source_url':'https://elections.cdn.sos.ca.gov/primary-ballot.pdf',
            'registration_status':'certified_primary_ballot'}
        html = '''<div data-original-id="US-CA"><h3><a href="California_gubernatorial_election,_2026">California</a></h3>
            <p>Primary Date: June 2, 2026</p><p>General Election Candidates</p>
            <ul><li>Test Candidate (D)</li><li>Other Candidate (R)</li></ul></div>'''
        snapshot = parse(html,2026,['CA'],'2026-10-07',{'CA':[certified]})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(root/'config/governor_candidates/2026/CA.json',{'candidates':[certified]})
            atomic_json(root/'config/governor_matchups/2026.json',snapshot)
            captured = {}
            def collector(cycle,roster,local,ballot_dates):
                captured.update(roster=roster,dates=ballot_dates)
                return {'schema':'usa_governor_source_v1','quality':{}}
            with patch('build_governor_finance.ROOT',root),patch('build_governor_finance.collect_ca',side_effect=collector), \
                 patch('sys.argv',['build_governor_finance.py','--cycle','2026','--state','CA','--public',str(root/'public')]):
                self.assertEqual(collect_state(),0)
            candidate = next(c for c in captured['roster'] if c['candidate_id']=='CA:certified:1')
            self.assertEqual(candidate['source_url'],certified['source_url'])
            self.assertEqual(candidate['registration_status'],'certified_primary_ballot')
            self.assertEqual(captured['dates'],{'2026-06-02':'P2026','2026-11-03':'G2026'})
