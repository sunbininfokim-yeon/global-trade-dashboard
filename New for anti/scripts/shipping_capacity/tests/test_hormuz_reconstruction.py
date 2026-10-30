"""Fixtures are tests only; production never emits fixture or seed values."""

import json
import unittest
import urllib.parse
from datetime import datetime, timezone

from shipping_capacity.hormuz_reconstruction import (
    COMTRADE_PREVIEW_URL, JODI_DOWNLOADS_URL, LEDGER_TERMS, STAC_SEARCH_URL,
    bbox_coverage, build_importer_receipts, build_producer_exports,
    collect_hormuz_reconstruction, compose_mass_balance, parse_comtrade_preview,
    parse_jodi_csv,
)


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
JODI_CSV_URL = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/primaryyear2026.csv"
JODI_HTML = '<a href="/_resources/files/downloads/oil-data/annual-csv/primary/primaryyear2026.csv">2026</a>'
HEADER = "REF_AREA,TIME_PERIOD,ENERGY_PRODUCT,FLOW_BREAKDOWN,UNIT_MEASURE,OBS_VALUE,ASSESSMENT_CODE\n"


def jodi_csv(values):
    lines = [HEADER.strip()]
    for (iso2, period), value in values.items():
        lines.append(f"{iso2},{period},CRUDEOIL,TOTEXPSB,KBD,{value},3")
        lines.append(f"{iso2},{period},CRUDEOIL,TOTEXPSB,KBBL,999999,3")  # other unit: ignored
    return "\n".join(lines) + "\n"


MONTHS = [f"2026-{month:02d}" for month in range(2, 8)]
JODI_VALUES = {}
for period in MONTHS:
    JODI_VALUES.update({("KW", period): "1129.0", ("QA", period): "-", ("BH", period): "0.0000",
                        ("SA", period): "4124.6", ("OM", period): "-", ("AE", period): "-"})


def comtrade_payload(reporter, period, partners):
    return {"data": [{
        "reporterCode": reporter, "period": period.replace("-", ""), "cmdCode": "2709", "flowCode": "M",
        "freqCode": "M", "partnerCode": partner, "partner2Code": 0, "customsCode": "C00", "motCode": 0,
        "netWgt": weight, "isNetWgtEstimated": False,
    } for partner, weight in partners]}


def square(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


STAC = {"type": "FeatureCollection", "links": [], "features": [
    {"id": "a", "geometry": square(55, 25, 58, 28), "properties": {"datetime": "2026-09-30T14:24:22Z", "platform": "sentinel-1c", "sat:orbit_state": "ascending"}},
    {"id": "b", "geometry": square(55, 25, 58, 28), "properties": {"datetime": "2026-09-30T14:24:50Z", "platform": "sentinel-1c", "sat:orbit_state": "ascending"}},
    {"id": "c", "geometry": square(55, 25, 56.6, 28), "properties": {"datetime": "2026-09-25T02:00:00Z", "platform": "sentinel-1d", "sat:orbit_state": "descending"}},
]}


def fixture_fetcher(url):
    if url == JODI_DOWNLOADS_URL:
        return JODI_HTML.encode()
    if url == JODI_CSV_URL:
        return jodi_csv(JODI_VALUES).encode()
    if url.startswith(COMTRADE_PREVIEW_URL):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        reporter, period = int(query["reporterCode"][0]), query["period"][0]
        period = f"{period[:4]}-{period[4:]}"
        if reporter == 392 and period == "2026-07":
            return json.dumps(comtrade_payload(392, period, [(414, 295_010_336.0), (682, 2_857_840_577.0)])).encode()
        return json.dumps({"data": []}).encode()
    if url.startswith(STAC_SEARCH_URL):
        return json.dumps(STAC).encode()
    raise AssertionError(f"unexpected url {url}")


def failing_fetcher(url):
    raise OSError("network down")


def term(value, low=None, high=None):
    return {"value": value, "low": low, "high": high}


class MassBalanceTests(unittest.TestCase):
    def full_terms(self, bounded=True):
        values = {
            "open_sea_departures": (100.0, 90.0, 110.0),
            "local_discharge_consumption": (10.0, 8.0, 12.0),
            "zone_inventory_change": (5.0, 0.0, 10.0),
            "local_loading_excluding_bypass": (20.0, 18.0, 22.0),
            "bypass_port_loading": (30.0, 25.0, 35.0),
            "other_maritime_inflow": (5.0, 4.0, 6.0),
        }
        return {key: term(value, low if bounded else None, high if bounded else None) for key, (value, low, high) in values.items()}

    def test_missing_term_holds_and_publishes_no_number(self):
        terms = self.full_terms()
        terms["zone_inventory_change"] = None
        result = compose_mass_balance(terms, term(40.0, 35.0, 45.0))
        self.assertEqual(result["status"], "hold_inputs_missing")
        self.assertEqual(result["missing_terms"], ["zone_inventory_change"])
        self.assertIsNone(result["unexplained_volume"])
        self.assertIsNone(result["unexplained_range"])

    def test_missing_confirmed_transit_holds(self):
        result = compose_mass_balance(self.full_terms(), None)
        self.assertEqual(result["missing_terms"], ["confirmed_transit_cargo"])

    def test_signed_sum_and_directional_interval(self):
        result = compose_mass_balance(self.full_terms(), term(40.0, 35.0, 45.0))
        self.assertEqual(result["status"], "computed")
        # 100 + 10 + 5 - 20 - 30 - 5
        self.assertEqual(result["hormuz_inflow_estimate"], 60.0)
        self.assertEqual(result["unexplained_volume"], 20.0)
        # low: (90+8+0) - (22+35+6) - 45 ; high: (110+12+10) - (18+25+4) - 35
        self.assertEqual(result["unexplained_range"], {"low": -10.0, "high": 50.0})

    def test_range_requires_every_bound(self):
        terms = self.full_terms(bounded=False)
        result = compose_mass_balance(terms, term(40.0, 35.0, 45.0))
        self.assertEqual(result["status"], "computed")
        self.assertIsNone(result["unexplained_range"])

    def test_negative_residual_is_held_not_zeroed(self):
        result = compose_mass_balance(self.full_terms(), term(80.0, 75.0, 85.0))
        self.assertEqual(result["status"], "hold_negative_residual_boundary_mismatch")
        self.assertIsNone(result["unexplained_volume"])
        self.assertEqual(result["diagnostic"]["unexplained_volume"], -20.0)

    def test_bounds_must_bracket_value(self):
        terms = self.full_terms()
        terms["bypass_port_loading"] = term(30.0, 31.0, 35.0)
        with self.assertRaises(ValueError):
            compose_mass_balance(terms, term(40.0, 35.0, 45.0))

    def test_every_research_term_is_in_the_ledger(self):
        self.assertEqual(
            [entry["id"] for entry in LEDGER_TERMS],
            ["open_sea_departures", "local_discharge_consumption", "zone_inventory_change",
             "local_loading_excluding_bypass", "bypass_port_loading", "other_maritime_inflow"],
        )
        self.assertEqual([entry["sign"] for entry in LEDGER_TERMS], [1, 1, 1, -1, -1, -1])


class ProducerTests(unittest.TestCase):
    def test_dash_is_not_reported_and_zero_is_reported(self):
        observations = parse_jodi_csv(jodi_csv({("QA", "2026-07"): "-", ("BH", "2026-07"): "0.0000"}))
        self.assertIsNone(observations[("QA", "2026-07")]["value"])
        self.assertEqual(observations[("BH", "2026-07")]["value"], 0.0)

    def test_column_change_and_conflicts_raise(self):
        with self.assertRaises(ValueError):
            parse_jodi_csv("REF_AREA,TIME_PERIOD\nKW,2026-07\n")
        conflicting = HEADER + "KW,2026-07,CRUDEOIL,TOTEXPSB,KBD,1,3\nKW,2026-07,CRUDEOIL,TOTEXPSB,KBD,2,3\n"
        with self.assertRaises(ValueError):
            parse_jodi_csv(conflicting)

    def test_group_total_needs_every_member(self):
        observations = parse_jodi_csv(jodi_csv(JODI_VALUES))
        rows = [{"iso2": iso2, "period": period, **row} for (iso2, period), row in observations.items()]
        exports = build_producer_exports({"observations": rows})
        latest = exports["hormuz_only_group"]["by_month"][-1]
        self.assertEqual(latest["status"], "incomplete_members_not_reported")
        self.assertIsNone(latest["value"])
        self.assertEqual(latest["missing_members"], ["QA"])
        qatar = next(row for row in exports["producers"] if row["iso2"] == "QA")
        self.assertTrue(all(point["value"] is None for point in qatar["series"]))

        complete = {key: ("1.0" if value == "-" else value) for key, value in JODI_VALUES.items()}
        observations = parse_jodi_csv(jodi_csv(complete))
        rows = [{"iso2": iso2, "period": period, **row} for (iso2, period), row in observations.items()]
        latest = build_producer_exports({"observations": rows})["hormuz_only_group"]["by_month"][-1]
        self.assertEqual(latest["value"], 1130.0)  # KW 1129 + QA 1 + BH 0; SA never grouped


class ImporterTests(unittest.TestCase):
    def test_rows_outside_request_raise(self):
        payload = comtrade_payload(392, "2026-07", [(414, 1000.0)])
        with self.assertRaises(ValueError):
            parse_comtrade_preview(payload, reporter_code=699, period="2026-07")

    def test_weight_is_tonnes_and_missing_weight_is_not_zero(self):
        payload = comtrade_payload(392, "2026-07", [(414, 295_010_336.0), (634, 0.0)])
        rows = {row["origin_iso2"]: row for row in parse_comtrade_preview(payload, reporter_code=392, period="2026-07")}
        self.assertEqual(rows["KW"]["net_weight_tonnes"], 295010.3)
        self.assertIsNone(rows["QA"]["net_weight_tonnes"])
        self.assertEqual(rows["QA"]["status"], "weight_not_reported")

    def test_no_rows_is_not_a_zero(self):
        receipts = build_importer_receipts({"months": ["2026-07"], "cells": [
            {"key": "CN:2026-07", "importer_iso2": "CN", "period": "2026-07", "rows": [], "status": "no_rows"},
        ]})
        china = next(row for row in receipts["importers"] if row["iso2"] == "CN")
        self.assertEqual(china["status"], "no_monthly_rows_in_window")
        self.assertEqual(china["origins"], [])


class SarTests(unittest.TestCase):
    def test_coverage_of_box(self):
        self.assertEqual(bbox_coverage([square(50, 20, 60, 30)]), 1.0)
        self.assertAlmostEqual(bbox_coverage([square(55.8, 25.9, 56.6, 27.0)]), 0.5, places=2)
        self.assertEqual(bbox_coverage([square(10, 10, 11, 11)]), 0.0)


class CollectTests(unittest.TestCase):
    def collect(self, **kwargs):
        return collect_hormuz_reconstruction(now=NOW, sleep=lambda seconds: None, **kwargs)

    def test_fetched_bundle_holds_headline(self):
        out = self.collect(fetch=True, fetcher=fixture_fetcher)
        self.assertEqual(out["status"], "available")
        self.assertEqual({key: source["status"] for key, source in out["sources"].items()},
                         {"jodi": "fetched", "comtrade": "fetched", "sentinel1": "fetched"})
        self.assertEqual(out["api_keys_required"], [])
        self.assertIsNone(out["headline"]["value"])
        self.assertEqual(out["headline"]["display_ko"], "미포착 화물량: 자료 부족으로 미산출")
        self.assertEqual(len(out["headline"]["blocking_terms"]), 7)
        self.assertEqual(out["mass_balance"]["period"]["period"], "2026-07")
        self.assertEqual(out["mass_balance"]["period"]["days"], 31)
        self.assertTrue(all(entry["value"] is None for entry in out["mass_balance"]["terms"]))
        self.assertIsNone(out["identifiability"]["result"])
        japan = next(row for row in out["importer_receipts"]["importers"] if row["iso2"] == "JP")
        self.assertEqual(japan["reported_months"], ["2026-07"])
        sar = out["sar_coverage"]
        self.assertEqual(sar["acquisition_dates"], 2)  # two scenes on 9/30 are one day
        self.assertEqual(sar["full_coverage_dates"], 1)
        self.assertEqual(sar["max_gap_days"], 5)
        self.assertIsNone(sar["vessel_detection"])

    def test_failure_keeps_last_good_copy(self):
        good = self.collect(fetch=True, fetcher=fixture_fetcher)
        out = self.collect(fetch=True, fetcher=failing_fetcher, previous=good)
        self.assertEqual({key: source["status"] for key, source in out["sources"].items()},
                         {"jodi": "cached_fallback", "comtrade": "cached_fallback", "sentinel1": "cached_fallback"})
        self.assertEqual(out["status"], "cached")
        self.assertEqual(out["producer_exports"]["months"], MONTHS)
        self.assertEqual(out["sources"]["jodi"]["retrieved_at"], good["sources"]["jodi"]["retrieved_at"])

    def test_no_cache_and_no_network_is_unavailable(self):
        out = self.collect(fetch=True, fetcher=failing_fetcher)
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(out["producer_exports"]["status"], "unavailable")
        self.assertIsNone(out["mass_balance"]["period"]["period"])

    def test_offline_rebuild_reuses_cache(self):
        good = self.collect(fetch=True, fetcher=fixture_fetcher)
        out = self.collect(fetch=False, previous=good)
        self.assertEqual(out["sources"]["comtrade"]["status"], "cached_offline")
        self.assertEqual(out["producer_exports"], good["producer_exports"])

    def test_official_context_feeds_confirmed_transit_candidates(self):
        official = {"chokepoints": {"hormuz": {
            "reference_cards": [{"cargo_category": "crude_condensate", "period": "2Q26"}],
            "supplementary_reference_cards": [{"period": "2026-08"}],
        }}}
        live = {"hormuz": {"metric_histories": {"tanker": {"history": [{"date": "2026-09-27", "value": 1.0}]}}}}
        out = self.collect(fetch=True, fetcher=fixture_fetcher, official_cargo=official, live_status=live)
        confirmed = next(entry for entry in out["mass_balance"]["terms"] if entry["id"] == "confirmed_transit_cargo")
        self.assertEqual(confirmed["status"], "unqualified_input")
        self.assertEqual(len(confirmed["candidates"]), 3)
        self.assertTrue(all(candidate["reason_labels_ko"] for candidate in confirmed["candidates"]))
        self.assertIsNone(confirmed["value"])


if __name__ == "__main__":
    unittest.main()
