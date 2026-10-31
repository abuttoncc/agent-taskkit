#!/usr/bin/env python3
"""Build a portable skill ZIP using an explicit file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
COMMON = ["SKILL.md", "catalog.json"]
PACKAGES = {
    "task-harness": COMMON + ["INSTALL.md", "references/operations.md", "references/red-lines.md", "references/verify.md",
                              "references/api.md", "references/workspace.md", "references/general.md",
                              "scripts/contract.py", "scripts/harness.py", "scripts/install.py", "scripts/workspace.py",
                              "assets/verify/spec.json", "assets/verify/expected.csv", "assets/general/request.md"],
    "finance-research": COMMON + ["references/research.md", "references/finance-methods.md", "references/finance-company.md",
                                  "references/finance-earnings.md", "references/finance-peers.md",
                                  "scripts/research.py", "scripts/finance.py", "scripts/taskharness.py",
                                  "assets/research/research.json", "assets/research/metrics.json", "assets/research/request.md",
                                  "assets/research/findings.md", "assets/research/review.md", "assets/research/report.md",
                                  "assets/research/expected.csv"],
}


def build_one(name, files, output):
    package = ROOT / "skills" / name
    version = json.loads((package / "catalog.json").read_text(encoding="utf-8"))["version"]
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual != set(files):
        raise ValueError(f"{name}: release list differs from package: {sorted(actual ^ set(files))}")
    target = output / f"{name}-{version}.zip"
    with ZipFile(target, "x", compression=ZIP_DEFLATED) as archive:
        for item in files:
            source = package / item
            if source.is_symlink() or package not in source.resolve().parents:
                raise ValueError(f"invalid release input: {name}/{item}")
            info = ZipInfo(f"{name}/{item}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    with ZipFile(target) as archive:
        assert archive.testzip() is None
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    return {"package": str(target), "files": len(files), "sha256": digest}


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    return [build_one(name, files, output) for name, files in PACKAGES.items()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.out), indent=2))
