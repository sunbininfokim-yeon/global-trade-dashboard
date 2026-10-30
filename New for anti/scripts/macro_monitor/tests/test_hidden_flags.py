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


if __name__ == "__main__":
    unittest.main()
