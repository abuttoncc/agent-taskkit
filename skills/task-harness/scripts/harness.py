#!/usr/bin/env python3
"""Workspace order, task files and handoffs; inspect without running task commands."""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
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
        request = (PACKAGE / "assets/general/request.md").read_text(encoding="utf-8")
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


def mentioned(transcript, needles):
    """Which needles occur in the session transcript; None when the runtime gave no readable transcript."""
    if not isinstance(transcript, str) or not transcript:
        return None
    try:
        path = Path(transcript)
        if not path.is_file():
            return None
        found, tail, width = set(), b"", max(len(n.encode()) for n in needles) if needles else 0
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                window = tail + block
                found.update(n for n in needles if n.encode() in window)
                tail = window[-width:] if width else b""
        return found
    except OSError:
        return None


def recent_hours(root):
    value = workspace.config(root).get("hook", {}).get("stop_recent_hours", RECENT_HOURS)
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 720,
            "hook.stop_recent_hours must be a number between 1 and 720")
    return value


def clip(text, limit=110):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def session_brief(payload, root=None):
    """SessionStart context: where tasks live, how to record them, and what is unfinished. Kept small on purpose."""
    if not isinstance(payload, dict):
        return None
    root = instance_root(payload, root)
    if root is None:
        return None
    tasks_dir = workspace.config(root).get("tasks_dir", "projects")
    script = Path(__file__).resolve()
    lines = [f"[task-harness] 需要跨会话推进或留存成果的工作，在 {root / tasks_dir}/<任务名>/ 建档并在阶段结束时 checkpoint；"
             f"简单问答不建档。命令：python3 '{script}' tasks|new|checkpoint --root '{root}'；规则见 '{PACKAGE / 'SKILL.md'}'。"]
    rows = [r for r in workspace.inventory(root)["tasks"]
            if r.get("state") in {"NEEDS_ATTENTION", "NO_HANDOFF"} or r.get("recorded_status") != "done"]
    rows.sort(key=lambda r: (r.get("state") != "NEEDS_ATTENTION", r.get("recorded_status") != "blocked", r["topic"]))
    for row in rows[:BRIEF_TASKS]:
        status = row.get("recorded_status") or "未交接"
        detail = row["issues"][0] if row.get("state") == "NEEDS_ATTENTION" else row.get("blocker") or row.get("next_step") or row.get("question")
        lines.append(f"- {row['topic']}（{status}{'，需关注' if row.get('state') == 'NEEDS_ATTENTION' else ''}）：{clip(detail)}")
    if len(rows) > BRIEF_TASKS:
        lines.append(f"- 另有 {len(rows) - BRIEF_TASKS} 项未完成，用 tasks 查看。")
    if rows:
        lines.append("续做同一目标先读该任务 README 与最新 handoffs/，不要另起新任务；别的会话在做的任务不要替它写 checkpoint。")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}


def stop_reminder(payload, now=None, root=None):
    """Optional Stop hook: remind once per session about this session's recently touched tasks whose records need attention.

    When the runtime passes transcript_path, only tasks named in this session's transcript count, so a session
    is never pushed to checkpoint work that another concurrent session owns."""
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return None
    root = instance_root(payload, root)
    if root is None:
        return None
    cutoff = (now or time.time()) - recent_hours(root) * 3600
    rows = [r for r in workspace.inventory(root)["tasks"]
            if r.get("state") in {"NEEDS_ATTENTION", "NO_HANDOFF"} and touched_since(root / r["path"], cutoff)]
    seen = mentioned(payload.get("transcript_path"), [r["path"] for r in rows])
    if seen is not None:
        rows = [r for r in rows if r["path"] in seen]
    pending = [f"- {r['topic']}：{r['issues'][0]}" for r in rows]
    if not pending:
        return None
    reason = ("task-harness：以下近期改动过的任务交接记录不完整，结束前请处理（不适用就说明原因后结束）：\n"
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
    create.add_argument("--template", default="general", help="general or verify; research tasks come from finance-research")
    create.add_argument("--scene", help="scene from catalog; defaults to the first scene of the selected template")
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
