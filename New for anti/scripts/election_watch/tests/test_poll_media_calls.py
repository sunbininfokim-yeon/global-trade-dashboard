"""Election-night media calls: hand-reviewed, unofficial, never contradicting a certified result."""
from datetime import datetime, timezone
from pathlib import Path
import json
import unittest
from election_watch.media_calls import check

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1]/'public/data'
class MediaCallsFileTests(unittest.TestCase):
    def setUp(self):
        self.ratings = json.loads((PUBLIC/'usa_election_ratings_review_v1.json').read_text())
        self.now = datetime(2026, 11, 5, tzinfo=timezone.utc)

    def test_published_file_is_valid(self):
        data = json.loads((PUBLIC/'usa_election_media_calls_v1.json').read_text())
        results = json.loads((ROOT/'config/usa_polls/results_2026.json').read_text())
        certified = {r.get('race_id'): r for r in results.get('results', [])}
        self.assertEqual(check(data, self.ratings, certified, datetime.now(timezone.utc)), [])

    def test_rules_reject_bad_calls(self):
        ok = {'race_id': 'USA:PA:governor', 'status': 'called', 'winner': 'Josh Shapiro', 'party': 'DEM',
              'called_by': ['AP'], 'called_at': '2026-11-04T01:00:00Z', 'source_url': 'https://apnews.com/x'}
        base = {'schema': 'usa_election_media_calls_v1', 'cycle': 2026}
        self.assertEqual(check({**base, 'calls': [ok]}, self.ratings, {}, self.now), [])
        bad = [{**ok, 'race_id': 'USA:PA:senate'},            # no 2026 Senate race in PA
               {**ok, 'called_at': '2026-11-03T20:00:00Z'},    # before polls close
               {**ok, 'party': 'GOP'}, {**ok, 'called_by': []}, {**ok, 'source_url': 'http://x'}]
        for c in bad:
            self.assertTrue(check({**base, 'calls': [c]}, self.ratings, {}, self.now), c)
        self.assertTrue(check({**base, 'calls': [ok, ok]}, self.ratings, {}, self.now))
        self.assertTrue(check({**base, 'calls': [ok]}, self.ratings, {'USA:PA:governor': {'party': 'REP'}}, self.now))
        self.assertEqual(check({**base, 'calls': [{**ok, 'status': 'runoff', 'winner': None, 'party': None}]},
                               self.ratings, {}, self.now), [])


if __name__ == '__main__':
    unittest.main()
