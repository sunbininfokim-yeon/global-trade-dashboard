import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(importlib.util.find_spec("exchange_calendars") and importlib.util.find_spec("sklearn"),
                     "optional direction research dependencies required")
class DynamicsResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from option_direction_model import calendar
        from research_direction_diagnostics import ReviewedCalendar
        cls.cal=ReviewedCalendar(calendar())

    def fixture(self):
        return {"dates":["2026-10-06","2026-10-07","2026-10-08"],
            "option_oi":{"call_oi":[100,110,121],"put_oi":[200,180,162],"atm_iv":[20,22,24],
                         "expiry":["202610","202610","202611"]},
            "futures_front":{"open_interest":[1000,1050,1100],"contract":["202612"]*3}}

    def test_changes_are_same_contract_and_next_session_only(self):
        from research_option_dynamics import dynamic_features
        values,excluded=dynamic_features(self.fixture(),self.cal)
        self.assertAlmostEqual(values["2026-10-07"][0],np.log(1.1))
        self.assertAlmostEqual(values["2026-10-07"][3],.02)
        self.assertNotIn("2026-10-08",values)
        self.assertIn("expiry_changed",excluded["2026-10-08"])

    def test_missing_day_is_not_bridged(self):
        from research_option_dynamics import dynamic_features
        d=self.fixture()
        d["dates"][1]="2026-10-05" # Actual holiday, not the required preceding session.
        values,_=dynamic_features(d,self.cal)
        self.assertNotIn("2026-10-08",values)

    def test_future_change_does_not_alter_past_change(self):
        from research_option_dynamics import dynamic_features
        d=self.fixture();before,_=dynamic_features(d,self.cal)
        d["option_oi"]["put_oi"][-1]=999999
        after,_=dynamic_features(d,self.cal)
        self.assertEqual(before["2026-10-07"],after["2026-10-07"])

    def test_calibrator_cannot_reverse_order_to_fake_reliability(self):
        from research_option_dynamics import sigmoid_calibration
        z=np.tile([-2.,-1.,1.,2.],30);y=np.tile([1,1,0,0],30)
        c=sigmoid_calibration(z,y)
        self.assertAlmostEqual(c["slope"],0,places=6)
        self.assertTrue(c["at_zero_slope"])

    def test_calibrator_learns_positive_order_when_present(self):
        from research_option_dynamics import sigmoid_calibration
        z=np.tile([-2.,-1.,1.,2.],30);y=np.tile([0,0,1,1],30)
        c=sigmoid_calibration(z,y)
        self.assertGreater(c["slope"],0)
        self.assertFalse(c["at_zero_slope"])

    def test_train_calibration_test_label_boundaries_are_purged(self):
        from research_option_dynamics import splits
        days=self.cal.sessions_in_range("2019-01-02","2026-10-30").strftime("%Y-%m-%d").tolist()
        rows=[{"date":d,"target_date":days[i+1],"y":i%2} for i,d in enumerate(days[:-1])]
        folds=list(splits(rows));self.assertTrue(folds)
        for start,train,calibration,test in folds:
            self.assertLess(max(r["target_date"] for r in train),min(r["date"] for r in calibration))
            self.assertLess(max(r["target_date"] for r in calibration),min(r["date"] for r in test))
            self.assertTrue(all(r["date"]>=start for r in test))

    def test_lag_only_uses_previous_nonprice_inputs(self):
        from research_option_dynamics import assemble
        dates=["2026-10-06","2026-10-07"]
        base=[{"date":day,"target_date":self.cal.next_session(day).strftime("%Y-%m-%d"),"y":1,"return":.01,
               "price_only":[1,2,3,4,5,6],"option_only":[i+1]*4} for i,day in enumerate(dates)]
        levels={d:[10+i]*5 for i,d in enumerate(dates)};changes={d:[20+i]*4 for i,d in enumerate(dates)}
        with patch("research_option_dynamics.extras",return_value=(levels,{})),patch("research_option_dynamics.dynamic_features",return_value=(changes,{})):
            rows,_=assemble(base,{},self.cal,1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["date"],dates[1]);self.assertEqual(rows[0]["feature_source_date"],dates[0])
        self.assertEqual(rows[0]["baseline"][-4:],[1]*4)
        self.assertEqual(rows[0]["levels"][-5:],[10]*5)

    def test_surface_excludes_night_and_other_expiry(self):
        from extract_private_option_surface import surface_day
        rows=[]
        for kind,strike,iv in [("call",100,20),("put",100,21),("put",95,25),("call",105,23)]:
            rows.append({"session":"regular","quality":"observed","expiry_or_contract_month":"202611",
                         "option_type":kind,"strike":strike,"implied_volatility":iv,"collected_at":"fixed"})
        rows.append({**rows[0],"session":"night","implied_volatility":99})
        rows.append({**rows[0],"expiry_or_contract_month":"202612","implied_volatility":99})
        p=surface_day(rows,100,"202611")
        self.assertEqual(p["status"],"observed_research")
        np.testing.assert_allclose(p["features"],[.04,.03,.01])

    def test_surface_missing_wing_is_not_interpolated(self):
        from extract_private_option_surface import surface_day
        rows=[{"session":"regular","quality":"observed","expiry_or_contract_month":"202611",
               "option_type":t,"strike":100,"implied_volatility":20} for t in ("call","put")]
        self.assertEqual(surface_day(rows,100,"202611")["status"],"unavailable")

    def test_surface_conflicting_same_time_quote_is_withheld(self):
        from extract_private_option_surface import surface_day
        r={"session":"regular","quality":"observed","expiry_or_contract_month":"202611",
           "option_type":"call","strike":100,"implied_volatility":20,"collected_at":"fixed"}
        p=surface_day([r,{**r,"implied_volatility":30}],100,"202611")
        self.assertEqual(p["status"],"unavailable")

    def shadow_fixture(self):
        from shadow_direction_engine import VERSION,BASE_NAMES,code_hashes
        from option_direction_model import digest
        import exchange_calendars as xc
        a={"schema_version":VERSION,"features":BASE_NAMES,"calendar_version":xc.__version__,
           "trained_through":"2026-10-30","created_at":"2026-11-01T01:00:00+00:00", "validation":"shadow only",
           "target":"next session close > open", "model":{"mean":[0]*10,"scale":[1]*10,"coef":[.1]*10,"intercept":0},
           "calibrator":{"slope":.5,"intercept":0,"at_zero_slope":False},"implementation_sha256":code_hashes()}
        a["model_id"]=digest(a)
        return a,{}, {"candidates":[{"ticker":"069500","rows":[]}]}

    def shadow_prediction(self,when,missing_price=False):
        from datetime import datetime
        from shadow_direction_engine import predict_shadow
        artifact,board,prices=self.shadow_fixture()
        with patch("shadow_direction_engine.fit",side_effect=AssertionError("must stay frozen")), \
             patch("shadow_direction_engine.option_features",return_value={"2026-10-30":[.1]*4}), \
             patch("shadow_direction_engine.price_data",return_value=({} if missing_price else {"2026-10-30":[.1,.2]},{})), \
             patch("shadow_direction_engine.richer_price_features",return_value=[{"price_only":[.1]*6}]):
            return predict_shadow(artifact,board,prices,"2026-10-30",datetime.fromisoformat(when))

    def test_shadow_never_refits_and_marks_before_open(self):
        r=self.shadow_prediction("2026-11-01T02:00:00+00:00")
        self.assertEqual(r["status"],"shadow_research")
        self.assertEqual(r["target_date"],"2026-11-02")
        self.assertAlmostEqual(r["probability_up"]+r["probability_non_up"],1)

    def test_shadow_after_open_is_retrospective_not_forward(self):
        self.assertEqual(self.shadow_prediction("2026-11-02T06:00:00+00:00")["status"],"retrospective_research")

    def test_shadow_cannot_backdate_before_model_existed(self):
        r=self.shadow_prediction("2026-10-31T02:00:00+00:00")
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["probability_up"])

    def test_shadow_requires_fresh_etf_price_as_well_as_options(self):
        r=self.shadow_prediction("2026-11-01T02:00:00+00:00",missing_price=True)
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["direction"])


if __name__=="__main__":unittest.main()
