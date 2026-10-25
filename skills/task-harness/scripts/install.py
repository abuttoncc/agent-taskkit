#!/usr/bin/env python3
"""Install/update a local skill package; never traverse or modify task instances."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

RECEIPT = ".installed.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def files(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"symlink in package: {path.relative_to(root)}")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if name == RECEIPT or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        require(not any(part.startswith(".") for part in Path(name).parts), f"hidden file in package: {name}")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def install(source, dest, update=False):
    require(not dest.is_symlink(), "installation destination cannot be a symlink")
    source, dest = source.resolve(), dest.resolve()
    require(source.is_dir(), "source package does not exist")
    require(source != dest and source not in dest.parents and dest not in source.parents, "source/destination overlap")
    hashes = files(source)
    for name in ("SKILL.md", "catalog.json", "scripts/contract.py", "scripts/harness.py", "scripts/install.py",
                 "references/red-lines.md", "references/verify.md", "references/api.md", "assets/verify/spec.json", "assets/verify/expected.csv"):
        require(name in hashes, f"incomplete package: {name}")
    info = json.loads((source / "catalog.json").read_text(encoding="utf-8"))
    require(info.get("name") == "task-harness" and info.get("schema") == "ablemind.task-harness/v1", "wrong package")
    require(isinstance(info.get("version"), str) and info["version"], "package version missing")
    if update:
        require((dest / RECEIPT).is_file(), "update requires an installation created by this installer")
        receipt = json.loads((dest / RECEIPT).read_text(encoding="utf-8"))
        require(receipt.get("files") == files(dest), "central package has local changes; preserve them before updating")
    else:
        require(not dest.exists(), "installation destination already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Stage a complete package beside the destination, then switch directories.
    with tempfile.TemporaryDirectory(prefix=".task-harness-", dir=dest.parent) as temporary:
        stage, backup = Path(temporary) / "new", Path(temporary) / "old"
        stage.mkdir()
        for name in hashes:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        require(files(stage) == hashes, "source changed while copying")
        (stage / RECEIPT).write_text(json.dumps({"version": info["version"], "files": hashes}, indent=2) + "\n")
        if update:
            dest.rename(backup)
        try:
            stage.rename(dest)
        except OSError:
            if update:
                backup.rename(dest)
            raise
    return {"package": str(dest), "version": info["version"], "action": "updated" if update else "installed",
            "instances": "not accessed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.source, args.dest, args.action == "update"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
