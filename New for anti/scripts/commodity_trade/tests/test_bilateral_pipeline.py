from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bilateral import ContractError, build_partition
from bilateral_jobs import execute_plan, make_job
from bilateral_provider import Provider, normalize_comtrade, normalize_korea, query_for, source_request
from build_bilateral import plan_jobs, public_parts, publish
from pipeline_store import atomic_json, read_json, single_writer
from export_control_screen import screen
from check_export_policy_sources import check_documents
from validate_bilateral_public import validate


def job(flow='X', source='comtrade', partner=None):
    return plan_jobs(['KOR' if source == 'korea_customs' else 'CHL'], ['2603'], ['202606'],
                     source=source, partners=[partner] if partner else None)[0 if flow == 'X' else 1]


def ct(partner=156, flow='X', weight=25, **kw):
    r = dict(typeCode='C', freqCode='M', period='202606', reporterCode=152,
             flowCode=flow, partnerCode=partner, partner2Code=0, classificationCode='H6',
             cmdCode='2603', customsCode='C00', motCode=0, netWgt=weight,
             fobvalue=50, cifvalue=55, primaryValue=50, isReported=False, isNetWgtEstimated=True, qty=25, qtyUnitCode=8)
    r.update(kw)
    return r


def body(*rows):
    return {'count': len(rows), 'data': list(rows)}


class AcquisitionTests(unittest.TestCase):
    def test_comtrade_preserves_flags_and_explicit_units(self):
        rows, complete = normalize_comtrade(body(ct()), job())
        self.assertTrue(complete)
        self.assertTrue(rows[0]['quality']['isNetWgtEstimated'])
        self.assertFalse(rows[0]['quality']['isReported'])
        self.assertNotIn('quantity_bbl', rows[0]['metrics'])

    def test_wrong_hs_revision_period_reporter_flow_scope_rejected(self):
        for change in [{'cmdCode': '7403'}, {'classificationCode': 'H5'}, {'period': '202605'},
                       {'reporterCode': 410}, {'flowCode': 'M'}, {'partner2Code': 842},
                       {'customsCode': 'C01'}, {'motCode': 1}]:
            with self.subTest(change=change), self.assertRaises(ContractError):
                normalize_comtrade(body(ct(**change)), job())

    def test_count_limit_and_truncation(self):
        self.assertFalse(normalize_comtrade(body(*[ct()]*500), job())[1])
        self.assertFalse(normalize_comtrade({**body(ct()), 'mayBeTruncated': True}, job())[1])
        with self.assertRaises(ContractError):
            normalize_comtrade({'count': 20, 'data': [ct()]}, job())

    def test_missing_declared_valuation_not_replaced_by_primary(self):
        rows, _ = normalize_comtrade(body(ct(fobvalue=None, primaryValue=100)), job())
        self.assertIsNone(rows[0]['metrics']['trade_value_usd'])
        self.assertEqual(rows[0]['quality']['primary_value_usd'], 100)

    def test_korea_hscd_partner_and_zero(self):
        doc = b'<response><header><resultCode>00</resultCode></header><body><items><item><year>2026.06</year><hsCd>2603</hsCd><statCd>SA</statCd><expWgt>0</expWgt><expDlr>0</expDlr><impWgt>12</impWgt><impDlr>34</impDlr></item></items></body></response>'
        j = job(source='korea_customs', partner='682')
        rows, complete = normalize_korea(doc, j)
        self.assertTrue(complete)
        self.assertEqual(rows[0]['metrics']['net_weight_kg'], 0)
        with self.assertRaises(ContractError):
            normalize_korea(doc.replace(b'<statCd>SA', b'<statCd>US'), j)
        self.assertFalse(normalize_korea(doc.replace(b'<items>', b'<totalCount>10</totalCount><items>'), j)[1])

    def test_korea_amount_only_and_entities(self):
        j = job(source='korea_customs', partner='682')
        doc = b'<response><header><resultCode>00</resultCode></header><body><items><item><year>2026.06</year><hsCd>2603</hsCd><statCd>SA</statCd><expDlr>10</expDlr></item></items></body></response>'
        rows, _ = normalize_korea(doc, j)
        self.assertIsNone(rows[0]['metrics']['net_weight_kg'])
        self.assertEqual(rows[0]['metrics']['trade_value_usd'], 10)
        with self.assertRaises(ContractError):
            normalize_korea(b'<!DOCTYPE foo>' + doc, j)

    def test_gateway_and_direct_share_same_parser(self):
        j = job()
        with patch.dict(os.environ, {'TRADE_GATEWAY_URL': 'https://example.test/api/trade-pipeline/query',
                                     'TRADE_PIPELINE_TOKEN': 'synthetic-gateway'}, clear=True):
            direct = Provider('preview', interval=0, http=lambda *a, **k: json.dumps(body(ct())).encode())(j)
            gateway = Provider('gateway', interval=0, http=lambda *a, **k: json.dumps(
                {'query_id': j['id'], 'status': 'ok', 'payload': json.dumps(body(ct()))}).encode())(j)
        self.assertEqual(direct['rows'], gateway['rows'])

    def test_missing_keys_do_not_call_network(self):
        with patch.dict(os.environ, {}, clear=True):
            for j in [job(), job(source='korea_customs', partner='682')]:
                p = Provider('direct', http=lambda *a, **k: self.fail('network called'))
                self.assertEqual(p(j)['status'], 'auth_required')
                self.assertEqual(p.calls, 0)

    def test_exceptions_and_auth_urls_not_exposed(self):
        def fail(*a, **k):
            raise OSError('serviceKey=synthetic-secret')
        result = Provider('preview', http=fail)(job())
        self.assertNotIn('synthetic-secret', json.dumps(result))

    def test_explicit_partner_query_does_not_expand_scope(self):
        url, _ = source_request(query_for(job(partner='682')), preview=True)
        self.assertIn('partnerCode=682', url)
        self.assertIn('flowCode=X', url)


class PersistenceTests(unittest.TestCase):
    def test_partial_direction_does_not_erase_old_imports(self):
        j = job()
        m = dict(j['meta'], requested_flows=['X', 'M'])
        j = make_job(m, ['*'])
        rows = [{'partner': '156', 'flow': f, 'period': '202606', 'metrics': {'net_weight_kg': 10}} for f in ['X', 'M']]
        def run(state, received, cycle):
            return execute_plan([j], state, cycle=cycle, max_requests=1, checkpoint=lambda s: None,
                provider=lambda _: {'query_id': j['id'], 'status': 'ok', 'response_complete': True, 'rows': received})['state']
        old = run(None, rows, 'a')
        new = run(old, rows[:1], 'b')
        self.assertEqual(new['data'], old['data'])
        self.assertEqual(new['jobs'][j['id']]['status'], 'partial')

    def state(self):
        j = job()
        rows, _ = normalize_comtrade(body(ct(), ct(0, weight=100)), j)
        return execute_plan([j], None, cycle='a', max_requests=1, checkpoint=lambda x: None,
                            provider=lambda j: {'query_id': j['id'], 'status': 'ok', 'response_complete': True,
                                                'rows': rows, 'retrieved_at': '2026-09-09T00:00:00Z'})['state']

    def test_missing_partner_metric_or_direction_preserves_previous(self):
        old = self.state()
        j = job()
        for candidate in [body(ct(0, weight=100)), body(ct(weight=None), ct(0, weight=100))]:
            rows, _ = normalize_comtrade(candidate, j)
            new = execute_plan([j], old, cycle='b', max_requests=1, checkpoint=lambda x: None,
                               provider=lambda _: {'query_id': j['id'], 'status': 'ok', 'response_complete': True, 'rows': rows})['state']
            self.assertEqual(new['data'], old['data'])

    def test_atomic_write_and_lock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'state.json'
            atomic_json(path, {'ok': 1})
            with self.assertRaises(ValueError):
                atomic_json(path, {'bad': float('nan')})
            self.assertEqual(read_json(path), {'ok': 1})
            with single_writer(Path(d)/'lock'):
                with self.assertRaises(BlockingIOError), single_writer(Path(d)/'lock'):
                    pass

    def test_manifest_parts_exist_and_empty_refresh_cannot_wipe(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = publish(self.state(), d, {'controls': []}, as_of='2026-09-09')
            for entry in manifest['entries']:
                self.assertTrue((Path(d)/entry['path']).exists())
            self.assertEqual(validate(d)['parts'], 1)
            before = (Path(d)/'index.json').read_bytes()
            with self.assertRaises(ContractError):
                publish({'data': {}, 'jobs': {}}, d, {'controls': []}, as_of='2026-09-09')
            self.assertEqual(before, (Path(d)/'index.json').read_bytes())

    def test_korea_world_denominator_only_same_refresh_cycle(self):
        jobs = plan_jobs(['KOR'], ['2603'], ['202606'], source='korea_customs', partners=['0', '682'])
        def provider(j):
            return {'query_id': j['id'], 'status': 'ok', 'response_complete': True,
                    'rows': [{'partner': j['partners'][0], 'flow': j['meta']['requested_flows'][0],
                              'period': '202606', 'metrics': {'net_weight_kg': 100 if j['partners'] == ['0'] else 25}}]}
        state = execute_plan(jobs, None, cycle='a', max_requests=4, provider=provider, checkpoint=lambda s: None)['state']
        parts = public_parts(state, {'controls': []}, as_of='2026-09-09')
        self.assertTrue(any(r['analysis']['net_weight_kg']['share_pct'] == 25 for p in parts for b in p['flows'].values() for r in b['rows']))
        # Refresh only the World job; old partners must NOT adopt new denominator.
        state = execute_plan(jobs[:1], state, cycle='b', max_requests=1, provider=provider, checkpoint=lambda s: None)['state']
        p = next(p for p in public_parts(state, {'controls': []}, as_of='2026-09-09') if p['meta']['value_basis'] == 'FOB' and p['flows']['X']['rows'])
        self.assertIsNone(p['flows']['X']['rows'][0]['analysis']['net_weight_kg']['share_pct'])


class PolicyTests(unittest.TestCase):
    def screen(self, **changes):
        options = dict(exporter_iso3='IDN', importer_iso3='KOR', hs='2604', period='202606', frequency='M',
                       catalogue={'as_of': '2026-08', 'controls': [{'id': 'idn-nickel-ore', 'iso': 'IDN', 'level': 'prohibited'}]}, as_of='2026-09-09')
        options.update(changes)
        return screen(**options)

    def test_ore_restriction_not_applied_to_refined_nickel(self):
        self.assertEqual(self.screen()['status'], 'potential_control_match')
        self.assertEqual(self.screen(hs='7502')['status'], 'not_assessed')
        self.assertIsNone(self.screen()['legal_clearance'])

    def test_unknown_dates_and_stale_seed_never_confirm_current_control(self):
        c = self.screen()['candidates'][0]
        self.assertEqual(c['status'], 'requires_review')
        self.assertIn('effective_dates_unverified', c['issues'])

    def test_exporter_not_importer_controls_and_no_match_not_clear(self):
        self.assertEqual(self.screen(exporter_iso3='KOR', importer_iso3='IDN')['status'], 'not_assessed')

    def test_future_partial_and_expired_period_rules(self):
        rule = {'id': 'test', 'iso': 'IDN', 'hs_prefixes': ['2604'], 'scope_verified': True,
                'official_document_verified': True, 'effective_from': '2026-06-15', 'review_valid_until': '2026-09-30'}
        self.assertEqual(self.screen(catalogue={'controls': [rule]})['candidates'][0]['temporal_status'], 'part_of_period')
        rule['effective_from'] = '2027-01-01'
        self.assertEqual(self.screen(catalogue={'controls': [rule]})['candidates'][0]['temporal_status'], 'not_yet_effective')

    def test_source_failure_preserves_last_hash_and_does_not_verify_law(self):
        docs = [{'rule_id': 'x', 'url': 'https://setkab.go.id/en/test/'}]
        first = check_documents(docs, http=lambda *a, **k: b'<html>' + b'x'*300 + b'</html>')
        def fail(*a, **k):
            raise OSError('offline')
        second = check_documents(docs, first, http=fail)
        old, new = first['sources'][docs[0]['url']], second['sources'][docs[0]['url']]
        self.assertEqual(new['sha256'], old['sha256'])
        self.assertEqual(new['status'], 'unavailable')
        self.assertFalse(new['current_legal_status_verified'])

    def test_policy_fetch_is_allowlisted(self):
        with self.assertRaises(ValueError):
            check_documents([{'rule_id': 'x', 'url': 'http://127.0.0.1/secret'}])


if __name__ == '__main__':
    unittest.main()
