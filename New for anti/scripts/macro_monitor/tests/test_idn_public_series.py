"""Indonesia (BPS WebAPI + FRED + Yahoo): idn_public_series. No network, no real key."""
from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import idn_public_series as idn  # noqa: E402

FAKE_KEY = "0123456789abcdef-fake"


def bps_doc(var, region, cells, years=((125, "2025"), (126, "2026")), turvar="0"):
    return {"status": "OK", "data-availability": "available", "turvar": [{"val": turvar, "label": "None"}],
            "tahun": [{"val": v, "label": lab} for v, lab in years],
            "datacontent": {f"{region}{var}{turvar}{y}{p}": v for (y, p), v in cells.items()}}


class Parse(unittest.TestCase):
    def test_cells_are_read_by_region_year_and_period(self):
        doc = bps_doc(2249, 151, {(126, 7): 2.9, (126, 8): 3.2, (125, 13): 1.6})
        doc["datacontent"]["1" + "2249" + "0" + "126" + "8"] = 99.0          # another region, same period
        self.assertEqual(idn.parse_bps(doc, 2249, 151, idn.MONTHS), [("2026-07-01", 2.9), ("2026-08-01", 3.2)])

    def test_quarters_and_survey_months(self):
        doc = bps_doc(1956, 800, {(126, 31): 3400000.0, (126, 32): 3576209.0, (126, 35): 1.0})
        self.assertEqual(idn.parse_bps(doc, 1956, 800, idn.QUARTERS), [("2026-01-01", 3400000.0), ("2026-04-01", 3576209.0)])
        doc = bps_doc(543, 9999, {(126, 189): 4.68, (125, 190): 4.85})
        self.assertEqual(sorted(idn.parse_bps(doc, 543, 9999, idn.SURVEYS)), [("2025-08-01", 4.85), ("2026-02-01", 4.68)])

    def test_three_years_per_request(self):
        self.assertEqual(idn.year_chunks(2015, 2026), ["115:117", "118:120", "121:123", "124:126"])

    def test_error_document_raises(self):
        with self.assertRaises(ValueError):
            idn.parse_bps({"status": "Error", "message": "'th' parameter is required"}, 1, 1, idn.MONTHS)


class Key(unittest.TestCase):
    def test_the_key_never_reaches_an_error_message(self):
        err = urllib.error.HTTPError(f"https://webapi.bps.go.id/v1/api/x/key/{FAKE_KEY}/", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=err), patch("time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                idn._get_json(2249, "125:126", FAKE_KEY)
        self.assertNotIn(FAKE_KEY, str(ctx.exception))
        self.assertIn("HTTP 403", str(ctx.exception))

    def test_without_a_key_nothing_is_fetched(self):
        with self.assertRaises(RuntimeError):
            idn.Sources(key=None).series("cpi_yoy")

    def test_card_links_are_public_pages(self):
        for spec in idn.SPECS.values():
            for url in spec.source_urls:
                self.assertNotIn("/key/", url)
                self.assertNotIn("webapi", url)


def fake_sources():
    months = [(f"{y}-{m:02d}-01", 100.0 + i) for i, (y, m) in enumerate((y, m) for y in range(2019, 2027) for m in range(1, 13))]
    data = {
        "cpi_yoy": [("2026-08-01", 3.2)], "unemployment": [("2025-08-01", 4.85), ("2026-02-01", 4.68)],
        "bi_rate": [("2026-08-01", 5.75)], "m2": months,
        "gdp": [(f"{y}-{m:02d}-01", 3000000.0 + 10000 * i) for i, (y, m) in enumerate((y, m) for y in (2025, 2026) for m in (1, 4, 7, 10))],
        "export_id": [("2025-07-01", 24000.0), ("2026-07-01", 26216.7)], "trade_balance": [("2026-07-01", 121.9)],
    }
    return idn.Sources(key=FAKE_KEY, bps=lambda name, key: data[name], fred=lambda s: [("2026-07-01", 133983.1)])


class Country(unittest.TestCase):
    def build(self):
        pack = {"countries": [{"iso3": "VNM", "indicators": []}], "countries_index": []}
        c = idn.ensure_country(pack)
        src = fake_sources()
        patches = {s: idn.build_patch(s, idn.series_for(s, src), retrieved_at="t") for s in idn.SPECS}
        idn.apply_all(c, patches, retrieved_at="t")
        return pack, c

    def test_created_once_with_observed_cards_only(self):
        pack, c = self.build()
        idn.ensure_country(pack)
        self.assertEqual([x["iso3"] for x in pack["countries"]], ["VNM", "IDN"])
        self.assertEqual([x["iso3"] for x in pack["countries_index"]], ["IDN"])
        chips = [ch["id"] for chips in c["categories"].values() for ch in chips]
        self.assertNotIn("gdp_yoy", chips)                       # a mode of the gdp chip, not a chip
        self.assertEqual(c["indicators"][[i["id"] for i in c["indicators"]].index("gdp")]["display"], "1.3% | 0.3%")
        # the Yahoo cards and the rating have no data yet (no overlay in this test): pruned, not shown empty
        gone = idn.prune_empty(c)
        self.assertEqual(sorted(gone), ["jci", "sovereign_ratings", "usdidr"])
        self.assertNotIn("usdidr", [ch["id"] for ch in c["categories"]["fx"]])

    def test_units_and_periods(self):
        _, c = self.build()
        by = {i["id"]: i for i in c["indicators"]}
        self.assertEqual(by["export_id"]["display"], "$26.2B")
        self.assertTrue(by["export_id"]["yoy_line"])
        self.assertEqual(by["trade_balance"]["display"], "+$0.1B")
        self.assertEqual(by["fx_reserves"]["display"], "$134B")
        self.assertEqual((by["unemployment"]["reference_period"], by["unemployment"]["asof"]), ("2026-02", "2026-02-28"))

    def test_headlines_only_for_cards_with_a_value(self):
        _, c = self.build()
        idn.sync_headlines(c)
        self.assertEqual([h["id"] for h in c["headlines"]], ["gdp_yoy", "cpi_yoy", "bi_rate"])


if __name__ == "__main__":
    unittest.main()
