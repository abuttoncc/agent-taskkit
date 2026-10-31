import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/finance-research"
HARNESS = ROOT / "skills/task-harness"
sys.path.insert(0, str(HARNESS / "scripts"))
sys.path.insert(0, str(PACKAGE / "scripts"))
import finance
import harness
import install
import research
import workspace

spec = importlib.util.spec_from_file_location("research_demo", ROOT / "examples/research_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class ResearchTest(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "workspace/test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runs)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.instance = self.base / "instance"
        self.result = demo.run(self.instance)
        self.task = self.instance / "projects/example-finance"

    def edit(self, name, callback):
        path = self.task / name
        data = json.loads(path.read_text())
        callback(data)
        path.write_text(json.dumps(data))

    def test_complete_research_and_exact_arithmetic(self):
        self.assertEqual(self.result["assessment"], "PASS")
        self.assertEqual(self.result["calculations"], {"revenue-growth": "25.00", "net-margin": "12.00"})
        result = research.check(self.task)
        self.assertEqual((result["required_count"], result["required_pass"]), (1, 1))
        self.assertIn("inputs/source-example.json", result["evidence_fingerprints"])

    def test_three_scenes_and_legacy_api_share_an_instance(self):
        (self.instance / "memory").mkdir(exist_ok=True)
        (self.instance / "memory/profile.md").write_text("personal preferences")
        before = (self.instance / "memory/profile.md").read_bytes()
        for scene in ("company", "earnings", "peers"):
            research.new(self.instance, scene, "financial question", scene)
            task = self.instance / "projects" / scene
            self.assertTrue((task / "request.md").exists())
            self.assertFalse((task / "spec.json").exists())
            self.assertEqual(json.loads((task / "task.json").read_text())["scene"], scene)
        harness.new(self.instance, "api", "API question", "verify")
        self.assertTrue((self.instance / "projects/api/spec.json").exists())
        self.assertEqual((self.instance / "memory/profile.md").read_bytes(), before)
        self.assertTrue(harness.doctor(self.instance)["errors"])

    def test_unknown_template_or_scene_writes_nothing(self):
        root = self.base / "invalid"
        for template, scene in (("produce", None), ("research", None), ("verify", "company")):
            with self.subTest(template=template, scene=scene), self.assertRaises(ValueError):
                harness.new(root, "test", "question", template, scene)
            self.assertFalse(root.exists())
        with self.assertRaises(ValueError): research.new(root, "test", "question", "api")
        self.assertFalse(root.exists())

    def test_nonpositive_base_is_not_reported_as_growth(self):
        for value in ("0", "-100"):
            self.edit("inputs/metrics.json", lambda x: x["metrics"][1].update(value=value))
            result = finance.calculate(self.task)
            self.assertEqual(result["results"][0]["status"], "NOT_MEANINGFUL")
            self.assertIsNone(result["results"][0]["value"])
            self.assertEqual(result["assessment"], "PARTIAL")

    def test_missing_data_stays_missing(self):
        self.edit("inputs/metrics.json", lambda x: x["metrics"][0].update(value=None))
        result = finance.calculate(self.task)
        self.assertTrue(all(x["status"] == "MISSING" for x in result["results"]))
        self.assertEqual(result["assessment"], "PARTIAL")

    def test_incompatible_units_entities_periods_and_nonfinite_are_rejected(self):
        original = (self.task / "inputs/metrics.json").read_bytes()
        for change in ({"unit": "USD million"}, {"entity": "Other Co"}, {"basis": "parent only"},
                       {"period": "FY2024"}, {"value": "NaN"}, {"value": "Infinity"}):
            (self.task / "inputs/metrics.json").write_bytes(original)
            self.edit("inputs/metrics.json", lambda x: x["metrics"][2].update(change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                finance.calculate(self.task)

    def test_modified_calculation_is_rejected(self):
        self.edit("outputs/calculations-01.json", lambda x: x["results"][0].update(value="99"))
        with self.assertRaisesRegex(ValueError, "changed"):
            research.check(self.task)

    def test_unknown_source_or_future_disclosure_is_rejected(self):
        path = self.task / "inputs/research.json"
        original = path.read_bytes()
        self.edit("inputs/research.json", lambda x: x["claims"][0].update(source_ids=["missing"]))
        with self.assertRaises(ValueError): research.check(self.task)
        path.write_bytes(original)
        self.edit("inputs/research.json", lambda x: x["sources"][0].update(published_at="2999-01-01"))
        with self.assertRaisesRegex(ValueError, "after as_of"): research.check(self.task)

    def test_missing_review_partial_failure_fail(self):
        path = self.task / "inputs/research.json"
        original = path.read_bytes()
        self.edit("inputs/research.json", lambda x: x.update(review=[]))
        self.assertEqual(research.check(self.task)["assessment"], "PARTIAL")
        path.write_bytes(original)
        self.edit("inputs/research.json", lambda x: x["review"][0].update(status="FAIL"))
        self.assertEqual(research.check(self.task)["assessment"], "FAIL")

    def test_revised_checklist_preserves_old_scope_and_exposes_new_missing_item(self):
        original = (self.task / "inputs/expected-v1.csv").read_bytes()
        (self.task / "inputs/expected-v2.csv").write_bytes(original + b"new-item,required,additional check,scope change,new evidence needed\n")
        self.edit("inputs/research.json", lambda x: x.update(expected="inputs/expected-v2.csv"))
        result = research.check(self.task)
        self.assertEqual(result["assessment"], "PARTIAL")
        self.assertEqual(result["required_count"], 2)
        self.assertEqual((self.task / "inputs/expected-v1.csv").read_bytes(), original)

    def test_calculation_source_must_be_registered(self):
        self.edit("inputs/metrics.json", lambda x: x["metrics"][0].update(source_id="unknown"))
        (self.task / "outputs/calculations-01.json").write_text(json.dumps(finance.calculate(self.task)))
        with self.assertRaisesRegex(ValueError, "unknown metric source"):
            research.check(self.task)

    def test_replay_detects_source_or_report_changes_and_cannot_overwrite(self):
        command = [sys.executable, "-B", str(PACKAGE / "scripts/research.py")]
        args = ["--root", str(self.task)]
        result = subprocess.run(command + ["replay", *args, "--report", "outputs/research-review-01.json"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command + ["check", *args, "--out", "outputs/research-review-01.json"], capture_output=True)
        self.assertEqual(result.returncode, 2)
        (self.task / "inputs/source-example.json").write_text('{"changed":true}')
        result = subprocess.run(command + ["replay", *args, "--report", "outputs/research-review-01.json"], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_research_evidence_cannot_escape_task(self):
        outside = self.base / "private.txt"
        outside.write_text("outside evidence")
        (self.task / "inputs/link.txt").symlink_to(outside)
        self.edit("inputs/research.json", lambda x: x["sources"][0].update(evidence=["inputs/link.txt"]))
        with self.assertRaisesRegex(ValueError, "escapes"):
            research.check(self.task)

    def test_installer_rejects_missing_advertised_resource(self):
        source = self.base / "package"
        shutil.copytree(PACKAGE, source)
        (source / "scripts/finance.py").unlink()
        with self.assertRaisesRegex(ValueError, "catalog resource missing"):
            install.install(source, self.base / "installed/finance-research")

    def test_done_research_needs_a_current_check_report(self):
        (self.task / "handoffs").mkdir(exist_ok=True)
        args = dict(deliverables=["deliverables/report-v1.md"], review="Reopened report and compared numbers with the sources.")
        with self.assertRaisesRegex(ValueError, "--report"):
            workspace.checkpoint(self.instance, "example-finance", "done", "Report delivered", **args)
        with self.assertRaisesRegex(ValueError, "must match"):
            workspace.checkpoint(self.instance, "example-finance", "done", "Report delivered", report="outputs/calculations-01.json", **args)
        result = workspace.checkpoint(self.instance, "example-finance", "done", "Report delivered",
                                      report="outputs/research-review-01.json", **args)
        self.assertEqual((result["state"], result["assessment"]), ("RECORDED", "PASS"))
        (self.task / "findings.md").write_text("Edited after the check", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "run the checker again"):
            workspace.checkpoint(self.instance, "example-finance", "done", "Again", report="outputs/research-review-01.json", **args)

    def test_skills_installed_side_by_side_find_each_other(self):
        skills = self.base / "skills"
        install.install(HARNESS, skills / "task-harness")
        install.install(PACKAGE, skills / "finance-research")
        command = [sys.executable, "-B", str(skills / "finance-research/scripts/research.py"), "new", "--root",
                   str(self.base / "other"), "--topic", "peer-check", "--question", "Compare two synthetic peers", "--scene", "peers"]
        result = subprocess.run(command, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads((self.base / "other/projects/peer-check/task.json").read_text(encoding="utf-8"))
        self.assertEqual((task["template"], task["scene"]), ("research", "peers"))
        alone = self.base / "alone"
        install.install(PACKAGE, alone / "finance-research")
        result = subprocess.run(command[:2] + [str(alone / "finance-research/scripts/research.py")] + command[3:],
                                capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task-harness not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
