from copy import deepcopy
import unittest
from election_watch.live_polls import normalize, summarize
from election_watch.poll_quality import answer_correction_fingerprint, review_fingerprint
from test_live_polls import POLICY, DAY, RID, poll


class AnswerCorrectionTests(unittest.TestCase):
    def fixture(self):
        raw = poll(pollster='Fixture primary', url='https://example.org/toplines.pdf')
        raw['answers'][0]['pct'] = 58
        policy = deepcopy(POLICY)
        expected = {'id':raw['id'],'race_id':RID,'pollster_group':'fixture',
            'field_start':raw['start_date'],'field_end':raw['end_date'],
            'population':raw['population'],'sample_n':raw['sample_size'],
            'answers':[{'name':'Kathy Hochul','pct':48,'party':'DEM'},
                       {'name':'Bruce Blakeman','pct':44,'party':'REP'}]}
        review={'reviewed_on':DAY,'snapshot_sha256':review_fingerprint(expected),
            'sources':[raw['url']],'primary_toplines':{'Kathy Hochul':48,'Bruce Blakeman':44},
            'disclosure_review':{'mode':'SYNTHETIC TEST ONLY'},'limitations_ko':'SYNTHETIC TEST ONLY',
            'provider_answer_correction':{'provider_snapshot_sha256':answer_correction_fingerprint(raw),
                'overrides':{'Kathy Hochul':48},'basis_ko':'SYNTHETIC TEST ONLY'},
            'admission':{'pollster':raw['pollster'],'provider_url':raw['url'],'group':'fixture',
                'methodology_url':raw['url'],'source_role':'pollster_primary','signal_eligible':False,
                'signal_exclusion_reasons':['party_commissioned_reference']}}
        policy['quality_reviews']={raw['id']:review}
        return raw,policy,review

    def test_primary_answer_used_with_original_value_and_reference_only(self):
        raw,policy,_=self.fixture(); original=deepcopy(raw)
        accepted,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected);self.assertEqual(raw,original)
        self.assertEqual(accepted[0]['answers'][0]['pct'],48)
        self.assertEqual(accepted[0]['provider_answer_correction']['provider_values'],{'Kathy Hochul':58})
        self.assertEqual(summarize(accepted,policy['races'][RID],DAY,7)['pollster_count'],0)

    def test_changed_provider_record_requires_new_review(self):
        for field,value in [('sample_size',601),('url','https://example.org/changed.pdf'),
                            ('sponsors',['Changed']),('end_date','2026-09-24')]:
            raw,policy,_=self.fixture();raw[field]=value
            accepted,rejected=normalize([raw],policy,DAY)
            self.assertFalse(accepted)
            self.assertEqual(rejected[0]['reason'],'provider_answer_correction_snapshot_changed')

    def test_every_answer_requires_primary_review(self):
        raw,policy,review=self.fixture();review['primary_toplines'].pop('Bruce Blakeman')
        self.assertFalse(normalize([raw],policy,DAY)[0])

    def test_correction_cannot_rename_or_invent_a_candidate(self):
        raw,policy,review=self.fixture();review['provider_answer_correction']['overrides']={'New Candidate':48}
        self.assertFalse(normalize([raw],policy,DAY)[0])

    def test_overrides_and_uncorrected_answers_must_match_primary(self):
        for edit in ('override','unchanged'):
            raw,policy,review=self.fixture()
            if edit=='override':review['provider_answer_correction']['overrides']['Kathy Hochul']=49
            else:review['primary_toplines']['Bruce Blakeman']=43
            self.assertFalse(normalize([raw],policy,DAY)[0])

    def test_primary_values_need_valid_percentages_and_primary_role(self):
        for value in [float('nan'),True,-1,110]:
            raw,policy,review=self.fixture();review['primary_toplines']['Kathy Hochul']=value
            self.assertFalse(normalize([raw],policy,DAY)[0])
        raw,policy,review=self.fixture();review['admission']['source_role']='aggregator'
        self.assertFalse(normalize([raw],policy,DAY)[0])

    def test_future_review_and_changed_normalized_snapshot_are_rejected(self):
        for field,value in [('reviewed_on','2027-01-01'),('snapshot_sha256','0'*64)]:
            raw,policy,review=self.fixture();review[field]=value
            self.assertFalse(normalize([raw],policy,DAY)[0])

    def test_correction_does_not_relax_candidate_matching(self):
        raw,policy,review=self.fixture();policy['races'][RID]['required_candidates']=['New Nominee','Bruce Blakeman']
        self.assertFalse(normalize([raw],policy,DAY)[0])
