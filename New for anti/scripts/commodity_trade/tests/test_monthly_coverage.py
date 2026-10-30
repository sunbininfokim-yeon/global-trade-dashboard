import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bilateral import ContractError
from monthly_coverage import coverage_report, observed_cells, observed_targets
from build_bilateral import main
from build_bilateral import plan_jobs
from bilateral_jobs import execute_plan
from bilateral_provider import Provider
from urllib.error import URLError
from pipeline_store import atomic_json


def panel(iso='ARG', months=('2026-03',), value=1, hs='1001'):
    return {'schema_version': 'commodity-trade-comtrade-priority-v1',
            'source': 'test', 'reporters': {iso: {'flows': {'exports': {'commodities': {
                'wheat': {'hs': hs, 'points': [{'month': m, 'value': value, 'unit': 'kg'} for m in months]}
            }}}}}}


class CoverageTests(unittest.TestCase):
    def test_network_failure_stops_after_one_attempt_and_is_sanitized(self):
        def fail(*args, **kwargs):
            raise URLError('synthetic-private-url')
        provider = Provider('preview', interval=0, http=fail)
        jobs = plan_jobs(['ARG', 'JPN'], ['1001'], ['202603'])
        r = execute_plan(jobs, None, cycle='a', max_requests=4, provider=provider, checkpoint=lambda s: None)
        self.assertEqual(r['attempted'], 1)
        self.assertEqual(r['stop_reason'], 'network_error')
        self.assertEqual(next(iter(r['state']['jobs'].values()))['status'], 'network_error')
        self.assertNotIn('synthetic-private-url', json.dumps(r))

    def test_rate_limit_stops_current_run_with_explicit_reason(self):
        jobs = plan_jobs(['ARG', 'JPN'], ['1001'], ['202603'])
        r = execute_plan(jobs, None, cycle='a', max_requests=4,
                         provider=lambda j: {'query_id': j['id'], 'status': 'rate_limited'},
                         checkpoint=lambda s: None)
        self.assertEqual(r['stop_reason'], 'rate_limited')
        self.assertEqual(r['attempted'], 1)

    def test_cli_rate_limit_nonzero_but_offline_publication_can_resume(self):
        class Limited:
            calls = 0
            def __call__(self, j):
                self.calls += 1
                if self.calls == 1:
                    return {'query_id': j['id'], 'status': 'ok', 'response_complete': True,
                            'rows': [{'partner': '156', 'flow': 'X', 'period': '202603',
                                      'metrics': {'net_weight_kg': 1}}]}
                return {'query_id': j['id'], 'status': 'rate_limited'}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            atomic_json(path / 'controls.json', {'controls': []})
            args = ['--checkpoint', str(path / 'state.json'), '--out-dir', str(path / 'feed'),
                    '--controls', str(path / 'controls.json'), '--reporters', 'ARG',
                    '--hs', '1001', '--months', '1', '--end-period', '202603']
            with patch('build_bilateral.Provider', return_value=Limited()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ['--fetch']), 3)
                self.assertEqual(main(args), 0)
            self.assertEqual(len(json.loads((path / 'state.json').read_text())['jobs']), 2)

    def test_zero_counts_but_null_bool_and_bad_period_do_not(self):
        self.assertEqual(len(list(observed_cells([panel(value=0)]))), 1)
        for p in [panel(value=None), panel(value=True), panel(value=float('nan')),
                  panel(months=('2026-13',)), panel(hs='10')]:
            self.assertEqual(list(observed_cells([p])), [])

    def test_unknown_panel_fails_closed(self):
        for p in [None, {}, {'schema_version': 'annual'}]:
            with self.assertRaises(ContractError):
                list(observed_cells([p]))

    def test_union_is_not_sum_and_partner_is_not_reporter(self):
        p = panel()
        index = {'entries': [{'reporter_iso3': 'ARG', 'frequency': 'M', 'period': '202603',
                              'partners': ['410'], 'flows': ['X'], 'hs': '1001'}]}
        r = coverage_report([p, p], index)
        self.assertEqual(r['counts']['any_monthly_reporters'], 1)
        self.assertEqual(len(r['countries']['ARG']['world_total_series']), 1)
        self.assertFalse(r['countries']['KOR']['bilateral_available'])

    def test_world_only_and_annual_not_bilateral_monthly(self):
        r = coverage_report([], {'entries': [
            {'reporter_iso3': 'ARG', 'frequency': 'M', 'partners': []},
            {'reporter_iso3': 'USA', 'frequency': 'A', 'partners': ['32']} ]})
        self.assertEqual(r['counts']['bilateral_reporters'], 0)

    def test_observed_dates_not_latest_calendar_and_no_fabricated_import(self):
        ts = observed_targets([panel(months=('2026-03', '2026-02', '2026-09'))],
                              ['ARG'], ['1001'], end_period='202608', month_count=1)
        self.assertEqual(ts, [('ARG', '1001', 'X', '202603')])

    def test_round_robin_deduplicates_sources(self):
        a = panel(months=('2026-03', '2026-02'))
        b = panel('JPN', months=('2026-05', '2026-04'))
        ts = observed_targets([a, a, b], ['ARG', 'JPN'], ['1001'], end_period='202608', month_count=2)
        self.assertEqual([x[0] for x in ts], ['ARG', 'JPN', 'ARG', 'JPN'])
        self.assertEqual(len(ts), 4)

    def test_status_empty_does_not_claim_zero_or_remove_total(self):
        r = coverage_report([panel()], {'jobs': {'j': {'query_meta': {
            'reporter_iso3': 'ARG', 'frequency': 'M'}, 'status': 'empty'}}})
        c = r['countries']['ARG']
        self.assertTrue(c['world_total_available'])
        self.assertEqual(c['bilateral_coverage'], 'not_acquired')
        self.assertEqual(c['bilateral_attempt_statuses'], {'empty': 1})

    def test_cli_observed_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            atomic_json(path / 'panel.json', panel())
            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(['--checkpoint', str(path / 'checkpoint.json'), '--plan-only',
                           '--period-strategy', 'observed', '--panel', str(path / 'panel.json'),
                           '--reporters', 'ARG,JPN', '--hs', '1001', '--end-period', '202608'])
            self.assertEqual(rc, 0)
            report = json.loads(out.getvalue())
            self.assertEqual(report['jobs'], 1)
            self.assertEqual(report['periods'], ['202603'])
            self.assertFalse((path / 'checkpoint.json').exists())


if __name__ == '__main__':
    unittest.main()
