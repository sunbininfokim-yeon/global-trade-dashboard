import copy
import tempfile
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import us_kr_direction_engine as engine
from option_direction_model import digest,read


class FrozenDirectionEngineTests(unittest.TestCase):
    def artifact(self):
        a={'schema_version':engine.VERSION,'features':engine.FEATURES,
           'trained_through':'2026-10-22','created_at':'2026-10-25T00:00:00+00:00',
           'implementation_sha256':engine.code_hashes(),
           'runtime_versions':{p:version(p) for p in engine.PACKAGES},'validation':'test fixture'}
        a['model_id']=digest(a)
        return a

    def test_model_modification_is_rejected(self):
        a=self.artifact();a['trained_through']='2026-10-23'
        with self.assertRaises(ValueError):engine.validate_model(a)

    def test_code_and_runtime_changes_need_new_version(self):
        for key,val in [('implementation_sha256',{}),('runtime_versions',{})]:
            a=self.artifact();a[key]=val
            a['model_id']=digest({k:v for k,v in a.items() if k!='model_id'})
            with self.assertRaises(ValueError):engine.validate_model(a)

    def test_no_prediction_after_cutoff_without_replay(self):
        r=engine.predict(self.artifact(),{},{},{},'2026-11-02',
                         now=datetime.fromisoformat('2026-11-02T08:31:00+09:00'))
        self.assertEqual(r['status'],'unavailable');self.assertFalse(r['results'])
        self.assertTrue(any('cutoff passed' in s for s in r['reasons']))

    def test_unclosed_US_session_never_used(self):
        r=engine.predict(self.artifact(),{},{},{},'2026-11-05',
                         now=datetime.fromisoformat('2026-11-04T20:00:00+09:00'))
        self.assertIn('required US session not closed',r['reasons'])

    def test_missing_fresh_inputs_are_unavailable_not_zero(self):
        r=engine.predict(self.artifact(),{},{},{},'2026-11-05',
                         now=datetime.fromisoformat('2026-11-05T08:00:00+09:00'))
        self.assertEqual(r['status'],'unavailable');self.assertEqual(r['results'],{})
        self.assertEqual(set(r['input_errors']),set(engine.TICKERS))

    def test_cannot_backdate_before_creation(self):
        a=self.artifact();a['created_at']='2026-11-04T00:00:00+00:00'
        a['model_id']=digest({k:v for k,v in a.items() if k!='model_id'})
        with self.assertRaises(ValueError):
            engine.predict(a,{},{},{},'2026-11-02',now=datetime.fromisoformat('2026-11-02T08:00:00+09:00'))

    def test_event_probability_is_not_always_up_direction(self):
        self.assertEqual(engine.interpret(.8,'direction_persists',False),'MAINTAIN')
        self.assertEqual(engine.interpret(.2,'opening_extends',False),'NO_EXTENSION')
        self.assertEqual(engine.interpret(.8,'opening_up',True),'REFERENCE_ONLY')
        self.assertEqual(engine.interpret(.5,'opening_up',False),'NEUTRAL')

    def test_immutable_idempotent_output_preserves_original_time(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'forecast.json';first={'generated_at':'first','score':51}
            self.assertEqual(engine.write_immutable(p,first),'written')
            self.assertEqual(engine.write_immutable(p,{'generated_at':'later','score':51}),'unchanged')
            self.assertEqual(read(p),first)
            with self.assertRaises(ValueError):engine.write_immutable(p,{'generated_at':'later','score':52})
            self.assertEqual(read(p),first)


if __name__=='__main__':unittest.main()
