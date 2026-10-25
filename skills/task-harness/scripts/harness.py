#!/usr/bin/env python3
"""Create an autonomous workspace; inspect it without running task commands."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from contract import load_contract, read_spec, require

PACKAGE = Path(__file__).resolve().parents[1]


def catalog():
    return json.loads((PACKAGE / "catalog.json").read_text(encoding="utf-8"))


def new(root, topic, question):
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic), "topic must be kebab-case")
    require(question.strip(), "question cannot be empty")
    today = date.today().isoformat()
    task = root / "projects" / topic
    marker = root / ".task-harness.json"
    if root.exists() and any(root.iterdir()):
        require(marker.is_file(), "nonempty directory is not a task-harness instance; choose another directory")
        config = json.loads(marker.read_text(encoding="utf-8"))
        require(config.get("schema") == "task-harness.instance/v1", "unknown instance schema")
        require((root / "AGENTS.md").is_file(), "existing instance is missing AGENTS.md; repair it first")
    require(not task.exists() and not task.is_symlink(), "task already exists; resume it or use a new topic")
    require(root in task.resolve().parents, "project path escapes instance")
    spec = json.loads((PACKAGE / "assets/verify/spec.json").read_text(encoding="utf-8"))
    spec.update(topic=topic, question=question, as_of=today, baseline=f"inputs/{today}-baseline-v1.json")
    files = {
        f"projects/{topic}/spec.json": json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        f"projects/{topic}/inputs/expected-v1.csv": (PACKAGE / "assets/verify/expected.csv").read_text(),
        f"projects/{topic}/README.md": f"""# {topic}

问题：{question}
状态：DRAFT，尚未冻结；填写 spec 与 expected 后开始正式验证。
公共包出生版本：{catalog()['version']}；底座 verify，场景 api。
当前合同：[spec.json](spec.json)；清单：[expected](inputs/expected-v1.csv)。
当前基线：无。最近观测/对账：无。未完成项：尚未形成清单。
下一步：填写范围、验收条件、停止条件和运行命令，然后用公共 contract.py freeze。
阻塞与解除条件：未记录；执行中据实更新。
来源见 sources.md；进度见 events.md；交付物放 deliverables/。
""",
        f"projects/{topic}/sources.md": "# 来源\n\n| ID | 来源/版本/日期 | 证据层级 | 本地证据 | 限制 |\n|---|---|---|---|---|\n",
        f"projects/{topic}/events.md": f"# 事件（追加）\n\n- {today} CREATED：尚未冻结，尚未执行验证。\n",
    }
    if not marker.exists():
        files.update({
            ".task-harness.json": json.dumps({"schema": "task-harness.instance/v1", "created_with": catalog()['version']}, indent=2) + "\n",
            "AGENTS.md": f"""# 任务工作区 · verify / api
公共技能包：{PACKAGE}
先读公共包 SKILL.md；按任务读取 references/verify.md 与 api.md。
公共包独立升级，本目录文件出生后自治；迁移机器时修正上面的路径。
| 现在要做什么 | 首先读 | 找什么证据 |
|---|---|---|
| 继续一项任务 | projects/<id>/README.md | 当前基线、最近结果、下一步与阻塞 |
| 确认完成条件 | projects/<id>/spec.json 与 inputs/expected-*.csv | 范围、逐项判据、停止条件 |
| 核对结论 | projects/<id>/outputs/ 与 sources.md | 对账、原始证据、证据层级 |
| 了解个人习惯 | memory/profile.md | 当前偏好 |
| 复用既有方法 | memory/assets.md 与 playbooks.local/ | 方法适用边界与来源 |
| 留问题 | Inbox/issues/ | 实际/预期/复现/影响/临时处理/证据 |
小问题直接答；不跨层宣布，不编数，不覆盖旧结果，不保存凭证。
""",
            "memory/profile.md": "# 个人偏好\n\n尚未记录。按用户实际偏好填写。\n",
            "memory/assets.md": "# 个人资产索引\n\n| 问题 | 路径或技能入口 | 适用边界 | 验证日期 |\n|---|---|---|---|\n",
        })
    # Check every destination before creating anything. Never merge into foreign files.
    for name in ("playbooks.local", "Inbox/issues", f"projects/{topic}/outputs", f"projects/{topic}/deliverables"):
        target = root / name
        require(root in target.resolve().parents, f"path escapes instance: {name}")
        require(not target.exists() or target.is_dir(), f"directory conflicts with file: {name}")
    for name in files:
        target = root / name
        require(root in target.resolve().parents, f"path escapes instance: {name}")
        require(not target.exists() and not target.is_symlink(), f"file already exists: {name}")
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(files[name])
    for name in ("outputs", "deliverables"):
        (task / name).mkdir()
    for name in ("playbooks.local", "Inbox/issues"):
        path = root / name
        require(root in path.resolve().parents, f"path escapes instance: {name}")
        path.mkdir(parents=True, exist_ok=True)
    return {"task": str(task), "state": "DRAFT", "next": "Fill spec.json and expected CSV, then freeze."}


def doctor(root):
    errors, tasks = [], []
    for name in ("AGENTS.md", ".task-harness.json", "memory/profile.md", "memory/assets.md"):
        if not (root / name).is_file():
            errors.append(f"missing {name}")
    marker = root / ".task-harness.json"
    if marker.is_file():
        require(json.loads(marker.read_text()).get("schema") == "task-harness.instance/v1", "unknown instance schema")
    for task in sorted((root / "projects").iterdir()) if (root / "projects").is_dir() else []:
        if not task.is_dir():
            continue
        try:
            require(root in task.resolve().parents, "task escapes instance")
            spec, rows = read_spec(task)
            if (task / spec["baseline"]).exists():
                load_contract(task)
                tasks.append({"topic": task.name, "state": "FROZEN", "contract_integrity": "PASS", "task_outcome": "not assessed"})
            else:
                tasks.append({"topic": task.name, "state": "READY_TO_FREEZE"})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            tasks.append({"topic": task.name, "state": "NEEDS_ATTENTION", "reason": str(exc)})
            errors.append(f"{task.name}: {exc}")
    return {"package": str(PACKAGE), "version": catalog()["version"], "tasks": tasks, "errors": errors,
            "capabilities": {"installed": "package found", "authorized": "unknown", "connected": "unknown", "effective": "unknown"},
            "claim_limit": "Read-only local structure/contract check; no API call or task command was run."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    create = sub.add_parser("new")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--topic", required=True)
    create.add_argument("--question", required=True)
    inspect = sub.add_parser("doctor")
    inspect.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "list":
        result = catalog()
    elif args.action == "new":
        result = new(args.root.resolve(), args.topic, args.question)
    else:
        result = doctor(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
