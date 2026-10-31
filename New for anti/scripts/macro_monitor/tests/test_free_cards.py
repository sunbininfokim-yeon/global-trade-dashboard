from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import free_cards as fc  # noqa: E402

MOF_CSV = """,,,
,,,Acquisition,Disposition,Net,,,,,,,,,Acquisition,Disposition,Net
2026,１月,Jan,"9,934","8,428","1,506",,,,,,,,,"89,346","80,593","8,753"
(令和8年),２月,Feb,1,1,0,,,,,,,,,"10","20",-10
,,,,,,,,,,,,,,,,
,９月,Sep,,,,,,,,,,,,,,
"""

PCPS = """<x><Series COUNTRY="G001" INDICATOR="PURAN" DATA_TRANSFORMATION="USD" FREQUENCY="M"><Obs TIME_PERIOD="2026-M08" OBS_VALUE="71.0"/><Obs TIME_PERIOD="2026-M09" OBS_VALUE="72.47"/></Series>
<Series COUNTRY="G001" INDICATOR="PURAN" DATA_TRANSFORMATION="INDEX" FREQUENCY="M"><Obs TIME_PERIOD="2026-M09" OBS_VALUE="273"/></Series></x>"""


class Readers(unittest.TestCase):
    def test_mof_year_carries_down_and_blank_months_are_skipped(self):
        self.assertEqual(fc.parse_mof_securities(MOF_CSV, 16), [("2026-01-01", 8753.0), ("2026-02-01", -10.0)])

    def test_sdmx_picks_the_one_matching_series(self):
        self.assertEqual(fc.parse_sdmx_series(PCPS, {"DATA_TRANSFORMATION": "USD", "FREQUENCY": "M"})[-1], ("2026-09-01", 72.47))
        with self.assertRaises(ValueError):
            fc.parse_sdmx_series(PCPS, {"FREQUENCY": "M"})                     # two match: ambiguous

    def test_ifo_rows(self):
        rows = [("Month/year", "Business Climate "), (" 09/2026", 89.9), (" 10/2026", 90.2), (None,)]
        self.assertEqual(fc.parse_ifo_rows(rows, 1), [("2026-09-01", 89.9), ("2026-10-01", 90.2)])


class Ops(unittest.TestCase):
    def test_scale_then_yoy(self):
        pts = [(f"2025-{m:02d}-01", 100.0) for m in range(1, 13)] + [("2026-01-01", 110.0)]
        self.assertAlmostEqual(fc.apply_ops(pts, [["scale", 0.1], ["pct_change", 12]], None)[-1][1], 10.0)

    def test_unknown_op_is_an_error(self):
        with self.assertRaises(KeyError):
            fc.apply_ops([("2026-01-01", 1.0)], [["guess"]], None)


class Registry(unittest.TestCase):
    def test_every_entry_is_valid_and_unique(self):
        entries = fc.load_registry()
        keys = [f"{e['iso3']}/{e['id']}" for e in entries]
        self.assertEqual(len(keys), len(set(keys)))
        for e in entries:
            self.assertEqual(fc.validate(e), [], f"{e['iso3']}/{e['id']}")

    def test_disabled_needs_a_reason(self):
        self.assertEqual(fc.validate({"iso3": "X", "id": "y", "enabled": False}), ["disabled entry without reason_ko"])

    def test_status_changes_only_when_something_did(self):
        st = {}
        fc.update_status(st, "K/x", ok=True, now="2026-10-31T00:00:00Z", patch={"display": "1", "reference_period": "2026-09"})
        before = json.dumps(st)
        fc.update_status(st, "K/x", ok=True, now="2026-11-01T00:00:00Z", patch={"display": "1", "reference_period": "2026-09"})
        self.assertEqual(json.dumps(st), before)
        fc.update_status(st, "K/x", ok=False, now="2026-11-02T00:00:00Z", error="down")
        self.assertEqual((st["K/x"]["consecutive_failures"], st["K/x"]["last_failed"]), (1, "2026-11-02"))


if __name__ == "__main__":
    unittest.main()
