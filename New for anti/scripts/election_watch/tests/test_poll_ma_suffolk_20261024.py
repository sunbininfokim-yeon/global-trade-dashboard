"""Finite MA Suffolk review: original import, official three-ticket field and replay."""
from copy import deepcopy
from pathlib import Path
import unittest

from election_watch.polls import read
from election_watch.live_polls import normalize, summarize
from election_watch.state_inputs import packets
from publish_state_packets import rebuild

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / 'public/data'
DAY = '2026-10-24'
RID = 'USA:MA:governor'
ID = 'gov202suf418414b7'


class MASuffolkReviewTests(unittest.TestCase):
    def setUp(self):
        self.audit = read(ROOT / 'research/2026/MA/suffolk-governor-20261024.json')
        self.raw = deepcopy(self.audit['provider_record'])
        # Historical evidence is finite; later daily publications are not its fixture.
        self.policy = read(ROOT / 'config/usa_polls/live_2026.json')
        self.policy['races'] = {RID: deepcopy(self.audit['reviewed_race_policy'])}
        self.policy['quality_reviews'] = {ID: deepcopy(self.audit['primary_review'])}

    def test_exact_primary_values_and_dates_without_mutating_import(self):
        original = deepcopy(self.raw)
        obs, held = normalize([self.raw], self.policy, DAY)
        self.assertFalse(held)
        row = obs[0]
        self.assertEqual([a['pct'] for a in row['answers']], [58.6, 36.0, 2.0])
        self.assertEqual([a['party'] for a in row['answers']], ['DEM', 'REP', 'IND'])
        self.assertEqual((row['field_start'], row['field_end'], row['sample_n']),
                         ('2026-10-14', '2026-10-18', 500))
        self.assertEqual(row['provider_metadata_correction']['provider_values'],
                         {'end_date': '2026-10-17'})
        self.assertEqual(row['provider_answer_correction']['provider_values'], {'Maura Healy': 59.0})
        self.assertEqual(self.raw, original)
        self.assertTrue(row['aggregation_eligibility']['eligible'])
        self.assertIsNone(row['source_quality']['accuracy_grade'])

    def test_corrected_field_end_controls_seven_and_fourteen_day_windows(self):
        obs, _ = normalize([self.raw], self.policy, DAY)
        race = self.policy['races'][RID]
        for window in (7, 14):
            self.assertEqual(summarize(obs, race, DAY, window)['party'], 'DEM')
        self.assertEqual(summarize(obs, race, '2026-10-25', 7)['status'], 'no_recent_poll')
        self.assertEqual(summarize(obs, race, '2026-10-25', 14)['party'], 'DEM')

    def test_three_governors_and_exact_spelling_alias_not_lieutenant_governors(self):
        race = self.policy['races'][RID]
        self.assertEqual(set(race['required_candidates']),
                         {'Maura Healey', 'Michael Minogue', 'Andrea James'})
        self.assertEqual(race['candidates']['Maura Healy']['canonical_name'], 'Maura Healey')
        self.assertEqual(race['candidates']['Andrea James']['party'], 'IND')
        for name in ('Driscoll', 'Oliver', 'Kittredge'):
            self.assertNotIn(name, race['candidates'])
        self.assertEqual(race['ballot_competition']['general_unopposed'], False)

    def test_changed_provider_values_methods_or_sponsor_need_review(self):
        for field, value in [('sample_size', 501), ('end_date', '2026-10-18'),
                             ('sponsors', []), ('internal', True), ('population', 'rv')]:
            raw = {**deepcopy(self.raw), field: value}
            obs, held = normalize([raw], self.policy, DAY)
            self.assertFalse(obs, field)
            self.assertEqual(held[0]['reason'], 'primary_review_provider_metadata_changed')
        raw = deepcopy(self.raw)
        raw['answers'][0]['pct'] = 60
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_future_review_and_incomplete_candidate_field_are_not_accepted(self):
        self.assertFalse(normalize([self.raw], self.policy, '2026-10-23')[0])
        raw = deepcopy(self.raw)
        raw['answers'] = raw['answers'][:2]
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_preserved_transport_and_source_receipts_are_not_redated(self):
        packet = next(p for p in packets() if p['state'] == 'MA')
        capture = packet['capture']
        self.assertEqual(capture['primary_records'], self.audit['previous_primary_records'])
        self.assertEqual(capture['receipt']['primary_supplement_receipts'],
                         self.audit['previous_primary_supplement_receipts'])
        self.assertEqual(capture['receipt']['prior_capture_receipt']['captured_at'],
                         self.audit['previous_capture_fetched_at'])
        self.assertTrue(set(self.audit['previous_provider_ids']) <=
                        {r['id'] for r in capture['provider_records']})
        self.assertEqual([r['fetched_at'][:10] for r in self.audit['source_fetch_receipts']],
                         ['2026-10-23', '2026-10-23'])
        self.assertTrue(self.audit['new_provider_collection'])
        self.assertFalse(self.audit['new_pdf_download'])
        self.assertFalse(self.audit['new_finance_collection'])

    def test_replay_preserves_other_states_root_dates_and_history_and_is_idempotent(self):
        packet = next(p for p in packets() if p['state'] == 'MA')
        old = read(PUBLIC / 'usa_election_live_polls_v1.json')
        history = read(PUBLIC / 'usa_election_poll_history_2026.json')
        new, archive = rebuild(old, history, [packet], PUBLIC)
        for rid, race in old['races'].items():
            if race['state'] != 'MA':
                self.assertEqual(new['races'][rid], race, rid)
                if rid in history['races']:
                    self.assertEqual(archive['races'][rid], history['races'][rid], rid)
        for key in ('as_of', 'fetched_at'):
            self.assertEqual(new[key], old[key])
        self.assertEqual(new['house_poll_focus'], old['house_poll_focus'])
        row = next(o for o in new['races'][RID]['observations'] if o['id'] == ID)
        self.assertEqual(row['field_end'], '2026-10-18')
        self.assertEqual(row['answers'][0]['pct'], 58.6)
        reference = next(o for o in new['races'][RID]['observations']
                         if o['id'] == 'gov202mas4d65da75')
        self.assertFalse(reference['aggregation_eligibility']['eligible'])
        self.assertIn('publisher_identified_release_review_pending',
                      reference['aggregation_eligibility']['reasons'])
        twice, twice_history = rebuild(new, archive, [packet], PUBLIC)
        self.assertEqual(twice, new)
        self.assertEqual(twice_history, archive)


if __name__ == '__main__':
    unittest.main()
