import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from election_watch.asset_prune import prune, stale, unretained

H = lambda c: c * 16


def put(public, rel, obj):
    path = public / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


class AssetPruneTest(unittest.TestCase):
    def test_keeps_index_side_roots_previous_generation_and_fixed_names(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            f = 'usa_election_finance/2026'
            put(p, f'{f}/national-{H("a")}.json', {'states': {'NY': {'data_file': f'{f}/states/NY-{H("b")}.json'}}})
            put(p, f'{f}/states/NY-{H("b")}.json', {'races': [{'data_file': f'{f}/races/NY-house-01-{H("c")}.json'}]})
            put(p, f'{f}/races/NY-house-01-{H("c")}.json', {})
            put(p, f'{f}/races/NY-house-02-{H("d")}.json', {})  # only the live polls board points here
            put(p, f'{f}/national-{H("e")}.json', {})  # previous generation
            put(p, f'{f}/national-{H("f")}.json', {})  # two generations old
            put(p, f'{f}/governor_context_inputs_v1.json', {})  # fixed-name script input
            put(p, 'usa_election_finance_index_v1.json', {'cycles': {'2026': {'national_file': f'{f}/national-{H("a")}.json'}}})
            put(p, 'usa_election_live_polls_v1.json', {'races': {'x': {'finance_file': f'{f}/races/NY-house-02-{H("d")}.json'}}})
            previous = {'cycles': {'2026': {'national_file': f'{f}/national-{H("e")}.json'}}}
            self.assertEqual(stale(p, 'usa_election_finance', [previous]), [f'{f}/national-{H("f")}.json'])
            self.assertEqual(list(unretained(p)), [f'{f}/national'])
            prune(p, 'usa_election_finance', [previous])
            self.assertEqual(unretained(p), {})
            self.assertTrue((p / f'{f}/governor_context_inputs_v1.json').exists())
            self.assertTrue((p / f'{f}/races/NY-house-02-{H("d")}.json').exists())

    def test_state_scope_leaves_other_states(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            e = 'usa_election_state_evidence/2026'
            for name in (f'NY-{H("1")}', f'CA-{H("2")}'):
                put(p, f'{e}/{name}.json', {})
            put(p, 'usa_election_state_evidence_index_v1.json', {'states': {}})
            self.assertEqual(prune(p, 'usa_election_state_evidence', prefixes={'NY'}), [f'{e}/NY-{H("1")}.json'])
            self.assertTrue((p / f'{e}/CA-{H("2")}.json').exists())

    def test_unparseable_root_refuses_to_guess(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            put(p, f'usa_superpac/2026/NY-{H("1")}.json', {})
            (p / 'broken.json').write_text('{"usa_superpac/2026/NY-' + H('1'))
            with self.assertRaises(ValueError):
                prune(p, 'usa_superpac')
            self.assertTrue((p / f'usa_superpac/2026/NY-{H("1")}.json').exists())


if __name__ == '__main__':
    unittest.main()
