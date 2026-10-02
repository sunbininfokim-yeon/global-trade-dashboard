"""The universe is three lists of 30, and the catalogue survives validation."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from export_controls.universe import (
    AGRI, ENERGY, EXCLUDED_ENTREPOTS, MINERALS, document, load,
)
from export_controls.catalogue import load as load_catalogue
from export_controls.validate import validate_document

ROOT = Path(__file__).resolve().parents[1]


class UniverseTest(unittest.TestCase):
    def test_each_group_has_thirty_distinct_countries(self):
        for name, rows in (("agri", AGRI), ("minerals", MINERALS), ("energy", ENERGY)):
            isos = [row["iso"] for row in rows]
            self.assertEqual(len(isos), 30, name)
            self.assertEqual(len(set(isos)), 30, name)
            for row in rows:
                self.assertTrue(row["commodities"], row["iso"])

    def test_entrepots_stay_out_of_the_thirties(self):
        watched = {row["iso"] for row in AGRI + MINERALS + ENERGY}
        for hub in EXCLUDED_ENTREPOTS:
            self.assertNotIn(hub["iso"], watched)

    def test_committed_json_matches_the_generator(self):
        self.assertEqual(load(ROOT / "universe.json"), document())

    def test_catalogue_passes(self):
        doc = load_catalogue()
        errors = validate_document(doc, load(ROOT / "universe.json"), today=date(2026, 9, 24))
        self.assertEqual(errors, [])

    def test_sugar_and_fuel_are_the_rows_read_this_week(self):
        doc = load_catalogue()
        by_id = {row["id"]: row for row in doc["controls"]}
        sugar = by_id["ind-sugar"]
        self.assertEqual(sugar["level"], "prohibited")
        self.assertEqual(sugar["until"], "2026-09-30")
        self.assertIn("17011490", sugar["hs_prefixes"])
        fuel = by_id["rus-fuel-products"]
        self.assertEqual(fuel["until"], "2027-01-31")
        self.assertEqual(fuel["category"], "energy")
        self.assertNotIn("ind-rice", by_id)
        coal = by_id["idn-coal-single-gate"]
        self.assertNotIn("ferroalloys", coal["commodities"])
        self.assertEqual(by_id["idn-ferroalloys-single-gate"]["category"], "minerals")

    def test_rows_sit_in_their_category_module(self):
        doc = load_catalogue()
        for row in doc["controls"]:
            self.assertEqual(doc["module_of"][row["id"]], row["category"], row["id"])

    def test_misfiled_row_is_reported(self):
        doc = load_catalogue()
        doc["module_of"] = {**doc["module_of"], "ind-sugar": "energy"}
        errors = validate_document(doc, load(ROOT / "universe.json"), today=date(2026, 9, 24))
        self.assertIn("ind-sugar: category agri filed in energy.json", errors)


if __name__ == "__main__":
    unittest.main()
