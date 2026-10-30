from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bilateral import ContractError, build_partition, country_view, period_key
from bilateral_jobs import execute_plan, make_job
from preview_bilateral import convert_snapshot


def meta(**changes):
    result = {"source": "synthetic_test", "reporter": "682", "hs": "2709",
              "hs_version": "HS2022", "scope_id": "synthetic_net_trade_all_modes",
              "value_basis": "FOB", "period": "202606", "frequency": "M"}
    result.update(changes)
    return result


def row(partner="156", flow="X", weight=25, value=50, **changes):
    result = {"partner": partner, "flow": flow, "period": "202606",
              "metrics": {"net_weight_kg": weight, "trade_value_usd": value}}
    result.update(changes)
    return result


class BilateralTests(unittest.TestCase):
    def test_two_directions_and_separate_metric_shares(self):
        rows = [row("0", weight=100, value=1000), row(), row("410", "M", 8, 90)]
        before = deepcopy(rows)
        out = build_partition(meta(), rows)
        x = out["flows"]["X"]["rows"][0]
        self.assertEqual(x["analysis"]["net_weight_kg"]["share_pct"], 25)
        self.assertEqual(x["analysis"]["trade_value_usd"]["share_pct"], 5)
        m = out["flows"]["M"]["rows"][0]
        self.assertEqual((m["exporter"], m["importer"]), ("410", "682"))
        self.assertIsNone(m["analysis"]["net_weight_kg"]["share_pct"])
        self.assertEqual(rows, before)

    def test_missing_weight_does_not_become_money_or_zero(self):
        out = build_partition(meta(), [row(weight=None, value=900)])
        r = out["flows"]["X"]["rows"][0]
        self.assertIsNone(r["metrics"]["net_weight_kg"])
        self.assertEqual(r["metrics"]["trade_value_usd"], 900)
        self.assertIsNone(r["metrics"]["quantity_bbl"])
        self.assertIsNone(r["analysis"]["net_weight_kg"]["rank"])

    def test_explicit_zero_preserved(self):
        p = build_partition(meta(), [row("0", weight=100), row(weight=0)])
        self.assertEqual(p["flows"]["X"]["rows"][0]["analysis"]["net_weight_kg"]["share_pct"], 0)

    def test_duplicate_is_deduplicated_not_summed(self):
        p = build_partition(meta(), [row(), row()])
        self.assertEqual(len(p["flows"]["X"]["rows"]), 1)
        with self.assertRaises(ContractError):
            build_partition(meta(), [row(), row(weight=1)])

    def test_mirror_never_reuses_importer_world_total(self):
        p = build_partition(meta(reporter="842", value_basis="CIF"), [row("0", "M", 100), row("682", "M", 10)])
        r = country_view(p, "682")[0]
        self.assertEqual((r["focus_flow"], r["source_flow"], r["counterparty"]), ("X", "M", "842"))
        self.assertEqual(r["reporting_basis"], "partner_report_mirror")
        self.assertIsNone(r["analysis"]["net_weight_kg"]["share_pct"])
        self.assertIsNone(r["analysis"]["net_weight_kg"]["rank"])

    def test_exact_commodity_identity_uses_hs(self):
        a = build_partition(meta(hs="2603"), [])
        b = build_partition(meta(hs="7403"), [])
        self.assertNotEqual(a["meta"]["commodity_id"], b["meta"]["commodity_id"])

    def test_periods_not_relabelled(self):
        for period, freq in [("202613", "M"), ("2026", "M"), ("202606", "A")]:
            with self.subTest(period=period), self.assertRaises(ContractError):
                period_key(period, freq)
        with self.assertRaises(ContractError):
            build_partition(meta(), [row(period="202505")])
        p = build_partition(meta(period="2025", frequency="A"), [row(period="2025")])
        self.assertEqual(p["meta"]["frequency"], "A")

    def test_invalid_numeric_values_rejected(self):
        for value in [True, -1, float("nan"), float("inf"), "bad"]:
            with self.subTest(value=value), self.assertRaises(ContractError):
                build_partition(meta(), [row(weight=value)])

    def test_ranks_are_per_flow_metric_and_ties(self):
        p = build_partition(meta(), [row("156", weight=20, value=1), row("410", weight=20, value=8),
                                    row("392", weight=10, value=3), row("156", "M", 1000, 1000)])
        r = {x["partner"]: x["analysis"] for x in p["flows"]["X"]["rows"]}
        self.assertEqual([r[k]["net_weight_kg"]["rank"] for k in ("156", "410", "392")], [1, 1, 3])
        self.assertEqual(r["410"]["trade_value_usd"]["rank"], 1)
        self.assertEqual(r["156"]["net_weight_kg"]["rank_scope"], "observed_partner_codes")

    def test_world_inconsistency_is_not_clamped(self):
        p = build_partition(meta(partners_disjoint=True), [row("0", weight=30), row("156", weight=20), row("410", weight=20)])
        self.assertEqual(p["flows"]["X"]["metrics"]["net_weight_kg"]["share_reason"], "observed_sum_exceeds_world")
        self.assertIsNone(p["flows"]["X"]["rows"][0]["analysis"]["net_weight_kg"]["share_pct"])

    def test_unknown_scope_suppresses_shares(self):
        p = build_partition(meta(scope_id="unknown"), [row("0", weight=100), row()])
        self.assertIsNone(p["flows"]["X"]["rows"][0]["analysis"]["net_weight_kg"]["share_pct"])

    def test_barrels_only_when_explicit(self):
        p = build_partition(meta(), [row(metrics={"quantity_bbl": 100}), row("0", metrics={"quantity_bbl": 200})])
        r = p["flows"]["X"]["rows"][0]
        self.assertEqual(r["analysis"]["quantity_bbl"]["share_pct"], 50)
        self.assertIsNone(r["metrics"]["net_weight_kg"])


class JobTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [make_job(meta(reporter=r), ["*"]) for r in ("682", "842", "410")]

    def ok(self, job):
        return {"query_id": job["id"], "status": "ok", "response_complete": True, "rows": [row()]}

    def run_plan(self, state=None, provider=None, **changes):
        options = dict(cycle="2026-09-16", max_requests=3, provider=provider or self.ok, checkpoint=lambda s: None)
        options.update(changes)
        return execute_plan(self.jobs, state, **options)

    def test_resume_budget_and_skip_success(self):
        saves = []
        a = self.run_plan(max_requests=1, checkpoint=saves.append)
        b = self.run_plan(a["state"], max_requests=1)
        self.assertEqual(len(b["state"]["data"]), 2)
        self.assertEqual(len(saves), 1)
        c = self.run_plan(b["state"])
        self.assertEqual(c["attempted"], 1)
        self.assertEqual(self.run_plan(c["state"])["attempted"], 0)
        self.assertEqual(self.run_plan(c["state"], cycle="2026-10-16")["attempted"], 3)

    def test_error_partial_empty_preserve_old_data(self):
        old = self.run_plan()["state"]
        for status in ("error", "empty", "partial"):
            def provider(j):
                r = self.ok(j)
                r.update(status="ok" if status == "partial" else status, response_complete=False)
                return r
            new = self.run_plan(old, provider, cycle="2026-10-16")["state"]
            self.assertEqual(old["data"], new["data"])
            self.assertTrue(all(e["status"] == status for e in new["jobs"].values()))

    def test_auth_and_rate_limit_stop(self):
        for status in ("auth_required", "rate_limited"):
            r = self.run_plan(provider=lambda j: {"query_id": j["id"], "status": status})
            self.assertEqual(r["attempted"], 1)

    def test_error_messages_cannot_leak_credentials(self):
        def bad(j):
            raise RuntimeError("serviceKey=synthetic-secret-must-not-appear")
        result = self.run_plan(provider=bad)
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_wrong_response_is_rejected(self):
        r = self.run_plan(provider=lambda j: {"query_id": "other", "status": "ok", "rows": []})
        self.assertEqual(r["state"]["data"], {})
        self.assertTrue(all(e["status"] == "contract_error" for e in r["state"]["jobs"].values()))

    def test_failing_first_job_does_not_starve_remaining_jobs(self):
        a = self.run_plan(provider=lambda j: {"query_id": j["id"], "status": "error"}, max_requests=1)
        b = self.run_plan(a["state"], max_requests=1)
        self.assertIn(self.jobs[1]["id"], b["state"]["data"])

    def test_persistence_failure_stops(self):
        def no_disk(s):
            raise OSError("disk failure")
        with self.assertRaises(OSError):
            self.run_plan(checkpoint=no_disk)

    def test_world_only_cannot_complete_bilateral_job(self):
        r = self.run_plan(provider=lambda j: {"query_id": j["id"], "status": "ok",
                                              "response_complete": True, "rows": [row("0")]})
        self.assertEqual(r["state"]["data"], {})
        self.assertTrue(all(e["status"] == "world_only" for e in r["state"]["jobs"].values()))

    def test_subset_cannot_claim_global_rank(self):
        with self.assertRaises(ContractError):
            make_job(meta(all_partners_verified=True), ["156", "410"])

    def test_partner_scope_is_checked_and_padding_is_normalized(self):
        j = make_job(meta(), ["076"])
        result = execute_plan([j], None, cycle="test", max_requests=1,
                              provider=lambda _: {"query_id": j["id"], "status": "ok", "response_complete": True,
                                                  "rows": [row("076")]}, checkpoint=lambda s: None)
        self.assertEqual(result["unfinished"], [])
        other = execute_plan([j], None, cycle="test", max_requests=1,
                             provider=lambda _: {"query_id": j["id"], "status": "ok", "response_complete": True,
                                                 "rows": [row("410")]}, checkpoint=lambda s: None)
        self.assertEqual(other["state"]["jobs"][j["id"]]["status"], "contract_error")

    def test_zero_budget_does_not_call_provider(self):
        self.assertEqual(self.run_plan(max_requests=0)["attempted"], 0)


class LegacyMigrationTests(unittest.TestCase):
    def test_actual_direction_wins_over_importer_label(self):
        item = {"ok": True, "source": "mirror_to_chn_minerals", "reporter": "CHN", "view": "importer",
                "hs_used": "2603", "grain": "month", "period": "202606",
                "partners": [{"partner_code": 842, "flow": "X", "period": "202606", "net_wgt": 0, "primary_value": 5}]}
        out = convert_snapshot({"resolved": [item]}, {"CHN": "156"})
        self.assertEqual(out["summary"]["direction_conflicts"], 1)
        p = out["partitions"][0]
        self.assertEqual(p["focus_rows"][0]["focus_flow"], "X")
        self.assertIsNone(p["focus_rows"][0]["metrics"]["net_weight_kg"])
        self.assertTrue(out["not_for_publication"])

    def test_mirror_annual_is_not_monthly(self):
        item = {"ok": True, "source": "mirror_import", "reporter": "COD", "legs": [
            {"via": "comtrade_CHN", "hs_used": "2603", "grain": "year", "as_of": "2024", "partners": [
                {"partner_code": 180, "flow": "M", "period": "2024", "net_wgt": 10, "primary_value": 30}]}]}
        out = convert_snapshot({"resolved": [item]}, {"COD": "180", "CHN": "156"})
        p = out["partitions"][0]
        self.assertEqual(p["meta"]["frequency"], "A")
        self.assertEqual(p["meta"]["reporter"], "156")
        self.assertEqual(p["focus_rows"][0]["focus_flow"], "X")


if __name__ == "__main__":
    unittest.main()
