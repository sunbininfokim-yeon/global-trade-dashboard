"""Unregistered releases require evidence; reference polls never vote in signals."""
from copy import deepcopy
import unittest
from election_watch.live_polls import normalize, summarize, build_live, poll_history
from election_watch.poll_quality import review_fingerprint
from test_live_polls import POLICY, DAY, RID, poll


class SourceAdmissionTests(unittest.TestCase):
    def release(self, eligible=True, historical=False):
        raw = poll(pollster='Unregistered local research', url='https://example.org/release.pdf')
        if historical:
            raw.update(start_date='2026-08-20', end_date='2026-08-22', created_at='2026-08-23')
        policy = deepcopy(POLICY)
        normalized = {'id': raw['id'], 'race_id': RID, 'pollster_group': 'local_fixture',
                      'field_start': raw['start_date'], 'field_end': raw['end_date'],
                      'population': raw['population'], 'sample_n': raw['sample_size'],
                      'answers': [{'name': a['choice'], 'pct': a['pct'],
                                   'party': policy['races'][RID]['candidates'][a['choice']]['party']}
                                  for a in raw['answers']]}
        review = {'reviewed_on': DAY, 'snapshot_sha256': review_fingerprint(normalized),
                  'sources': [raw['url']], 'primary_toplines': {'Kathy Hochul': 48, 'Bruce Blakeman': 44},
                  'disclosure_review': {'mode': 'SYNTHETIC TEST ONLY'},
                  'limitations_ko': 'SYNTHETIC TEST ONLY',
                  'admission': {'pollster': raw['pollster'], 'provider_url': raw['url'],
                                'group': 'local_fixture', 'methodology_url': raw['url'],
                                'source_role': 'pollster_primary', 'signal_eligible': eligible,
                                'signal_exclusion_reasons': [] if eligible else ['incomparable_question'],
                                'allow_historical_reference': historical}}
        policy['quality_reviews'] = {raw['id']: review}
        return raw, policy

    def test_unregistered_pollster_with_reviewed_release_can_join(self):
        raw, policy = self.release()
        rows, rejected = normalize([raw], policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(rows[0]['source_admission'], 'reviewed_release')
        self.assertEqual(rows[0]['source_quality']['verification_level'], 'primary_toplines_checked')
        self.assertEqual(summarize(rows, policy['races'][RID], DAY, 7)['status'], 'single_poll_lead')

    def test_just_a_source_url_does_not_claim_verification(self):
        raw, _ = self.release()
        rows, rejected = normalize([raw], POLICY, DAY)
        self.assertFalse(rows)
        self.assertEqual(rejected[0]['reason'], 'pollster_not_selected')
        self.assertEqual(rejected[0]['source_url'], raw['url'])
        self.assertEqual(rejected[0]['verification'], 'not_accepted_not_verified')

    def test_publisher_identity_hold_cannot_be_bypassed_by_values_or_registered_pollster(self):
        raw,policy=self.release()
        policy['excluded_records']={raw['id']:'publisher_identity_unverified'}
        policy['pollsters'][raw['pollster']]={'group':'local_fixture','hosts':['example.org'],
                                             'methodology_url':raw['url']}
        rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(rejected[0]['reason'],'publisher_identity_unverified')

    def test_review_is_bound_to_pollster_url_and_values(self):
        for changes, reason in [({'pollster': 'Different institute'}, 'source_review_changed'),
                                ({'url': 'https://example.org/different.pdf'}, 'source_review_changed'),
                                ({'answers': [{'choice': 'Kathy Hochul', 'pct': 49},
                                              {'choice': 'Bruce Blakeman', 'pct': 44}]},
                                 'quality_review_snapshot_changed')]:
            raw, policy = self.release()
            rows, rejected = normalize([{**raw, **changes}], policy, DAY)
            self.assertFalse(rows)
            self.assertEqual(rejected[0]['reason'], reason)

    def test_release_review_does_not_whitelist_shared_document_host(self):
        raw, policy = self.release()
        raw.update(id='new', url='https://example.org/unrelated.pdf')
        rows, rejected = normalize([raw], policy, DAY)
        self.assertFalse(rows)
        self.assertEqual(rejected[0]['reason'], 'pollster_not_selected')

    def test_incomplete_or_future_review_cannot_admit_unknown_source(self):
        for field, value, reason in [('disclosure_review', {}, 'incomplete_source_review'),
                                     ('reviewed_on', '2026-10-01', 'future_quality_review')]:
            raw, policy = self.release()
            policy['quality_reviews'][raw['id']][field] = value
            rows, rejected = normalize([raw], policy, DAY)
            self.assertFalse(rows)
            self.assertEqual(rejected[0]['reason'], reason)

    def test_reference_values_are_kept_but_do_not_create_a_poll_lead(self):
        raw, policy = self.release(eligible=False)
        board = build_live([raw], policy, {'schema': 'usa_confirmed_results_v1', 'results': []},
                           DAY, DAY, 'test')
        race = board['races'][RID]
        self.assertEqual(len(race['observations']), 1)
        window = race['windows']['7']
        self.assertEqual(window['reference_ids'], [raw['id']])
        self.assertEqual(window['included_ids'], [])
        self.assertEqual(window['pollster_count'], 0)
        self.assertIsNone(window['party'])
        self.assertEqual(board['coverage']['reference_only_observations'], 1)

    def test_historical_matchup_does_not_become_current_general_signal(self):
        raw, policy = self.release(eligible=False, historical=True)
        rows, rejected = normalize([raw], policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(rows[0]['display_group'], 'historical_matchup_reference')
        self.assertFalse(rows[0]['aggregation_eligibility']['eligible'])
        policy['quality_reviews'][raw['id']]['admission']['signal_eligible'] = True
        rows, rejected = normalize([raw], policy, DAY)
        self.assertFalse(rows)
        self.assertEqual(rejected[0]['reason'], 'outside_reviewed_general_period')

    def test_reference_never_displaces_latest_eligible_poll(self):
        raw, policy = self.release(eligible=False)
        rows, rejected = normalize([raw, poll('eligible', end_date='2026-09-25')], policy, DAY)
        self.assertFalse(rejected)
        window = summarize(rows, policy['races'][RID], DAY, 7)
        self.assertEqual(window['included_ids'], ['eligible'])
        self.assertEqual(window['reference_ids'], [raw['id']])

    def test_source_review_does_not_bypass_party_sample_or_district_checks(self):
        for changes in [{'partisan': 'DEM'}, {'sample_size': None}, {'seat_name': 'NY-18'}]:
            raw, policy = self.release()
            rows, rejected = normalize([{**raw, **changes}], policy, DAY)
            self.assertFalse(rows)
            self.assertEqual(len(rejected), 1)

    def test_party_commissioned_release_requires_bound_reference_only_review(self):
        raw, policy = self.release(eligible=False)
        raw.update(partisan='DEM', sponsors=['Fixture party committee'])
        admission = policy['quality_reviews'][raw['id']]['admission']
        admission.update(allow_partisan_reference=True, reviewed_partisan='DEM',
                         reviewed_sponsors=raw['sponsors'])
        rows, rejected = normalize([raw], policy, DAY)
        self.assertFalse(rejected)
        self.assertIn('party_commissioned_reference', rows[0]['aggregation_eligibility']['reasons'])
        self.assertEqual(summarize(rows, policy['races'][RID], DAY, 7)['pollster_count'], 0)
        for change in [{'sponsors': ['Different sponsor']}, {'partisan': 'REP'}, {'internal': True}]:
            self.assertFalse(normalize([{**raw, **change}], policy, DAY)[0])
        admission['signal_eligible'] = True
        self.assertFalse(normalize([raw], policy, DAY)[0])

    def test_reference_live_list_closes_after_election_and_history_survives(self):
        raw, policy = self.release(eligible=False)
        results = {'schema': 'usa_confirmed_results_v1', 'results': []}
        board = build_live([raw], policy, results, '2026-11-04', DAY, 'test')
        self.assertEqual(board['races'][RID]['observations'], [])
        self.assertEqual(board['races'][RID]['windows']['7']['reference_ids'], [])
        self.assertEqual(len(poll_history([raw], policy, '2026-11-04')['races'][RID]['observations']), 1)
