import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/task-harness"
sys.path.insert(0, str(PACKAGE / "scripts"))
import harness
import workspace


class HookSessionTest(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "workspace/test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runs)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "instance"
        self.environment = patch.dict(os.environ, {name: "" for name in
            ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_SESSION_ID")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        harness.new(self.root, "alpha", "Work belonging to session A")
        harness.new(self.root, "beta", "Work belonging to session B")
        self.a = "session-a-" + self.temp.name
        self.b = "session-b-" + self.temp.name

    def payload(self, session):
        return {"cwd": str(self.root), "session_id": session}

    def test_unknown_session_never_falls_back_to_all_recent_tasks(self):
        for transcript in (None, "", str(self.root / "missing.jsonl")):
            with self.subTest(transcript=transcript):
                self.assertIsNone(harness.stop_reminder({
                    **self.payload(self.a + str(transcript)), "transcript_path": transcript}))

    def test_task_inventory_and_other_hook_text_do_not_establish_ownership(self):
        transcript = self.root / "inventory.jsonl"
        transcript.write_text(json.dumps({"type": "tool_result", "output":
            "projects/alpha projects/beta; task-harness: checkpoint beta"}) + "\n")
        self.assertIsNone(harness.stop_reminder({
            **self.payload(self.a), "transcript_path": str(transcript)}))

    def test_two_bound_sessions_only_check_their_own_tasks(self):
        workspace.bind_session(self.root, "alpha", self.a)
        workspace.bind_session(self.root, "beta", self.b)
        for session, own, other in [(self.a, "alpha", "beta"), (self.b, "beta", "alpha")]:
            result = harness.stop_reminder(self.payload(session))
            self.assertIn(own, result["reason"])
            self.assertNotIn(other, result["reason"])
            self.assertIsNone(harness.stop_reminder(self.payload(session)))
        self.assertIsNone(harness.stop_reminder(self.payload("unbound")))

    def test_binding_is_idempotent_and_does_not_rewrite_task_records(self):
        task = self.root / "projects/alpha"
        before = {str(p.relative_to(task)): p.read_bytes() for p in task.rglob("*") if p.is_file()}
        for _ in range(2):
            result = subprocess.run([sys.executable, "-B", str(PACKAGE / "scripts/harness.py"),
                "bind", "--root", str(self.root), "--topic", "alpha", "--session-id", self.a],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {str(p.relative_to(task)): p.read_bytes()
            for p in task.rglob("*") if p.is_file()})
        self.assertIn("alpha", harness.stop_reminder(self.payload(self.a))["reason"])

    def test_new_and_checkpoint_bind_the_current_runtime_session(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": self.a}):
            harness.new(self.root, "gamma", "Automatically bound new task")
        self.assertEqual(workspace.session_tasks(self.root, self.a), ["gamma"])
        with patch.dict(os.environ, {"CODEX_SESSION_ID": self.b}):
            workspace.checkpoint(self.root, "beta", "active", "Started", "Continue")
        self.assertEqual(workspace.session_tasks(self.root, self.b), ["beta"])
        self.assertIsNone(harness.stop_reminder(self.payload(self.b)))
        workspace.bind_session(self.root, "alpha", self.b)
        self.assertIn("alpha", harness.stop_reminder(self.payload(self.b))["reason"])

    def test_missing_session_id_cannot_share_anonymous_scope(self):
        self.assertIsNone(harness.stop_reminder({"cwd": str(self.root)}))
        with self.assertRaises(ValueError):
            workspace.bind_session(self.root, "alpha", "")

    def test_concurrent_bindings_do_not_overwrite_each_other(self):
        bindings = [(topic, session) for topic in ("alpha", "beta") for session in (self.a, self.b)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda pair: workspace.bind_session(self.root, *pair), bindings * 4))
        self.assertEqual(workspace.session_tasks(self.root, self.a), ["alpha", "beta"])
        self.assertEqual(workspace.session_tasks(self.root, self.b), ["alpha", "beta"])

    def test_removed_task_does_not_hide_another_bound_task(self):
        workspace.bind_session(self.root, "alpha", self.a)
        workspace.bind_session(self.root, "beta", self.a)
        (self.root / "projects/alpha").rename(self.root / "removed-alpha")
        result = harness.stop_reminder(self.payload(self.a))
        self.assertIn("beta", result["reason"])
        self.assertNotIn("alpha", result["reason"])


if __name__ == "__main__":
    unittest.main()
