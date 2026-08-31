from __future__ import annotations

import json
import unittest

from macro_monitor.cpi.api import fetch_series


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TestCpiApi(unittest.TestCase):
    def test_unregistered_fetch_splits_to_ten_year_windows(self):
        requests = []

        def opener(request, timeout):
            self.assertEqual(timeout, 45)
            payload = json.loads(request.data)
            requests.append(payload)
            year = payload["endyear"]
            return _Response({
                "status": "REQUEST_SUCCEEDED",
                "message": [],
                "Results": {"series": [{
                    "seriesID": "CUSRTEST",
                    "data": [{"year": year, "period": "M01", "value": "100"}],
                }]},
            })

        result = fetch_series(
            ["CUSRTEST"], registration_key="", start_year=2011, end_year=2026, opener=opener,
        )
        self.assertEqual([(row["startyear"], row["endyear"]) for row in requests], [("2011", "2020"), ("2021", "2026")])
        self.assertTrue(all("registrationkey" not in row and "catalog" not in row for row in requests))
        self.assertEqual(len(result["CUSRTEST"]["data"]), 2)


if __name__ == "__main__":
    unittest.main()
