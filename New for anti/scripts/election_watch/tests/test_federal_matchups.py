import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from election_watch.federal_matchups import attach_matchups, parse_ca_house, parse_reported_field, validate_snapshot
from publish_federal_matchups import publish


class FederalMatchupTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / 'config/federal_matchups/2026.json').read_text())

    def test_certified_ca_parser_requires_general_ballot_and_complete_universe(self):
        text = 'General Election - November 3, 2026\n' + '\n'.join(
            f'United States Representative District {n}\nDem Name Democratic\nRep Name Republican\n'
            for n in range(1, 53)) + 'State Senate District 1\nState Candidate Democratic'
        rows = parse_ca_house(text, 'https://example.org/general.pdf', '2026-10-07')
        self.assertEqual(len(rows), 52)
        self.assertEqual(len(rows['USA:CA:house:52']['candidates']), 2)
        with self.assertRaises(ValueError):
            parse_ca_house(text.replace('General Election', 'Primary Election'), 'https://example.org/primary', '2026-10-07')
        with self.assertRaises(ValueError):
            parse_ca_house(text.replace('District 52', 'District 53'), 'https://example.org/general', '2026-10-07')

    def test_reported_field_does_not_import_unresolved_candidates_or_unreviewed_ratings(self):
        header = ['State', 'Incumbent / Seat Status', 'Democratic Candidate', 'Republican Candidate', 'Cook Rating']
        names = {f'State {n}': f'{n:02d}' for n in range(35)}
        def html(dem):
            rows = [header] + [[state, 'Incumbent', dem, 'Rep Name', 'Toss-Up'] for state in names]
            return '<table>' + ''.join('<tr>' + ''.join(f'<td>{x}</td>' for x in row) + '</tr>' for row in rows) + '</table>'
        rows = parse_reported_field(html('Dem Name'), 'senate', names, 'https://example.org/report', '2026-10-07')
        self.assertEqual(len(rows), 35)
        self.assertNotIn('rating', next(iter(rows.values())))
        with self.assertRaises(ValueError):
            parse_reported_field(html('Primary winner TBD'), 'senate', names, 'https://example.org/report', '2026-10-07')

    def test_real_roster_preserves_same_party_and_independent_ballots(self):
        validate_snapshot(self.snapshot, '2026-10-07')
        races = self.snapshot['races']
        self.assertEqual(sum(r['office'] == 'senate' for r in races.values()), 35)
        self.assertEqual({c['party'] for c in races['USA:CA:house:04']['candidates']}, {'DEM'})
        self.assertIn('REP', races['USA:CA:house:04']['absent_parties'])
        self.assertEqual({c['party'] for c in races['USA:CA:house:06']['candidates']}, {'DEM', 'IND'})
        self.assertEqual(len(races['USA:AK:senate']['candidates']), 4)

    def test_invalid_snapshot_does_not_overwrite_last_good_board(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'board.json'
            source = Path(temp) / 'snapshot.json'
            dest.write_text(json.dumps({'countries': [{'iso3': 'USA', 'ui_ready': {'state_drilldown': {'states': []}}}]}))
            before = dest.read_bytes()
            changes = [lambda d: d.update(reviewed_on='2027-01-01'),
                       lambda d: d['races']['USA:AK:senate']['candidates'].append(copy.deepcopy(d['races']['USA:AK:senate']['candidates'][0])),
                       lambda d: d['races']['USA:AK:senate'].update(district='01'),
                       lambda d: d['races']['USA:CA:house:01'].update(absent_parties=['DEM']),
                       lambda d: d['races']['USA:AK:senate'].update(source_url='https://user:secret@example.org'),
                       lambda d: d['incumbents']['S001198'].update(election_years=[2014, 2014])]
            for change in changes:
                data = copy.deepcopy(self.snapshot); change(data); source.write_text(json.dumps(data))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    publish(source, dest, '2026-10-07')
                self.assertEqual(dest.read_bytes(), before)

    def test_publication_is_idempotent_and_preserves_other_countries_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'board.json'
            other = {'iso3': 'KOR', 'ui_ready': {'untouched': True}}
            board = {'as_of': 'original', 'countries': [other, {'iso3': 'USA', 'ui_ready': {'state_drilldown': {'states': [{'id': 'CA'}]}}}]}
            dest.write_text(json.dumps(board))
            publish(ROOT / 'config/federal_matchups/2026.json', dest, '2026-10-07')
            once = dest.read_bytes()
            publish(ROOT / 'config/federal_matchups/2026.json', dest, '2026-10-07')
            after = json.loads(dest.read_text())
            self.assertEqual(dest.read_bytes(), once)
            self.assertEqual(after['countries'][0], other)
            self.assertEqual(after['as_of'], 'original')

    def test_term_count_uses_senate_elections_not_house_service_or_appointments(self):
        history = self.snapshot['incumbents']
        self.assertEqual(history['S001198']['election_years'], [2014, 2020])
        self.assertEqual(len(history['C001035']['election_years']), 5)
        self.assertEqual(len(history['C001056']['election_years']), 4)
        self.assertEqual(history['M001244']['election_years'], [])


if __name__ == '__main__':
    unittest.main()
