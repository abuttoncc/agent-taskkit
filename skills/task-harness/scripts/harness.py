#!/usr/bin/env python3
"""Workspace order, task files and handoffs; inspect without running task commands."""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time

sys.dont_write_bytecode = True
from contract import load_contract, read_spec, require, utf8_argv
import workspace

PACKAGE = Path(__file__).resolve().parents[1]
catalog = workspace.catalog
RECENT_HOURS = 24          # default only; instances override with hook.stop_recent_hours
BRIEF_TASKS = 5


def new(root, topic, question, template="general", scene=None):
    extension = catalog().get("extensions", {}).get(template)
    require(extension is None, f"{template} tasks are created by the {extension['skill']} skill" if extension else "")
    options = {x["name"]: x for x in catalog()["templates"]}
    require(template in options, "unknown template")
    info = options[template]
    scene = scene or info["scenes"][0]
    require(scene in info["scenes"], "scene does not belong to this template")
    today = date.today().isoformat()
    guide = f"公共流程：{info['reference']}；场景卡：{info['scene_resources'][scene]}（相对 task-harness 包）。"
    if template == "verify":
        spec = json.loads((PACKAGE / "assets/verify/spec.json").read_text(encoding="utf-8"))
        spec.update(topic=topic, question=question, as_of=today, baseline=f"inputs/{today}-baseline-v1.json")
        files = {"spec.json": json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                 "inputs/expected-v1.csv": (PACKAGE / "assets/verify/expected.csv").read_text(encoding="utf-8"),
                 **workspace.ledgers(today)}
    else:
        asset = "team/request.md" if template == "team" else "general/request.md"
        request = (PACKAGE / "assets" / asset).read_text(encoding="utf-8")
        files = {"request.md": request.replace("{{question}}", question)}
    return workspace.new_task(root, topic, question, template, scene, files, guide)


def doctor(root):
    errors, tasks = [], []
    root = root.resolve()
    data = workspace.config(root)
    if not any((root / name).is_file() for name in ("AGENTS.md", "CLAUDE.md")):
        errors.append("missing workspace rules entry")
    directory = workspace.task_directory(root, data.get("tasks_dir", "projects"))
    for task in sorted(directory.iterdir()) if directory.exists() else []:
        if not task.is_dir():
            continue
        try:
            require(root in task.resolve().parents, "task escapes instance")
            template = workspace.metadata(task)["template"]
            row = {"topic": task.name, "template": template, **workspace.handoff_check(task)}
            if template == "verify":
                spec, _ = read_spec(task)
                row["contract"] = "READY_TO_FREEZE"
                if (task / spec["baseline"]).exists():
                    load_contract(task)
                    row["contract"] = "FROZEN"
            extension = catalog().get("extensions", {}).get(template)
            if extension:
                row["checker"] = f"{extension['skill']}; content is not re-checked here"
            tasks.append(row)
            # A verify contract is frozen before any checkpoint exists, so NO_HANDOFF is normal there.
            if row["issues"] and not (template == "verify" and row["state"] == "NO_HANDOFF"):
                errors.append(f"{task.name}: {row['state']}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            tasks.append({"topic": task.name, "state": "NEEDS_ATTENTION", "reason": str(exc)})
            errors.append(f"{task.name}: {exc}")
    return {"package": str(PACKAGE), "version": catalog()["version"], "tasks": tasks, "errors": errors,
            "capabilities": {"installed": "package found", "authorized": "unknown", "connected": "unknown", "effective": "unknown"},
            "claim_limit": "Read-only local structure/contract check; no API call or task command was run."}


def touched_since(task, cutoff):
    for path in task.rglob("*"):
        try:
            if path.is_file() and path.stat().st_mtime >= cutoff:
                return True
        except OSError:
            continue
    return False


def instance_root(payload, root=None):
    """An explicit --root wins (instance kept in a subdirectory); otherwise walk up from the session cwd."""
    if root is not None:
        root = Path(root).resolve()
        return root if (root / workspace.MARKER).is_file() else None
    start = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    return next((p for p in (start, *start.parents) if (p / workspace.MARKER).is_file()), None)


def recent_hours(root):
    value = workspace.config(root).get("hook", {}).get("stop_recent_hours", RECENT_HOURS)
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 720,
            "hook.stop_recent_hours must be a number between 1 and 720")
    return value


def session_brief(payload, root=None):
    """SessionStart context: where tasks live, and the names of unfinished tasks.

    This hook runs before the user message, so it must not inject another task's next step.
    """
    if not isinstance(payload, dict):
        return None
    root = instance_root(payload, root)
    if root is None:
        return None
    tasks_dir = workspace.config(root).get("tasks_dir", "projects")
    script = Path(__file__).resolve()
    lines = [f"[task-harness] 需要跨会话推进或留存成果的工作，在 {root / tasks_dir}/<任务名>/ 建档并在阶段结束时 checkpoint；"
             f"简单问答不建档。命令：python3 '{script}' tasks|new|checkpoint --root '{root}'；规则见 '{PACKAGE / 'SKILL.md'}'。"]
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        lines.append(f"实际新建或续做任务后，执行 python3 '{script}' bind --root '{root}' --topic <任务名> "
                     f"--session-id {shlex.quote(session_id)} 绑定本会话；new/checkpoint 在运行时提供会话环境时自动绑定。"
                     "只读总览或参考其他任务不绑定，Stop 仅检查已绑定任务。")
    rows = [r for r in workspace.inventory(root)["tasks"]
            if r.get("state") in {"NEEDS_ATTENTION", "NO_HANDOFF"} or r.get("recorded_status") != "done"]
    rows.sort(key=lambda r: (r.get("state") != "NEEDS_ATTENTION", r.get("recorded_status") != "blocked", r["topic"]))
    if rows:
        shown = [r["topic"] for r in rows[:BRIEF_TASKS]]
        extra = f"；另有 {len(rows) - len(shown)} 项" if len(rows) > len(shown) else ""
        lines.append(
            f"未完成 {len(rows)} 项：{'、'.join(shown)}{extra}。"
            "续做其中一项时，先读该任务 README 与最新 handoffs/，不要另起新任务。"
            "不要把未点名的任务当成当前目标，也不要替其他会话写 checkpoint。"
        )
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}


def stop_reminder(payload, now=None, root=None):
    """Remind only for explicitly bound tasks; unknown session ownership always passes."""
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return None
    root = instance_root(payload, root)
    session_id = payload.get("session_id")
    if root is None or not isinstance(session_id, str) or not session_id.strip():
        return None
    cutoff = (now or time.time()) - recent_hours(root) * 3600
    pending = []
    for topic in workspace.session_tasks(root, session_id):
        try:
            task = workspace.task_path(root, topic)
        except (OSError, ValueError):
            continue  # A removed task must not suppress reminders for other bound work.
        row = workspace.handoff_check(task)
        if row.get("state") in {"NEEDS_ATTENTION", "NO_HANDOFF"} and touched_since(task, cutoff):
            pending.append(f"- {topic}：{row['issues'][0]}")
    if not pending:
        return None
    reason = ("task-harness：以下本会话已绑定且近期改动过的任务交接记录不完整，结束前请处理：\n"
              + "\n".join(pending)
              + "\n用 harness.py checkpoint 记录当前状态；已交付文件不原位改写，修订另存新文件名。")
    key = hashlib.sha256(f"{Path.home()}|{root}|{payload.get('session_id', '')}".encode()).hexdigest()[:16]
    state = Path(tempfile.gettempdir()) / f"task-harness-hook-{key}"
    digest = hashlib.sha256(reason.encode()).hexdigest()
    if state.is_file() and state.read_text(encoding="utf-8") == digest:
        return None
    state.write_text(digest, encoding="utf-8")
    return {"decision": "block", "reason": reason}


def hook_config(runtime, root=None):
    events = {}
    target = f" --root '{Path(root).resolve()}'" if root else ""
    for event, flag, message in (("SessionStart", "session-start", "Loading task brief"), ("Stop", "stop", "Checking task handoffs")):
        command = {"type": "command", "command": f"python3 '{Path(__file__).resolve()}' hook --event {flag}{target}", "timeout": 30}
        if runtime == "codex":
            command["statusMessage"] = message
        events[event] = [{"hooks": [command]}]
    return {"hooks": events}


def main():
    utf8_argv()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    hook = sub.add_parser("hook", help="runtime hook entry; reads the hook payload on stdin")
    hook.add_argument("--event", choices=("stop", "session-start"), default="stop")
    hook.add_argument("--root", type=Path, help="instance root when it is not an ancestor of the session cwd")
    hook.add_argument("--print-config", choices=("claude", "codex"), help="print the hook settings snippet instead")
    initialize = sub.add_parser("init")
    initialize.add_argument("--root", type=Path, required=True)
    initialize.add_argument("--tasks-dir", help="relative task directory, default projects")
    bind = sub.add_parser("bind", help="associate a resumed task with this runtime session, without changing its records")
    bind.add_argument("--root", type=Path, required=True)
    bind.add_argument("--topic", required=True)
    bind.add_argument("--session-id", help="defaults to CODEX_THREAD_ID, CODEX_SESSION_ID or CLAUDE_SESSION_ID")
    for action in ("tasks", "handoff", "doctor"):
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
    save.add_argument("--report", help="checker report; required for done verify/research tasks")
    save.add_argument("--overwritten", action="append", default=[], help="delivered file already changed in place; recorded, not hidden")
    save.add_argument("--reason", default="")
    create = sub.add_parser("new")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--topic", required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--template", default="general", help="general, team, or verify; research tasks come from finance-research")
    create.add_argument("--scene", help="scene from catalog; defaults to the first scene of the selected template")
    grow = sub.add_parser("evolve", help="record one evidenced team suggestion locally; do not edit this package")
    grow.add_argument("--root", type=Path, required=True)
    grow.add_argument("--topic", required=True)
    args = parser.parse_args()
    if args.action == "hook":
        if args.print_config:
            print(json.dumps(hook_config(args.print_config, args.root), ensure_ascii=False, indent=2))
            return 0
        try:
            payload = json.load(sys.stdin)
            result = session_brief(payload, args.root) if args.event == "session-start" else stop_reminder(payload, root=args.root)
        except Exception:  # a reminder must never break the host session
            return 0
        if result:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.action == "list":
        result = catalog()
    elif args.action == "init":
        result = workspace.init(args.root.resolve(), args.tasks_dir)
    elif args.action == "bind":
        result = workspace.bind_session(args.root.resolve(), args.topic, args.session_id)
    elif args.action == "tasks":
        result = workspace.inventory(args.root.resolve())
    elif args.action == "handoff":
        result = workspace.handoff_check(workspace.task_path(args.root.resolve(), args.topic))
    elif args.action == "checkpoint":
        result = workspace.checkpoint(args.root.resolve(), args.topic, args.status, args.summary,
                                      args.next_step, args.blocker, args.deliverable, args.review,
                                      args.overwritten, args.reason, args.report)
    elif args.action == "new":
        result = new(args.root.resolve(), args.topic, args.question, args.template, args.scene)
    elif args.action == "evolve":
        result = workspace.evolve(args.root.resolve(), args.topic)
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
