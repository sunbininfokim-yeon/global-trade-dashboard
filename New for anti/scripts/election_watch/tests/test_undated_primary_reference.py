"""Unknown release dates remain null and cannot authorize polling signals."""
import copy
import unittest
from tests.test_live_polls import poll, POLICY, DAY
from election_watch.live_polls import normalize
from election_watch.poll_quality import answer_correction_fingerprint, review_fingerprint
from election_watch.poll_html_evidence import canonical_region

class UndatedPrimaryTests(unittest.TestCase):
    def fixture(self):
        raw=poll('primary-synthetic-undated'); observed=normalize([raw],POLICY,DAY)[0][0]
        raw['created_at']=None; doc={'url':raw['url'],'sha256':'a'*64}
        raw['primary_source_capture']={'status':'primary_documents_rechecked','original_reviewed_on':DAY,'documents':[{**doc,'status':'unchanged'}]}
        fingerprint=answer_correction_fingerprint(raw)
        review={'reviewed_on':DAY,'provider_record_sha256':fingerprint,'primary_supplement_record_sha256':fingerprint,
            'primary_documents':[doc],'snapshot_sha256':review_fingerprint(observed),'sources':[raw['url']],
            'primary_toplines':{'Kathy Hochul':48,'Bruce Blakeman':44},'disclosure_review':{'publication_date_status':'not_disclosed'},
            'limitations_ko':'Synthetic reference','admission':{'pollster':raw['pollster'],'provider_url':raw['url'],
            'methodology_url':raw['url'],'group':'quinnipiac','source_role':'pollster_primary','signal_eligible':False,
            'signal_exclusion_reasons':['publication_date_not_disclosed']}}
        policy=copy.deepcopy(POLICY);policy['quality_reviews']={raw['id']:review};return raw,policy
    def test_null_date_preserved_reference_only(self):
        raw,policy=self.fixture();accepted,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected);self.assertIsNone(accepted[0]['provider_record_date'])
        self.assertFalse(accepted[0]['aggregation_eligibility']['eligible'])
    def test_unknown_date_without_required_review_is_held(self):
        for kind in ('receipt','eligible','disclosure','exclusion'):
            raw,policy=self.fixture();review=policy['quality_reviews'][raw['id']]
            if kind=='receipt':raw.pop('primary_source_capture')
            if kind=='eligible':review['admission']['signal_eligible']=True
            if kind=='disclosure':review['disclosure_review']['publication_date_status']='not_verified'
            if kind=='exclusion':review['admission']['signal_exclusion_reasons']=['other']
            with self.subTest(kind=kind):self.assertFalse(normalize([raw],policy,DAY)[0])
    def test_exact_html_document_recheck_and_changed_page(self):
        from tests.test_poll_html_evidence import HTMLEvidenceTests, HTML
        import hashlib
        test=HTMLEvidenceTests();entry=test.entry()
        entry['documents']=[{'url':entry['documents'][0]['url'],'format':'reviewed_html_document_v1','sha256':hashlib.sha256(HTML).hexdigest()}]
        rows,receipts=test.merge(entry)
        self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')
        rows,receipts=test.merge(entry,HTML.replace(b'51',b'52'))
        self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
        with self.assertRaises(ValueError):test.merge(entry,approved=False)
