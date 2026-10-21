"""Synthetic transport fixtures; never published or approved as real polls."""
from copy import deepcopy
import hashlib
import unittest
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.poll_quality import answer_correction_fingerprint as fingerprint

DAY='2026-10-21'
URL='https://www.ppic.org/synthetic-question-scope-test.pdf'
BODY=b'%PDF-synthetic-test-only'
DOC={'url':URL,'sha256':hashlib.sha256(BODY).hexdigest()}
RAW={'id':'primary-synthetic-three-way','subject':'2026 Synthetic Test','poll_type':'us-senator',
     'pollster':'Synthetic Fixture','start_date':'2026-08-05','end_date':'2026-08-15',
     'created_at':'2026-08-28','sample_size':1000,'population':'lv','url':URL,
     'seat_name':None,'internal':False,'partisan':None,'sponsors':[],
     'answers':[{'choice':n,'pct':p}for n,p in [('Candidate A',44),('Candidate B',38),('Candidate C',7)]]}
API={**deepcopy(RAW),'id':'synthetic-later-api',
     'answers':[{'choice':'Candidate A','pct':47},{'choice':'Candidate B','pct':41}]}
class Response:
    status=200
    def __init__(self,url):self.url=url
    def geturl(self):return self.url
    def read(self,n):return BODY[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass
class InitialQuestionScopeTests(unittest.TestCase):
    def entry(self):
        return {'state':'XX','reviewed_on':DAY,'record':deepcopy(RAW),'record_sha256':fingerprint(RAW),
          'documents':[deepcopy(DOC)],'same_wave_separate_question_reviews':[{
            'id':API['id'],'reason':'different_initial_ballot_question',
            'provider_snapshot_sha256':fingerprint(API),'primary_record_sha256':fingerprint(RAW),
            'reviewed_on':DAY,'wave_id':'synthetic-one-wave','primary_question':'Q3 three-candidate ballot',
            'question':'Q4 two-candidate ballot','primary_ballot_format':'initial_named_multicandidate',
            'provider_ballot_format':'initial_named_two_candidate','source_document':deepcopy(DOC)}]}
    def merge(self,entry=None,api=None,isolate=False,opener=None):
        return merge_primary_supplements([api or deepcopy(API)],{
            'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry or self.entry()]},
            DAY,opener=opener or (lambda req,**kw:Response(req.full_url)),isolate_conflicts=isolate)
    def test_exact_questions_survive_without_false_conflict(self):
        rows,receipts=self.merge()
        self.assertEqual(len(rows),2);self.assertEqual(rows[0],API)
        self.assertEqual(rows[1]['answers'],RAW['answers'])
        self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')
        self.assertEqual(receipts[0]['separate_question_provider_ids'],[API['id']])
        self.assertEqual(receipts[0]['provider_duplicate_ids'],[])
    def test_changed_values_sample_sponsor_or_id_never_inherit_approval(self):
        for patch in ({'id':'different-api-id'},{'sample_size':1001},{'sponsors':['different client']},
          {'answers':[{'choice':'Candidate A','pct':48},{'choice':'Candidate B','pct':41}]}):
            with self.subTest(patch=patch),self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
                self.merge(api={**deepcopy(API),**patch})
        rows,receipts=self.merge(api={**deepcopy(API),'end_date':'2026-08-16'})
        self.assertEqual(receipts[0]['separate_question_provider_ids'],[])
    def test_missing_future_or_different_document_review_is_rejected(self):
        for patch in ({'reviewed_on':'2026-10-22'},{'source_document':{'url':URL,'sha256':'0'*64}},
          {'primary_record_sha256':'0'*64},{'primary_question':None},{'wave_id':None},
          {'provider_ballot_format':'informed_two_candidate'}):
            entry=self.entry();entry['same_wave_separate_question_reviews'][0].update(patch)
            with self.subTest(patch=patch),self.assertRaisesRegex(ValueError,'unreviewed_initial_ballot_question_scope'):
                self.merge(entry)
    def test_unreviewed_candidate_is_not_exempt_with_exact_provider_hash(self):
        api=deepcopy(API);api['answers'][0]['choice']='Unreviewed Candidate'
        entry=self.entry();entry['same_wave_separate_question_reviews'][0]['provider_snapshot_sha256']=fingerprint(api)
        with self.assertRaisesRegex(ValueError,'initial_ballot_candidate_scope_mismatch'):self.merge(entry,api)
    def test_source_failure_preserves_original_values_and_dates(self):
        def fail(*args,**kw):raise OSError('synthetic offline')
        rows,receipts=self.merge(opener=fail)
        self.assertEqual(rows[1]['answers'],RAW['answers']);self.assertEqual(rows[1]['end_date'],RAW['end_date'])
        self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
    def test_changed_question_is_still_isolated_as_real_conflict(self):
        api=deepcopy(API);api['answers'][0]['pct']=48
        rows,receipts=self.merge(api=api,isolate=True)
        self.assertEqual(len(rows),1)
        self.assertEqual(receipts[0]['status'],'primary_provider_conflict_reference_only')
        self.assertEqual(receipts[0]['conflicting_provider_records'],[api])
