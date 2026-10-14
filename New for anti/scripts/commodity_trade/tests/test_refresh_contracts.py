import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comtrade_totals import select_totals
from build_comtrade_priority_monthly import _merge_points
from refresh_preservation import preserve_monthly
from check_freshness import check_status, observation_warnings
from sources.korea_customs import fetch_monthly_hs_world, parse_itemtrade_xml
from refresh_pipeline import run_stage, observation_health
import refresh_pipeline


class RefreshContracts(unittest.TestCase):
    def test_total_never_depends_on_row_order_or_size(self):
        total=dict(reporterCode=76,partnerCode=0,partner2Code=0,customsCode='C00',motCode=0,
                   period='202606',cmdCode='1201',flowCode='X',primaryValue=6266777036,netWgt=14505018184.774)
        detail={**total,'motCode':1,'primaryValue':2312,'netWgt':245}
        for rows in ([total,detail],[detail,total],[detail,total,total]):
            self.assertEqual(select_totals(rows),[total])
        self.assertEqual(select_totals([total], reporter='076'), [total])
        self.assertEqual(select_totals([total], periods={'202607'}), [])
        with self.assertRaises(ValueError):
            select_totals([total,{**total,'primaryValue':100}])

    def test_scope_and_invalid_metrics_fail_closed(self):
        for value in [float('nan'),float('inf'),-1,True]:
            with self.assertRaises(ValueError):
                select_totals([dict(primaryValue=value)])
        self.assertEqual(select_totals([dict(partner2Code=123),dict(customsCode='C01')]),[])
        with self.assertRaises(ValueError):
            _merge_points([],[{'month':'2026-06'},{'month':'2026-06'}])

    def test_failed_or_regressed_source_preserves_country_history(self):
        old={'energy':{'commodities':{'crude_oil':{'countries':{
            'SAU':{'points':[dict(month='2026-06',value=100,unit='KTONS')]},
            'USA':{'points':[dict(month='2026-06',value=200,unit='KTONS')]}}}}}}
        new={'energy':{'commodities':{'crude_oil':{'countries':{
            'USA':{'points':[dict(month='2026-05',value=150,unit='KTONS')]}}}}}}
        preserve_monthly(old,new)
        c=new['energy']['commodities']['crude_oil']['countries']
        self.assertEqual(c['SAU']['points'][0]['value'],100)
        self.assertEqual(c['USA']['latest_available_month'],'2026-06')
        self.assertEqual(old['energy']['commodities']['crude_oil']['countries']['USA']['points'][0]['value'],200)

    def test_watchdog_distinguishes_attempt_from_success(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        good={'last_attempt_at':now.isoformat(),'status':'completed','scope':'scheduled'}
        self.assertEqual(check_status(good,now),[])
        self.assertIn('collection_partial_or_failed',check_status({**good,'status':'partial'},now))
        self.assertIn('collection_attempt_stale_or_invalid',check_status({**good,'last_attempt_at':(now-timedelta(days=36)).isoformat()},now))
        self.assertIn('no_full_scheduled_collection',check_status({**good,'scope':'smoke'},now))

    def test_korea_gateway_uses_cloudflare_key_and_shared_parser(self):
        xml='<response><header><resultCode>00</resultCode></header><body><items><item><year>2026.08</year><hsCode>2709</hsCode><expWgt>0</expWgt><impWgt>123</impWgt><expDlr>0</expDlr><impDlr>45</impDlr></item></items></body></response>'
        def answer(req,timeout):
            q=json.loads(req.data)
            self.assertNotIn('serviceKey',q)
            self.assertEqual(q['partners'],['0'])
            m=MagicMock();m.__enter__.return_value=io.BytesIO(json.dumps(dict(query_id=q['query_id'],status='ok',payload=xml)).encode())
            return m
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'TRADE_GATEWAY_URL':'https://example.com/api/trade-pipeline/query','TRADE_PIPELINE_TOKEN':'mock-token'},clear=True),patch('sources.korea_customs.urlopen',side_effect=answer):
            result=fetch_monthly_hs_world(period='202608',hs_code='2709',cache_dir=Path(d))
            self.assertTrue(result['available'])
            self.assertEqual(result['series_by_flow']['M'][0]['value'],123)
            self.assertEqual(result['series_by_flow']['X'][0]['value'],0)
            self.assertNotIn('mock-token',next(Path(d).glob('*.xml')).read_text())

    def test_entities_are_rejected_before_xml_parsing(self):
        with patch('sources.korea_customs.ET.fromstring') as parse:
            with self.assertRaises(ValueError):
                parse_itemtrade_xml(b'<!DOCTYPE a><response/>',period='202608',hs_code='2709')
            parse.assert_not_called()

    def test_bilateral_successful_process_is_not_complete_acquisition(self):
        result=MagicMock(returncode=0,stdout=b'{"planned_jobs":100,"unfinished_jobs":40,"network_requests":60}')
        status={'stages':[]}
        with patch('refresh_pipeline.subprocess.run',return_value=result):
            self.assertTrue(run_stage('bilateral', ['build_bilateral.py'], status))
        self.assertEqual(status['stages'][0]['status'],'partial')
        self.assertEqual(status['stages'][0]['unfinished_jobs'],40)

    def test_fresh_generated_time_does_not_hide_old_observations(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        status={'observations':{'countries':{'SAU':{'world_latest_period':'202509',
                                                 'bilateral_latest_period':None}}}}
        warnings=observation_warnings(status,now)
        self.assertEqual(warnings[0]['lag_months'],13)
        self.assertEqual(warnings[1]['issue'],'not_acquired')

    def test_observation_health_reads_reporting_months_not_generated_date(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'commodity_trade_coverage_v1.json').write_text(json.dumps({'countries':{}}))
            for name in ('monthly','comtrade_priority','national_priority','saudi_bulletin'):
                (root/f'commodity_trade_{name}_v1.json').write_text(json.dumps({
                    'generated_at':'2026-10-07','nested':{'points':[{'month':'2026-06','value':0}]}}))
            self.assertEqual(observation_health(root)['assets']['monthly']['latest_observed_month'],'2026-06')

    def test_orchestrator_records_partial_without_erasing_last_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            path=root/'commodity_trade_refresh_status_v1.json'
            path.write_text(json.dumps({'last_success_at':'2026-09-16T00:00:00+00:00'}))
            def stage(name,argv,status,*_):
                status['stages'].append({'stage':name,'status':'failed' if name=='global_sources' else 'completed'})
                return name!='global_sources'
            with patch.object(refresh_pipeline,'PUBLIC',root),patch.object(refresh_pipeline,'run_stage',side_effect=stage),patch.object(refresh_pipeline,'observation_health',return_value={}),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['refresh_pipeline.py','--batch','0']):
                self.assertEqual(refresh_pipeline.main(),0)
            result=json.loads(path.read_text())
            self.assertEqual(result['status'],'partial')
            self.assertEqual(result['last_success_at'],'2026-09-16T00:00:00+00:00')
            self.assertIn('auth_required',[s['status'] for s in result['stages']])

    def test_orchestrator_release_failure_cannot_report_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def stage(name,argv,status,*_):
                status['stages'].append({'stage':name,'status':'failed' if name=='release_gate' else 'completed'})
                return name!='release_gate'
            with patch.object(refresh_pipeline,'PUBLIC',root),patch.object(refresh_pipeline,'run_stage',side_effect=stage),patch.object(refresh_pipeline,'observation_health',return_value={}),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['refresh_pipeline.py','--batch','0']):
                self.assertEqual(refresh_pipeline.main(),1)
            self.assertEqual(json.loads((root/'commodity_trade_refresh_status_v1.json').read_text())['status'],'partial')


if __name__=='__main__':
    unittest.main()
