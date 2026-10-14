from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bilateral_jobs import execute_plan
from build_bilateral import plan_jobs, publish, read_controls, main as bilateral_main
from pipeline_store import atomic_json, read_json
from validate_bilateral_public import validate
from export_control_screen import with_documents
from resume_queue import resume_plan, pending_ids, SETTLED
from observation_health import product_health, history_gaps
from monthly_coverage import coverage_report
from check_freshness import check_status, observation_warnings
import refresh_pipeline


def jobs():
    return plan_jobs(['USA','BRA'],['2709','1201'],['202606'])


def state():
    return {'schema':'bilateral-checkpoint-v1','jobs':{},'data':{}}


def acquire(j):
    return {'query_id':j['id'],'status':'ok','response_complete':True,
        'rows':[{'partner':'156','flow':j['meta']['requested_flows'][0],
                 'period':j['meta']['period'],'metrics':{'net_weight_kg':25}}],
        'retrieved_at':'2026-10-12T00:00:00+00:00'}


class QueueTests(unittest.TestCase):
    def execute(self,s,p,budget,provider=acquire):
        return execute_plan(p['jobs'],s,cycle=p['cycle'],max_requests=budget,
            provider=provider,checkpoint=lambda s:None,settled_statuses=SETTLED,
            max_attempts_per_cycle=3)['state']

    def test_unfinished_plan_survives_six_months_and_new_candidates(self):
        s=state(); p=resume_plan(s,'batch0',jobs(),'2026-10')
        s=self.execute(s,p,1)
        newer=plan_jobs(['ARG'],['1001'],['202611'])
        for cycle in ('2026-11','2026-12','2027-01','2027-02','2027-03','2027-04'):
            p=resume_plan(s,'batch0',newer,cycle)
            self.assertEqual(p['cycle'],'2026-10')
            self.assertEqual(p['jobs'],jobs())
        s=self.execute(s,p,100)
        self.assertEqual(pending_ids(p['jobs'],s,p['cycle']),[])
        next_plan=resume_plan(s,'batch0',newer,'2027-04')
        self.assertEqual(next_plan['cycle'],'2027-04')
        self.assertEqual(next_plan['jobs'],newer)

    def test_bounded_runs_visit_whole_plan_without_success_repeats(self):
        s=state(); visited=[]
        def provider(j):
            visited.append(j['id']); return acquire(j)
        for _ in range(4):
            p=resume_plan(s,'batch0',jobs(),'2026-10')
            s=self.execute(s,p,2,provider)
        self.assertEqual(len(visited),len(jobs()))
        self.assertEqual(len(set(visited)),len(visited))

    def test_sixty_request_waves_cover_large_plan(self):
        s=state(); visited=[]
        large=plan_jobs(['USA','BRA','ARG'],[f'{1000+i:04d}' for i in range(27)],['202606'])
        def provider(j): visited.append(j['id']); return acquire(j)
        for cycle in ('2026-10','2026-11','2026-11'):
            p=resume_plan(s,'batch0',large,cycle)
            s=self.execute(s,p,60,provider)
        self.assertEqual(len(visited),162)
        self.assertEqual(len(set(visited)),162)
        self.assertEqual(pending_ids(p['jobs'],s,p['cycle']),[])

    def test_empty_is_not_zero_is_not_retried_daily_and_retains_data(self):
        s=state(); p=resume_plan(s,'batch0',jobs(),'2026-09'); s=self.execute(s,p,100)
        old=deepcopy(s['data'])
        p=resume_plan(s,'batch0',jobs(),'2026-10')
        def empty(j): return {'query_id':j['id'],'status':'empty'}
        s=self.execute(s,p,100,empty)
        self.assertEqual(s['data'],old)
        self.assertEqual(pending_ids(p['jobs'],s,p['cycle']),[])
        s2=self.execute(s,p,100,lambda _:self.fail('empty was re-requested'))
        self.assertEqual(s2,s)
        p2=resume_plan(s,'batch0',jobs(),'2026-11')
        self.assertEqual(len(pending_ids(p2['jobs'],s,p2['cycle'])),len(jobs()))

    def test_bad_cells_defer_after_three_without_blocking_future_cycles(self):
        s=state(); p=resume_plan(s,'batch0',jobs(),'2026-10')
        def bad(j): return {'query_id':'wrong','status':'ok'}
        for _ in range(3): s=self.execute(s,p,100,bad)
        self.assertEqual(pending_ids(p['jobs'],s,p['cycle']),[])
        self.assertTrue(all(j['status']=='contract_error' for j in s['jobs'].values()))
        self.assertEqual(self.execute(s,p,100,lambda _:self.fail('fourth attempt')),s)
        self.assertEqual(resume_plan(s,'batch0',jobs(),'2026-11')['cycle'],'2026-11')

    def test_rate_limit_stops_immediately_and_keeps_progress_pending(self):
        s=state(); p=resume_plan(s,'batch0',jobs(),'2026-10')
        calls=[]
        def limited(j):
            calls.append(j['id']); return {'query_id':j['id'],'status':'rate_limited'}
        for _ in range(4): s=self.execute(s,p,100,limited)
        self.assertEqual(len(calls),4)
        self.assertEqual(len(pending_ids(p['jobs'],s,p['cycle'])),len(jobs()))
        self.assertEqual(resume_plan(s,'batch0',jobs(),'2026-11')['cycle'],'2026-10')

    def test_success_discovery_appends_without_requerying_same_cycle(self):
        s=state(); p=resume_plan(s,'batch0',jobs()[:1],'2026-10'); s=self.execute(s,p,100)
        p=resume_plan(s,'batch0',jobs(),'2026-10')
        self.assertEqual(len(pending_ids(p['jobs'],s,p['cycle'])),len(jobs())-1)

    def test_corrupt_saved_identity_fails_closed(self):
        s=state(); resume_plan(s,'batch0',jobs(),'2026-10')
        s['active_plans']['batch0']['jobs'][0]['meta']['period']='202601'
        with self.assertRaises(ValueError): resume_plan(s,'batch0',jobs(),'2026-10')

    def test_rescreen_without_network_keeps_observation_vintage(self):
        s=state(); p=resume_plan(s,'batch0',jobs(),'2026-10'); s=self.execute(s,p,100)
        before=deepcopy(s['data'])
        with tempfile.TemporaryDirectory() as d:
            old=publish(s,d,{'controls':[],'as_of':'2026-08'},as_of='2026-09-19')
            new=publish(s,d,{'controls':[],'as_of':'2026-10'},as_of='2026-10-12')
            self.assertEqual(len(old['entries']),len(new['entries']))
            part=json.loads((Path(d)/new['entries'][0]['path']).read_text())
            row=next(r for b in part['flows'].values() for r in b['rows'])
            self.assertEqual(row['export_control']['checked_as_of'],'2026-10-12')
            self.assertEqual(row['export_control']['catalogue_as_of'],'2026-10')
            self.assertIsNone(row['export_control']['legal_clearance'])
        self.assertEqual(s['data'],before)

    def test_cli_persists_plan_before_request_and_resumes_original_month(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); checkpoint=root/'checkpoint.json'; out=root/'output'
            controls=root/'controls.json'; atomic_json(controls,{'controls':[],'as_of':'2026-10'})
            argv=['--fetch','--checkpoint',str(checkpoint),'--out-dir',str(out),'--controls',str(controls),
                  '--reporters','USA','--hs','2709','--months','1','--max-requests','1',
                  '--resume-plan','batch0','--cycle','2026-10','--end-period','202606']
            class FakeProvider:
                calls=0
                def __call__(self,j):
                    saved=read_json(checkpoint)
                    self_outer.assertEqual(len(saved['active_plans']['batch0']['jobs']),2)
                    self.calls+=1
                    return acquire(j)
            self_outer=self
            with patch('build_bilateral.Provider',return_value=FakeProvider()),redirect_stdout(io.StringIO()):
                self.assertEqual(bilateral_main(argv),0)
            argv[argv.index('2026-10')]='2026-11'
            argv[argv.index('202606')]='202607'
            with patch('build_bilateral.Provider',return_value=FakeProvider()),redirect_stdout(io.StringIO()):
                self.assertEqual(bilateral_main(argv),0)
            s=read_json(checkpoint)
            self.assertEqual(s['active_plans']['batch0']['cycle'],'2026-10')
            self.assertEqual({p['meta']['period'] for p in s['data'].values()},{'202606'})
            self.assertEqual(pending_ids(s['active_plans']['batch0']['jobs'],s,'2026-10'),[])
            self.assertEqual(validate(out)['parts'],2)

    def test_real_seed_rescreens_without_acquisition_or_observation_edits(self):
        script=Path(__file__).resolve().parents[1]
        original=read_json(script/'deployment/seed_checkpoint.json')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); checkpoint=root/'checkpoint.json'; atomic_json(checkpoint,original)
            with patch('bilateral_provider.Provider.__call__',side_effect=AssertionError('network forbidden')),redirect_stdout(io.StringIO()):
                self.assertEqual(bilateral_main(['--checkpoint',str(checkpoint),'--out-dir',str(root/'out')]),0)
            self.assertEqual(read_json(checkpoint)['data'],original['data'])
            self.assertGreater(validate(root/'out')['parts'],0)
            index=read_json(root/'out/index.json')
            self.assertEqual(index['policy_catalogue_as_of'],read_controls(script.parents[1]/'public/data/export_controls')['as_of'])


class HealthTests(unittest.TestCase):
    def test_historical_policy_document_cannot_override_latest_catalogue(self):
        rule={'id':'idn-nickel-ore','url':'https://example.test/current',
              'effective_from':'2026-10-01','hs_prefixes':['260400'],
              'official_document_verified':True,'scope_verified':True}
        catalogue={'controls':[rule],'as_of':'2026-10'}
        doc={'rule_id':rule['id'],'url':'https://example.test/2019',
             'effective_from':'2020-01-01','hs_prefixes':['2604']}
        enriched=with_documents(catalogue,{'documents':[doc]})['controls'][0]
        for key in rule: self.assertEqual(enriched[key],rule[key])
        self.assertEqual(catalogue['controls'][0],rule)

    def test_missing_policy_module_stops_publication(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'manifest.json').write_text(json.dumps({'modules':[{'file':'missing.json'}]}))
            with self.assertRaises(ValueError): read_controls(d)

    def test_one_fresh_product_does_not_hide_stale_crude_or_missing_imports(self):
        coverage={'countries':{'SAU':{'world_total_series':[
            {'hs':'2709','flow':'X','months':['202509'],'latest_period':'202509','source':'test','unit':'kg'},
            {'hs':'2710','flow':'X','months':['202609'],'latest_period':'202609','source':'test','unit':'usd'}],
            'bilateral_series':[{'hs':'2709','flows':['X'],'period':'202508','source':'comtrade'}]}}}
        products=product_health(coverage)
        crude=next(p for p in products if p['hs']=='2709' and p['flow']=='X')
        self.assertIsNone(crude['latest_common_period'])
        self.assertFalse(crude['same_period_latest'])
        warnings=observation_warnings({'observations':{'products':products}},datetime(2026,10,12,tzinfo=timezone.utc))
        self.assertTrue(any(w['hs']=='2709' and w['issue']=='stale_or_invalid_observation' for w in warnings))
        self.assertTrue(any(w['hs']=='2709' and w['flow']=='M' and w['issue']=='not_acquired' for w in warnings))
        self.assertTrue(any(w['hs']=='2709' and w['issue']=='latest_period_mismatch' for w in warnings))

    def test_held_zero_is_observed_but_not_display_eligible(self):
        panel={'schema_version':'commodity-trade-comtrade-priority-v1','reporters':{'USA':{
            'flows':{'exports':{'commodities':{'crude_oil':{'hs':'2709','points':[
                {'month':'2026-06','value':100,'unit':'kg','publication':{'eligible_for_display':True}},
                {'month':'2026-08','value':0,'unit':'kg','publication':{'eligible_for_display':False}}]}}}}}}}
        c=coverage_report([panel],{})
        x=c['countries']['USA']['world_total_series'][0]
        self.assertEqual(x['latest_period'],'202608')
        self.assertEqual(x['latest_eligible_period'],'202606')
        self.assertEqual(x['publication_held_months'],['202608'])
        product=next(p for p in product_health(c) if p['reporter']=='USA' and p['hs']=='2709' and p['flow']=='X')
        self.assertEqual(product['world_sources'][0]['observed_history_gaps'],['202607'])
        self.assertEqual(product['comparison_status'],'date_alignment_only_not_a_denominator')

    def test_daily_resume_does_not_hide_missing_full_refresh(self):
        now=datetime(2026,10,12,tzinfo=timezone.utc)
        s={'scope':'scheduled','run_kind':'resume','last_attempt_at':now.isoformat(),
           'status':'partial','execution_status':'completed'}
        self.assertIn('full_collection_attempt_stale_or_missing',check_status(s,now))
        s.update(last_full_attempt_at=now.isoformat(),last_full_execution_status='completed')
        self.assertEqual(check_status(s,now),[])
        s['last_full_attempt_at']='2026-08-01T00:00:00+00:00'
        self.assertIn('full_collection_attempt_stale_or_missing',check_status(s,now))

    def test_resume_skips_world_sources_and_korea_requests(self):
        with tempfile.TemporaryDirectory() as d:
            stages=[]
            def stage(name,argv,status,*_):
                stages.append((name,argv))
                status['stages'].append({'stage':name,'status':'completed','exit_code':0})
                return True
            with patch.object(refresh_pipeline,'PUBLIC',Path(d)),patch.object(refresh_pipeline,'run_stage',side_effect=stage),patch.object(refresh_pipeline,'observation_health',return_value={}),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['refresh_pipeline.py','--batch','0','--resume-only']):
                self.assertEqual(refresh_pipeline.main(),0)
            self.assertEqual([s[0] for s in stages],['bilateral','coverage','release_gate'])
            self.assertIn('--resume-plan',stages[0][1])
            result=json.loads((Path(d)/'commodity_trade_refresh_status_v1.json').read_text())
            self.assertEqual(result['execution_status'],'completed')
            self.assertEqual(result['coverage_status'],'partial_observed_not_global_coverage')
            self.assertEqual(result['run_kind'],'resume')


if __name__=='__main__':
    unittest.main()
