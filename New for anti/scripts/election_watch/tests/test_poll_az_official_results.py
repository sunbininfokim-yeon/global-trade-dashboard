"""The isolated AZ source descriptor must reach the existing official-results output."""
import json
import unittest
from pathlib import Path

import collect_official_results as collect

ROOT = Path(__file__).resolve().parents[1]


class ArizonaSourceTest(unittest.TestCase):
    def test_registered_source_reaches_all_ten_known_races_with_original_counts(self):
        config = collect.load_config()
        sources = {s['state']: s for s in config['sources']}
        self.assertIn('AZ', sources)
        source = sources['AZ']
        self.assertFalse(source['render_fallback'])
        raw = (ROOT / 'tests/fixtures/enhanced_voting_az_20261105.json').read_text()
        expected_url = json.loads(raw)['_fixture_provenance']['url']
        self.assertEqual(source['url'], expected_url)
        known = {'USA:AZ:governor'} | {f'USA:AZ:house:{i:02d}' for i in range(1, 10)}

        class RecordedSource:
            def text(self, url, *, render_fallback):
                if url != expected_url or render_fallback:
                    raise AssertionError('unexpected source or immediate retry')
                return raw

        doc = collect.build(dict(config, sources=[source]), RecordedSource(), known, None)
        self.assertEqual(set(doc['races']), known)
        self.assertEqual(doc['sources'][0]['status'], 'ok')
        self.assertEqual(doc['sources'][0]['county_rows'], 15)
        self.assertEqual(doc['races']['USA:AZ:house:01']['candidates'][0]['votes'], 167807)
        self.assertEqual(doc['races']['USA:AZ:house:06']['candidates'][0]['votes'], 163197)
        self.assertEqual(doc['races']['USA:AZ:governor']['candidates'][0]['name'], 'Katie Hobbs')
        self.assertTrue(all(r['status'] == 'unofficial_count' for r in doc['races'].values()))
        self.assertTrue(all('winner' not in r for r in doc['races'].values()))


if __name__ == '__main__':
    unittest.main()
