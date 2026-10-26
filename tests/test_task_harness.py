import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/task-harness"
sys.path.insert(0, str(PACKAGE / "scripts"))
import contract
import harness
import install


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ContractTest(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "workspace/test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_runs)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.instance = self.base / "instance"
        harness.new(self.instance, "api-check", "Validate the fixture API", "verify")
        self.task = self.instance / "projects/api-check"
        spec = json.loads((self.task / "spec.json").read_text())
        spec.update(scope={"included": ["fixture"], "excluded": [], "population": "one fixture",
                           "enumeration": "bounded", "denominator_basis": "test definition"},
                    run_command="python3 fixture.py", environment="local test", sample_plan="one sample", stop_rule="one request")
        spec["revision"]["reason"] = "initial test"
        self.save("spec.json", spec)
        with (self.task / spec["expected"]).open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "requirement", "description", "basis", "acceptance"])
            for ident, kind in (("main", "required"), ("question", "investigate"), ("excluded", "not_applicable")):
                writer.writerow([ident, kind, "check", "fixture", "exact match"])
        self.frozen = contract.freeze_contract(self.task)
        (self.task / "outputs").mkdir(exist_ok=True)
        (self.task / "outputs/evidence.txt").write_text("actual local test evidence")

    def save(self, name, value):
        (self.task / name).write_text(json.dumps(value), encoding="utf-8")

    def rows(self):
        return [{"id": ident, "status": "PASS", "evidence_level": "fixture result", "detail": "checked fixture",
                 "evidence": ["outputs/evidence.txt"]} for ident in ("main", "question")]

    def observed(self, rows=None, **extra):
        value = {"baseline_sha256": self.frozen["sha256"], "observed_at": datetime.now(timezone.utc).isoformat(),
                 "rows": self.rows() if rows is None else rows}
        value.update(extra)
        self.save("outputs/observations.json", value)
        return "outputs/observations.json"

    def test_assessment_matrix(self):
        for scenario, status in (("pass", "PASS"), ("fail", "FAIL"), ("missing", "PARTIAL"),
                                 ("investigate", "PARTIAL"), ("duplicate", "FAIL"),
                                 ("unexpected", "PARTIAL"), ("excluded", "PARTIAL")):
            with self.subTest(scenario=scenario):
                rows = self.rows()
                if scenario == "fail": rows[0]["status"] = "FAIL"
                if scenario == "missing": rows.pop(0)
                if scenario == "investigate": rows[1]["status"] = "NOT_RUN"; rows[1]["evidence"] = []
                if scenario == "duplicate": rows.append(rows[0].copy())
                if scenario in ("unexpected", "excluded"): rows.append({**rows[0], "id": scenario})
                result = contract.compare_observations(self.task, self.observed(rows))
                self.assertEqual(result["assessment"], status)
                self.assertEqual(result["required_count"], 1)

    def test_freeze_and_report_never_overwrite(self):
        original = (self.task / self.frozen["baseline"]).read_bytes()
        with self.assertRaises(ValueError): contract.freeze_contract(self.task)
        self.assertEqual((self.task / self.frozen["baseline"]).read_bytes(), original)
        target = self.task / "outputs/report.json"
        contract.write_new(target, {"old": "FAIL"})
        with self.assertRaises(FileExistsError): contract.write_new(target, {"new": "PASS"})
        self.assertEqual(json.loads(target.read_text()), {"old": "FAIL"})

    def test_modified_spec_is_rejected(self):
        spec = json.loads((self.task / "spec.json").read_text())
        spec["question"] = "Changed after seeing result"
        self.save("spec.json", spec)
        with self.assertRaisesRegex(ValueError, "spec changed"): contract.load_contract(self.task)

    def test_modified_expected_is_rejected(self):
        with (self.task / "inputs/expected-v1.csv").open("a") as f: f.write("added,required,x,y,z\n")
        with self.assertRaisesRegex(ValueError, "expected list changed"): contract.load_contract(self.task)

    def test_evidence_tamper_invalidates_replay(self):
        report = contract.compare_observations(self.task, self.observed())
        self.save("outputs/report-comparison.json", report)
        self.assertEqual(contract.replay(self.task, "outputs/report-comparison.json")["integrity"], "PASS")
        (self.task / "outputs/evidence.txt").write_text("changed evidence")
        with self.assertRaisesRegex(ValueError, "changed"): contract.replay(self.task, "outputs/report-comparison.json")

    def test_observation_binding_and_time(self):
        for extra in ({"baseline_sha256": "wrong"}, {"observed_at": "2000-01-01T00:00:00+00:00"},
                      {"observed_at": "2026-10-25T00:00:00"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                contract.compare_observations(self.task, self.observed(**extra))

    def test_evidence_level_and_files_required(self):
        for change in ({"evidence": []}, {"evidence": ["outputs/missing.json"]}, {"evidence_level": ""}):
            rows = self.rows(); rows[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                contract.compare_observations(self.task, self.observed(rows))

    def test_cli_exit_codes_and_report_preservation(self):
        rows = self.rows(); rows[0]["status"] = "FAIL"
        observed = self.observed(rows)
        command = [sys.executable, "-B", str(PACKAGE / "scripts/contract.py"), "compare", "--root", str(self.task),
                   "--observations", observed, "--out", "outputs/cli-comparison.json"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = (self.task / "outputs/cli-comparison.json").read_bytes()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual((self.task / "outputs/cli-comparison.json").read_bytes(), report)
        result = subprocess.run([sys.executable, "-B", str(PACKAGE / "scripts/contract.py"), "replay", "--root", str(self.task),
                                 "--report", "outputs/cli-comparison.json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_paths_and_symlinks_cannot_escape(self):
        (self.base / "outside.txt").write_text("outside")
        (self.task / "outputs/link.txt").symlink_to(self.base / "outside.txt")
        for name in ("../../../outside.txt", str(self.base / "outside.txt"), "outputs/link.txt", ".env", ".git/config"):
            rows = self.rows(); rows[0]["evidence"] = [name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                contract.compare_observations(self.task, self.observed(rows))

    def test_revision_preserves_history_and_tracks_removed_id(self):
        old_path = self.task / self.frozen["baseline"]
        old_bytes = old_path.read_bytes()
        spec = json.loads((self.task / "spec.json").read_text())
        spec["revision"] = {"previous_baseline": spec["baseline"], "reason": "Reduce scope explicitly"}
        spec["baseline"] = spec["baseline"].replace("-v1", "-v2")
        spec["expected"] = "inputs/expected-v2.csv"
        self.save("spec.json", spec)
        text = (self.task / "inputs/expected-v1.csv").read_text()
        (self.task / spec["expected"]).write_text("\n".join(line for line in text.splitlines() if not line.startswith("question,")) + "\n")
        result = contract.freeze_contract(self.task)
        self.assertEqual(result["changes"]["removed_ids"], ["question"])
        self.assertEqual(old_path.read_bytes(), old_bytes)
        old_path.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "previous baseline changed"): contract.load_contract(self.task)

    def test_new_task_preserves_personal_files(self):
        profile = self.instance / "memory/profile.md"
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text("personal preference")
        before = snapshot(self.instance)
        harness.new(self.instance, "second", "another task")
        after = snapshot(self.instance)
        for name in before: self.assertEqual(before[name], after[name])
        with self.assertRaises(ValueError): harness.new(self.instance, "api-check", "collision")
        self.assertEqual(snapshot(self.instance), after)

    def test_foreign_workspace_refused(self):
        foreign = self.base / "foreign"; foreign.mkdir()
        (foreign / "AGENTS.md").write_text("my own conventions")
        before = snapshot(foreign)
        with self.assertRaises(ValueError): harness.new(foreign, "api-check", "test")
        self.assertEqual(snapshot(foreign), before)

    def test_doctor_is_read_only_and_does_not_claim_effectiveness(self):
        before = snapshot(self.instance)
        result = harness.doctor(self.instance)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["capabilities"]["effective"], "unknown")
        self.assertEqual(snapshot(self.instance), before)

    def test_install_update_preserves_instance_and_refuses_modified_package(self):
        dest = self.base / "installed/task-harness"
        install.install(PACKAGE, dest)
        before = snapshot(self.instance)
        next_source = self.base / "next-package"
        shutil.copytree(PACKAGE, next_source)
        with (next_source / "references/api.md").open("a") as handle: handle.write("\nA documented update.\n")
        info = json.loads((next_source / "catalog.json").read_text()); info["version"] = "0.4.1"
        (next_source / "catalog.json").write_text(json.dumps(info))
        install.install(next_source, dest, update=True)
        self.assertEqual(snapshot(self.instance), before)
        self.assertIn("A documented update", (dest / "references/api.md").read_text())
        (dest / "references/api.md").write_text("local changes")
        with self.assertRaisesRegex(ValueError, "local changes"): install.install(PACKAGE, dest, update=True)
        self.assertEqual((dest / "references/api.md").read_text(), "local changes")


if __name__ == "__main__":
    unittest.main()
