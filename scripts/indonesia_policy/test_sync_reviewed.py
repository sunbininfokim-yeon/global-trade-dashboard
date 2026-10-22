import fcntl
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from sync_reviewed import run, Gateway, load_manifest, DatabaseLease, main


def entry(name="idn-a", host="test.go.id"):
    return dict(document_id=name, url=f"https://{host}/{name}", primary_stage="coal")


def doc(e):
    text = "Official reviewed source " * 10
    return dict(document_id=e["document_id"], country_code="IDN", legal_status="unverified",
                source_url=e["url"], observed_at="2026-10-21T00:00:00Z", content_kind="official_text",
                body_status="extracted", text_content=text, content_hash=hashlib.sha256(text.encode()).hexdigest(), topics=["coal"])


class SyncTests(unittest.TestCase):
    def test_cli_requires_database_lease_and_busy_runner_never_fetches(self):
        rpc = Mock(return_value={"acquired": False})
        with tempfile.TemporaryDirectory() as root, patch("sync_reviewed.Gateway", return_value=rpc), patch("sync_reviewed.run") as refresh:
            with patch("sys.argv", ["sync_reviewed.py", "--write", "--state-dir", root]):
                with self.assertRaisesRegex(RuntimeError, "busy on another runner"):
                    main()
            refresh.assert_not_called()
            self.assertEqual(rpc.call_args.args[0], "idn_acquire_sync_lease")

    def test_database_lease_fences_writes_and_release_failure_does_not_mask_original(self):
        token = str(uuid.uuid4())
        rpc = Mock(side_effect=[{"acquired": True, "lease_token": token}, True, False, False, RuntimeError("DB down")])
        with patch("sys.stderr") as stderr:
            with self.assertRaisesRegex(RuntimeError, "lease lost"):
                with DatabaseLease(rpc, "mac:1") as lease:
                    self.assertIs(lease("idn_store_document", {"p_document": {}}), False)
                    lease("idn_store_source_check", {"p_check": {}})
            self.assertTrue(stderr.write.called)
        self.assertEqual(rpc.call_args_list[2].args, ("idn_sync_store_document", {"p_document": {}, "p_lease_token": token}))
        self.assertFalse(any(c.args[0] == "idn_sync_store_source_check" for c in rpc.call_args_list))
        self.assertEqual(rpc.call_args.args, ("idn_release_sync_lease", {"p_lease_token": token}))

    def test_cli_status_and_stop_do_not_acquire_lease_or_request_sources(self):
        with tempfile.TemporaryDirectory() as root, patch("sync_reviewed.Gateway") as gateway, patch("sync_reviewed.run") as refresh, patch("builtins.print"):
            (Path(root)/"STOP").touch()
            with patch("sys.argv", ["sync_reviewed.py", "--write", "--state-dir", root]):
                self.assertEqual(main(), 0)
            gateway.assert_not_called(); refresh.assert_not_called()
            gateway.return_value.return_value = {"country": "IDN", "lease": {"active": False}}
            with patch("sys.argv", ["sync_reviewed.py", "--status"]):
                self.assertEqual(main(), 0)
            gateway.return_value.assert_called_once_with("idn_sync_status", {})

    def test_failed_deferred_partial_and_complete_batches_are_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = [entry(), entry("idn-b")]
            first = run(manifest, root, lambda *_: True, limit=1, collect_fn=Mock(side_effect=ValueError("blocked")), pause=lambda _: None)
            self.assertEqual(first["state"], "unavailable")
            second = run(manifest, root, lambda *_: True, limit=1, collect_fn=Mock(), pause=lambda _: None)
            self.assertEqual(second["state"], "deferred")
            self.assertEqual(json.loads((Path(root)/"status.json").read_text())["last_batch"]["state"], "deferred")
        with tempfile.TemporaryDirectory() as root:
            metadata = {**doc(entry()), "content_kind": "official_metadata"}
            result = run([entry(), entry("idn-b", "other.go.id")], root, lambda *_: True,
                         collect_fn=Mock(side_effect=[metadata, doc(entry("idn-b", "other.go.id"))]), pause=lambda _: None)
            self.assertEqual(result["state"], "partial"); self.assertEqual(result["complete_text_checks"], 1)
        with tempfile.TemporaryDirectory() as root:
            result = run([entry()], root, lambda *_: True, collect_fn=lambda e, *_: doc(e), pause=lambda _: None)
            self.assertEqual(result["state"], "ok")

    def test_lost_heartbeat_keeps_source_and_cursor_for_retry(self):
        with tempfile.TemporaryDirectory() as root:
            heartbeat = Mock(side_effect=RuntimeError("lease lost")); collect = Mock()
            with self.assertRaisesRegex(RuntimeError, "lease lost"):
                run([entry()], root, Mock(), collect_fn=collect, heartbeat=heartbeat)
            collect.assert_not_called()

    def test_unknown_audit_acknowledgment_never_advances_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            rpc = lambda name, _: True if name == "idn_store_document" else None
            with self.assertRaisesRegex(RuntimeError, "invalid IDN audit response"):
                run([entry(), entry("idn-b")], root, rpc, limit=1, collect_fn=lambda e, *_: doc(e), pause=lambda _: None)
            state = json.loads((Path(root)/"status.json").read_text())
            self.assertEqual(state["cursor"], 0);self.assertIsNotNone(state["active"])

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
