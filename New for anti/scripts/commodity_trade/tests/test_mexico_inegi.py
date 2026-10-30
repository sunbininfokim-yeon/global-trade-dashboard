from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sources.mexico_inegi import _page_count, parse_chapter_value_page  # noqa: E402


class MexicoInegiTests(unittest.TestCase):
    def test_parse_hs4_values_by_flow_and_omit_confidential(self) -> None:
        document = """
        <script>var llamada=Actualiza('1','7','34','33')</script>
        <table id="ResultTable"><tr>
          <td>Importaciones</td><td>ID="[Tarifa].&amp;[27]&amp;[2709]"</td><td>1,234</td>
        </tr><tr>
          <td>Exportaciones</td><td>ID="[Tarifa].&amp;[27]&amp;[2709]"</td><td>2,345.5</td>
        </tr><tr>
          <td>Importaciones</td><td>ID="[Tarifa].&amp;[27]&amp;[2710]"</td><td>C</td>
        </tr></table>
        """
        observed = parse_chapter_value_page(document)
        self.assertEqual(observed["M"], {"2709": 1234.0})
        self.assertEqual(observed["X"], {"2709": 2345.5})
        self.assertEqual(_page_count(document), 2)
