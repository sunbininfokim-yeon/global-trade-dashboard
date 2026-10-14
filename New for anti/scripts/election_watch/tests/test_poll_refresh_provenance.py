"""National rebuilds preserve historical state receipts alongside focus data."""
from copy import deepcopy
import unittest
from election_watch.poll_refresh_provenance import retain_state_provenance


class NationalRefreshProvenanceTests(unittest.TestCase):
    def data(self):
        previous = {'schema': 'usa_live_polls_v1', 'cycle': 2026,
            'state_captures': {'VA': {'captured_at': '2026-10-09T01:00:00Z',
                'primary_supplement_receipts': [{'id': 'primary-fixture',
                    'original_reviewed_on': '2026-10-08'}]}},
            'races': {'USA:VA:house:01': {'as_of': '2026-10-09',
                'fetched_at': '2026-10-09T01:00:00Z', 'source_status': 'ok',
                'source_url': 'https://api.votehub.com/polls?subject=2026'}}}
        board = {'schema': 'usa_live_polls_v1', 'cycle': 2026,
            'fetched_at': '2026-10-10T01:00:00Z', 'as_of': '2026-10-10',
            'house_poll_focus': {'race_count': 104},
            'races': {'USA:VA:house:01': {'observations': [{'id': 'fresh-fixture'}]}}}
        history = {'cycle': 2026, 'races': {'USA:VA:house:01': {'observations': []}}}
        return previous, board, history

    def test_fresh_national_data_and_focus_do_not_erase_state_dates(self):
        old, board, history = self.data()
        original = deepcopy(old)
        retain_state_provenance(board, history, old)
        self.assertEqual(board['state_captures'], original['state_captures'])
        self.assertEqual(history['state_captures'], original['state_captures'])
        self.assertEqual(board['fetched_at'], '2026-10-10T01:00:00Z')
        self.assertEqual(board['house_poll_focus']['race_count'], 104)
        self.assertEqual(board['races']['USA:VA:house:01']['observations'][0]['id'], 'fresh-fixture')
        provenance = board['races']['USA:VA:house:01']['state_capture_provenance']
        self.assertEqual(provenance['fetched_at'], '2026-10-09T01:00:00Z')
        self.assertEqual(history['races']['USA:VA:house:01']['state_capture_provenance'], provenance)
        self.assertEqual(old, original)

    def test_repeated_daily_refresh_does_not_retimestamp_state_capture(self):
        old, board, history = self.data()
        retain_state_provenance(board, history, old)
        next_board = deepcopy(board)
        next_board['fetched_at'] = '2026-10-11T01:00:00Z'
        retain_state_provenance(next_board, history, board)
        self.assertEqual(next_board['races']['USA:VA:house:01']['state_capture_provenance'],
                         board['races']['USA:VA:house:01']['state_capture_provenance'])
        self.assertEqual(next_board['state_captures'], old['state_captures'])

    def test_cross_cycle_receipts_are_rejected(self):
        old, board, history = self.data()
        old['cycle'] = 2024
        with self.assertRaisesRegex(ValueError, 'schema/cycle'):
            retain_state_provenance(board, history, old)
