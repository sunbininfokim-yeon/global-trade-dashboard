"""apply_hidden_flags.py: demo cards are hidden, observed ones shown, and the flag follows the status."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apply_hidden_flags as ahf  # noqa: E402


def pack(status):
    return {"countries": [{"iso3": "GBR",
                           "indicators": [{"id": "ism_mfg", "data_status": status}, {"id": "cpi_yoy", "data_status": "live"}],
                           "categories": {"growth": [{"id": "ism_mfg"}], "inflation": [{"id": "cpi_yoy"}]},
                           "headlines": [{"id": "ism_mfg"}, {"id": "cpi_yoy"}]}]}


class Flags(unittest.TestCase):
    def test_demo_card_chip_and_headline_hidden(self):
        p = pack("demo")
        self.assertEqual(ahf.apply(p), {"GBR": 1})
        c = p["countries"][0]
        self.assertTrue(c["indicators"][0]["hidden"] and c["categories"]["growth"][0]["hidden"] and c["headlines"][0]["hidden"])
        self.assertNotIn("hidden", c["indicators"][1])

    def test_flag_clears_once_the_card_is_observed(self):
        p = pack("demo")
        ahf.apply(p)
        p["countries"][0]["indicators"][0]["data_status"] = "live"
        ahf.apply(p)
        c = p["countries"][0]
        self.assertNotIn("hidden", c["indicators"][0])
        self.assertNotIn("hidden", c["categories"]["growth"][0])

    def test_overrides(self):
        p = pack("demo")
        ahf.apply(p, {"show": ["GBR:ism_mfg"], "hide": ["GBR:cpi_yoy"]})
        c = p["countries"][0]
        self.assertNotIn("hidden", c["indicators"][0])
        self.assertTrue(c["indicators"][1]["hidden"])


class BrokenFreeCards(unittest.TestCase):
    def setUp(self):
        self.pack = {"countries": [{"iso3": "EMU", "indicators": [
            {"id": "ifo", "data_status": "live", "source": "ifo:gsk"},
            {"id": "pmi", "data_status": "live", "source": "other:pipeline"},
            {"id": "hkma", "data_status": "live", "source": "hkma:x"}]}]}
        self.reg = [{"iso3": "EMU", "id": "ifo", "enabled": False, "source": "ifo:gsk"},
                    {"iso3": "EMU", "id": "pmi", "enabled": False, "source": "pmi:licensed"},
                    {"iso3": "EMU", "id": "hkma", "source": "hkma:x"}]

    def test_switched_off_after_going_live_is_hidden_but_another_pipelines_card_is_not(self):
        self.assertEqual(ahf.broken_free_cards(self.reg, {}, self.pack), ["EMU:ifo"])

    def test_failing_for_days_is_hidden_and_comes_back_after_a_read(self):
        bad = {"EMU/hkma": {"consecutive_failures": ahf.FREE_CARD_FAIL_HIDE}}
        self.assertIn("EMU:hkma", ahf.broken_free_cards(self.reg, bad, self.pack))
        ok = {"EMU/hkma": {"consecutive_failures": ahf.FREE_CARD_FAIL_HIDE - 1}}
        self.assertNotIn("EMU:hkma", ahf.broken_free_cards(self.reg, ok, self.pack))


if __name__ == "__main__":
    unittest.main()
