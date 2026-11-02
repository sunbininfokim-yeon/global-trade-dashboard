import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server


class ObservedModeTest(unittest.TestCase):
    def test_no_prices_does_not_silently_load_synthetic(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(server, "ROOT", Path(folder)), patch.object(server, "FORCE_SYNTHETIC", False):
                result = server.snapshot()
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["sources"], {})

    def test_synthetic_requires_explicit_mode(self):
        with patch.object(server, "FORCE_SYNTHETIC", True):
            self.assertEqual(server.snapshot()["status"], "synthetic")


if __name__ == "__main__":
    unittest.main()
