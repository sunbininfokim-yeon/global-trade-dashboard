import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from election_watch.official_results import parse_clarity, parse_enhanced_voting, race_id  # noqa: E402
import collect_official_results as collect  # noqa: E402

FX = HERE / 'tests' / 'fixtures'
load = lambda name: json.loads((FX / name).read_text(encoding='utf-8'))


class RaceIdTest(unittest.TestCase):
    def test_state_contest_names_map_to_board_races(self):
        self.assertEqual(race_id('GA', 'US Senate'), 'USA:GA:senate')
        self.assertEqual(race_id('CO', 'United States Senator'), 'USA:CO:senate')
        self.assertEqual(race_id('CO', 'Governor / Lieutenant Governor'), 'USA:CO:governor')
        self.assertEqual(race_id('IA', 'Governor and Lt. Governor'), 'USA:IA:governor')
        self.assertEqual(race_id('GA', 'US House of Representatives - District 2'), 'USA:GA:house:02')
        self.assertEqual(race_id('CO', 'Representative to the 120th United States Congress - District 8'), 'USA:CO:house:08')
        self.assertEqual(race_id('IA', 'United States Representative District 1'), 'USA:IA:house:01')
        for other in ('Lieutenant Governor', 'State Senate - District 1', 'State Senator - District 3', 'Secretary of State'):
            self.assertIsNone(race_id('GA', other), other)


class ParseTest(unittest.TestCase):
    def test_clarity_keeps_state_counts_and_drops_write_ins(self):
        races = parse_clarity('IA', load('clarity_ia_summary_20261104.json'))
        senate = races['USA:IA:senate']
        self.assertEqual(senate['precincts_total'], 99)
        self.assertEqual(senate['precincts_reporting'], 7)
        self.assertNotIn('Write-in', [c['name'] for c in senate['candidates']])
        self.assertEqual(senate['candidates'][0]['party'], 'DEM')
        self.assertEqual(senate['leader']['party'], 'DEM')
        self.assertEqual(senate['status'], 'unofficial_count')
        self.assertIn('USA:IA:governor', races)
        self.assertEqual(senate['reporting_unit'], 'county')
        self.assertNotIn(' and ', races['USA:IA:governor']['candidates'][0]['name'], 'running mate dropped')
        co = parse_clarity('CO', load('clarity_co_summary_20261104.json'))
        self.assertEqual(sorted(co), ['USA:CO:governor', 'USA:CO:house:08', 'USA:CO:senate'])
        self.assertEqual({c['party'] for c in co['USA:CO:senate']['candidates']} >= {'DEM', 'REP', 'LIB'}, True, 'LBR maps to LIB')

    def test_enhanced_voting_strips_party_suffix_and_sums_county_precincts(self):
        races = parse_enhanced_voting('GA', load('enhanced_voting_ga_20261104.json'))
        senate = races['USA:GA:senate']
        names = [c['name'] for c in senate['candidates']]
        self.assertIn('Jon Ossoff', names)
        self.assertIn('Mike Collins', names)
        self.assertTrue(next(c for c in senate['candidates'] if c['name'] == 'Jon Ossoff')['incumbent'])
        self.assertEqual(senate['precincts_total'], 18, 'two fixture counties: 6 + 12')
        self.assertEqual(round(sum(c['pct'] for c in senate['candidates'])), 100)
        self.assertNotIn('Secretary of State', [r['contest_name'] for r in races.values()])


class BuildTest(unittest.TestCase):
    CONFIG = {'cycle': 2026, 'election_date': '2026-11-03', 'sources': [
        {'state': 'IA', 'kind': 'clarity', 'base_url': 'https://x.test/IA/1'},
        {'state': 'GA', 'kind': 'enhanced_voting', 'url': 'https://x.test/ga.json'}]}

    class Fake:
        def __init__(self, fail_ga=False):
            self.fail_ga = fail_ga

        def text(self, url):
            if url.endswith('current_ver.txt'):
                return '384570\n'
            if url.endswith('summary.json'):
                return (FX / 'clarity_ia_summary_20261104.json').read_text(encoding='utf-8')
            if self.fail_ga:
                raise TimeoutError('slow')
            return (FX / 'enhanced_voting_ga_20261104.json').read_text(encoding='utf-8')

    def test_only_board_races_are_written(self):
        known = {'USA:IA:senate', 'USA:GA:senate'}
        doc = collect.build(self.CONFIG, self.Fake(), known, None)
        self.assertEqual(sorted(doc['races']), ['USA:GA:senate', 'USA:IA:senate'])
        self.assertTrue(all(s['status'] == 'ok' for s in doc['sources']))
        self.assertTrue(doc['races']['USA:IA:senate']['source_url'].startswith('https://x.test/IA/1/384570/'))

    def test_a_failed_state_keeps_its_last_count_marked_stale(self):
        known = {'USA:IA:senate', 'USA:GA:senate'}
        first = collect.build(self.CONFIG, self.Fake(), known, None)
        second = collect.build(self.CONFIG, self.Fake(fail_ga=True), known, first)
        self.assertEqual(next(s for s in second['sources'] if s['state'] == 'GA')['status'], 'failed')
        self.assertTrue(second['races']['USA:GA:senate']['stale'])
        self.assertNotIn('stale', second['races']['USA:IA:senate'])


if __name__ == '__main__':
    unittest.main()
