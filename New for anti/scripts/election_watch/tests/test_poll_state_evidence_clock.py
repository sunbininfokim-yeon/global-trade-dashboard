"""Exercise the state CLI below the projection subprocess boundary."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from election_watch.polls import read
import refresh_state_evidence as cli


class StateEvidenceClockTests(unittest.TestCase):
    def run_cli(self, later_review, catalog):
        public = Path(cli.PUBLIC)
        original = read(public / 'usa_election_live_polls_v1.json')
        before = deepcopy(original)
        built = []

        def load(path):
            value = read(path)
            if catalog == 'federal' and path == cli.ROOT / 'config/federal_matchups/2026.json':
                value['races']['USA:WA:house:03']['reviewed_on'] = later_review
            if catalog == 'governor' and path == cli.ROOT / 'config/governor_matchups/2026.json':
                value['contests']['CA']['ballot_reviewed_on'] = later_review
            return value

        def publish(public, plan, selected, builder, generated_at):
            self.assertEqual(selected, [('D', 'CT')])
            built.append(builder('CT', 'D'))
            return {'processed_state_count': 1, 'last_processed_state': 'CT',
                    'errors': {}, 'deep_source_review_remaining': []}

        with patch.object(cli, 'read', side_effect=load), \
             patch.object(cli, 'publish_states', side_effect=publish) as writer, \
             patch('sys.argv', ['state-evidence', '--state', 'CT', '--as-of', original['as_of']]), \
             patch('sys.stdout', new=StringIO()):
            if later_review > datetime.now(timezone.utc).date().isoformat():
                with self.assertRaisesRegex(ValueError, 'future catalog review'):
                    cli.main()
                writer.assert_not_called()
                return
            self.assertEqual(cli.main(), 0)
        state = built[0]
        self.assertEqual(state['checked_as_of'], original['as_of'])
        self.assertEqual(state['source_dates']['poll_as_of'], original['as_of'])
        self.assertEqual(state['source_dates']['poll_fetched_at'], original['fetched_at'])
        self.assertEqual(state['live_capture_receipt'], original.get('state_captures', {}).get('CT'))
        self.assertTrue(all(r['polling']['windows_checked_as_of'] == original['as_of']
                            for r in state['races']))
        self.assertEqual(read(public / 'usa_election_live_polls_v1.json'), before)

    def test_later_other_state_federal_review_keeps_old_ct_poll_and_receipt_clock(self):
        self.run_cli('2026-10-13', 'federal')

    def test_later_other_state_governor_review_keeps_old_ct_poll_and_receipt_clock(self):
        self.run_cli('2026-10-13', 'governor')

    def test_actual_future_review_never_writes_state_evidence(self):
        future = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        for catalog in ('federal', 'governor'):
            with self.subTest(catalog=catalog):
                self.run_cli(future, catalog)


if __name__ == '__main__':
    unittest.main()
