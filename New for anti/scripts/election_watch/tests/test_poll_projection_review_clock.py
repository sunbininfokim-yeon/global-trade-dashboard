"""An old published snapshot must not deadlock refresh after a newer state review."""
import sys
from copy import deepcopy
import unittest
from unittest.mock import patch

import refresh_state_evidence as refresh
from election_watch.state_evidence import build_state
import test_poll_state_evidence as fixtures


class ProjectionReviewClockTests(unittest.TestCase):
    def test_actual_oregon_projection_accepts_new_identity_without_redating_polls(self):
        # Production regression: the main runner used its Oct 11 poll snapshot
        # with Oct 14 OR finance identities and stopped before replaying capture.
        polls_path = refresh.PUBLIC/'usa_election_live_polls_v1.json'
        read = refresh.read
        original = deepcopy(read(polls_path))
        original.update(as_of='2026-10-11', fetched_at='2026-10-11T00:16:19.749666+00:00')
        for race in original['races'].values():
            if race['state'] == 'OR':
                race.pop('as_of', None)
                race.pop('fetched_at', None)
        observed = []

        def publish(public, plan, selected, builder, checked_at):
            self.assertEqual(selected, [('C', 'OR')])
            observed.append(builder('OR', 'C'))
            return {'processed_state_count': 1, 'last_processed_state': 'OR',
                    'errors': {}, 'deep_source_review_remaining': []}

        with patch.object(refresh, 'publish_states', side_effect=publish), \
             patch.object(refresh, 'read', side_effect=lambda path: original if path == polls_path else read(path)), \
             patch.object(sys, 'argv', ['refresh_state_evidence', '--state', 'OR',
                                       '--as-of', original['as_of']]):
            self.assertEqual(refresh.main(), 0)
        state = observed[0]
        self.assertEqual(state['checked_as_of'], original['as_of'])
        self.assertGreaterEqual(state['review_checked_as_of'], '2026-10-14')
        self.assertEqual(state['source_dates']['poll_as_of'], original['as_of'])
        self.assertEqual(state['source_dates']['poll_fetched_at'], original['fetched_at'])
        self.assertTrue(all(r['polling']['windows_checked_as_of'] == original['as_of']
                            for r in state['races']))
        self.assertGreater(state['office_coverage']['house']['candidate_id_links'], 0)

    def test_new_audit_keeps_original_windows_and_null_amounts(self):
        fixture = fixtures.StateEvidenceTests(); fixture.setUp()
        inputs = fixture.fixture()
        audit = {'schema': 'usa_governor_finance_audit_v1', 'state': 'AK', 'cycle': 2026,
                 'status': 'collected_normalization_held', 'captured_at': '2026-10-14T01:00:00Z'}
        state = build_state('AK', 'B', fixture.plan, *inputs, '2026-10-08',
                            governor_audits={'AK': audit})
        self.assertEqual(state['review_checked_as_of'], '2026-10-14')
        self.assertEqual(state['checked_as_of'], '2026-10-08')
        self.assertEqual(state['governor_source_route']['audit'], audit)
        self.assertIsNone(state['races'][-1]['finance']['all_reported_candidates']['support_cents'])
        self.assertEqual(state['races'][0]['polling']['fetched_at'], inputs[3]['fetched_at'])

    def test_future_access_receipt_still_blocks_projection(self):
        fixture = fixtures.StateEvidenceTests(); fixture.setUp()
        with self.assertRaisesRegex(ValueError, 'future catalog review'):
            build_state('AK', 'B', fixture.plan, *fixture.fixture(), '2026-10-08',
                        governor_access={'AK': {'checked_at': '2999-10-17T00:00:00Z'}})


if __name__ == '__main__':
    unittest.main()
