import copy
import json
import sys
import tempfile
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_us_kr_preopen as runner


class RunnerTests(unittest.TestCase):
    def yahoo_chart(self):
        unix = lambda stamp: int(datetime.fromisoformat(stamp).timestamp())
        return {
            'timestamp': [unix('2026-11-06T09:30:00-05:00'), unix('2026-11-09T09:30:00-05:00')],
            'meta': {'symbol': 'QQQ', 'instrumentType': 'ETF', 'regularMarketPrice': 679.35,
                     'regularMarketTime': unix('2026-11-09T16:00:00-05:00')},
            'indicators': {'adjclose': [{'adjclose': [656.10, None]}], 'quote': [{'close': [656.10, None]}]},
        }

    @patch.object(runner.requests, 'get')
    def test_recovers_delayed_bar_from_exact_regular_close(self, get):
        chart = self.yahoo_chart()
        get.return_value.json.return_value = {'chart': {'result': [chart]}}
        pair, field = runner.yahoo_session_pair('QQQ', '2026-11-06', '2026-11-09', '2026-11-09T21:00:00Z')
        self.assertEqual([r['close'] for r in pair], [656.10, 679.35])
        self.assertEqual(field, 'regular_market_close_no_adjustment')
        chart['indicators']['adjclose'][0]['adjclose'][1] = 679.32
        pair, field = runner.yahoo_session_pair('QQQ', '2026-11-06', '2026-11-09', '2026-11-09T21:00:00Z')
        self.assertEqual(pair[-1]['close'], 679.32)
        self.assertEqual(field, 'adjusted_close')

    @patch.object(runner.requests, 'get')
    def test_refuses_intraday_stale_and_unadjustable_quotes(self, get):
        for case in ('intraday', 'stale', 'action', 'adjusted'):
            with self.subTest(case=case):
                chart = self.yahoo_chart()
                if case == 'intraday':
                    chart['meta']['regularMarketTime'] -= 60
                elif case == 'stale':
                    chart['meta']['regularMarketTime'] -= 3 * 86400
                elif case == 'action':
                    chart['events'] = {'dividends': {'1': {'amount': 1}}}
                else:
                    chart['indicators']['quote'][0]['close'][0] += 1
                get.return_value.json.return_value = {'chart': {'result': [chart]}}
                with self.assertRaisesRegex(ValueError, 'adjusted basis'):
                    runner.yahoo_session_pair('QQQ', '2026-11-06', '2026-11-09', '2026-11-09T21:00:00Z')

    def forecast(self,status='research_preopen_forecast',target='2026-11-05'):
        score={'probability':.51,'score_0_100':51,'direction':'UP','information_state':'model_score_with_calibration'}
        return {'status':status,'target_date':target,'generated_at':'2026-11-05T07:00:00+09:00',
                'model_id':'a'*64,'input_hashes':{'board':'one'},'results':{'KOSPI':{'scores':{'opening_up':score}}} if status!='unavailable' else {},
                'KR_source_date':'2026-11-04','required_US_session':'2026-11-04',
                'forecast_cutoff_KST':'2026-11-05T08:30:00+09:00','trained_through':'2026-10-22','reasons':[]}

    def test_first_record_is_immutable_and_revision_not_primary(self):
        with tempfile.TemporaryDirectory() as td:
            f=self.forecast();first,path=runner.archive_forecast(f,td);original=path.read_bytes()
            self.assertTrue(first['eligible_for_primary_evaluation'])
            same=copy.deepcopy(f);same['generated_at']='2026-11-05T07:10:00+09:00'
            old,samepath=runner.archive_forecast(same,td)
            self.assertEqual(old['generated_at'],f['generated_at']);self.assertEqual(path,samepath)
            changed=copy.deepcopy(same);changed['input_hashes']['board']='two'
            revision,rpath=runner.archive_forecast(changed,td)
            self.assertFalse(revision['eligible_for_primary_evaluation']);self.assertNotEqual(path,rpath)
            self.assertEqual(path.read_bytes(),original)

    def test_unavailable_and_replay_never_become_first_forecast(self):
        with tempfile.TemporaryDirectory() as td:
            for status in ['unavailable','retrospective_replay']:
                record,path=runner.archive_forecast(self.forecast(status),td)
                self.assertIsNone(path);self.assertFalse(record['eligible_for_primary_evaluation'])
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_failed_same_target_refresh_keeps_explicit_previous_record(self):
        old=runner.display_payload(self.forecast())
        failed=self.forecast('unavailable');failed['reasons']=['source missing']
        new=runner.display_payload(failed,old)
        self.assertEqual(new['cards'],old['cards']);self.assertEqual(new['generated_at'],old['generated_at'])
        self.assertEqual(new['refresh']['status'],'unavailable')

    def test_new_target_does_not_inherit_yesterday_score(self):
        old=runner.display_payload(self.forecast(target='2026-11-04'))
        new=runner.display_payload(self.forecast('unavailable'),old)
        self.assertEqual(new['cards'],[]);self.assertEqual(new['target_date'],'2026-11-05')
        self.assertEqual(new['last_available']['target_date'],'2026-11-04')

    def test_up_down_complements_only_for_direction_events(self):
        f=self.forecast()
        scores=f['results']['KOSPI']['scores']
        scores['closing_up']=dict(scores['opening_up'],probability=.43,score_0_100=43,direction='DOWN')
        scores['direction_persists']=dict(scores['opening_up'],direction='MAINTAIN')
        original=copy.deepcopy(f)
        payload=runner.display_payload(f)
        out=payload['cards'][0]['scores']
        self.assertEqual(out['opening_up']['up_probability'],.51)
        self.assertEqual(out['opening_up']['down_probability'],.49)
        self.assertAlmostEqual(out['closing_up']['down_probability'],.57)
        self.assertNotIn('down_probability',out['direction_persists'])
        self.assertIn('not estimated',payload['probability_contract']['flat_probability'])
        self.assertEqual(f,original)

    def test_reference_only_probabilities_remain_reference_only(self):
        f=self.forecast()
        f['results']['KOSPI']['scores']['opening_up'].update(direction='REFERENCE_ONLY',information_state='recent_base_rate_only')
        score=runner.display_payload(f)['cards'][0]['scores']['opening_up']
        self.assertEqual(score['direction'],'REFERENCE_ONLY')
        self.assertEqual(score['information_state'],'recent_base_rate_only')

    def test_neutral_and_invalid_display_probabilities(self):
        f=self.forecast()
        f['results']['KOSPI']['scores']['opening_up'].update(probability=.5,score_0_100=50,direction='NEUTRAL')
        score=runner.display_payload(f)['cards'][0]['scores']['opening_up']
        self.assertEqual((score['up_probability'],score['down_probability']),(.5,.5))
        self.assertEqual(score['direction'],'NEUTRAL')
        for value in [float('nan'),-1,2,True,None]:
            f['results']['KOSPI']['scores']['opening_up']['probability']=value
            with self.assertRaises(ValueError):runner.display_payload(f)

    def test_raw_merge_only_changes_detailed_leaf(self):
        b={'kr':{'investor_nets':{'detailed_15007':{'old':1},'other':99}},'us_oi_snap':{'keep':2}}
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'2026-11-04';folder.mkdir()
            for n in runner.REQUIRED_FILES:(folder/n).write_text('fixture')
            with patch.object(runner,'merge_date_folder',return_value={'new':2}):
                out,report=runner.board_with_raw(b,Path(td),'2026-11-04')
            self.assertEqual(b['kr']['investor_nets']['detailed_15007'],{'old':1})
            self.assertEqual(out['us_oi_snap'],b['us_oi_snap'])
            self.assertEqual(out['kr']['investor_nets']['other'],99)
            self.assertEqual(report['status'],'merged_expected_source_only')

    def test_no_fallback_to_old_raw_folder(self):
        b={'kr':{'investor_nets':{'detailed_15007':{}}}}
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'2026-11-03').mkdir()
            out,r=runner.board_with_raw(b,Path(td),'2026-11-04')
            self.assertEqual(out,b);self.assertEqual(r['date'],'2026-11-04')
            self.assertEqual(r['status'],'expected_folder_incomplete')

    def test_missing_window_history_is_backfilled_but_future_folder_is_not_used(self):
        b={'kr':{'investor_nets':{'detailed_15007':{}}}}
        with tempfile.TemporaryDirectory() as td:
            for day in ['2026-11-03','2026-11-04','2026-11-05']:
                folder=Path(td)/day;folder.mkdir()
                for n in runner.REQUIRED_FILES:(folder/n).write_text('fixture')
            with patch.object(runner,'merge_date_folder',return_value={}) as merge:
                out,r=runner.board_with_raw(b,Path(td),'2026-11-04')
            self.assertEqual(r['merged_dates'],['2026-11-03','2026-11-04'])
            self.assertEqual(merge.call_count,2)

    def test_partial_kr_window_not_zero_filled(self):
        with patch.object(runner,'fetch_naver_chart',return_value={}):
            with self.assertRaises(ValueError):runner.collect_kr_prices('2026-11-04',datetime.now())

    def args(self,root):
        model=root/'model.json';model.write_text('{}')
        board=root/'board.json';board.write_text('{}')
        return SimpleNamespace(model=model,board=board,target='2026-11-05',replay=False,
            stocks=None,kospi=None,us=None,krx_root=None,refresh_prices=True,
            run_dir=root/'run',archive_dir=root/'archive',public_output=None)

    def test_replay_publication_rejected_before_collection(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.args(Path(td));a.replay=True;a.public_output=Path(td)/'us_kr_direction_v1.json'
            with self.assertRaises(ValueError):runner.run(a)
            self.assertFalse(a.run_dir.exists())

    def test_unclosed_session_skips_network(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td));failed=self.forecast('unavailable')
            with patch.object(runner,'validate_model'),patch.object(runner,'collect_kr_prices') as kr,patch.object(runner,'collect_us_prices') as us,patch.object(runner,'predict',return_value=failed):
                code=runner.run(args,now=datetime.fromisoformat('2026-11-04T20:00:00+09:00'))
            self.assertEqual(code,2);kr.assert_not_called();us.assert_not_called()

    def test_generation_time_is_after_collection_not_start_time(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td));times=iter([datetime.fromisoformat(t) for t in
                ['2026-11-05T08:29:00+09:00','2026-11-05T08:31:00+09:00']])
            with patch.object(runner,'validate_model'),patch.object(runner,'collect_kr_prices',return_value=({'candidates':[]},{'candidates':[]})),patch.object(runner,'collect_us_prices',return_value={'symbols':{}}),patch.object(runner,'predict',return_value=self.forecast('unavailable')) as predict:
                runner.run(args,clock=lambda:next(times))
            self.assertEqual(predict.call_args.kwargs['now'].minute,31)

    def test_collection_failure_blocks_successful_stale_inference(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td))
            with patch.object(runner,'validate_model'),patch.object(runner,'collect_kr_prices',side_effect=OSError('source offline')),patch.object(runner,'predict',return_value=self.forecast()):
                code=runner.run(args,now=datetime.fromisoformat('2026-11-05T08:00:00+09:00'))
            self.assertEqual(code,2)
            out=json.loads((args.run_dir/'forecast.json').read_text());self.assertEqual(out['results'],{})
            attempts=list(args.archive_dir.glob('*/'+'a'*16+'/attempts/*.json'))
            self.assertEqual(len(attempts),1)
            self.assertEqual(json.loads(attempts[0].read_text())['status'],'unavailable')
            self.assertFalse(list(args.archive_dir.glob('*/'+'a'*16+'/first.json')))

    def test_attempt_receipt_preserves_refresh_time_and_replay_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            f=self.forecast('unavailable');f['reasons']=['missing source']
            path=runner.record_attempt(f,td)
            self.assertEqual(json.loads(path.read_text())['reasons'],['missing source'])
            self.assertEqual(runner.record_attempt(f,td),path)
            self.assertIsNone(runner.record_attempt(self.forecast('retrospective_replay'),td))
            self.assertEqual(len(list(Path(td).rglob('*.json'))),1)

    def test_comparison_change_creates_revision_without_replacing_primary(self):
        with tempfile.TemporaryDirectory() as td:
            f=self.forecast();_,first=runner.archive_forecast(f,td)
            original=first.read_bytes();f['comparisons']={'status':'available','comparison_id':'new'}
            r,path=runner.archive_forecast(f,td)
            self.assertNotEqual(path,first);self.assertFalse(r['eligible_for_primary_evaluation'])
            self.assertEqual(first.read_bytes(),original)

    def test_comparison_failure_does_not_suppress_primary_forecast(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td));args.comparison_model=Path(td)/'absent.json'
            with patch.object(runner,'validate_model'),patch.object(runner,'collect_kr_prices',return_value=({'candidates':[]},{'candidates':[]})),patch.object(runner,'collect_us_prices',return_value={'symbols':{}}),patch.object(runner,'predict',return_value=self.forecast()):
                code=runner.run(args,now=datetime.fromisoformat('2026-11-05T08:00:00+09:00'))
            self.assertEqual(code,0)
            f=json.loads((args.run_dir/'forecast.json').read_text())
            self.assertEqual(f['comparisons']['status'],'unavailable')
            self.assertEqual(f['status'],'research_preopen_forecast')


if __name__=='__main__':unittest.main()
