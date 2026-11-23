from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive_kr_cpi_base2020 as ar  # noqa: E402


def doc(months, vals, weights=None):
    return {"items": [{"code": c, "weight": w} for c, w in (weights or {"0": 1000, "A": 10}).items()],
            "months": months, "monthly": {"0": vals, "A": vals}}


class SameBase(unittest.TestCase):
    def test_a_new_month_on_the_same_base_is_appended(self):
        ok, _ = ar.same_base(doc(["2026-09", "2026-10"], [118.1, 118.4]),
                             doc(["2026-09", "2026-10", "2026-11"], [118.1, 118.4, 118.6]))
        self.assertTrue(ok)

    def test_rebasing_freezes(self):
        self.assertFalse(ar.same_base(doc(["2026-10"], [118.4]), doc(["2026-10"], [104.2]))[0])
        self.assertFalse(ar.same_base(doc(["2026-10"], [118.4]),
                                      doc(["2026-10"], [118.4], {"0": 1000, "A": 12}))[0])

    def test_months_axis(self):
        self.assertEqual(ar.months_between("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])


class Archive(unittest.TestCase):
    def test_committed_archive_is_the_old_base(self):
        if not ar.OUT.exists():
            self.skipTest("archive not present")
        import json
        d = json.loads(ar.OUT.read_text(encoding="utf-8"))
        self.assertEqual((d["base"], d["weight_year"]), ("2020=100", "2022"))
        leaves = {i["code"] for i in d["items"]} - {i["parent"] for i in d["items"]}
        self.assertEqual(len(leaves), 458)
        self.assertEqual(len(d["monthly"]["0"]), len(d["months"]))


if __name__ == "__main__":
    unittest.main()
