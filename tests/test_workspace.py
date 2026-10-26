import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/task-harness"
sys.path.insert(0, str(PACKAGE / "scripts"))
import harness
import workspace
from test_task_harness import snapshot


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "workspace/test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runs)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "instance"

    def start(self):
        harness.new(self.root, "brief", "Prepare a plan from the supplied materials")
        return self.root / "projects/brief"

    def complete(self, task):
        (task / "deliverables").mkdir(exist_ok=True)
        (task / "deliverables/plan.md").write_text("A synthetic plan for testing handoff integrity.")
        return workspace.checkpoint(self.root, "brief", "done", "Plan delivered",
                                    deliverables=["deliverables/plan.md"], review="Opened plan and checked it against the requested scope.")

    def test_empty_init_has_no_dummy_tasks_or_empty_asset_folders(self):
        workspace.init(self.root)
        self.assertEqual(set(snapshot(self.root)), {"AGENTS.md", "WORKSPACE.md", ".task-harness.json"})
        self.assertEqual(workspace.inventory(self.root)["tasks"], [])
        self.assertFalse((self.root / "projects").exists())
        self.assertFalse((self.root / "memory").exists())
        before = snapshot(self.root)
        workspace.init(self.root)
        self.assertEqual(snapshot(self.root), before)

    def test_existing_project_keeps_all_rules_and_custom_task_location(self):
        self.root.mkdir()
        for name in ("AGENTS.md", "CLAUDE.md", "README.md", "source.py"):
            (self.root / name).write_text("Original content: " + name)
        before = snapshot(self.root)
        workspace.init(self.root, "work/tasks")
        harness.new(self.root, "brief", "Prepare a plan")
        after = snapshot(self.root)
        for name, digest in before.items():
            self.assertEqual(after[name], digest)
        self.assertTrue((self.root / "work/tasks/brief/request.md").is_file())
        self.assertEqual(workspace.inventory(self.root)["tasks"][0]["path"], "work/tasks/brief")
        with self.assertRaises(ValueError): workspace.init(self.root, "projects")
        self.assertEqual(snapshot(self.root), after)

    def test_claude_only_project_does_not_get_competing_agents_file(self):
        self.root.mkdir()
        (self.root / "CLAUDE.md").write_text("Existing conventions")
        workspace.init(self.root)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(harness.doctor(self.root)["errors"], [])

    def test_conflict_is_detected_before_any_write(self):
        self.root.mkdir()
        (self.root / "WORKSPACE.md").write_text("Existing entry")
        before = snapshot(self.root)
        with self.assertRaises(ValueError): workspace.init(self.root)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.root / ".task-harness.json").exists())

    def test_task_directory_parent_file_rejected_before_bootstrap(self):
        self.root.mkdir()
        (self.root / "work").write_text("An existing user file")
        before = snapshot(self.root)
        with self.assertRaises(ValueError): workspace.init(self.root, "work/tasks")
        self.assertEqual(snapshot(self.root), before)

    def test_general_new_is_minimal_and_duplicate_preserves_everything(self):
        task = self.start()
        self.assertEqual(set(snapshot(task)), {"README.md", "request.md", "task.json"})
        self.assertEqual(json.loads((task / "task.json").read_text())["template"], "general")
        before = snapshot(self.root)
        with self.assertRaises(ValueError): harness.new(self.root, "brief", "Same topic")
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(workspace.inventory(self.root)["tasks"][0]["state"], "NO_HANDOFF")

    def test_active_blocked_done_and_reopen_keep_snapshots(self):
        task = self.start()
        workspace.checkpoint(self.root, "brief", "active", "Outline ready", "Write plan")
        workspace.checkpoint(self.root, "brief", "blocked", "Missing attachment", "Continue after attachment arrives", "Attachment not available; receiving it releases the blocker")
        first = snapshot(task / "handoffs")
        self.complete(task)
        workspace.checkpoint(self.root, "brief", "active", "User requests a revision", "Revise plan")
        for name, digest in first.items():
            self.assertEqual(snapshot(task / "handoffs")[name], digest)
        row = workspace.inventory(self.root)["tasks"][0]
        self.assertEqual(row["recorded_status"], "active")
        self.assertEqual(row["next_step"], "Revise plan")
        self.assertEqual(len(workspace.snapshots(task)), 4)

    def test_incomplete_handoff_writes_nothing(self):
        self.start()
        for args in ({"status": "active"}, {"status": "blocked", "next_step": "continue"},
                     {"status": "done", "review": "Reviewed"}):
            before = snapshot(self.root)
            with self.assertRaises(ValueError):
                workspace.checkpoint(self.root, "brief", summary="Progress", **args)
            self.assertEqual(snapshot(self.root), before)

    def test_done_requires_review_and_no_blocker(self):
        task = self.start()
        (task / "answer.md").write_text("Answer")
        for args in ({}, {"review": "Checked", "blocker": "Still blocked"}):
            with self.assertRaises(ValueError):
                workspace.checkpoint(self.root, "brief", "done", "Finished", deliverables=["answer.md"], **args)
        self.assertFalse((task / "handoffs").exists())

    def test_changed_delivery_and_changed_scope_are_visible_without_rewriting_history(self):
        task = self.start()
        self.complete(task)
        before = snapshot(task / "handoffs")
        (task / "deliverables/plan.md").write_text("Revised plan")
        self.assertEqual(workspace.handoff_check(task)["state"], "NEEDS_ATTENTION")
        self.assertTrue(harness.doctor(self.root)["errors"])
        self.assertEqual(snapshot(task / "handoffs"), before)
        self.complete(task)
        (task / "request.md").write_text("Changed scope")
        self.assertEqual(workspace.handoff_check(task)["state"], "NEEDS_ATTENTION")

    def test_paths_and_symlink_escapes_write_nothing(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("Private test fixture")
        for directory in ("../outside", str(outside), ".git/tasks", "projects/../outside", "WORKSPACE.md", "AGENTS.md/tasks"):
            with self.assertRaises(ValueError): workspace.init(self.root, directory)
            self.assertFalse(self.root.exists())
        self.root.mkdir()
        (self.root / "projects").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): workspace.init(self.root)
        self.assertFalse((self.root / ".task-harness.json").exists())
        (self.root / "projects").unlink()
        self.root.rmdir()
        task = self.start()
        (task / "link").symlink_to(outside, target_is_directory=True)
        for ref in ("../other/answer.md", "link/private.txt", str(outside / "private.txt"), ".env"):
            with self.assertRaises(ValueError):
                workspace.checkpoint(self.root, "brief", "done", "No", deliverables=[ref], review="Checked")
        self.assertFalse((task / "handoffs").exists())

    def test_old_instance_does_not_get_migrated(self):
        self.root.mkdir()
        (self.root / ".task-harness.json").write_text(json.dumps({"schema": "task-harness.instance/v1", "created_with": "0.3.0"}))
        (self.root / "AGENTS.md").write_text("User-owned old entry")
        old = self.root / "projects/old-task"
        old.mkdir(parents=True)
        (old / "README.md").write_text("Legacy task progress")
        (old / "spec.json").write_text('{"question":"Old task"}')
        before = snapshot(self.root)
        workspace.init(self.root)
        harness.new(self.root, "brief", "A different goal")
        after = snapshot(self.root)
        for name, digest in before.items(): self.assertEqual(after[name], digest)
        self.assertFalse((self.root / "WORKSPACE.md").exists())
        self.assertEqual(len(workspace.inventory(self.root)["tasks"]), 2)

    def test_inventory_is_read_only_and_does_not_enter_escaped_task(self):
        self.start()
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "projects/other").symlink_to(outside, target_is_directory=True)
        before = snapshot(self.root)
        rows = workspace.inventory(self.root)["tasks"]
        self.assertEqual(rows[1]["state"], "NEEDS_ATTENTION")
        self.assertEqual(snapshot(self.root), before)

    def test_cli_uses_general_and_reports_missing_then_valid_handoff(self):
        command = [sys.executable, "-B", str(PACKAGE / "scripts/harness.py")]
        def run(*args):
            return subprocess.run(command + list(args) + ["--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(run("init").returncode, 0)
        result = run("new", "--topic", "brief", "--question", "Prepare a plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["template"], "general")
        self.assertEqual(run("handoff", "--topic", "brief").returncode, 1)
        result = run("checkpoint", "--topic", "brief", "--status", "active", "--summary", "Outline ready", "--next", "Write plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run("handoff", "--topic", "brief").returncode, 0)
        self.assertEqual(len(json.loads(run("tasks").stdout)["tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
