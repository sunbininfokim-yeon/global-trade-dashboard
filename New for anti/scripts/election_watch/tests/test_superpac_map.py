from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from build_superpac import publish, atomic_json
from build_superpac_map import build, candidate_cards
from election_watch.superpac import build_snapshot, SourceError
from election_watch.superpac_schedule import collection_plan, reporting_cycle
from election_watch.governor_wa import collect, METADATA
from test_superpac import record


class ScheduleTests(unittest.TestCase):
    def test_future_rollover_and_corrections(self):
        self.assertEqual(reporting_cycle(date(2026, 11, 4)), 2026)
        self.assertEqual(reporting_cycle(date(2027, 1, 1)), 2028)
        self.assertEqual(collection_plan(date(2027, 1, 1)), [2028, 2026])
        self.assertEqual(collection_plan(date(2028, 12, 1)), [2028, 2026])
        self.assertEqual(collection_plan(date(2029, 2, 1)), [2030, 2028])

    def test_weekly_gate_and_manual_cycle(self):
        self.assertEqual(collection_plan(date(2026, 9, 7), 'weekly'), [])
        self.assertEqual(collection_plan(date(2026, 9, 6), 'weekly'), [2026, 2024])
        self.assertEqual(collection_plan(date(2026, 9, 7), 'weekly', True, 2024), [2024])
        with self.assertRaises(ValueError): collection_plan(date(2026, 9, 6), cycle=2027)


class MapTests(unittest.TestCase):
    def test_join_phase_no_spend_and_statewide_scope(self):
        roster = [{'candidate_id': 'H6AK00002', 'office': 'H', 'state': 'AK', 'district': '00', 'name': 'NO SPEND', 'party': 'DEM'}]
        snap = build_snapshot(2026, roster, [record(), record(sub_id='2', election_type='G2026', support_oppose_indicator='O')])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(root / 'congressional_districts/USA/AK.json', {'source': '119th test geometry', 'features': [{'properties': {'state_id': 'AK', 'district': '00'}}]})
            publish(snap, root)
            catalog = build(root)
            state = json.loads((root / json.loads((root / catalog['cycles']['2026']['national_file']).read_text())['states']['AK']['data_file']).read_text())
            summary = next(r for r in state['races'] if r['office'] == 'house')
            race = json.loads((root / summary['data_file']).read_text())
            self.assertEqual(race['race_id'], 'USA:AK:house:00')
            self.assertTrue(race['map_join']['existing_geometry_found'])
            self.assertFalse(race['map_join']['boundary_election_match_verified'])
            candidate = next(c for c in race['candidates'] if c['candidate_id'] == 'H6AK00001')
            self.assertEqual(candidate['election_types']['P2026']['totals_by_category']['super_pac']['oppose_cents'], 0)
            self.assertEqual(candidate['election_types']['G2026']['totals_by_category']['super_pac']['oppose_cents'], 1025)
            missing = next(c for c in race['candidates'] if c['candidate_id'] == 'H6AK00002')
            self.assertIsNone(missing['totals_by_category']['super_pac']['support_cents'])
            governor = next(r for r in state['races'] if r['office'] == 'governor')
            self.assertEqual(governor['status'], 'unsupported')
            self.assertEqual(governor['map_join']['scope'], 'statewide')
            self.assertIsNone(governor['totals_by_category']['super_pac']['support_cents'])

    def test_candidate_names_share_id_and_negative_adjustment(self):
        snap = build_snapshot(2026, [], [record(), record(sub_id='2', candidate_name='CHANGED NAME', expenditure_amount='-0.25', candidate_party='DEM')])
        candidates = candidate_cards(snap['spending'], [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['totals_by_category']['super_pac']['support_cents'], 1000)
        self.assertEqual(candidates[0]['reported_parties'], ['DEM', 'REP'])

    def test_reuse_files_when_only_check_time_changes(self):
        snap = build_snapshot(2026, [], [record()])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publish(snap, root)
            first = build(root)
            snap['generated_at'] = '2026-09-07T00:00:00+00:00'
            publish(snap, root)
            second = build(root)
            self.assertEqual(first['cycles']['2026']['national_file'], second['cycles']['2026']['national_file'])
            self.assertEqual(len(list((root / 'usa_superpac/2026').glob('AK*'))), 1)
            self.assertEqual(second['cycles']['2026']['source_status']['federal']['last_success_at'], snap['generated_at'])

    def test_failed_build_keeps_last_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publish(build_snapshot(2026, [], [record()]), root)
            build(root)
            catalog_path = root / 'usa_election_finance_index_v1.json'
            old = catalog_path.read_bytes()
            with patch('build_superpac_map.immutable', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): build(root)
            self.assertEqual(catalog_path.read_bytes(), old)


class WashingtonTests(unittest.TestCase):
    def metadata(self, revision=1):
        return {'rowsUpdatedAt': revision, 'columns': [{'fieldName': 'report_number', 'description': 'amendments: original report records are not included'}]}

    def row(self, **changes):
        row = {'id': '1.entity', 'origin': 'C6.3 - Identified Entities', 'candidate_office': 'Governor',
            'report_type': 'Independent Expenditure', 'for_or_against': 'For', 'candidate_candidacy_id': '11', 'candidate_entity_id': '12',
            'sponsor_entity_id': '13', 'candidate_name': 'TEST', 'sponsor_name': 'TEST SPONSOR',
            'report_date': '2024-09-01', 'election_year': '2024', 'report_number': '14', 'portion_of_amount': '12.34',
            'total_cycle': '9999999', 'total_this_report': '999999', 'url': {'url': 'https://my.pdc.wa.gov/test'}}
        row.update(changes)
        return row

    def test_candidate_portion_only_no_electioneering_double_count(self):
        rows = [self.row(), self.row(id='2.entity', report_type='Electioneering Communication')]
        payload = collect(2024, fetch=lambda url: self.metadata() if url == METADATA else rows)
        self.assertEqual(len(payload['spending']), 1)
        self.assertEqual(payload['spending'][0]['support_cents'], 1234)
        self.assertEqual(payload['spending'][0]['election_type'], 'UNKNOWN')
        self.assertEqual(payload['spending'][0]['category'], 'state_independent_spender_unclassified')

    def test_revision_change_and_duplicates_fail(self):
        for rows, revisions in [([self.row()], [1, 2]), ([self.row(), self.row()], [1, 1])]:
            metadata_calls = iter(revisions)
            with self.assertRaises(SourceError):
                collect(2024, fetch=lambda url: self.metadata(next(metadata_calls)) if url == METADATA else rows)

    def test_wa_only_cycle_does_not_claim_federal_coverage(self):
        payload = collect(2024, fetch=lambda url: self.metadata() if url == METADATA else [self.row()])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(root / 'usa_governor_finance/2024/WA.json', payload)
            catalog = build(root)
            self.assertEqual(catalog['cycles']['2024']['source_status']['federal']['status'], 'not_collected')
            self.assertEqual(json.loads((root / catalog['cycles']['2024']['national_file']).read_text())['states']['WA']['governor_status'], 'partial')
            self.assertIsNone(json.loads((root / catalog['cycles']['2024']['national_file']).read_text())['states']['CA']['totals_by_office']['governor']['super_pac']['support_cents'])

if __name__ == '__main__': unittest.main()
