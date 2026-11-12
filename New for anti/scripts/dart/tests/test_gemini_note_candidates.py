import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_kfa.gemini_note_candidates import candidate_report, scan_with_gemini
from dart_kfa.pe_cr_evidence import reviewed_facts


FIXTURES = Path(__file__).with_name("fixtures")


class GeminiCandidateTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((FIXTURES / "pe_cr_gemini_itt_2025_rows.json").read_text())
        self.replay = json.loads((FIXTURES / "pe_cr_gemini_itt_2025_replay.json").read_text())

    def test_itt_candidates_use_original_cells_and_cannot_enter_engine(self):
        report = candidate_report(self.packet, self.replay)
        self.assertEqual(report["approved_facts"], 0)
        self.assertEqual(report["origin"], "offline_replay")
        self.assertEqual(report["roles_not_proposed"], [])
        self.assertEqual([c["source_cell"]["amount"] for c in report["candidates"]], ["125.2", "411.8", "671.9"])
        self.assertTrue(all(c["status"] == "requires_review" for c in report["candidates"]))
        with self.assertRaisesRegex(ValueError, "invalid:reviewed_schema"):
            reviewed_facts(report, {})

    def test_model_cannot_supply_amount_or_approve_own_row(self):
        for extra in ({"amount": "1"}, {"status": "verified"}, {"source_url": "https://example.com"}):
            choice = {**self.replay["matches"][0], **extra}
            with self.assertRaisesRegex(ValueError, "invalid:model_match_fields"):
                candidate_report(self.packet, {"matches": [choice]})

    def test_ambiguous_duplicate_or_out_of_scope_rows_rejected(self):
        first, second, *_ = self.replay["matches"]
        duplicate = {**second, "row_id": first["row_id"]}
        with self.assertRaisesRegex(ValueError, "conflict:duplicate_model_match"):
            candidate_report(self.packet, {"matches": [first, duplicate]})
        for row_id in ("no-such-row", "n9-r2-prior"):
            with self.assertRaisesRegex(ValueError, "invalid:model_role_or_row_id"):
                candidate_report(self.packet, {"matches": [{**first, "row_id": row_id}]})
        packet = deepcopy(self.packet)
        packet["rows"][1]["currency"] = "KRW"
        with self.assertRaisesRegex(ValueError, "invalid:model_role_or_row_id"):
            candidate_report(packet, {"matches": [first]})

    def test_exact_public_filing_and_date_required(self):
        for url in ("https://www.sec.gov.example/Archives/edgar/data/216228/000021622826000012/itt-20251231.htm",
                    self.packet["filing_url"].replace("000021622826000012", "000021622826000013"),
                    self.packet["filing_url"] + "?token=test"):
            with self.assertRaisesRegex(ValueError, "invalid:public_filing"):
                candidate_report({**self.packet, "filing_url": url}, self.replay)
        packet = deepcopy(self.packet)
        packet["rows"][0]["period_end"] = "2025-02-31"
        with self.assertRaisesRegex(ValueError, "invalid:iso_date"):
            candidate_report(packet, self.replay)

    def test_dart_order_flow_and_balance_distinct(self):
        packet = {**self.packet, "profile": "shipbuilding", "source": "DART", "entity_id": "00164742",
                  "filing_id": "20260318001394", "filing_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001394",
                  "currency": "KRW"}
        row = {**self.packet["rows"][0], "label": "신규 수주", "currency": "KRW", "period_start": "2025-01-01"}
        packet["rows"] = [row]
        report = candidate_report(packet, {"matches": [{"role": "new_orders", "row_id": row["id"]}]})
        self.assertEqual(report["roles_not_proposed"], ["order_backlog"])
        with self.assertRaisesRegex(ValueError, "incompatible:model_row_kind"):
            candidate_report(packet, {"matches": [{"role": "order_backlog", "row_id": row["id"]}]})

    def test_live_request_is_one_bounded_labels_only_post(self):
        requests = []

        def transport(request):
            requests.append(request)
            body = json.loads(request.data)
            self.assertEqual(request.get_method(), "POST")
            self.assertTrue(request.full_url.startswith("https://generativelanguage.googleapis.com/"))
            self.assertNotIn("secret-for-test", request.full_url)
            self.assertEqual(request.get_header("X-goog-api-key"), "secret-for-test")
            prompt = body["contents"][0]["parts"][0]["text"]
            self.assertIn("Work in process", prompt)
            for value in ("125.2", "671.9", "n9-r2-prior", "0000216228", self.packet["filing_url"], "secret-for-test"):
                self.assertNotIn(value, prompt)
            self.assertNotIn("tools", body)
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(self.replay)}]}}]}

        result = scan_with_gemini(self.packet, model="gemini-test", api_key="secret-for-test", transport=transport)
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["origin"], "gemini")
        self.assertEqual(len(result["candidates"]), 3)

    def test_missing_key_or_empty_rows_does_not_call_provider(self):
        def never(_):
            self.fail("Unexpected call")

        with self.assertRaisesRegex(ValueError, "missing:GEMINI_API_KEY"):
            scan_with_gemini(self.packet, model="gemini-test", api_key=None, transport=never)
        packet = {**self.packet, "rows": [self.packet["rows"][-1]]}
        result = scan_with_gemini(packet, model="gemini-test", api_key="secret-for-test", transport=never)
        self.assertEqual(result["origin"], "no_eligible_rows")
        self.assertEqual(len(result["roles_not_proposed"]), 3)

    def test_blocked_truncated_and_malformed_responses_fail_closed(self):
        for candidate, error in (({"finishReason": "MAX_TOKENS"}, "gemini_incomplete_response"),
                                 ({"finishReason": "STOP", "content": {"parts": [{"text": "secret test response"}]}}, "invalid:gemini_response")):
            with self.assertRaisesRegex(ValueError, error):
                scan_with_gemini(self.packet, model="gemini-test", api_key="secret-for-test",
                                 transport=lambda _: {"candidates": [candidate]})


if __name__ == "__main__":
    unittest.main()
