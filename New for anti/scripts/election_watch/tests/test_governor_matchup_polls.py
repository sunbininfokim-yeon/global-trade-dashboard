from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from election_watch.governor_matchups import parse, apply_matchups, apply_ballot_reviews, URL
from election_watch.superpac import SourceError
from build_superpac import atomic_json
from build_superpac_map import build, candidate_cards
from refresh_live_polls import main as refresh_polls


def panel(state, year=2026, names=('Test Democrat (D)', 'Test Republican (R)')):
    return f'''<div data-original-id="US-{state}" class="igm-map-content">
    <h3><a href="https://ballotpedia.org/{state}_gubernatorial_election,_{year}">{state}🡭</a></h3>
    <p>Primary Date: June 2, {year}</p><p>General Election Candidates</p>
    <ul>{''.join('<li>'+name+'</li>' for name in names)}</ul></div>'''


class GovernorMatchupTests(unittest.TestCase):
    def test_official_ballot_review_fills_held_source_and_preserves_candidate_source(self):
        held = parse(panel('SC', names=('Named Person (D)', 'Primary Runoff Winner (R)')),
                     2026, ['SC'], '2026-10-07')
        nominees = parse(panel('SC'), 2026, ['SC'], '2026-10-07')['contests']['SC']['candidates']
        source = 'https://vrems.scvotes.sc.gov/Candidate/CandidateSearch?electionId=22596'
        for c in nominees:
            c['source_url'] = source
            c['registration_status'] = 'official_general_ballot_listing'
        reviews = {'schema': 'usa_governor_ballot_reviews_v1', 'cycle': 2026, 'reviewed_on': '2026-10-07',
            'contests': {'SC': {'state': 'SC', 'election_date': '2026-11-03', 'source_url': source,
                'source_role': 'state_election_agency', 'evidence_note_ko': 'Active general ballot listing',
                'candidates': nominees}}}
        combined = apply_ballot_reviews(held, reviews, '2026-10-07')
        self.assertEqual(combined['coverage']['held_states'], [])
        self.assertEqual(held['coverage']['held_states'], ['SC'])
        policy = apply_matchups({'cycle': 2026, 'races': {}, 'states': []}, combined, '2026-10-07')
        self.assertEqual(policy['races']['USA:SC:governor']['governor_roster']['source_url'], source)
        self.assertEqual(apply_ballot_reviews(combined, reviews, '2026-10-07'), combined)
        for field, value in (('cycle', 2024), ('reviewed_on', '2026-10-08')):
            invalid = deepcopy(reviews)
            invalid[field] = value
            with self.assertRaises(SourceError):
                apply_ballot_reviews(held, invalid, '2026-10-07')
        invalid = deepcopy(reviews)
        invalid['contests']['SC']['state'] = 'NC'
        with self.assertRaises(SourceError):
            apply_ballot_reviews(held, invalid, '2026-10-07')

    def test_only_current_state_panels_not_past_results_or_territories(self):
        data = parse(panel('CA') + panel('CA', 2022) + panel('GU'), 2026, ['CA'], '2026-10-07')
        self.assertEqual(set(data['contests']), {'CA'})
        self.assertEqual(data['coverage']['reviewed_matchup_count'], 1)
        self.assertEqual(data['contests']['CA']['candidates'][0]['registration_status'],
                         'reported_general_ballot_not_state_certification')

    def test_placeholder_and_incomplete_source_hold_whole_state(self):
        data = parse(panel('OK', names=('Named Person (D)', 'August 25 Primary Runoff Winner (R)')),
                     2026, ['OK'], '2026-10-07')
        self.assertEqual(data['coverage']['held_states'], ['OK'])
        self.assertEqual(data['contests']['OK']['candidates'], [])
        data = parse(panel('OK', names=('Named Person (D)',)), 2026, ['OK'], '2026-10-07')
        self.assertEqual(data['contests']['OK']['status'], 'review_required')

    def test_changed_universe_duplicate_state_or_name_fail_closed(self):
        for value, states in ((panel('CA'), ['CA', 'NY']), (panel('CA') * 2, ['CA']),
                              (panel('CA', names=('Same Name (D)', 'Same Name (R)')), ['CA'])):
            with self.assertRaises(SourceError):
                parse(value, 2026, states, '2026-10-07')

    def test_registry_alias_requires_full_name_party_and_keeps_id(self):
        registry = {'NY': [{'candidate_id': 'NY:official:1', 'name': 'Kathy C. Hochul',
            'reported_name_aliases': ['Kathy Hochul'], 'party': 'DEM'}]}
        data = parse(panel('NY', names=('Gov. Kathy Hochul (D)', 'Bruce Blakeman (R)')),
                     2026, ['NY'], '2026-10-07', registry)
        self.assertEqual(data['contests']['NY']['candidates'][0]['candidate_id'], 'NY:official:1')
        data = parse(panel('NY', names=('K. Hochul (D)', 'Bruce Blakeman (R)')),
                     2026, ['NY'], '2026-10-07', registry)
        self.assertNotEqual(data['contests']['NY']['candidates'][0]['candidate_id'], 'NY:official:1')

    def test_reviewed_multi_candidate_matchup_not_reduced_to_two_parties(self):
        data = parse(panel('AK', names=('First Name (R)', 'Second Name (D)', 'Third Name (R)', 'Fourth Name (I)')),
                     2026, ['AK'], '2026-10-07')
        policy = apply_matchups({'cycle': 2026, 'races': {}, 'states': []}, data, '2026-10-07')
        self.assertEqual(len(policy['races']['USA:AK:governor']['required_candidates']), 4)
        self.assertEqual(policy['races']['USA:AK:governor']['schedule_status'], 'reported_general_matchup')

    def test_existing_reviewed_matchup_conflicts_fail_not_silent_replacement(self):
        data = parse(panel('CA'), 2026, ['CA'], '2026-10-07')
        policy = apply_matchups({'cycle': 2026, 'races': {}, 'states': []}, data, '2026-10-07')
        other = deepcopy(data)
        other['contests']['CA']['candidates'][0]['name'] = 'Someone Else'
        with self.assertRaises(SourceError):
            apply_matchups(policy, other, '2026-10-07')
        with self.assertRaises(SourceError):
            apply_matchups(policy, data, '2026-10-06')

    def test_nominee_roster_does_not_claim_spending_coverage_or_zero(self):
        data = parse(panel('CA'), 2026, ['CA'], '2026-10-07')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = build(root, governor_rosters=data)
            national = json.loads((root / catalog['cycles']['2026']['national_file']).read_text())
            state = json.loads((root / national['states']['CA']['data_file']).read_text())
            entry = next(r for r in state['races'] if r['office'] == 'governor')
            race = json.loads((root / entry['data_file']).read_text())
            self.assertEqual(race['status'], 'unsupported')
            self.assertEqual(race['candidate_roster_status'], 'reported_general_matchup')
            self.assertEqual(len(race['candidates']), 2)
            self.assertIsNone(race['totals_by_category']['state_independent_spender_unclassified']['support_cents'])

    def test_reviewed_aliases_survive_map_candidate_cards(self):
        entry = {'candidate_id': 'NY:1', 'name': 'Kathy C. Hochul',
                 'reported_name_aliases': ['Kathy Hochul'], 'party': 'DEM'}
        self.assertEqual(candidate_cards([], [entry])[0]['reported_names'], ['Kathy C. Hochul', 'Kathy Hochul'])

    def test_corrupt_scope_or_coverage_rejected_before_map_publication(self):
        valid = parse(panel('CA'), 2026, ['CA'], '2026-10-07')
        for field, value in (('state', 'NY'), ('office', 'S'), ('election_year', 2024)):
            data = deepcopy(valid)
            data['contests']['CA']['candidates'][0][field] = value
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(SourceError):
                    build(Path(tmp), governor_rosters=data)
                self.assertFalse((Path(tmp) / 'usa_election_finance_index_v1.json').exists())
        data = deepcopy(valid)
        data['coverage']['reviewed_matchup_count'] = 2
        with self.assertRaises(SourceError):
            apply_matchups({'cycle': 2026, 'races': {}, 'states': []}, data, '2026-10-07')

    def test_future_roster_reports_failed_health_and_preserves_last_poll_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / 'policy.json'
            roster = root / 'roster.json'
            output = root / 'usa_election_live_polls_v1.json'
            atomic_json(policy, {'cycle': 2026, 'races': {}, 'states': []})
            atomic_json(roster, parse(panel('CA'), 2026, ['CA'], '2026-10-07'))
            atomic_json(output, {'previous_valid_snapshot': True})
            with patch('refresh_live_polls.apply_watchlist', side_effect=lambda value, _: value), \
                 patch('refresh_live_polls.apply_priorities', side_effect=lambda value, *args: value), \
                 patch('sys.argv', ['refresh_live_polls.py', '--policy', str(policy),
                       '--governor-matchups', str(roster), '--output', str(output), '--as-of', '2026-10-06']):
                self.assertEqual(refresh_polls(), 1)
            self.assertEqual(json.loads(output.read_text()), {'previous_valid_snapshot': True})
            health = json.loads((root / 'usa_election_live_polls_status_v1.json').read_text())
            self.assertEqual(health['status'], 'error')
            self.assertEqual(health['error_type'], 'SourceError')


if __name__ == '__main__':
    unittest.main()
