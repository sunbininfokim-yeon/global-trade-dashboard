"""Exact RCV question reviews stay outside ordinary election lead counts."""
from copy import deepcopy
import hashlib
import io
import unittest
from unittest.mock import patch
from election_watch.poll_quality import ranked_choice_question, answer_correction_fingerprint
from election_watch.poll_primary_supplements import merge_primary_supplements

DAY='2026-10-09'

class RankedChoiceTests(unittest.TestCase):
    def setUp(self):
        self.raw={'id':'provider-pair','subject':'2026 Alaska','poll_type':'us-senator',
            'pollster':'Fixture','url':'https://publisher.example/release','start_date':'2026-09-28',
            'end_date':'2026-09-30','created_at':'2026-10-01','population':'lv','sample_size':758,
            'internal':False,'partisan':None,'sponsors':[],
            'answers':[{'choice':'A','pct':48},{'choice':'B','pct':47}]}
        self.race={'ballot_system':'ranked_choice','required_candidates':['A','B','C','D'],
            'candidates':{n:{'canonical_name':n} for n in ('A','B','C','D')}}
        self.review={'provider_record_sha256':answer_correction_fingerprint(self.raw),'reviewed_on':DAY,
            'admission':{'signal_eligible':False,'source_role':'pollster_primary',
                'signal_exclusion_reasons':['ranked_choice_separate_question_reference']},
            'sources':['https://publisher.example/release'],'disclosure_review':{'sample_n':758},
            'primary_toplines':{'A':48,'B':47},'ranked_choice_question':{'kind':'forced_two_candidate',
                'question':'Forced pair including leaners','label_ko':'강제 양자','compared_candidates':['A','B']}}

    def test_exact_pair_is_reference_and_changed_record_is_held(self):
        result=ranked_choice_question(self.raw,self.review,self.race,DAY)
        self.assertFalse(result['aggregation_eligible']);self.assertFalse(result['election_result'])
        changed=deepcopy(self.raw);changed['answers'][0]['pct']=49
        with self.assertRaisesRegex(ValueError,'not_reviewed'):
            ranked_choice_question(changed,self.review,self.race,DAY)

    def test_partial_first_choice_and_eligible_simulation_rejected(self):
        review=deepcopy(self.review);review['ranked_choice_question']['kind']='first_preference'
        with self.assertRaisesRegex(ValueError,'field mismatch'):
            ranked_choice_question(self.raw,review,self.race,DAY)
        review=deepcopy(self.review);review['admission']['signal_eligible']=True
        with self.assertRaisesRegex(ValueError,'exact reference'):
            ranked_choice_question(self.raw,review,self.race,DAY)

    def test_exception_requires_rcv_ballot_and_exact_question_review(self):
        with self.assertRaisesRegex(ValueError,'not_reviewed'):
            ranked_choice_question(self.raw,{},self.race,DAY)
        with self.assertRaisesRegex(ValueError,'outside ranked'):
            ranked_choice_question(self.raw,self.review,{},DAY)
        self.assertIsNone(ranked_choice_question(self.raw,{}, {},DAY))

    def entry(self):
        raw=deepcopy(self.raw);raw['id']='primary-first-choice'
        raw['answers'] += [{'choice':'C','pct':2},{'choice':'D','pct':1}]
        body=b'%PDF-fixture'
        return {'state':'AK','reviewed_on':DAY,'record':raw,'record_sha256':answer_correction_fingerprint(raw),
            'documents':[{'url':'https://publisher.example/download?id=exact','format':'reviewed_pdf_v1',
                'sha256':hashlib.sha256(body).hexdigest()}],
            'same_wave_separate_question_reviews':[{'id':self.raw['id'],
                'provider_snapshot_sha256':answer_correction_fingerprint(self.raw),
                'reason':'different_ranked_choice_question','question':'Forced pair'}]},body

    def merge(self,rows,entry,body):
        class Response(io.BytesIO):
            status=200
            def geturl(self):return entry['documents'][0]['url']
        snapshot={'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]}
        with patch('election_watch.poll_primary_supplements.primary_document_approved',return_value=True):
            return merge_primary_supplements(rows,snapshot,DAY,opener=lambda *a,**k:Response(body))

    def test_separate_question_survives_and_later_exact_duplicate_deduplicates(self):
        entry,body=self.entry();rows,checks=self.merge([self.raw],entry,body)
        self.assertEqual(len(rows),2);self.assertEqual(checks[0]['status'],'primary_documents_rechecked')
        self.assertEqual(checks[0]['separate_question_provider_ids'],[self.raw['id']])
        later=deepcopy(entry['record']);later['id']='later-api-first-choice'
        rows,checks=self.merge([self.raw,later],entry,body)
        self.assertEqual(len(rows),2);self.assertEqual(checks[0]['provider_duplicate_ids'],[later['id']])
        changed=deepcopy(self.raw);changed['answers'][0]['pct']=49
        with self.assertRaisesRegex(ValueError,'wave_conflict'):self.merge([changed],entry,body)

    def test_document_signature_failure_preserves_original_reference(self):
        entry,body=self.entry();rows,checks=self.merge([],entry,b'PK\x03\x04wrong-format')
        self.assertEqual(checks[0]['status'],'carried_forward_reference_only')
        self.assertEqual(rows[0]['end_date'],'2026-09-30')
        snapshot={'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':[entry]}
        with patch('election_watch.poll_primary_supplements.primary_document_approved',return_value=False):
            with self.assertRaisesRegex(ValueError,'unreviewed primary document'):
                merge_primary_supplements([],snapshot,DAY)

if __name__=='__main__':unittest.main()
