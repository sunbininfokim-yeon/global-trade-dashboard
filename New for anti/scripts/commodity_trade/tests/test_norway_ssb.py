from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from sources.norway_ssb import _dataset_values, select_current_lines  # noqa: E402


class NorwaySsbTests(unittest.TestCase):
    def test_current_kg_lines_are_selected_by_explicit_hs_prefix(self) -> None:
        metadata = {
            "variables": [
                {
                    "code": "Varekoder",
                    "values": ["27090001_2001", "27090002_1999", "27111100_1988"],
                    "valueTexts": [
                        "Crude oil (2001-) (Q1=kg, Q2=m³)",
                        "Old crude oil (1999-2000) (Q1=kg, Q2=barrel)",
                        "Natural gas, liquefied (1988-) (Q1=kg, Q2=none)",
                    ],
                }
            ]
        }
        self.assertEqual(select_current_lines(metadata, ["2709", "271111"]), {
            "2709": ["27090001_2001"],
            "271111": ["27111100_1988"],
        })

    def test_jsonstat_rows_follow_dimension_order(self) -> None:
        dataset = {
            "id": ["Varekoder", "ContentsCode"],
            "size": [2, 2],
            "dimension": {
                "Varekoder": {"category": {"index": {"A": 0, "B": 1}}},
                "ContentsCode": {"category": {"index": {"Mengde1": 0, "Verdi": 1}}},
            },
            "value": [1, 10, 2, 20],
        }
        self.assertEqual(_dataset_values(dataset), [
            ({"Varekoder": "A", "ContentsCode": "Mengde1"}, 1.0),
            ({"Varekoder": "A", "ContentsCode": "Verdi"}, 10.0),
            ({"Varekoder": "B", "ContentsCode": "Mengde1"}, 2.0),
            ({"Varekoder": "B", "ContentsCode": "Verdi"}, 20.0),
        ])
