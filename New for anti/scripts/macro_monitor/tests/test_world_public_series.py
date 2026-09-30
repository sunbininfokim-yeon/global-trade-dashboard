"""world_public_series: shared readers and card plumbing (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import world_public_series as w  # noqa: E402


class Periods(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(w.period_key("2026-08"), "2026-08-01")
        self.assertEqual(w.period_key("2026-Q2"), "2026-04-01")
        self.assertEqual(w.period_key("2026Q2"), "2026-04-01")
        self.assertEqual(w.period_key("2026 AUG"), "2026-08-01")
        self.assertEqual(w.period_key("2026 Q3"), "2026-07-01")
        self.assertEqual(w.period_key("2026-W39"), "2026-09-25")              # the ISO week's Friday
        self.assertIsNone(w.period_key("2026"))


class Transforms(unittest.TestCase):
    def test_monthly_last_keeps_the_last_day(self):
        pts, last = w.monthly_last([("2026-08-28", 1.0), ("2026-08-31", 2.0), ("2026-09-28", 3.0)])
        self.assertEqual(pts, [("2026-08-01", 2.0), ("2026-09-01", 3.0)])
        self.assertEqual(last, "2026-09-28")

    def test_money_format(self):
        k = w.money("C$", 1)
        self.assertEqual(w.ups._FORMATS[k](8.84), "+C$8.8B")
        self.assertEqual(w.ups._FORMATS[k](-3.0), "-C$3.0B")

    def test_trade_balance_only_for_common_months(self):
        f = w.Fetch()
        f._cache[("imf", "ITG", "XXX", w.IMF_EXPORTS)] = [("2026-06-01", 10e9), ("2026-07-01", 11e9)]
        f._cache[("imf", "ITG", "XXX", w.IMF_IMPORTS)] = [("2026-06-01", 12e9)]
        self.assertEqual(w.imf_trade_balance(f, "XXX"), [("2026-06-01", -2.0)])


class Readers(unittest.TestCase):
    def test_imf_picks_the_one_matching_series(self):
        xml = ('<Series INDICATOR="TRGMV_REVS" UNIT="USD" FREQUENCY="M"><Obs TIME_PERIOD="2026-M07" OBS_VALUE="7.0E11"/></Series>'
               '<Series INDICATOR="TRGMV_REVS" UNIT="XDR" FREQUENCY="M"><Obs TIME_PERIOD="2026-M07" OBS_VALUE="5.0E11"/></Series>')
        w._IMF_TEXT.clear()
        with patch.object(w, "_get", return_value=xml.encode()):
            self.assertEqual(w.read_imf("IL", "IND", w.IMF_RESERVES), [("2026-07-01", 7.0e11)])
            with self.assertRaises(ValueError):
                w.read_imf("IL", "IND", (("INDICATOR", "TRGMV_REVS"),))     # two series match
        w._IMF_TEXT.clear()

    def test_bcb_drops_dates_after_today(self):
        rows = b'[{"data":"01/01/2020","valor":"4.5"},{"data":"04/11/2099","valor":"13.75"}]'
        with patch.object(w, "_get", return_value=rows), patch.object(w.time, "sleep"):
            pts = w.read_bcb(432, start="01/01/2020")
        self.assertEqual(pts[0], ("2020-01-01", 4.5))
        self.assertNotIn("2099-11-04", dict(pts))

    def test_sidra_quarters(self):
        body = ('[{"V":"Valor","D3C":"Trimestre (Código)"},{"V":"0.5","D3C":"202602"},{"V":"...","D3C":"202601"}]').encode()
        with patch.object(w, "_get", return_value=body):
            self.assertEqual(w.read_sidra("t/x"), [("2026-04-01", 0.5)])


if __name__ == "__main__":
    unittest.main()
