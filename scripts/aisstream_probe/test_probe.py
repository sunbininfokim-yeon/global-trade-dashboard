import json
from pathlib import Path
import tempfile
import unittest

from probe import Probe, regions_at, type_group, valid_imo, valid_mmsi


def position(mmsi=123456789, lat=26.5, lon=56.5, **extra):
    return {"MessageType": "PositionReport", "MetaData": {"MMSI": mmsi},
            "Message": {"PositionReport": {"UserID": mmsi, "Latitude": lat,
                                          "Longitude": lon, **extra}}}


class ProbeTests(unittest.TestCase):
    def test_empty_sample_not_zero_vessels(self):
        report = Probe().report()
        self.assertIsNone(report["inside_vessel_total"])
        self.assertIsNone(report["crude_barrels"])
        self.assertFalse(report["full_population_coverage_known"])
        self.assertEqual(report["regions"]["hormuz"]["status"], "not_observed_in_sample_not_zero_vessels")

    def test_repeat_mmsi_not_double_counted(self):
        probe = Probe()
        probe.ingest(position())
        probe.ingest(position())
        region = probe.report()["regions"]["hormuz"]
        self.assertEqual(region["position_messages_received"], 2)
        self.assertEqual(region["unique_mmsi_observed_during_window"], 1)

    def test_controls_do_not_imply_focal_coverage(self):
        probe = Probe()
        probe.ingest(position(lat=51.9, lon=4.2))
        self.assertEqual(probe.report()["status"], "controls_observed_focal_not_observed_in_sample")

    def test_out_of_range_nan_invalid_and_identity_mismatch(self):
        probe = Probe()
        for event in [position(lat=91), position(lat=float("nan")), position(Valid=False)]:
            probe.ingest(event)
        event = position()
        event["MetaData"]["MMSI"] = 987654321
        probe.ingest(event)
        self.assertEqual(probe.report()["regions"]["hormuz"]["unique_mmsi_observed_during_window"], 0)
        self.assertEqual(probe.invalid_messages, 4)

    def test_static_fields_link_to_same_observed_ship(self):
        probe = Probe()
        probe.ingest(position())
        probe.ingest({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 123456789},
                      "Message": {"ShipStaticData": {"UserID": 123456789,
                                                    "ImoNumber": 9074729, "Type": 80}}})
        self.assertEqual(probe.report()["regions"]["hormuz"]["valid_imo_available"], 1)
        self.assertEqual(probe.vessels["123456789"]["imo"], "9074729")

    def test_ais_cargo_cannot_split_container_bulk(self):
        self.assertEqual(type_group(70), "cargo_ais_code_container_bulk_not_distinguished")
        self.assertEqual(type_group(80), "tanker_ais_code_not_crude_cargo_confirmed")
        self.assertEqual(type_group(None), "unknown")

    def test_identifiers_validation(self):
        self.assertIsNone(valid_mmsi(True))
        self.assertIsNone(valid_mmsi("123"))
        self.assertIsNone(valid_imo(9074728))
        self.assertEqual(valid_imo(9074729), "9074729")

    def test_static_only_not_current_inside_stock(self):
        probe = Probe()
        probe.ingest({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 123456789},
                      "Message": {"ShipStaticData": {"UserID": 123456789, "ImoNumber": 9074729}}})
        self.assertEqual(probe.report()["regions"]["hormuz"]["unique_mmsi_observed_during_window"], 0)

    def test_secret_redacted_and_upstream_error_not_stored(self):
        probe = Probe()
        probe.ingest({"error": "invalid secret_test_value"})
        probe.ingest(position())
        probe.vessels["123456789"]["name"] = "secret_test_value"
        with tempfile.TemporaryDirectory() as folder:
            probe.save(Path(folder), "secret_test_value")
            for filename in Path(folder).glob("*.json"):
                text = filename.read_text()
                self.assertNotIn("secret_test_value", text)
                json.loads(text)
        self.assertTrue(probe.server_rejected)

    def test_subscription_confirmation_is_not_vessel(self):
        probe = Probe()
        probe.ingest({"MessageType": "SubscriptionConfirmation", "Message": {}})
        self.assertEqual(probe.confirmations, 1)
        self.assertEqual(len(probe.vessels), 0)

    def test_regions_are_explicit_rectangles(self):
        self.assertEqual(regions_at(26.5, 56.5), ["hormuz"])
        self.assertEqual(regions_at(0, 0), [])


if __name__ == "__main__":
    unittest.main()
