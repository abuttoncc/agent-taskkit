"""Locate the task-harness scripts this skill builds on (sibling install or TASK_HARNESS_HOME)."""
import json
import os
from pathlib import Path
import sys

MINIMUM = (0, 5, 0)


def locate():
    here = Path(__file__).resolve().parents[1]
    candidates = [Path(os.environ["TASK_HARNESS_HOME"])] if os.environ.get("TASK_HARNESS_HOME") else []
    candidates.append(here.parent / "task-harness")
    for home in candidates:
        catalog = home / "catalog.json"
        if (home / "scripts/workspace.py").is_file() and catalog.is_file():
            version = json.loads(catalog.read_text(encoding="utf-8"))["version"]
            if tuple(int(x) for x in version.split(".")[:3]) < MINIMUM:
                raise ValueError(f"task-harness {version} is too old; finance-research needs >= 0.5.0")
            return home
    raise ValueError("task-harness not found; install it beside finance-research or set TASK_HARNESS_HOME")


HOME = locate()
if str(HOME / "scripts") not in sys.path:
    sys.path.insert(0, str(HOME / "scripts"))
