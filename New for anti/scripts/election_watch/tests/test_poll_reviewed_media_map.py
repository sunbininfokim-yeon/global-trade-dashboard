import copy
from datetime import datetime, timezone
import unittest

from apply_reviewed_media_map import apply
from election_watch.media_calls import check, resolve_reviewed_party_call


class ReviewedCallMapTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, tzinfo=timezone.utc)
        self.rid = 'USA:PA:governor'
        self.review = {'schema': 'usa_reviewed_public_media_map_v1', 'cycle': 2026,
            'election_date': '2026-11-03', 'publisher': 'AP',
            'method': 'manual_review_of_public_map_win_labels_only',
            'source_url': 'https://interactives.apelections.org/election-results/assets/apnews/embeds/ge-bop-map/index.html',
            'reviewed_at': '2026-11-05T12:00:00Z', 'calls': [{'race_id': self.rid, 'party': 'DEM'}]}
        self.race = {'election_date': '2026-11-03', 'office': 'governor', 'poll_type': 'governor',
            'candidates': {'Josh Shapiro': {'party': 'DEM'}, 'Stacy Garrity': {'party': 'REP'}},
            'ballot_review': {'source_url': 'https://example.test/ballot', 'reviewed_on': '2026-10-30'}}
        self.board = {self.rid: self.race}
        self.ratings = {'offices': {'governor': {'races': [{'race_id': self.rid}]}}}
        self.previous = {'schema': 'usa_election_media_calls_v1', 'cycle': 2026, 'calls': []}

    def run_apply(self, review=None, board=None, previous=None):
        return apply(review or self.review, board or self.board, previous or self.previous, self.ratings, {}, self.now)

    def test_unique_party_candidate_resolves_with_evidence_and_replay_is_idempotent(self):
        self.race['candidates']['J. Shapiro'] = {'party': 'DEM', 'canonical_name': 'Josh Shapiro'}
        out, held = self.run_apply()
        self.assertFalse(held)
        c = out['calls'][0]
        self.assertEqual(c['winner'], 'Josh Shapiro')
        self.assertIsNone(c['called_at'])
        self.assertEqual(c['verified_at'], self.review['reviewed_at'])
        self.assertEqual(out['candidate_identity_sources'][c['winner_resolution_ref']]['source_url'], 'https://example.test/ballot')
        self.assertEqual(self.run_apply(previous=out), (out, []))
        self.assertEqual(self.previous['calls'], [])

    def test_multiple_or_missing_names_are_held_and_never_inferred_from_lead(self):
        self.race['candidates']['Another Democrat'] = {'party': 'DEM'}
        self.race['leader'] = {'name': 'Josh Shapiro', 'party': 'DEM'}
        out, held = self.run_apply()
        self.assertEqual(out['calls'], [])
        self.assertEqual(len(held), 1)
        self.race['candidates'] = {}
        self.assertEqual(len(self.run_apply()[1]), 1)

    def test_wrong_election_or_unreviewed_candidate_is_held(self):
        for updates in ({'election_date': '2024-11-05'}, {'poll_type': 'primary'}, {'ballot_review': {}}):
            race = dict(self.race, **updates)
            out, held = self.run_apply(board={self.rid: race})
            self.assertFalse(out['calls'])
            self.assertEqual(len(held), 1)

    def test_nga_fallback_requires_explicit_existing_full_identity_contract(self):
        self.race.pop('ballot_review')
        c = self.race['candidates']['Josh Shapiro']
        c.update(identity_source_url='https://www.nga.org/governors/elections/',
                 identity_basis='NGA_general_candidate_section_full_name_party_office_cycle')
        self.assertEqual(resolve_reviewed_party_call(self.race, 'DEM')[0], 'Josh Shapiro')
        c['identity_basis'] = 'poll_name_only'
        with self.assertRaises(ValueError):
            resolve_reviewed_party_call(self.race, 'DEM')

    def test_no_source_scope_lead_duplicate_or_future_review_is_accepted(self):
        bad = [dict(self.review, publisher='Unknown'), dict(self.review, reviewed_at='2099-11-05T12:00:00Z'),
               dict(self.review, reviewed_at='2026-11-03T12:00:00Z'),
               dict(self.review, calls=[dict(self.review['calls'][0], status='leading')]),
               dict(self.review, calls=self.review['calls'] * 2)]
        for review in bad:
            with self.assertRaises(ValueError):
                self.run_apply(review=review)

    def test_direct_article_call_is_preserved_and_party_conflict_is_rejected(self):
        previous, _ = self.run_apply()
        c = previous['calls'][0]
        c.update(source_url='https://apnews.com/article/direct', verified_at='2026-11-04T12:00:00Z')
        previous['updated_at'] = '2026-11-05T16:00:00Z'
        out, _ = self.run_apply(previous=previous)
        self.assertEqual(out['calls'][0], c)
        self.assertEqual(out['updated_at'], previous['updated_at'])
        bad = copy.deepcopy(self.review)
        bad['calls'][0]['party'] = 'REP'
        with self.assertRaises(ValueError):
            self.run_apply(review=bad, previous=previous)
        previous['candidate_identity_sources'] = {}
        self.assertTrue(check(previous, self.ratings, {}, self.now))


if __name__ == '__main__':
    unittest.main()
