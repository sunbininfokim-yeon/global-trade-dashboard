from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from build_chokepoint_stress import ContractError as StressContractError  # noqa: E402
from build_chokepoint_stress import build_stress  # noqa: E402


def shipping_fixture() -> dict:
    return {
        "chokepoints": [
            {"id": "alpha", "name_ko": "알파", "name_en": "Alpha"},
            {"id": "beta", "name_ko": "베타", "name_en": "Beta"},
        ],
        "chokepoints_live": {
            "alpha": {
                "latest_date": "2026-08-08",
                "metrics": {
                    "all": {
                        "change_pct": -10,
                        "current_7d_mean_dwt": 90,
                        "prior_28d_mean_dwt": 100,
                    }
                },
            },
            "beta": {
                "latest_date": "2026-08-09",
                "metrics": {
                    "all": {
                        "change_pct": 4,
                        "current_7d_mean_dwt": 104,
                        "prior_28d_mean_dwt": 100,
                    }
                },
            },
        },
    }


class ChokepointStressTests(unittest.TestCase):
    def test_arithmetic_mean_worst_and_conservative_date(self) -> None:
        result = build_stress(shipping_fixture(), generated_at="2026-08-10T00:00:00+00:00")
        self.assertEqual(result["index_pct"], -3)
        self.assertEqual(result["worst_id"], "alpha")
        self.assertEqual(result["worst_change_pct"], -10)
        self.assertEqual(result["as_of"], "2026-08-08")
        self.assertEqual(result["contributor_count"], 2)

    def test_missing_all_metric_is_rejected(self) -> None:
        fixture = shipping_fixture()
        del fixture["chokepoints_live"]["alpha"]["metrics"]["all"]
        with self.assertRaises(StressContractError):
            build_stress(fixture)


class PublicManifestTests(unittest.TestCase):
    def test_pages_a_to_e_have_four_unique_slots(self) -> None:
        path = APP_DIR / "public" / "data" / "home_signal_series_v1.json"
        with path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(set(manifest["pages"]), set("ABCDE"))
        slot_ids = []
        for page in manifest["pages"].values():
            self.assertEqual(len(page["slots"]), 4)
            slot_ids.extend(slot["id"] for slot in page["slots"])
        self.assertEqual(len(slot_ids), len(set(slot_ids)))

    def test_public_contracts_do_not_contain_null(self) -> None:
        names = (
            "chokepoint_stress_v1.json",
            "home_signal_series_v1.json",
            "kospi_risk_slot_v1.json",
        )
        for name in names:
            with (APP_DIR / "public" / "data" / name).open(encoding="utf-8") as handle:
                doc = json.load(handle)
            self.assertNotIn(None, _walk_values(doc), name)


def _walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


if __name__ == "__main__":
    unittest.main()
