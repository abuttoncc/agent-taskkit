#!/usr/bin/env python3
"""Build a portable skill ZIP using an explicit file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/task-harness"
FILES = ["SKILL.md", "INSTALL.md", "catalog.json", "references/operations.md", "scripts/contract.py", "scripts/harness.py", "scripts/install.py",
         "references/red-lines.md", "references/verify.md", "references/api.md", "assets/verify/spec.json", "assets/verify/expected.csv",
         "scripts/finance.py", "scripts/research.py", "references/research.md", "references/finance-methods.md",
         "references/finance-company.md", "references/finance-earnings.md", "references/finance-peers.md",
         "assets/research/research.json", "assets/research/metrics.json", "assets/research/request.md",
         "assets/research/findings.md", "assets/research/review.md", "assets/research/report.md", "scripts/workspace.py", "references/workspace.md",
         "references/general.md", "assets/general/request.md"]


def build(output):
    version = json.loads((PACKAGE / "catalog.json").read_text())["version"]
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"task-harness-{version}.zip"
    with ZipFile(target, "x", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            source = PACKAGE / name
            if source.is_symlink() or PACKAGE not in source.resolve().parents:
                raise ValueError(f"invalid release input: {name}")
            info = ZipInfo(f"task-harness/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    with ZipFile(target) as archive:
        assert archive.testzip() is None
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n")
    return {"package": str(target), "files": len(FILES), "sha256": digest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.out), indent=2))
