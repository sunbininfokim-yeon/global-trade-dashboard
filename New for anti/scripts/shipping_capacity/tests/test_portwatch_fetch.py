"""Transport and publication failures must never masquerade as fresh data."""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import build_snapshot
from shipping_capacity.portwatch import PortWatchClient


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def feature(day, portid="chokepoint2", capacity=10):
    return {"attributes": {"date": f"2026-10-{day:02d}", "portid": portid, "capacity": capacity}}


class PortWatchFetchTests(unittest.TestCase):
    @patch("shipping_capacity.portwatch.time.sleep")
    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_http_400_can_recover_without_changing_the_requested_chokepoint(self, urlopen, sleep):
        urlopen.side_effect = [
            urllib.error.HTTPError("https://example.test", 400, "Bad Request", {}, None),
            response({"features": [feature(25)]}),
        ]
        self.assertEqual(PortWatchClient().fetch_series("chokepoint2")[0]["portid"], "chokepoint2")
        self.assertEqual(urlopen.call_count, 2)

    @patch("shipping_capacity.portwatch.time.sleep")
    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_http_200_arcgis_error_retries_and_recovers_same_observations(self, urlopen, sleep):
        urlopen.side_effect = [
            response({"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}}),
            response({"features": [feature(25), feature(24, capacity=0)]}),
        ]
        rows = PortWatchClient().fetch_series("chokepoint2")
        self.assertEqual([row["date"] for row in rows], ["2026-10-24", "2026-10-25"])
        self.assertEqual(rows[0]["capacity"], 0)
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual([parse_qs(urlparse(r.full_url).query)["f"] for r in requests], [["json"], ["pjson"]])
        sleep.assert_called_once_with(1)

    @patch("shipping_capacity.portwatch.time.sleep")
    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_persistent_arcgis_error_is_bounded(self, urlopen, sleep):
        urlopen.side_effect = [response({"error": {"code": 400, "message": "Invalid URL"}}) for _ in range(3)]
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            PortWatchClient().fetch_series("chokepoint2")
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    @patch("shipping_capacity.portwatch.time.sleep")
    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_timeout_and_http_503_retry(self, urlopen, sleep):
        urlopen.side_effect = [
            TimeoutError("timeout"),
            urllib.error.HTTPError("https://example.test", 503, "unavailable", {}, None),
            response({"features": [feature(25)]}),
        ]
        self.assertEqual(len(PortWatchClient().fetch_series("chokepoint2")), 1)
        self.assertEqual(urlopen.call_count, 3)

    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_authorization_errors_are_not_retried(self, urlopen):
        urlopen.return_value = response({"error": {"code": 403, "message": "Forbidden"}})
        with self.assertRaisesRegex(RuntimeError, "403"):
            PortWatchClient().fetch_series("chokepoint2")
        self.assertEqual(urlopen.call_count, 1)

    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_malformed_empty_or_wrong_identity_cannot_become_fresh(self, urlopen):
        for payload in ({}, [], {"features": []}, {"features": [feature(25, portid="chokepoint1")]},
                        {"features": [feature(25, capacity=None)]}):
            with self.subTest(payload=payload):
                urlopen.return_value = response(payload)
                with self.assertRaises(RuntimeError):
                    PortWatchClient().fetch_series("chokepoint2")

    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_short_transfer_limited_page_is_not_end_of_history(self, urlopen):
        urlopen.side_effect = [
            response({"features": [feature(25), feature(24)], "exceededTransferLimit": True}),
            response({"features": [feature(23)], "exceededTransferLimit": False}),
        ]
        rows = PortWatchClient().fetch_series("chokepoint2", record_count=4)
        self.assertEqual(len(rows), 3)
        params = parse_qs(urlparse(urlopen.call_args.args[0].full_url).query)
        self.assertEqual(params["resultOffset"], ["2"])

    @patch("shipping_capacity.portwatch.urllib.request.urlopen")
    def test_later_page_failure_does_not_return_truncated_success(self, urlopen):
        urlopen.side_effect = [response({"features": [feature(25)], "exceededTransferLimit": True}),
                               response({"error": {"code": 400, "message": "Invalid URL"}})]
        with self.assertRaisesRegex(RuntimeError, "failed after"):
            PortWatchClient(retry_attempts=1).fetch_series("chokepoint2", record_count=2)

    @patch.object(PortWatchClient, "fetch_series", return_value=[feature(25)["attributes"]])
    def test_insufficient_history_cannot_replace_cached_status(self, _fetch):
        with self.assertRaisesRegex(RuntimeError, "insufficient history"):
            PortWatchClient().fetch_status("chokepoint2")


class PortWatchPublishGateTests(unittest.TestCase):
    def test_older_upstream_result_cannot_replace_a_newer_observation(self):
        previous = {"suez": {"latest_date": "2026-10-25", "metrics": {"all": {}}}}
        with patch.object(PortWatchClient, "fetch_status", return_value={
            "latest_date": "2026-10-18", "metrics": {"all": {}}
        }):
            snapshot = build_snapshot.build_snapshot(
                Path(build_snapshot.__file__).parent / "config",
                fetch_portwatch=True,
                fallback_live_status=previous,
            )
        self.assertEqual(snapshot["chokepoints_live"]["suez"]["latest_date"], "2026-10-25")
        self.assertTrue(snapshot["chokepoints_live"]["suez"]["fallback_used"])
        self.assertIn("regressed", snapshot["live_fetch_errors"][0]["error"])

    def test_failed_live_collection_exits_before_touching_any_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "shipping_capacity_v1.json"
            artifacts = [output] + [root / f"shipping_capacity_{name}_v1.json" for name in ("scenario_grid", "diagnostics", "backtests")]
            for artifact in artifacts:
                artifact.write_text('{"preserve": true}\n')
            snapshot = {"live_fetch_errors": [{"chokepoint_id": "panama", "error": "Invalid URL"}]}
            with patch("sys.argv", ["build_snapshot.py", "--fetch-portwatch", "--output", str(output)]), \
                 patch("build_snapshot.build_snapshot", return_value=snapshot), \
                 patch("build_snapshot.build_artifact_bundle") as bundle, \
                 patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(root / "summary.md")}), \
                 patch("build_snapshot.load_json", return_value={}):
                with self.assertRaises(SystemExit) as error:
                    build_snapshot.main()
            self.assertEqual(error.exception.code, 1)
            bundle.assert_not_called()
            for artifact in artifacts:
                self.assertEqual(artifact.read_text(), '{"preserve": true}\n')
            self.assertIn("panama", (root / "summary.md").read_text())

    def test_successful_live_collection_still_publishes_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "shipping_capacity_v1.json"
            bundle = {key: {"bundle_id": "matching", "artifact_type": key} for key in ("screen", "scenario_grid", "diagnostics", "backtests")}
            with patch("sys.argv", ["build_snapshot.py", "--fetch-portwatch", "--output", str(output)]), \
                 patch("build_snapshot.build_snapshot", return_value={"live_fetch_errors": []}), \
                 patch("build_snapshot.build_artifact_bundle", return_value=bundle):
                build_snapshot.main()
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 4)


if __name__ == "__main__":
    unittest.main()
