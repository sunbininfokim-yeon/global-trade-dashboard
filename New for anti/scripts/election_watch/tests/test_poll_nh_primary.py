"""NH question samples, reference variants and exact nominee joins."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.poll_targets import apply_targets

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/usa_polls'
PUBLIC = ROOT.parent.parent / 'public/data'
DAY = '2026-10-09'


def read(path):
    return json.loads(path.read_text())


class NewHampshireEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.policy = apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),
            read(ROOT/'config/governor_matchups/2026.json'), DAY),
            read(CONFIG/'targets_2026.json'), read(CONFIG/'ballot_reviews_2026.json'), DAY)
        self.policy['quality_reviews'] = read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/NH-primary-20261009.json')
        self.rows = [r['provider_record'] for r in self.audit['records']]

    def test_question_samples_not_total_sample_for_senate(self):
        observations, rejected = normalize(self.rows, self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual([o['sample_n'] for o in observations], [1519, 1520])
        self.assertEqual([[a['pct'] for a in o['answers']] for o in observations], [[51, 43], [40, 49]])
        self.assertTrue(all(o['source_quality']['verification_level'] == 'primary_toplines_checked'
                            for o in observations))
        self.assertTrue(all(o['source_quality']['accuracy_grade'] is None for o in observations))
        self.assertTrue(all(o['field_end'] == '2026-10-05' for o in observations))

    def test_allocated_senate_reference_never_votes_with_initial_ballot(self):
        observations, _ = normalize(self.rows, self.policy, DAY)
        senate, governor = observations
        self.assertFalse(senate['aggregation_eligibility']['eligible'])
        self.assertIn('undecided_preference_allocation_reference', senate['aggregation_eligibility']['reasons'])
        for window in [7, 14]:
            signal = summarize([senate], self.policy['races'][senate['race_id']], DAY, window)
            self.assertIsNone(signal['party'])
            self.assertEqual(signal['reference_poll_count'], 1)
            signal = summarize([governor], self.policy['races'][governor['race_id']], DAY, window)
            self.assertEqual(signal['party'], 'REP')
            self.assertEqual(signal['pollster_count'], 1)
            self.assertEqual(signal['evidence_quality']['coverage'], 'single_source')

    def test_nonresponse_and_minor_candidates_not_zero_filled(self):
        observations, _ = normalize(self.rows, self.policy, DAY)
        senate, governor = observations
        for row in observations:
            self.assertEqual(len(row['answers']), 2)
            disclosure = row['source_quality']['disclosure_review']
            self.assertTrue(disclosure['other_option_available'])
            self.assertTrue(disclosure['minor_candidates_not_named'])
            self.assertIsNone(disclosure['initial_ballot_before_candidate_information'])
            self.assertEqual(disclosure['unreported_question_count'], 5)
        self.assertTrue(senate['source_quality']['disclosure_review']['includes_undecided_preference_allocation'])
        self.assertIsNone(governor['source_quality']['disclosure_review']['includes_undecided_preference_allocation'])
        self.assertEqual(governor['source_quality']['disclosure_review']['non_candidate_responses']['undecided'], 11)

    def test_changed_record_needs_new_review(self):
        for field, value in [('sample_size', 1520), ('end_date', '2026-10-06'),
                             ('url', 'https://example.org/new'), ('sponsors', ['new sponsor'])]:
            row = copy.deepcopy(self.rows[0])
            row[field] = value
            self.assertFalse(normalize([row], self.policy, DAY)[0])

    def test_known_name_error_held_but_new_correct_api_poll_can_join(self):
        raw = copy.deepcopy(next(r for r in self.audit['provider_records_reviewed']
                                 if r['id'] == 'us-202unic08cf0d0'))
        observations, rejected = normalize([raw], self.policy, DAY)
        self.assertFalse(observations)
        self.assertIn('NH01_provider_Stephany_name_typo', rejected[0]['reason'])
        raw['id'] = 'future-correct-name-fixture'
        for answer in raw['answers']:
            if answer['choice'] == 'Stephany Shaheen':
                answer['choice'] = 'Stefany Shaheen'
        observations, rejected = normalize([raw], self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(observations[0]['race_id'], 'USA:NH:house:01')
        self.assertEqual(observations[0]['source_quality']['verification_level'], 'partial')
        self.assertIn('primary_values_rechecked', observations[0]['source_quality']['missing_fields'])

    def test_secondary_roster_never_certified_or_unopposed(self):
        roster = self.audit['roster_review']
        self.assertEqual(roster['candidate_count'], 11)
        self.assertEqual(roster['coverage'], 'reviewed_secondary_only_official_portal_403')
        self.assertFalse(roster['unopposed_verified_races'])
        federal = read(ROOT/'config/federal_matchups/2026.json')['races']
        nh = [r for r in federal.values() if r['state'] == 'NH']
        self.assertEqual(len(nh), 3)
        self.assertEqual(sum(len(r['candidates']) for r in nh), 8)
        self.assertTrue(all(r['status'] == 'reported_general_matchup' for r in nh))
        self.assertTrue(all(r['source_role'] == 'reviewed_secondary_nominee_listing' for r in nh))
        self.assertEqual(self.policy['races']['USA:NH:senate']['general_from'], '2026-09-09')
        self.assertTrue(roster['non_election_senate_class_3_not_added'])

    def test_constitution_fec_reported_party_not_republican(self):
        reviews = read(CONFIG/'state_finance_identities_2026.json')['races']['USA:NH:senate']
        minor = next(r for r in reviews if r['candidate_id'] == 'S2NH00223')
        self.assertEqual(minor['party'], 'CST')
        self.assertEqual(minor['reported_party_mapping']['public_party'], 'CST')
        self.assertIn('RNC', minor['reported_party_mapping']['fec_parties'])
        raw = next(r for r in self.audit['provider_records_reviewed'] if r['id'] == 'us-202uni02a0a46f')
        obs, rejected = normalize([raw], self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(next(a['party'] for a in obs[0]['answers'] if a['name'] == 'Edmond Laplante'), 'CST')

    def merge(self, body=b'%PDF-fixture', rows=None, url=None):
        entry = copy.deepcopy(next(e for e in read(CONFIG/'primary_supplements_2026.json')['records']
                                   if e['record']['id'] == self.rows[0]['id']))
        entry['documents'][0]['sha256'] = hashlib.sha256(b'%PDF-fixture').hexdigest()
        if url:
            entry['documents'][0]['url'] = url
        class Response:
            status = 200
            def geturl(self): return entry['documents'][0]['url']
            def read(self, *args): return body
            def __enter__(self): return self
            def __exit__(self, *args): return False
        return merge_primary_supplements(rows or [],
            {'schema': 'usa_reviewed_primary_poll_supplements_v1', 'cycle': 2026, 'records': [entry]},
            DAY, ['NH'], lambda *args, **kwargs: Response())

    def test_only_finite_reviewed_shared_cdn_document_allowed(self):
        with self.assertRaises(ValueError):
            self.merge(url='https://d3nkl3psvxxpe9.cloudfront.net/documents/unreviewed-new-nh.pdf')

    def test_document_change_keeps_original_date_and_values(self):
        rows, receipts = self.merge(body=b'%PDF-changed')
        self.assertEqual(receipts[0]['status'], 'carried_forward_reference_only')
        self.assertEqual(rows[0]['end_date'], '2026-10-05')
        self.assertEqual(rows[0]['answers'], self.rows[0]['answers'])

    def test_later_api_same_wave_is_one_record_or_conflict(self):
        later = copy.deepcopy(self.rows[0]); later['id'] = 'later-api-fixture'
        rows, receipts = self.merge(rows=[later])
        self.assertEqual(len(rows), 1)
        self.assertEqual(receipts[0]['provider_duplicate_ids'], ['later-api-fixture'])
        later['sample_size'] = 1520
        with self.assertRaises(ValueError): self.merge(rows=[later])

    def test_blocked_finance_never_becomes_zero_or_new_fec_collection(self):
        access = read(PUBLIC/'usa_governor_source_access/2026/NH.json')
        self.assertEqual(access['status'], 'source_access_blocked')
        self.assertFalse(access['financial_data_collected'])
        self.assertFalse(access['candidate_amounts_available'])
        self.assertFalse(self.audit['finance_review']['federal_FEC_recollected'])
        self.assertTrue(all(e['role'] != 'current_public_export' for e in access['endpoints']))

    def test_state_receipt_matches_its_own_access_probe(self):
        index = read(PUBLIC/'usa_election_state_evidence_index_v1.json')
        state = read(PUBLIC/index['states']['NH']['data_file'])
        access = read(PUBLIC/'usa_governor_source_access/2026/NH.json')
        self.assertEqual(state['live_capture_receipt']['governor_source_checked_at'], access['checked_at'])
        self.assertEqual(state['work_status'], 'live_poll_sources_reviewed_finance_blocked')
        self.assertEqual([state['office_coverage'][o]['scheduled_races']
                          for o in ['house', 'senate', 'governor']], [2, 1, 1])


if __name__ == '__main__':
    unittest.main()
