import json
import copy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from election_watch.official_results import enhanced_local_results, parse_clarity, parse_enhanced_voting, race_id  # noqa: E402
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

        def text(self, url, **kwargs):
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


class EnhancedExportTest(unittest.TestCase):
    def setUp(self):
        self.export = load('enhanced_voting_az_20261105.json')

    def test_actual_export_maps_all_ten_contests_without_inventing_a_senate_race(self):
        races = parse_enhanced_voting('AZ', self.export)
        self.assertEqual(set(races), {'USA:AZ:governor'} | {f'USA:AZ:house:{i:02d}' for i in range(1, 10)})
        gov = races['USA:AZ:governor']
        self.assertEqual(gov['candidates'][0]['name'], 'Katie Hobbs')
        self.assertEqual(gov['candidates'][0]['votes'], 1235630)
        self.assertEqual(gov['candidates'][0]['pct'], 55.54)
        self.assertEqual(gov['candidates'][0]['source_candidate_id'], '26')
        self.assertEqual(gov['total_votes'], 2224838)
        self.assertEqual((gov['precincts_reporting'], gov['precincts_total']), (1384, 1762))
        self.assertEqual(gov['reporting_unit'], 'precinct')
        self.assertEqual(races['USA:AZ:house:06']['precincts_total'], 248)
        self.assertTrue(all(r['status'] == 'unofficial_count' for r in races.values()))
        self.assertTrue(all('winner' not in r for r in races.values()))
        self.assertEqual({c['party'] for c in gov['candidates']}, {'DEM', 'REP', 'GRN', 'NOL', None})
        self.assertIsNone(race_id('AZ', 'State Representative - District No. 1'))

    def test_root_counties_and_nested_counties_are_alternatives_not_additive(self):
        expected = parse_enhanced_voting('AZ', self.export)
        nested = copy.deepcopy(self.export)
        nested['results']['localResults'] = nested.pop('localResults')
        self.assertEqual(parse_enhanced_voting('AZ', nested), expected)
        both = copy.deepcopy(self.export)
        both['results']['localResults'] = copy.deepcopy(both['localResults'])
        self.assertEqual(parse_enhanced_voting('AZ', both), expected)
        both['results']['localResults'] = []
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            parse_enhanced_voting('AZ', both)

    def test_missing_count_is_not_reported_zero(self):
        self.export['localResults'][0]['ballotItems'][0]['precinctsReporting'] = None
        race = parse_enhanced_voting('AZ', self.export)['USA:AZ:house:09']
        self.assertIsNone(race['precincts_reporting'])
        self.assertEqual(race['precincts_total'], 170)
        for bad in (None, -1, True, 1.5, 'NaN'):
            invalid = copy.deepcopy(self.export)
            invalid['results']['ballotItems'][0]['ballotOptions'][0]['voteCount'] = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'voteCount'):
                parse_enhanced_voting('AZ', invalid)

    def test_duplicate_counties_contests_and_candidates_fail_instead_of_double_counting(self):
        for mutate in (
            lambda d: d['localResults'].append(copy.deepcopy(d['localResults'][0])),
            lambda d: d['results']['ballotItems'].append(copy.deepcopy(d['results']['ballotItems'][0])),
            lambda d: d['results']['ballotItems'][0]['ballotOptions'].append(copy.deepcopy(d['results']['ballotItems'][0]['ballotOptions'][0])),
        ):
            invalid = copy.deepcopy(self.export)
            mutate(invalid)
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                parse_enhanced_voting('AZ', invalid)

    def test_write_in_aggregate_remains_in_denominator_but_cannot_be_named_leader(self):
        for option in self.export['results']['ballotItems'][0]['ballotOptions']:
            option['voteCount'] = 0
        self.export['results']['ballotItems'][0]['ballotOptions'][3]['voteCount'] = 100
        race = parse_enhanced_voting('AZ', self.export)['USA:AZ:house:01']
        self.assertEqual(race['total_votes'], 100)
        self.assertTrue(race['candidates'][0]['is_write_in_aggregate'])
        self.assertIsNone(race['leader'])
        self.assertEqual(race['candidates'][0]['pct'], 100)


class EnhancedBuildTest(unittest.TestCase):
    CONFIG = {'cycle': 2026, 'election_date': '2026-11-03', 'sources': [
        {'state': 'AZ', 'kind': 'enhanced_voting', 'url': 'https://example.test/results.json',
         'expected_result_name': 'Arizona', 'authority_ko': '주 선거 당국'}]}

    class Fake:
        def __init__(self, data):
            self.data = data

        def text(self, url, **kwargs):
            return json.dumps(self.data)

    def setUp(self):
        self.export = load('enhanced_voting_az_20261105.json')
        self.known = set(parse_enhanced_voting('AZ', self.export))

    def test_publication_date_and_provenance_are_kept_separately_from_fetch_time(self):
        doc = collect.build(self.CONFIG, self.Fake(self.export), self.known, None)
        receipt = doc['sources'][0]
        self.assertEqual(receipt['status'], 'ok')
        self.assertEqual(receipt['county_rows'], 15)
        self.assertEqual(len(receipt['document_sha256']), 64)
        self.assertEqual(doc['races']['USA:AZ:governor']['source_published_at'], self.export['createdAt'])

    def test_invalid_empty_older_or_different_election_response_preserves_last_good(self):
        first = collect.build(self.CONFIG, self.Fake(self.export), self.known, None)
        original = copy.deepcopy(first)
        for change in (
            lambda d: d.update(electionDate='2024-11-05'),
            lambda d: d['results'].update(name='Different state'),
            lambda d: d.update(createdAt='2026-11-04T00:00:00Z'),
            lambda d: d.update(createdAt='2099-11-05T00:00:00Z'),
            lambda d: d['results'].update(ballotItems=[]),
            lambda d: d['results']['ballotItems'].pop(),
            lambda d: d['results']['ballotItems'][0]['ballotOptions'][0].update(voteCount=None),
        ):
            bad = copy.deepcopy(self.export)
            change(bad)
            doc = collect.build(self.CONFIG, self.Fake(bad), self.known, first)
            self.assertEqual(doc['sources'][0]['status'], 'failed')
            self.assertEqual(doc['sources'][0]['published_at'], first['sources'][0]['published_at'])
            self.assertEqual(doc['sources'][0]['fetched_at'], first['sources'][0]['fetched_at'])
            self.assertIn('attempted_at', doc['sources'][0])
            self.assertEqual(doc['races'], {rid: dict(r, stale=True) for rid, r in first['races'].items()})
        self.assertEqual(first, original)

    def test_zero_and_downward_count_corrections_are_valid_not_automatic_winners(self):
        first = collect.build(self.CONFIG, self.Fake(self.export), self.known, None)
        corrected = copy.deepcopy(self.export)
        corrected['results']['ballotItems'][0]['ballotOptions'][0]['voteCount'] = 0
        doc = collect.build(self.CONFIG, self.Fake(corrected), self.known, first)
        self.assertEqual(doc['sources'][0]['status'], 'ok')
        race = doc['races']['USA:AZ:house:01']
        self.assertEqual(next(c for c in race['candidates'] if c['source_candidate_id'] == '2')['votes'], 0)
        self.assertNotIn('stale', race)
        self.assertNotIn('winner', race)

    def test_previous_other_election_is_never_carried_forward(self):
        with self.assertRaisesRegex(ValueError, 'different election'):
            collect.build(self.CONFIG, self.Fake(self.export), self.known,
                          {'cycle': 2024, 'election_date': '2024-11-05'})


class SourceConfigTest(unittest.TestCase):
    def test_direct_json_failure_does_not_issue_a_second_browser_request(self):
        fetcher = collect.Fetcher()
        fetcher.rendered = Mock()
        with patch.object(collect.urllib.request, 'urlopen', side_effect=TimeoutError('slow')):
            with self.assertRaisesRegex(ValueError, 'no browser retry'):
                fetcher.text('https://example.test/results.json', render_fallback=False)
        fetcher.rendered.assert_not_called()

    def test_independent_sources_are_loaded_without_changing_shared_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'config.json'
            path.write_text(json.dumps(BuildTest.CONFIG))
            sources = root / 'states'
            sources.mkdir()
            data = dict(EnhancedBuildTest.CONFIG['sources'][0], cycle=2026, election_date='2026-11-03')
            (sources / 'AZ.json').write_text(json.dumps(data))
            merged = collect.load_config(path, sources)
            self.assertEqual([s['state'] for s in merged['sources']], ['IA', 'GA', 'AZ'])
            self.assertEqual(json.loads(path.read_text()), BuildTest.CONFIG)
            for updates in ({'state': 'GA'}, {'cycle': 2024}, {'election_date': '2026-08-04'}):
                (sources / 'AZ.json').write_text(json.dumps(dict(data, **updates)))
                with self.assertRaises(ValueError):
                    collect.load_config(path, sources)
            (sources / 'AZ.json').unlink()
            (sources / 'GA.json').write_text(json.dumps(dict(data, state='GA')))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                collect.load_config(path, sources)


if __name__ == '__main__':
    unittest.main()
