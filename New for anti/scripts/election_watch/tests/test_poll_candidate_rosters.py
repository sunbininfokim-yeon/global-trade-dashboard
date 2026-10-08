"""Synthetic parser inputs are never published as candidates or poll data."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from election_watch.candidate_coverage import candidate_coverage
from election_watch.federal_matchups import parse_michigan_general, merge_ballot_reviews, attach_matchups

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent.parent / 'public/data'
DAY = '2026-10-08'


def michigan():
    text = ['Michigan Department of State', 'Official Candidate Listing', 'General Election',
            'Tuesday, November 3, 2026', 'U.S. Senate 6 Year Term (1) Position',
            'Democratic Party Senate, Dem 04/14/2026 Petitions',
            'Republican Party Senate, Rep 04/17/2026 Petitions']
    for n in range(1, 14):
        suffix = 'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'
        text += [f'{n}{suffix} District Representative in Congress 2 Year Term (1) Position',
                 f'Democratic Party District{n}, Dem 04/20/2026 Petitions',
                 f'Republican Party District{n}, Rep 04/20/2026 Petitions']
        if n == 1:
            text += ['Green Party Independent, Other 08/03/2026 Convention',
                     'DISQ No Party Affiliation Rejected, Person 07/16/2026 Petitions']
    text += ['1st District State Senator 4 Year Term (1) Position',
             'Democratic Party WRONG, Legislature 04/20/2026 Petitions']
    return '\n'.join(text)


class CandidateRosterTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / 'config/federal_matchups/2026.json').read_text())
        self.ballots = json.loads((ROOT / 'config/usa_polls/ballot_reviews_2026.json').read_text())
        self.board = json.loads((PUBLIC / 'elections_board_v1.json').read_text())
        self.polls = json.loads((PUBLIC / 'usa_election_live_polls_v1.json').read_text())
        self.catalog = json.loads((ROOT / 'config/usa_polls/targets_2026.json').read_text())

    def test_official_parser_separates_federal_state_and_disqualified_candidates(self):
        rows = parse_michigan_general(michigan(), DAY)
        self.assertEqual(len(rows), 14)
        first = rows['USA:MI:house:01']
        self.assertEqual(len(first['candidates']), 3)
        self.assertEqual(first['excluded_candidates'][0]['agency_status'], 'DISQ')
        self.assertNotIn('Legislature WRONG', [c['name'] for r in rows.values() for c in r['candidates']])
        self.assertEqual(first['status'], 'reported_general_matchup')

    def test_wrong_cycle_primary_unknown_status_and_incomplete_universe_hold(self):
        for raw in (michigan().replace('General Election', 'Primary Election'),
                    michigan().replace('November 3, 2026', 'November 5, 2024'),
                    michigan().replace('DISQ', 'UNREVIEWED'),
                    michigan().replace('13th District Representative', '14th District Representative')):
            with self.subTest(raw=raw[:90]), self.assertRaises(ValueError):
                parse_michigan_general(raw, DAY)

    def test_agency_field_replaces_reported_nominee_without_turning_listing_into_result(self):
        merged = merge_ballot_reviews(self.snapshot, self.ballots, DAY)
        frost = merged['races']['USA:FL:house:10']
        self.assertEqual(len(frost['candidates']), 1)
        self.assertTrue(frost['official_general_unopposed'])
        self.assertIn('REP', frost['absent_parties'])
        self.assertEqual(frost['status'], 'reported_general_matchup')
        self.assertNotIn('winner', frost)
        # Older reported MI04 must not restore the wrong former field.
        self.assertEqual(merged['races']['USA:MI:house:04']['candidates'][0]['name'], 'Sean McCann')

    def test_certified_full_ballot_is_not_downgraded_by_reviewed_major_party_field(self):
        merged = merge_ballot_reviews(self.snapshot, self.ballots, DAY)
        self.assertEqual(merged['races']['USA:CA:house:04'], self.snapshot['races']['USA:CA:house:04'])
        broken = deepcopy(self.ballots); broken['reviewed_on'] = '2027-01-01'
        with self.assertRaises(ValueError): merge_ballot_reviews(self.snapshot, broken, DAY)

    def test_50_state_display_audit_reconciles_offices_without_counting_nonelection_states(self):
        audit = candidate_coverage(self.board, self.polls, self.catalog, DAY)
        self.assertEqual(len(audit['states']), 50)
        self.assertEqual([audit['totals'][o]['expected'] for o in ('house', 'senate', 'governor')], [435, 35, 36])
        for totals in audit['totals'].values():
            self.assertEqual(totals['available'] + totals['missing'], totals['expected'])
        self.assertEqual(audit['states']['NY']['offices']['senate']['status'], 'not_on_2026_ballot')
        self.assertEqual(audit['states']['MI']['offices']['house']['display_roster'], 13)
        self.assertEqual(audit['states']['MI']['offices']['governor']['races'][0]['source_url'],
                         'https://www.nga.org/governors/elections/')

    def test_michigan_and_unopposed_names_do_not_depend_on_a_poll_feed(self):
        audit = candidate_coverage(self.board, {}, self.catalog, DAY)
        self.assertEqual(audit['states']['MI']['offices']['house']['available'], 13)
        self.assertEqual(audit['states']['FL']['offices']['house']['available'], 28)
        roster = next(c for c in self.board['countries'] if c['iso3'] == 'USA')['ui_ready']['state_drilldown']['states']
        michigan_state = next(s for s in roster if s['id'] == 'MI')
        attached = attach_matchups([{'id': 'MI'}], self.snapshot, DAY, self.ballots)
        self.assertEqual(attached[0]['election_matchups'], michigan_state['election_matchups'])

    def test_incomplete_state_or_apportionment_catalog_does_not_publish_false_coverage(self):
        broken = deepcopy(self.catalog); del broken['states']['WY']
        with self.assertRaises(ValueError): candidate_coverage(self.board, self.polls, broken, DAY)


if __name__ == '__main__': unittest.main()
