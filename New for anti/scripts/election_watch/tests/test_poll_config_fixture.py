"""Published state joins must not borrow an unrelated state's review date."""
from copy import deepcopy
import unittest
from tests.poll_config_fixture import published_snapshot_day


class PublishedFixtureClockTests(unittest.TestCase):
    def test_newer_state_capture_survives_older_national_anchor(self):
        board = {'as_of': '2026-10-11', 'fetched_at': '2026-10-15T00:00:00Z',
                 'races': {'USA:NC:senate': {'as_of': '2026-10-14'},
                           'USA:WA:house:03': {'as_of': '2026-10-13'}}}
        original = deepcopy(board)
        self.assertEqual(published_snapshot_day(board, '2026-10-13'), '2026-10-14')
        self.assertEqual(board, original)

    def test_legacy_and_empty_races_keep_the_national_observation_clock(self):
        for races in ({}, {'USA:NC:senate': {}}):
            self.assertEqual(published_snapshot_day(
                {'as_of': '2026-10-11', 'races': races}, '2026-10-09'), '2026-10-11')

    def test_newer_catalog_is_validated_without_changing_observations(self):
        board = {'as_of': '2026-10-11', 'races': {'USA:NC:senate': {'as_of': '2026-10-14'}}}
        self.assertEqual(published_snapshot_day(board, '2026-10-15'), '2026-10-15')
        self.assertEqual(board['races']['USA:NC:senate']['as_of'], '2026-10-14')


if __name__ == '__main__': unittest.main()
