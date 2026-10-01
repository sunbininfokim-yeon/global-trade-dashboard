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


class MoreReaders(unittest.TestCase):
    def test_mof_months_stop_at_the_last_closed_quarter(self):
        rows = [
            "年,月,日,Year,Month,Day,金額(amount),売買通貨,Currency pairs",
            "令和8年,4月,30日,2026,Apr,30,\"62,787\",米ドル売り・日本円買い,the US dollar (sold) the Japanese yen (bought)",
            ",5月,1日,,May,1,\"54,561\",米ドル売り・日本円買い,the US dollar (sold) the Japanese yen (bought)",
            "令和8年4月〜6月期計,,,April - June 2026,,,\"117,348\",,",
            "令和8年,7月,1日,2026,Jul,1,100,米ドル買い・日本円売り,the Japanese yen (sold) the US dollar (bought)",
        ]
        with patch.object(w, "_get", return_value="\n".join(rows).encode("shift_jis")):
            pts = w.read_mof_intervention()
        self.assertEqual(pts, [("2026-04-01", -6.2787), ("2026-05-01", -5.4561), ("2026-06-01", 0.0)])

    def test_ecb_programme_holdings_and_net(self):
        app = ("x\n,,a\n2026,July,-73,-1554,-1237,-24306,0,0,0,0,2019,191303,218192,1681781\n"
               ",August,-44,-1566,-1227,-12570,0,0,0,0,1976,189737,216966,1669210\n")
        with patch.object(w, "_get", return_value=app.encode()):
            got = w.read_ecb_programme("APP")
        self.assertEqual(got["holdings"][-1], ("2026-08-01", 1976 + 189737 + 216966 + 1669210))
        self.assertEqual(got["net"][0], ("2026-07-01", -73 - 1554 - 1237 - 24306))

    def test_tesouro_picks_the_maturity_nearest_ten_years(self):
        csv_text = ("Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha\n"
                    "Tesouro Prefixado com Juros Semestrais;01/01/2027;31/08/2026;13,10\n"
                    "Tesouro Prefixado com Juros Semestrais;01/01/2037;31/08/2026;13,55\n"
                    "Tesouro Selic;01/03/2031;31/08/2026;0,08\n")
        with patch.object(w, "_get", return_value=csv_text.encode("latin-1")):
            pts, last = w.read_tesouro_prefixado_10y()
        self.assertEqual((pts, last), ([("2026-08-01", 13.55)], "2026-08-31"))


if __name__ == "__main__":
    unittest.main()
