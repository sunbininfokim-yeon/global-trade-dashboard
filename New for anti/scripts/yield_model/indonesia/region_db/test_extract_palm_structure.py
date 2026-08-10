"""Focused tests for the palm maturity-table row repair."""

import unittest

from .extract_palm_structure import (
    _history_consistency,
    _structure_consistency,
    history_values,
    structure_values,
)


class PalmStructureValuesTest(unittest.TestCase):
    def test_old_space_grouped_row(self):
        values = structure_values(
            "66 835 962 446 11 022 1 040 303 3 690 480 3 834,48")
        self.assertEqual(
            values, [66835, 962446, 11022, 1040303, 3690480, 3834])

    def test_new_dot_grouped_row(self):
        values = structure_values(
            "97.254 338.927 38.752 474.933 979.649 2.890")
        self.assertEqual(
            values, [97254, 338927, 38752, 474933, 979649, 2890])

    def test_consistency_detects_wrong_grouping(self):
        good = [97254, 338927, 38752, 474933, 979649, 2890]
        bad = [97, 254338, 92738, 752474, 933979, 6492890]
        self.assertLess(_structure_consistency(good), _structure_consistency(bad))

    def test_national_history_row(self):
        values = history_values("2.105.960 26.359.543 16.970.694 45.436.197")
        self.assertEqual(values, [2105960, 26359543, 16970694, 45436197])
        self.assertLess(_history_consistency(values), 0.001)


if __name__ == "__main__":
    unittest.main()
