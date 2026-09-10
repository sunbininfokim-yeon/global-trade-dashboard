import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
import zipfile
from election_watch.superpac import FecClient, SourceError, build_snapshot, candidates_from_bulk, import_governor, money, normalize
from build_superpac import publish


def record(**overrides):
    row = {'sub_id': '1', 'candidate_id': 'H6AK00001', 'candidate_name': 'TEST CANDIDATE',
           'candidate_office': 'H', 'candidate_office_state': 'AK', 'candidate_office_district': '00',
           'candidate_party': 'REP', 'committee_id': 'C00000001', 'committee': {'committee_type': 'O', 'name': 'TEST COMMITTEE'},
           'election_type': 'P2026', 'expenditure_amount': '10.25', 'support_oppose_indicator': 'S',
           'is_notice': False, 'most_recent': True, 'dissemination_date': '2026-05-01', 'filing_date': '2026-06-01'}
    row.update(overrides)
    return row


class FinanceTests(unittest.TestCase):
    def test_classification_phase_party_separate(self):
        rows = [record(), record(sub_id='2', election_type='G2026', support_oppose_indicator='O'),
                record(sub_id='3', committee={'committee_type': 'V'}), record(sub_id='4', committee={'committee_type': 'I'}),
                record(sub_id='5', candidate_party='DEM'), record(sub_id='6', committee={'committee_type': 'U'})]
        snap = build_snapshot(2026, [], rows)
        self.assertEqual(len(snap['spending']), 6)
        self.assertEqual(snap['summary']['super_pac_support_cents'], 2050)
        self.assertEqual(snap['summary']['super_pac_oppose_cents'], 1025)
        self.assertEqual(snap['summary']['hybrid_pac_support_cents'], 1025)
        self.assertEqual(snap['summary']['single_candidate_ie_support_cents'], 1025)

    def test_notices_memos_amendments_deletions(self):
        snap = build_snapshot(2026, [], [record(), record(), record(sub_id='2', is_notice=True), record(sub_id='3', memo_code='X'), record(sub_id='4', most_recent=False), record(sub_id='5', action_code='D'), record(sub_id='6', most_recent=None)])
        self.assertEqual(snap['summary']['super_pac_support_cents'], 1025)
        self.assertEqual(snap['quality']['included_records'], 1)
        self.assertEqual(snap['status'], 'partial')

    def test_unknown_id_never_name_matched(self):
        snap = build_snapshot(2026, [], [record(candidate_id='')])
        self.assertEqual(snap['spending'], [])
        self.assertEqual(snap['quality']['excluded_records']['unresolved_id'], 1)

    def test_negative_adjustments_and_exact_cents(self):
        self.assertEqual(money('-10.23'), -1023)
        for bad in (None, True, 'NaN', 'Infinity', '0.001'):
            with self.assertRaises(ValueError): money(bad)
        snap = build_snapshot(2026, [], [record(), record(sub_id='2', expenditure_amount='-0.25')])
        self.assertEqual(snap['summary']['super_pac_support_cents'], 1000)

    def test_president_national_and_at_large(self):
        self.assertEqual(normalize(record(), 2026)['district'], '00')
        pres = normalize(record(candidate_office='P', candidate_id='P60000001', candidate_office_state='NH'), 2026)
        self.assertEqual(pres['state'], 'US')
        self.assertIsNone(pres['district'])
        with self.assertRaises(ValueError): normalize(record(candidate_office_district=None), 2026)
        with self.assertRaises(ValueError): normalize(record(candidate_office='G'), 2026)

    def test_equal_amount_distinct_records_not_deduplicated(self):
        snap = build_snapshot(2026, [], [record(), record(sub_id='2')])
        self.assertEqual(snap['summary']['super_pac_support_cents'], 2050)

    def test_roster_includes_candidates_without_spending(self):
        candidates = [{'candidate_id': 'H6AK00001', 'office': 'H', 'state': 'AK'}, {'candidate_id': 'H6AK00002', 'office': 'H', 'state': 'AK'}]
        snap = build_snapshot(2026, candidates, [record()])
        self.assertEqual(len(snap['candidates']), 2)
        self.assertIsNone(snap['coverage']['governor']['AK']['amount_cents'])

    def test_bulk_cycle_filter_preserves_pre_statutory_candidates(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('cn.txt', 'H6AK00001|TEST|REP|2026|AK|H|00|C|N|C00000001|||||\nP80000001|FUTURE|DEM|2028|US|P|00|C|F|C00000002|||||\n')
        result = list(candidates_from_bulk(data.getvalue(), 2026))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['candidate_status'], 'N')

    def test_governor_review_and_scope(self):
        row = dict(source_id='WA:1', candidate_id='WA:C1', candidate_name='TEST', party='DEM', committee_id='WA:P1', committee_name='TEST IE', election_type='P2026', source_url='https://www.pdc.wa.gov/test', classification_source_url='https://www.pdc.wa.gov/test', as_of='2026-09-01', office='governor', state='WA', category='state_independent_expenditure_committee', reviewed=True, is_current=True, direction='support', amount_usd='2.30')
        payload = dict(schema='usa_governor_ie_import_v1', cycle=2026, state='WA', coverage='partial', records=[row])
        snap = import_governor(build_snapshot(2026, [], []), payload)
        self.assertEqual(snap['spending'][0]['support_cents'], 230)
        self.assertEqual(snap['coverage']['governor']['WA']['status'], 'partial')
        row['office'] = 'mayor'
        with self.assertRaises(ValueError): import_governor(build_snapshot(2026, [], []), payload)


class CollectionTests(unittest.TestCase):
    def test_seek_cursor_and_secret_redaction(self):
        calls = []
        def fetch(url):
            calls.append(parse_qs(urlparse(url).query))
            if len(calls) == 1: return {'results': [record()], 'pagination': {'last_indexes': {'last_index': '1', 'last_expenditure_date': '2026-01-01'}}}
            return {'results': [], 'pagination': {}}
        client = FecClient('private-test-key', fetch=fetch, pause=lambda _: None)
        self.assertEqual(len(list(client.rows('schedules/schedule_e/', cycle=2026))), 1)
        self.assertEqual(calls[1]['last_index'], ['1'])
        self.assertEqual(calls[1]['last_expenditure_date'], ['2026-01-01'])
        self.assertNotIn('private-test-key', json.dumps(client.sources))

    def test_repeated_cursor_fails(self):
        client = FecClient('key', fetch=lambda _: {'results': [record()], 'pagination': {'last_indexes': {'last_index': '1'}}}, pause=lambda _: None)
        with self.assertRaises(SourceError): list(client.rows('schedules/schedule_e/'))

    def test_page_cap_fails(self):
        client = FecClient('key', max_pages=1, fetch=lambda _: {'results': [record()], 'pagination': {'last_indexes': {'last_index': '1'}}}, pause=lambda _: None)
        with self.assertRaises(SourceError): list(client.rows('schedules/schedule_e/'))

    def test_missing_key_never_fetches(self):
        client = FecClient('', fetch=lambda _: self.fail('must not fetch'))
        with self.assertRaises(SourceError): list(client.rows('schedules/schedule_e/'))

    def test_immutable_multi_cycle_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snap = build_snapshot(2026, [], [record()])
            publish(snap, root)
            old = json.loads((root / 'usa_superpac_index_v1.json').read_text())
            path = old['cycles']['2026']['state_files']['AK']
            publish(snap, root)
            self.assertEqual(len(list((root / 'usa_superpac/2026').glob('AK*'))), 1)
            publish(build_snapshot(2024, [], []), root)
            self.assertEqual(set(json.loads((root / 'usa_superpac_index_v1.json').read_text())['cycles']), {'2024', '2026'})
            self.assertEqual(json.loads((root / path).read_text())['spending'][0]['support_cents'], 1025)

    def test_failed_stream_does_not_publish(self):
        def stream():
            yield record()
            raise SourceError('interrupted')
        with self.assertRaises(SourceError): build_snapshot(2026, [], stream())

if __name__ == '__main__': unittest.main()
