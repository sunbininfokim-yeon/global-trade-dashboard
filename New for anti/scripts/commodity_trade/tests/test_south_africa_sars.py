import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sources.south_africa_sars import _checkboxes, _chapter_selection_name, _hidden_fields  # noqa: E402


class SouthAfricaSarsTests(unittest.TestCase):
    def test_parses_aspnet_fields_and_tariff_selector(self):
        document = """
        <input type="hidden" name="__VIEWSTATE" value="state&amp;value" />
        <input id="ctl00_ContentPlaceHolder1_ddlTariffs_4" type="checkbox"
               name="ctl00$ContentPlaceHolder1$ddlTariffs$4" />
        <label for="ctl00_ContentPlaceHolder1_ddlTariffs_4">26030000 - Copper Ores</label>
        """
        self.assertEqual(_hidden_fields(document), {"__VIEWSTATE": "state&value"})
        self.assertEqual(
            _checkboxes(document, control="ddlTariffs"),
            [
                {
                    "id": "ctl00_ContentPlaceHolder1_ddlTariffs_4",
                    "name": "ctl00$ContentPlaceHolder1$ddlTariffs$4",
                    "label": "26030000 - Copper Ores",
                }
            ],
        )

    def test_chapter_index_matches_portal_order_for_hs26(self):
        self.assertEqual(_chapter_selection_name(26), "ctl00$ContentPlaceHolder1$ddlChapters$25")


if __name__ == "__main__":
    unittest.main()
