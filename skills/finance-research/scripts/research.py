#!/usr/bin/env python3
"""Create research tasks and check their source links, calculations and acceptance coverage."""
import argparse
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import taskharness  # noqa: F401  (puts task-harness scripts on sys.path)
from contract import EXPECTED_FIELDS, REQUIREMENTS, RESULTS, fingerprint, nonempty, require, safe_path, utf8_argv, write_new
from finance import verify_saved
import workspace

PACKAGE = Path(__file__).resolve().parents[1]
SCENES = {"company": "references/finance-company.md", "earnings": "references/finance-earnings.md",
          "peers": "references/finance-peers.md"}


def new(root, topic, question, scene="company"):
    require(scene in SCENES, "scene must be company, earnings or peers")
    assets, today = PACKAGE / "assets/research", date.today().isoformat()
    files = {}
    for name in ("request.md", "findings.md", "review.md"):
        files[name] = (assets / name).read_text(encoding="utf-8")
    files["request.md"] = files["request.md"].replace("## 问题与对象", f"## 问题与对象\n\n{question}", 1)
    files["inputs/report-template.md"] = (assets / "report.md").read_text(encoding="utf-8")
    files["inputs/metrics.json"] = (assets / "metrics.json").read_text(encoding="utf-8")
    files["inputs/expected-v1.csv"] = (assets / "expected.csv").read_text(encoding="utf-8")
    record = json.loads((assets / "research.json").read_text(encoding="utf-8"))
    record["as_of"] = today
    files["inputs/research.json"] = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    files.update(workspace.ledgers(today))
    version = json.loads((PACKAGE / "catalog.json").read_text(encoding="utf-8"))["version"]
    guide = f"研究流程：finance-research 包 references/research.md；场景卡：{SCENES[scene]}。"
    return workspace.new_task(root, topic, question, "research", scene, files, guide,
                              {"created_by": f"finance-research {version}"})


def check(root):
    record_path = safe_path(root, "inputs/research.json")
    data = json.loads(record_path.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and data.get("schema_version") == 1, "research schema_version must be 1")
    require(nonempty(data.get("as_of")), "research needs as_of")
    as_of = date.fromisoformat(data["as_of"])
    issues, evidence = [], {}

    def capture(ref):
        path = safe_path(root, ref)
        require(path.is_file() and path.stat().st_size > 0, f"missing or empty evidence: {ref}")
        evidence[ref] = fingerprint(path)

    def objects(field):
        rows = data.get(field)
        require(isinstance(rows, list), f"{field} must be a list")
        require(all(isinstance(x, dict) and nonempty(x.get("id")) for x in rows), f"{field} items need IDs")
        require(len({x["id"] for x in rows}) == len(rows), f"duplicate IDs in {field}")
        return rows

    sources = objects("sources")
    if not sources:
        issues.append("No sources registered")
    source_ids = {x["id"] for x in sources}
    for source in sources:
        for key in ("citation", "locator", "accessed_at"):
            require(nonempty(source.get(key)), f"source {source['id']} needs {key}")
        date.fromisoformat(source["accessed_at"])
        published = source.get("published_at")
        if published is None:
            issues.append(f"Source {source['id']}: publication date unknown")
        else:
            require(date.fromisoformat(published) <= as_of, f"source {source['id']} was published after as_of")
        refs = source.get("evidence")
        require(isinstance(refs, list) and refs, "source needs local evidence")
        for ref in refs:
            capture(ref)
    reports = data.get("calculation_files")
    require(isinstance(reports, list) and all(nonempty(x) for x in reports), "calculation_files must be local paths")
    calculations = {}
    for ref in reports:
        capture(ref)
        report = verify_saved(root, ref)
        capture(report["input_file"])
        for result in report["results"]:
            require(result["id"] not in calculations, "calculation IDs must be unique across reports")
            calculations[result["id"]] = result
            for metric in result["inputs"]:
                require(metric["source_id"] in source_ids, f"unknown metric source: {metric['source_id']}")
            if result["status"] != "PASS":
                issues.append(f"Calculation {result['id']}: {result['status']}")
    claims = objects("claims")
    if not claims:
        issues.append("No claims registered")
    for claim in claims:
        require(claim.get("kind") in {"fact", "inference", "hypothesis"}, "invalid claim kind")
        require(nonempty(claim.get("statement")), "claim needs a statement")
        refs = claim.get("source_ids")
        require(isinstance(refs, list) and refs and all(isinstance(x, str) and x in source_ids for x in refs),
                "claim needs known source IDs")
        if claim["kind"] != "fact":
            require(nonempty(claim.get("reasoning")), "inference/hypothesis needs reasoning")
        refs = claim.get("calculation_ids", [])
        require(isinstance(refs, list) and all(isinstance(x, str) and x in calculations for x in refs), "unknown calculation ID")
    expected_file = data.get("expected", "inputs/expected-v1.csv")
    checklist = safe_path(root, expected_file)
    require(checklist.parent == root / "inputs" and checklist.suffix == ".csv", "expected must be an inputs/*.csv file")
    with checklist.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(EXPECTED_FIELDS <= set(reader.fieldnames or []), "expected CSV lacks required columns")
        require(len(reader.fieldnames) == len(set(reader.fieldnames)), "duplicate expected columns")
        expected = list(reader)
    require(expected, "expected CSV has no acceptance items")
    for row in expected:
        require(None not in row and all(nonempty(row.get(k)) for k in EXPECTED_FIELDS), "invalid expected row")
        require(row["requirement"] in REQUIREMENTS, "invalid requirement")
    require(len({r["id"] for r in expected}) == len(expected), "duplicate expected IDs")
    require(any(r["requirement"] != "not_applicable" for r in expected), "no applicable acceptance items")
    reviews = objects("review")
    by_id = {x["id"]: x for x in reviews}
    for row in reviews:
        require(row.get("status") in RESULTS and nonempty(row.get("detail")), "review needs status and detail")
        refs = row.get("evidence")
        require(isinstance(refs, list), "review evidence must be a list")
        require(row["status"] == "NOT_RUN" or refs, "executed review needs evidence")
        for ref in refs:
            capture(ref)
    unexpected = sorted(set(by_id) - {r["id"] for r in expected})
    if unexpected:
        issues.append(f"Unplanned review IDs: {', '.join(unexpected)}")
    failed, required_count, required_pass = [], 0, 0
    for row in expected:
        review = by_id.get(row["id"], {"status": "NOT_RUN"})
        status = review["status"]
        if row["requirement"] == "not_applicable":
            if row["id"] in by_id and status != "SKIP":
                issues.append(f"Not-applicable item was executed: {row['id']}")
        else:
            if row["requirement"] == "required":
                required_count += 1
                required_pass += status == "PASS"
                if status == "FAIL":
                    failed.append(row["id"])
            if status != "PASS":
                issues.append(f"Acceptance {row['id']}: {status}")
    outputs = data.get("deliverables")
    require(isinstance(outputs, list), "deliverables must be a list")
    if not outputs:
        issues.append("No deliverable registered")
    for ref in outputs:
        require(root / "deliverables" in safe_path(root, ref).parents, "deliverables must be under deliverables/")
        capture(ref)
    require(isinstance(data.get("limitations"), list) and all(nonempty(x) for x in data["limitations"]), "limitations must be a string list")
    for name in ("request.md", "findings.md", "review.md"):
        capture(name)
    capture("inputs/research.json")
    capture(expected_file)
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "as_of": data["as_of"],
            "assessment": "FAIL" if failed else "PARTIAL" if issues else "PASS", "issues": issues,
            "required_count": required_count, "required_pass": required_pass, "failed_ids": failed,
            "sources": len(sources), "claims": len(claims), "calculations": len(calculations),
            "limitations": data["limitations"], "evidence_fingerprints": evidence,
            "claim_limit": "Local traceability, arithmetic replay and recorded acceptance only; not validation of source truth or investment merit."}


def main():
    utf8_argv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("new", "check", "replay"))
    p.add_argument("--root", type=Path, required=True, help="task directory; for new, the workspace")
    p.add_argument("--topic")
    p.add_argument("--question")
    p.add_argument("--scene", default="company", choices=tuple(SCENES))
    p.add_argument("--out", help="new task-relative outputs/*.json for check")
    p.add_argument("--report", help="saved report for replay")
    args = p.parse_args()
    root = args.root.resolve()
    if args.action == "new":
        require(args.topic and args.question and not args.out and not args.report, "new needs --topic and --question")
        print(json.dumps(new(root, args.topic, args.question, args.scene), ensure_ascii=False, indent=2))
        return 0
    if args.action == "check":
        require(args.out and not args.report, "check requires --out only")
        out = safe_path(root, args.out)
        require(root / "outputs" in out.parents and out.suffix == ".json", "report must be outputs/*.json")
        require(not out.exists(), "report already exists; use a new name")
        result = check(root)
        write_new(out, result)
    else:
        require(args.report and not args.out, "replay requires --report only")
        saved = json.loads(safe_path(root, args.report).read_text(encoding="utf-8"))
        result = check(root)
        stable = lambda x: {k: v for k, v in x.items() if k != "created_at"}
        require(stable(saved) == stable(result), "research report or evidence changed; save a new review run")
    print(json.dumps({k: v for k, v in result.items() if k != "evidence_fingerprints"}, ensure_ascii=False, indent=2))
    return 0 if result["assessment"] == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
