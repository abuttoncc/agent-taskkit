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
import workspace

PACKAGE = Path(__file__).resolve().parents[1]


def catalog():
    return json.loads((PACKAGE / "catalog.json").read_text(encoding="utf-8"))


def new(root, topic, question, template="general", scene=None):
    options = {x["name"]: x for x in catalog()["templates"]}
    require(template in options, "unknown template")
    scene = scene or options[template]["scenes"][0]
    require(scene in options[template]["scenes"], "scene does not belong to this template")
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic), "topic must be kebab-case")
    require(question.strip(), "question cannot be empty")
    today = date.today().isoformat()
    root = root.resolve()
    marker = root / ".task-harness.json"
    if root.exists() and any(root.iterdir()):
        require(marker.is_file(), "nonempty directory is not a task-harness instance; use init explicitly or choose another directory")
    workspace_files, config = workspace.bootstrap(root)
    directory = workspace.task_directory(root, config.get("tasks_dir", "projects"))
    task = directory / topic
    require(not task.exists() and not task.is_symlink(), "task already exists; resume it or use a new topic")
    require(root in task.resolve().parents, "project path escapes instance")
    prefix = str(task.relative_to(root))
    definition = "spec.json" if template == "verify" else "request.md"
    files = {
        f"{prefix}/task.json": json.dumps({"schema_version": 1, "template": template, "scene": scene,
            "question": question, "created_at": today, "created_with": catalog()["version"]}, ensure_ascii=False, indent=2) + "\n",
        f"{prefix}/README.md": f"""# {topic}

问题：{question}
入口：先读最新 handoffs/*.json（若无，任务尚未记录交接），再读 [{definition}]({definition})。
新建状态：DRAFT；初始下一步：填写目标、范围、交付与完成条件。进度以最新交接为准。
公共包出生版本：{catalog()['version']}；流程 {template}，场景 {scene}。
公共流程：{options[template]['reference']}；场景卡：{options[template]['scene_resources'][scene]}（相对公共包）。
资料与结果按实际需要建立 inputs/、outputs/、deliverables/、tmp/；已有项目按其规则放置。
需要追溯时补 sources.md；范围变更与重要决策记 events.md，不覆盖旧结果。
交接时使用 checkpoint 留下摘要、下一步、阻塞和交付依据；同目标续做，不因换会话重建。
""",
    }
    if template != "general":
        files[f"{prefix}/inputs/expected-v1.csv"] = (PACKAGE / "assets/verify/expected.csv").read_text()
        files[f"{prefix}/sources.md"] = "# 来源\n\n| ID | 来源/版本/日期 | 证据层级 | 本地证据 | 限制 |\n|---|---|---|---|---|\n"
        files[f"{prefix}/events.md"] = f"# 事件（追加）\n\n- {today} CREATED：DRAFT，尚未执行。\n"
    if template == "verify":
        spec = json.loads((PACKAGE / "assets/verify/spec.json").read_text(encoding="utf-8"))
        spec.update(topic=topic, question=question, as_of=today, baseline=f"inputs/{today}-baseline-v1.json")
        files[f"{prefix}/spec.json"] = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
    elif template == "research":
        for name in ("request.md", "findings.md", "review.md", "report.md", "research.json", "metrics.json"):
            target = f"inputs/{name}" if name.endswith(".json") else "inputs/report-template.md" if name == "report.md" else name
            content = (PACKAGE / "assets/research" / name).read_text(encoding="utf-8")
            if name == "research.json":
                record = json.loads(content)
                record["as_of"] = today
                content = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            if name == "request.md":
                content = content.replace("## 问题与对象", f"## 问题与对象\n\n{question}")
            files[f"{prefix}/{target}"] = content
    else:
        files[f"{prefix}/request.md"] = (PACKAGE / "assets/general/request.md").read_text().replace("{{question}}", question)
    files.update(workspace_files)
    workspace.create_files(root, files)
    return {"task": str(task), "state": "DRAFT", "template": template, "scene": scene,
            "next": "Fill the task definition; create material folders only when needed."}


def doctor(root):
    errors, tasks = [], []
    root = root.resolve()
    config = workspace.config(root)
    if not any((root / name).is_file() for name in ("AGENTS.md", "CLAUDE.md")):
        errors.append("missing workspace rules entry")
    directory = workspace.task_directory(root, config.get("tasks_dir", "projects"))
    for task in sorted(directory.iterdir()) if directory.exists() else []:
        if not task.is_dir():
            continue
        try:
            require(root in task.resolve().parents, "task escapes instance")
            info = workspace.metadata(task)
            if info["template"] == "general":
                review = workspace.handoff_check(task)
                tasks.append({"topic": task.name, "template": "general", **review})
                if review["issues"]:
                    errors.append(f"{task.name}: {review['state']}")
                continue
            if info["template"] == "research":
                from research import check
                review = check(task)
                tasks.append({"topic": task.name, "template": "research", "state": "REVIEWED" if review["assessment"] == "PASS" else "NEEDS_ATTENTION",
                              "recorded_assessment": review["assessment"], "issues": review["issues"], "task_outcome": "semantic content not assessed"})
                if review["assessment"] != "PASS":
                    errors.append(f"{task.name}: {review['assessment']}")
                continue
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
    initialize = sub.add_parser("init")
    initialize.add_argument("--root", type=Path, required=True)
    initialize.add_argument("--tasks-dir", help="relative task directory, default projects")
    for action in ("tasks", "handoff"):
        command = sub.add_parser(action)
        command.add_argument("--root", type=Path, required=True)
        if action == "handoff":
            command.add_argument("--topic", required=True)
    save = sub.add_parser("checkpoint")
    save.add_argument("--root", type=Path, required=True)
    save.add_argument("--topic", required=True)
    save.add_argument("--status", choices=("active", "blocked", "done"), required=True)
    save.add_argument("--summary", required=True)
    save.add_argument("--next", dest="next_step", default="")
    save.add_argument("--blocker", default="")
    save.add_argument("--deliverable", action="append", default=[])
    save.add_argument("--review", default="")
    create = sub.add_parser("new")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--topic", required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--template", choices=tuple(x["name"] for x in catalog()["templates"]), default="general")
    create.add_argument("--scene", help="scene from catalog; defaults to the first scene of the selected template")
    inspect = sub.add_parser("doctor")
    inspect.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "list":
        result = catalog()
    elif args.action == "init":
        result = workspace.init(args.root.resolve(), args.tasks_dir)
    elif args.action == "tasks":
        result = workspace.inventory(args.root.resolve())
    elif args.action == "handoff":
        result = workspace.handoff_check(workspace.task_path(args.root.resolve(), args.topic))
    elif args.action == "checkpoint":
        result = workspace.checkpoint(args.root.resolve(), args.topic, args.status, args.summary,
                                      args.next_step, args.blocker, args.deliverable, args.review)
    elif args.action == "new":
        result = new(args.root.resolve(), args.topic, args.question, args.template, args.scene)
    else:
        result = doctor(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("errors") or result.get("issues") else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
