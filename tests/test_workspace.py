import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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

    def test_control_files_are_not_deliverables(self):
        task = self.start()
        workspace.checkpoint(self.root, "brief", "active", "Outline ready", "Write plan")
        for ref in ("request.md", "README.md", "task.json", "handoffs/000001.json"):
            with self.assertRaises(ValueError):
                workspace.checkpoint(self.root, "brief", "done", "Finished", deliverables=[ref], review="Checked")
        self.assertEqual(len(workspace.snapshots(task)), 1)

    def test_work_in_progress_edits_are_reported_without_flagging(self):
        task = self.start()
        workspace.checkpoint(self.root, "brief", "active", "Outline ready", "Write plan")
        (task / "request.md").write_text("Scope clarified during work", encoding="utf-8")
        review = workspace.handoff_check(task)
        self.assertEqual(review["state"], "RECORDED")
        self.assertEqual(review["changed_since_checkpoint"], ["request.md"])

    def test_delivered_file_is_frozen_and_revision_uses_new_name(self):
        task = self.start()
        self.complete(task)
        workspace.checkpoint(self.root, "brief", "active", "User requests a revision", "Write plan v2")
        (task / "deliverables/plan.md").write_text("Overwritten in place", encoding="utf-8")
        self.assertEqual(workspace.handoff_check(task)["state"], "NEEDS_ATTENTION")
        before = snapshot(task / "handoffs")
        with self.assertRaises(ValueError):
            workspace.checkpoint(self.root, "brief", "active", "Still revising", "Finish v2")
        self.assertEqual(snapshot(task / "handoffs"), before)
        (task / "deliverables/plan.md").write_text("A synthetic plan for testing handoff integrity.")
        (task / "deliverables/plan-v2.md").write_text("Revised plan", encoding="utf-8")
        workspace.checkpoint(self.root, "brief", "done", "Plan v2 delivered", deliverables=["deliverables/plan-v2.md"],
                             review="Compared v2 with the revision request and reopened the file.")
        self.assertEqual(workspace.handoff_check(task)["state"], "RECORDED")

    def test_lost_delivery_can_be_recorded_but_not_hidden(self):
        task = self.start()
        self.complete(task)
        (task / "deliverables/plan.md").write_text("Overwritten before this rule existed", encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.checkpoint(self.root, "brief", "active", "Revising", "Write v2", overwritten=["deliverables/plan.md"])
        workspace.checkpoint(self.root, "brief", "active", "Revising", "Write v2",
                             overwritten=["deliverables/plan.md"], reason="Original bytes not backed up")
        self.assertEqual(workspace.handoff_check(task)["state"], "RECORDED")
        latest = json.loads(workspace.snapshots(task)[-1].read_text(encoding="utf-8"))
        self.assertEqual(latest["overwritten"]["deliverables/plan.md"]["reason"], "Original bytes not backed up")
        (task / "deliverables/plan.md").write_text("Changed again", encoding="utf-8")
        self.assertEqual(workspace.handoff_check(task)["state"], "NEEDS_ATTENTION")

    def test_new_task_works_without_utf8_locale(self):
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0"}
        result = subprocess.run([sys.executable, "-B", "-X", "utf8=0", str(PACKAGE / "scripts/harness.py"), "new",
                                 "--root", str(self.root), "--topic", "brief", "--question", "整理方案材料"],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("整理方案材料", (self.root / "projects/brief/request.md").read_text(encoding="utf-8"))

    def test_stop_hook_reminds_once_and_stays_quiet_elsewhere(self):
        task = self.start()
        payload = {"cwd": str(task), "session_id": f"test-{id(self)}"}
        first = harness.stop_reminder(payload)
        self.assertEqual(first["decision"], "block")
        self.assertIn("brief", first["reason"])
        self.assertIsNone(harness.stop_reminder(payload))
        self.assertIsNone(harness.stop_reminder({**payload, "session_id": "other", "stop_hook_active": True}))
        self.assertIsNone(harness.stop_reminder({**payload, "session_id": "later"}, now=time.time() + 2 * 86400))
        self.assertIsNone(harness.stop_reminder({"cwd": str(self.base), "session_id": "elsewhere"}))
        workspace.checkpoint(self.root, "brief", "active", "Outline ready", "Write plan")
        self.assertIsNone(harness.stop_reminder({**payload, "session_id": "after-checkpoint"}))
        result = subprocess.run([sys.executable, "-B", str(PACKAGE / "scripts/harness.py"), "hook"],
                                input="not json", capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        config = json.loads(subprocess.run([sys.executable, "-B", str(PACKAGE / "scripts/harness.py"), "hook", "--print-config", "codex"],
                                           capture_output=True, text=True).stdout)
        self.assertIn("--event stop", config["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.assertIn("--event session-start", config["hooks"]["SessionStart"][0]["hooks"][0]["command"])

    def test_session_brief_is_small_and_lists_unfinished_work(self):
        self.assertIsNone(harness.session_brief({"cwd": str(self.base)}))
        workspace.init(self.root, "work/tasks")
        empty = harness.session_brief({"cwd": str(self.root)})["hookSpecificOutput"]
        self.assertEqual(empty["hookEventName"], "SessionStart")
        self.assertIn("work/tasks/", empty["additionalContext"])
        self.assertEqual(empty["additionalContext"].count("\n"), 0)
        harness.new(self.root, "brief", "Prepare a plan")
        workspace.checkpoint(self.root, "brief", "active", "Outline ready", "Write the plan body")
        for index in range(6):
            harness.new(self.root, f"extra-{index}", "Another goal")
        text = harness.session_brief({"cwd": str(self.root / "work")})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Write the plan body", text)
        self.assertIn("另有 2 项", text)
        self.assertLess(len(text.encode("utf-8")), 2000)

    def test_stop_window_comes_from_instance_config(self):
        task = self.start()
        marker = self.root / ".task-harness.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        data["hook"] = {"stop_recent_hours": 1}
        marker.write_text(json.dumps(data), encoding="utf-8")
        payload = {"cwd": str(task), "session_id": f"window-{id(self)}"}
        self.assertIsNone(harness.stop_reminder(payload, now=time.time() + 2 * 3600))
        self.assertEqual(harness.stop_reminder(payload)["decision"], "block")
        data["hook"] = {"stop_recent_hours": 0}
        marker.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            harness.stop_reminder({**payload, "session_id": "bad-window"})

    def test_stop_reminder_only_covers_tasks_this_session_named(self):
        self.start()
        harness.new(self.root, "other-work", "Owned by a concurrent session")
        transcript = self.base / "session.jsonl"
        transcript.write_text('{"tool":"Edit","file_path":"projects/brief/request.md"}\n', encoding="utf-8")
        result = harness.stop_reminder({"cwd": str(self.root), "session_id": f"mine-{id(self)}", "transcript_path": str(transcript)})
        self.assertIn("brief", result["reason"])
        self.assertNotIn("other-work", result["reason"])
        transcript.write_text("an unrelated question", encoding="utf-8")
        self.assertIsNone(harness.stop_reminder({"cwd": str(self.root), "session_id": f"q-{id(self)}", "transcript_path": str(transcript)}))

    def test_hook_root_option_reaches_a_subdirectory_instance(self):
        project = self.base / "project"
        self.root = project / "workspace"
        self.start()
        payload = {"cwd": str(project), "session_id": f"root-{id(self)}"}
        self.assertIsNone(harness.session_brief(payload))
        self.assertIn("brief", harness.session_brief(payload, self.root)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(harness.stop_reminder(payload, root=self.root)["decision"], "block")
        self.assertIsNone(harness.session_brief(payload, project))
        command = [sys.executable, "-B", str(PACKAGE / "scripts/harness.py"), "hook", "--event", "session-start", "--root", str(self.root)]
        result = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")
        config = harness.hook_config("claude", self.root)
        self.assertIn(f"--root '{self.root.resolve()}'", config["hooks"]["Stop"][0]["hooks"][0]["command"])

    def test_research_template_points_to_companion_skill(self):
        with self.assertRaisesRegex(ValueError, "finance-research"):
            harness.new(self.root, "company", "Study a company", "research")
        self.assertFalse(self.root.exists())

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
