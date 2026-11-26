from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import us_realestate as ure  # noqa: E402


class Transforms(unittest.TestCase):
    def test_spread_uses_same_or_previous_day(self):
        mort = [("2026-11-19", 7.20), ("2026-11-26", 7.21)]
        dgs10 = [("2026-11-18", 4.80), ("2026-11-19", 4.90), ("2026-11-25", 4.91)]   # no 11-26 print yet
        out = ure.spread_on_dates(mort, dgs10)
        self.assertEqual([d for d, _ in out], ["2026-11-19", "2026-11-26"])
        self.assertAlmostEqual(out[0][1], 230.0)
        self.assertAlmostEqual(out[1][1], 230.0)

    def test_spread_skips_dates_before_the_other_series(self):
        self.assertEqual(ure.spread_on_dates([("2000-01-01", 8.0)], [("2001-01-01", 6.0)]), [])

    def test_ratio_index_averages_to_100(self):
        a = [("1987-01-01", 100.0), ("1987-02-01", 200.0), ("1987-03-01", 300.0)]
        b = [("1987-01-01", 100.0), ("1987-02-01", 100.0), ("1987-03-01", 100.0)]
        out = ure.ratio_index(a, b)
        self.assertAlmostEqual(sum(v for _, v in out) / 3, 100.0)
        self.assertAlmostEqual(out[2][1], 150.0)

    def test_extra_note_names_both_peaks(self):
        pts = [("2006-05-01", 132.9), ("2012-01-01", 80.0), ("2022-05-01", 135.1), ("2026-09-01", 120.2)]
        n = ure.extra_note("price_to_rent", pts)
        self.assertIn("135.1(2022-05)", n)
        self.assertIn("132.9(2006-05)", n)
        self.assertIn("지금 120.2", n)
        self.assertEqual(ure.extra_note("mortgage_30y", pts), "")

    def test_extra_note_delinquency_and_spread(self):
        d = [("1991-01-01", 12.0), ("2010-01-01", 8.7), ("2026-04-01", 1.5)]
        n = ure.extra_note("delinq_cre", d)
        self.assertIn("최고 12.00%(1991Q1)", n)
        self.assertIn("금융위기 이후 최고 8.70%(2010Q1)", n)
        sp = [(f"2000-01-{i:02d}", float(v)) for i, v in enumerate(range(100, 300, 10), 1)]
        self.assertIn("중앙값 200bp", ure.extra_note("mortgage_spread", sp))

    def test_every_spec_has_a_transform_and_a_format(self):
        fake = lambda sid: [("2020-01-01", 1.0), ("2021-01-01", 2.0)]
        census = lambda: {"Data center": [("2020-01-01", 1000.0)]}
        for sid, spec in ure.SPECS.items():
            ure.series_for(sid, fake, census)
            self.assertIn(spec.fmt, ups._FORMATS)


class Apply(unittest.TestCase):
    def pack(self):
        return {"ui": {"category_tabs": [{"id": "liquidity", "order": 1}, {"id": "inflation", "order": 6}]},
                "countries": [{"iso3": "USA", "active_categories": ["liquidity"], "categories": {"liquidity": []}, "indicators": []}]}

    def patch(self, sid):
        spec = ure.SPECS[sid]
        return ups.build_patch(spec, [("2026-07-01", 1.5), ("2026-10-01", 1.6)], retrieved_at="2026-11-26T00:00:00Z")

    def test_creates_tab_and_cards_once(self):
        p = self.pack()
        patches = {sid: self.patch(sid) for sid in ("mortgage_30y", "bank_cre_loans")}
        changed = ure.apply(p, patches)
        self.assertIn("(tab)", changed)
        usa = p["countries"][0]
        self.assertEqual([t["id"] for t in p["ui"]["category_tabs"]], ["liquidity", "inflation", "realestate"])
        self.assertEqual(usa["active_categories"][-1], "realestate")
        self.assertEqual([c["id"] for c in usa["categories"]["realestate"]], ["mortgage_30y", "bank_cre_loans"])
        self.assertTrue(next(i for i in usa["indicators"] if i["id"] == "bank_cre_loans")["yoy_line"])
        snap = json.dumps(p, sort_keys=True)
        self.assertEqual(ure.apply(p, {sid: self.patch(sid) for sid in patches}), [])
        self.assertEqual(json.dumps(p, sort_keys=True), snap)

    def test_missing_series_makes_no_empty_card(self):
        p = self.pack()
        ure.apply(p, {"mortgage_30y": self.patch("mortgage_30y")})
        ids = [i["id"] for i in p["countries"][0]["indicators"]]
        self.assertEqual(ids, ["mortgage_30y"])


class Capex(unittest.TestCase):
    def raw(self):
        months = [f"{y}-{m:02d}-01" for y in range(2019, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
        quarters = [d for d in months if d[5:7] in ("01", "04", "07")]
        out = {}
        for label, _, _, cadence, k in ure.CAPEX:
            pts = months if cadence == "monthly" else quarters
            out[label] = [(d, (1000.0 if k == 1e-3 else 1.0) * (1 + i * 0.01)) for i, d in enumerate(pts)]
        return out

    def test_three_panels_on_one_monthly_axis(self):
        panels = ure.capex_panels(self.raw(), months=24)
        self.assertEqual([p["id"] for p in panels], ["capex_index", "capex_construction", "capex_yoy"])
        for p in panels:
            self.assertEqual(len(p["dates"]), 24)
            self.assertTrue(p["markers"])
            self.assertTrue(all(len(s["values"]) == 24 for s in p["series"]))
        self.assertEqual(panels[0]["dates"][-1], "26.9")
        self.assertEqual(len(panels[0]["series"]), 7)
        self.assertEqual(len(panels[1]["series"]), 4)                     # the four construction lines only

    def test_index_starts_at_100_and_quarters_sit_mid_quarter(self):
        p = ure.capex_panels(self.raw(), months=24)[0]
        for s in p["series"]:
            self.assertEqual(next(v for v in s["values"] if v is not None), 100.0)
        q = next(s for s in p["series"] if s["label"].endswith("(분기)"))
        on = [p["dates"][i] for i, v in enumerate(q["values"]) if v is not None]
        self.assertTrue(all(int(d.split(".")[1]) in (2, 5, 8, 11) for d in on))

    def test_census_two_digit_years(self):
        import io
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Value of Private Construction"])
        ws.append(["Date", "Data center", "Manufacturing"])
        ws.append(["Sep-26p", 96462, 167226])
        ws.append(["Jan-93", None, 30000])
        buf = io.BytesIO()
        wb.save(buf)
        out = ure.parse_census_private(buf.getvalue())
        self.assertEqual(out["Data center"], [("2026-09-01", 96462.0)])
        self.assertEqual(out["Manufacturing"][0], ("1993-01-01", 30000.0))


class CreditMerge(unittest.TestCase):
    def test_us_panels(self):
        from macro_monitor import credit_merge as cm
        fake = lambda sid: [(f"20{y:02d}-{m:02d}-01", 1.0 + y / 10) for y in range(15, 27) for m in (1, 4, 7, 10)]
        panels = cm.us_panels(fake, quarters=8)
        self.assertEqual([p["id"] for p in panels], ["us_delinq_rates", "us_chargeoff_rates", "us_delinq_vs_chargeoff"])
        self.assertEqual(panels[0]["dates"][-1], "26.4Q")
        self.assertEqual(len(panels[0]["series"]), 6)

    def test_kr_panels_and_idempotent_apply(self):
        from macro_monitor import credit_merge as cm
        seg = {"id": "segments", "type": "bars", "unit": "%", "dates": ["26.1Q", "26.2Q"],
               "series": [{"label": "가계", "values": [0.4, 0.4]}, {"label": "기업", "values": [0.7, 0.68]}]}
        flow = {"id": "flow", "type": "stack", "unit": "조원", "dates": ["26.1Q", "26.2Q"],
                "series": [{"label": "신규연체", "values": [8.0, 8.75]}, {"label": "상각", "values": [-3.0, -3.09]}]}
        pack = {"countries": [{"iso3": "KOR", "categories": {"liquidity": [{"id": "delinq_monthly", "label_ko": "대출 연체율(월)"}]},
                               "indicators": [
                                   {"id": "delinq_monthly", "label_ko": "대출 연체율(월)", "panels": [
                                       {"id": "m_segments", "type": "lines", "unit": "%", "dates": ["26.9"], "series": [{"label": "전체", "values": [0.59]}]}]},
                                   {"id": "delinq_all", "panels": [seg, flow]}]}]}
        self.assertEqual(cm.apply(pack, None), ["KOR"])
        host = pack["countries"][0]["indicators"][0]
        ids = [p["id"] for p in host["panels"]]
        self.assertEqual(ids, ["m_segments", "kr_hh_corp_q", "kr_writeoff"])
        self.assertTrue(all(p.get("markers") for p in host["panels"]))
        wo = host["panels"][2]
        self.assertEqual(wo["series"][1]["values"], [3.0, 3.09])                 # charge-offs drawn as positive amounts
        self.assertEqual(pack["countries"][0]["categories"]["liquidity"][0]["label_ko"], cm.KR_LABEL)
        self.assertEqual(cm.apply(pack, None), [])


if __name__ == "__main__":
    unittest.main()
