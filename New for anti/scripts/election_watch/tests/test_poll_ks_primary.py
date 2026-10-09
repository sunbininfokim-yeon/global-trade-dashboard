import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from election_watch.governor_ks import (IE_INDEX, PAC_INDEX, parse_ie_index,
    summarize_indices, recheck_document_references, collect_audit)
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.poll_targets import apply_targets
from election_watch.superpac import SourceError
import refresh_governor_finance_audit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/usa_polls'
PUBLIC = ROOT.parent.parent/'public/data'
DAY = '2026-10-09'
read = lambda p: json.loads(p.read_text())


class KansasPollTests(unittest.TestCase):
    def setUp(self):
        self.gov = read(ROOT/'config/governor_matchups/2026.json')
        self.federal = read(ROOT/'config/federal_matchups/2026.json')['races']
        self.policy = apply_targets(apply_matchups(read(CONFIG/'live_2026.json'), self.gov, DAY),
            read(CONFIG/'targets_2026.json'), read(CONFIG/'ballot_reviews_2026.json'), DAY)
        self.policy['quality_reviews'] = read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/KS-primary-20261009.json')
        self.rows = [r['provider_record'] for r in self.audit['records']]

    def observations(self):
        observations, held = normalize(self.rows, self.policy, DAY)
        self.assertFalse(held); self.assertEqual(len(observations), 3)
        return observations

    def test_four_federal_districts_one_election_senator_and_minor_party(self):
        federal = {k: v for k, v in self.federal.items() if v['state'] == 'KS'}
        self.assertEqual(set(federal), {'USA:KS:senate'} | {f'USA:KS:house:{n:02d}' for n in range(1, 5)})
        self.assertEqual(sum(len(r['candidates']) for r in federal.values()), 15)
        senate = federal['USA:KS:senate']['candidates']
        david = next(c for c in senate if c['party'] == 'LIB')
        self.assertEqual(david['name'], 'David C. Graham')
        self.assertIsNone(david['candidate_id'])
        self.assertEqual(david['reported_candidate_id'], 'S2KS00154')
        self.assertEqual(self.policy['races']['USA:KS:senate']['candidates']['David Graham']['party'], 'LIB')
        self.assertNotIn('Jerry Moran', [c['name'] for c in senate])

    def test_primary_winners_do_not_certify_entire_general_ballot_or_unopposed_result(self):
        for race in [r for r in self.federal.values() if r['state'] == 'KS']:
            self.assertEqual(race['coverage'], 'reported_active_candidate_listing')
            for c in race['candidates']:
                if c['party'] in ('DEM', 'REP'):
                    self.assertTrue(c['primary_nominee_review']['not_general_ballot_certification'])
        # Coover's 100% primary result is still an opposed November contest.
        self.assertEqual(self.federal['USA:KS:house:02']['candidates'][0]['primary_nominee_review']['primary_votes'], 38737)
        for rid, race in self.policy['races'].items():
            if race['state'] != 'KS': continue
            self.assertEqual(race['general_from'], '2026-08-05')
            self.assertIsNone(race['ballot_competition']['general_unopposed'])
            self.assertFalse(race['ballot_competition']['confirmed_winner'])
        self.assertEqual(len(self.gov['contests']['KS']['candidates']), 2)
        self.assertEqual([c['running_mate']['separate_governor_candidate'] for c in self.gov['contests']['KS']['candidates']], [False, False])

    def test_reviewed_fec_id_is_separate_from_unverified_secondary_id(self):
        senate = self.federal['USA:KS:senate']['candidates']
        self.assertEqual({c['name']: c['candidate_id'] for c in senate if c['party'] in ('DEM', 'REP')},
            {'Adam Hamilton': 'S6KS00312', 'Roger Marshall': 'S0KS00315'})
        self.assertEqual(sum(bool(c['candidate_id']) for r in self.federal.values() if r['state'] == 'KS' and r['office'] == 'house' for c in r['candidates']), 12)

    def test_emerson_full_field_undecided_and_rounding_are_not_reallocated(self):
        observations = [o for o in self.observations() if o['pollster_group'] == 'emerson']
        self.assertEqual(len(observations), 2)
        senate = next(o for o in observations if o['race_id'].endswith('senate'))
        self.assertEqual({a['name']: a['pct'] for a in senate['answers']},
                         {'Roger Marshall': 43, 'Adam Hamilton': 45, 'David Graham': 4})
        disclosure = senate['source_quality']['disclosure_review']
        self.assertEqual(disclosure['unrounded_primary_toplines']['David Graham'], 3.7)
        self.assertEqual(disclosure['non_candidate_responses']['undecided'], 8.2)
        for o in observations:
            self.assertEqual(o['sample_n'], 750)
            self.assertTrue(o['source_quality']['disclosure_review']['question_wording_checked'])
            self.assertTrue(o['aggregation_eligibility']['eligible'])
            self.assertIsNone(o['source_quality']['accuracy_grade'])

    def test_latest_siena_toplines_are_reference_until_wave_metadata_verified(self):
        o = next(o for o in self.observations() if o['id'] == 'gov202thecdc40b4c')
        self.assertEqual(o['sample_n'], 605)  # Provider-reported, not primary-verified.
        self.assertIsNone(o['source_quality']['question_sample_n'])
        self.assertFalse(o['source_quality']['disclosure_review']['primary_metadata_checked'])
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        self.assertIn('current_questionnaire_and_metadata_not_primary_verified', o['aggregation_eligibility']['reasons'])

    def test_recent_windows_do_not_call_old_emerson_or_reference_siena_a_winner(self):
        obs = self.observations()
        for rid in ('USA:KS:senate', 'USA:KS:governor'):
            for days in (7, 14):
                result = summarize([o for o in obs if o['race_id'] == rid], self.policy['races'][rid], DAY, days)
                self.assertFalse(result['included_ids'])
                self.assertIsNone(result['party'])

    def test_changed_sample_commissioner_url_or_answers_invalidates_exact_review(self):
        for field, value in [('sample_size', 751), ('sponsors', ['Different commissioner']),
                             ('url', 'https://emersoncollegepolling.com/other-release/')]:
            raw = copy.deepcopy(self.rows[0]); raw[field] = value
            self.assertFalse(normalize([raw], self.policy, DAY)[0])
        raw = copy.deepcopy(self.rows[0]); raw['answers'][0]['pct'] += 1
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_drive_folder_and_preprimary_record_are_held_and_no_house_poll_invented(self):
        held = [r['provider_record'] for r in self.audit['held_records']]
        obs, rejected = normalize(held, self.policy, DAY)
        self.assertFalse(obs); self.assertEqual(len(rejected), 3)
        self.assertEqual(self.audit['house_poll_discovery']['provider_records'], 0)
        self.assertFalse(self.audit['house_poll_discovery']['forecast_or_market_or_generic_ballot_imported'])
        self.assertFalse(self.audit['discovered_not_ingested'][0]['primary_sample_and_dates_verified'])


class KansasReportIndexTests(unittest.TestCase):
    def setUp(self):
        self.roster = read(ROOT/'config/governor_matchups/2026.json')['contests']['KS']['candidates']
        self.reviews = read(ROOT/'config/governor_finance/KS_2026_document_reviews.json')

    def html(self, rows=None, end_td='</td>'):
        if rows is None:
            # Current official HTML omits one </td>; valid implied HTML closure.
            rows = f'<tr><td>Example committee</td><td>---</td><td><a href="{IE_INDEX.rsplit("/",1)[0]}/202607/example.pdf">202607</a>{end_td}<td></td><td></td></tr>'
        header = '<tr><td>Committee Name</td>'+''.join(f'<td>Receipts &amp; Expenditures {p}</td>' for p in ('202601','202607','202610','202701'))+'</tr>'
        return ('<h1>INDEPENDENT EXPENDITURES</h1><p>2026 Election Cycle</p><p>Last Updated: August 21, 2026</p><table>'+header+rows+'<tr>'+('<td>&nbsp;</td>'*5)+'</tr></table>').encode()

    def pac(self):
        return b'<p>Political Action Committees</p><p>2026 Election Cycle</p><p>Statement of Organization</p><p>Last Updated: October 7, 2026</p><table><tr><td>S/O</td></tr></table>'

    def test_optional_td_closure_and_blank_rows_preserve_report_links(self):
        a = parse_ie_index(self.html(), DAY)
        b = parse_ie_index(self.html(end_td=''), DAY)
        self.assertEqual(a['reports'], b['reports'])
        self.assertEqual(a['indexed_report_links'], 1)
        self.assertEqual(a['indexed_committees'], 1)
        self.assertEqual(a['source_updated_on'], '2026-08-21')
        self.assertIsNone(a['reports'][0]['filing_date'])
        self.assertEqual(a['reports'][0]['election_stage'], 'unknown')

    def test_wrong_cycle_columns_duplicate_and_unreviewed_host_fail_closed(self):
        valid = self.html()
        for raw in [valid.replace(b'2026 Election', b'2024 Election'),
                    valid.replace(b'202701', b'202601'),
                    valid.replace(b'www.kansas.gov', b'example.com'),
                    valid.replace(b'/202607/example.pdf', b'/../../unreviewed.pdf'),
                    valid.replace(b'202607</a>', b'202610</a>'), b'<html>Access denied</html>',
                    valid.replace(b'</table>', b''),
                    self.html('<tr><td>Empty committee</td>'+('<td>---</td>'*4)+'</tr>')]:
            with self.assertRaises((SourceError, ValueError)): parse_ie_index(raw, DAY)
        row = self.html().decode().split('<tr>')[2].split('</tr>')[0]
        with self.assertRaises(SourceError):parse_ie_index(self.html('<tr>'+row+'</tr><tr>'+row+'</tr>'), DAY)
        with self.assertRaises(SourceError):parse_ie_index(valid, '2026-08-20')

    def test_index_and_pac_organization_legend_never_claim_money_or_support(self):
        audit = summarize_indices(self.html(), self.pac(), 2026, self.roster, DAY+'T10:00:00+00:00')
        self.assertFalse(audit['financial_data_collected'])
        self.assertFalse(audit['candidate_amounts_available'])
        self.assertEqual(audit['input_record_unit'], 'report_link_not_transaction')
        self.assertIsNone(audit['current_governor_target_records'])
        for c in audit['candidate_audits']:
            self.assertIsNone(c['support_cents']); self.assertIsNone(c['oppose_cents'])
        with self.assertRaises(SourceError):summarize_indices(self.html(), self.pac(), 2024, self.roster, DAY+'T10:00:00+00:00')
        with self.assertRaises(SourceError):summarize_indices(self.html(), self.pac().replace(b'Statement of Organization',b'Support/Oppose'), 2026, self.roster, DAY+'T10:00:00+00:00')

    def reference(self, fetch, missing=False):
        review = copy.deepcopy(self.reviews); body = b'%PDF-reviewed'; review['documents'] = review['documents'][:1]
        review['documents'][0]['sha256'] = hashlib.sha256(body).hexdigest()
        index = {'reports': [] if missing else [{'report_url': review['documents'][0]['url']}]}
        return recheck_document_references(review, self.roster, index, DAY+'T23:00:00+00:00', fetch)

    def test_reviewed_rows_are_not_report_totals_or_current_general_amounts(self):
        refs = self.reference(lambda u: b'%PDF-reviewed')
        row = refs[0]['reviewed_document']['rows'][0]
        self.assertEqual(row['amount_cents'], 850000)
        self.assertNotEqual(row['amount_cents'], refs[0]['reviewed_document']['report_total_cents'])
        self.assertEqual(row['election_stage'], 'pre_nomination_reference')
        self.assertFalse(refs[0]['aggregation_eligible'])
        self.assertEqual(self.reviews['documents'][1]['index_period_label'], '202607')
        self.assertEqual(self.reviews['documents'][1]['report_period_checkbox'], '202610')

    def test_changed_failed_and_missing_pdf_preserve_original_reference_date(self):
        def failed(url):raise OSError('unavailable')
        for fetch, missing, status in [(lambda u:b'changed', False,'carried_forward_reference_document_changed'),
                (failed,False,'carried_forward_reference_source_unavailable'),
                (failed,True,'carried_forward_reference_source_link_missing')]:
            r = self.reference(fetch, missing)[0]
            self.assertEqual(r['status'], status)
            self.assertEqual(r['reviewed_document']['checked_at'], self.reviews['documents'][0]['checked_at'])
            self.assertFalse(r['aggregation_eligible'])

    def test_changed_candidate_identity_or_general_stage_cannot_use_old_reference(self):
        for field, value in [('candidate_id', 'different'), ('election_stage', 'general'), ('amount_cents', -1)]:
            review = copy.deepcopy(self.reviews); review['documents'][0]['rows'][0][field] = value
            with self.assertRaises(ValueError):recheck_document_references(review, self.roster, {'reports': []}, DAY+'T23:00:00+00:00', lambda u:b'')

    def test_source_failure_leaves_previous_published_audit_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'usa_governor_finance_audits/2026/KS.json'; p.parent.mkdir(parents=True)
            before = b'{"status":"previous_valid","captured_at":"2026-10-08T01:00:00Z"}\n';p.write_bytes(before)
            with patch('sys.argv', ['refresh_governor_finance_audit.py','--state','KS','--public',temp]), \
                    patch.object(refresh_governor_finance_audit, 'collect_ks', side_effect=SourceError('changed source')), \
                    patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(refresh_governor_finance_audit.main(), 1)
            self.assertEqual(p.read_bytes(), before)

    def test_collector_does_not_accept_redirected_or_empty_report_index(self):
        class Response:
            status=200
            def geturl(self):return 'https://example.com/blocked'
            def read(self,*a):return b''
            def __enter__(self):return self
            def __exit__(self,*a):return False
        with self.assertRaises(SourceError):collect_audit(2026, self.roster, lambda *a,**k:Response())


if __name__ == '__main__':unittest.main()
