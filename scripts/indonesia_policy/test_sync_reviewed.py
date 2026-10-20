import fcntl
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from sync_reviewed import run, Gateway, load_manifest


def entry(name="idn-a", host="test.go.id"):
    return dict(document_id=name, url=f"https://{host}/{name}", primary_stage="coal")


def doc(e):
    text = "Official reviewed source " * 10
    return dict(document_id=e["document_id"], country_code="IDN", legal_status="unverified",
                source_url=e["url"], observed_at="2026-10-21T00:00:00Z", content_kind="official_text",
                body_status="extracted", text_content=text, content_hash=hashlib.sha256(text.encode()).hexdigest(), topics=["coal"])


class SyncTests(unittest.TestCase):
    def test_active_registry_includes_later_reviewed_coal_sources(self):
        ids = {e["document_id"] for e in load_manifest()}
        self.assertTrue({"idn-kemendag-permendag-15-2026", "idn-pmk-51-2025", "idn-esdm-permen-6-2026"} <= ids)

    def test_import_failure_reuses_artifact_and_does_not_advance_until_audit_written(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            collect = Mock(side_effect=lambda e, *_: doc(e))
            failed = [False]
            def rpc(name, args):
                calls.append((name, args))
                if name == "idn_store_source_check" and not failed[0]:
                    failed[0] = True
                    raise RuntimeError("DB unavailable")
                return True
            with self.assertRaisesRegex(RuntimeError, "DB unavailable"):
                run([entry(), entry("idn-b")], root, rpc, limit=1, collect_fn=collect, pause=lambda _: None)
            state = json.loads((Path(root)/"status.json").read_text())
            self.assertEqual(state["cursor"], 0)
            self.assertIsNotNone(state["active"])
            result = run([entry(), entry("idn-b")], root, rpc, limit=1, collect_fn=collect, pause=lambda _: None)
            self.assertEqual(result["cursor"], 1)
            self.assertEqual(collect.call_count, 1)
            self.assertEqual(len([c for c in calls if c[0] == "idn_store_document"]), 2)

    def test_blocked_host_cooldown_is_retained_across_runs_and_other_hosts_progress(self):
        with tempfile.TemporaryDirectory() as root:
            collect = Mock(side_effect=[ValueError("blocked_or_maintenance"), doc(entry("idn-c", "other.go.id"))])
            manifest = [entry(), entry("idn-b"), entry("idn-c", "other.go.id")]
            result = run(manifest, root, lambda *_: True, limit=1, collect_fn=collect, pause=lambda _: None)
            self.assertEqual(result["source_failures"], 1)
            result = run(manifest, root, lambda *_: True, limit=2, collect_fn=collect, pause=lambda _: None)
            self.assertEqual(result["cooldown_skips"], 1)
            self.assertEqual(collect.call_count, 2)
            self.assertEqual(result["cycle"], 1)

    def test_stop_lock_and_manifest_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            collect = Mock()
            (p/"STOP").touch()
            self.assertTrue(run([entry()], root, Mock(), collect_fn=collect)["stopped"])
            collect.assert_not_called()
            (p/"STOP").unlink()
            with open(p/"sync.lock", "r+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    run([entry()], root, Mock(), collect_fn=collect)
            run([entry()], root, lambda *_: True, collect_fn=lambda e, *_: doc(e), pause=lambda _: None)
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                run([entry("idn-other")], root, Mock(), collect_fn=collect)

    def test_modified_artifact_and_non_idn_rpc_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError):
                run([entry()], root, Mock(side_effect=RuntimeError("DB failed")), collect_fn=lambda e, *_: doc(e), pause=lambda _: None)
            p = next(Path(root).glob("cycle-*.json"))
            value = json.loads(p.read_text()); value["document"]["text_content"] += "tampered"
            p.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "invalid saved source"):
                run([entry()], root, Mock(), collect_fn=Mock())
        gateway = object.__new__(Gateway)
        with self.assertRaisesRegex(ValueError, "not an IDN"):
            gateway("mail_claim", {})

    def test_database_gateway_refuses_redirects_and_bounds_response_bodies(self):
        gateway = object.__new__(Gateway); gateway.url = "https://project.supabase.co"; gateway.key = "fixture-secret"
        response = MagicMock(); response.__enter__.return_value = response; response.status_code = 302
        with patch("sync_reviewed.requests.post", return_value=response) as post:
            with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                gateway("idn_mail_review_queue", {})
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
        response.status_code = 200; response.iter_content.return_value = [b"x" * (256 * 1024 + 1)]
        with patch("sync_reviewed.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "too large"):
                gateway("idn_mail_review_queue", {})


if __name__ == "__main__":
    unittest.main()
