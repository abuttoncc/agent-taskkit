"""Workspace initialization, derived task inventory and append-only handoffs."""
from datetime import date, datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re

from contract import fingerprint, nonempty, replay, require, safe_path, write_new

PACKAGE = Path(__file__).resolve().parents[1]
MARKER = ".task-harness.json"
TOPIC = r"[a-z0-9]+(?:-[a-z0-9]+)*"
CONTROL_FILES = {("task.json",), ("README.md",), ("request.md",), ("spec.json",)}


def catalog():
    return json.loads((PACKAGE / "catalog.json").read_text(encoding="utf-8"))


def template_info(name):
    """Built-in templates plus task types owned by companion skills (e.g. research)."""
    data = catalog()
    for item in data["templates"]:
        if item["name"] == name:
            return item
    extension = data.get("extensions", {}).get(name) if isinstance(name, str) else None
    require(extension is not None, "unknown task template")
    return {"name": name, **extension}


def definition_file(template):
    return template_info(template).get("definition", "request.md")


def ledgers(today):
    return {"sources.md": "# 来源\n\n| ID | 来源/版本/日期 | 证据层级 | 本地证据 | 限制 |\n|---|---|---|---|---|\n",
            "events.md": f"# 事件（追加）\n\n- {today} CREATED：DRAFT，尚未执行。\n"}


def task_directory(root, name):
    require(nonempty(name) and not Path(name).is_absolute(), "tasks_dir must be relative")
    require(all(part not in {".", ".."} and not part.startswith(".") for part in name.split("/")),
            "tasks_dir must use visible directory names without traversal")
    require(name.split("/")[0] not in {"AGENTS.md", "CLAUDE.md", "WORKSPACE.md", "README.md"},
            "tasks_dir conflicts with a workspace entry")
    path = safe_path(root, name)
    require(not path.exists() or path.is_dir(), "tasks_dir conflicts with a file")
    for parent in path.parents:
        if parent == root:
            break
        require(not parent.exists() or parent.is_dir(), "tasks_dir parent conflicts with a file")
    return path


def config(root):
    marker = root / MARKER
    require(not marker.is_symlink(), "instance marker cannot be a symlink")
    data = json.loads(marker.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and data.get("schema") == "task-harness.instance/v1", "unknown instance schema")
    task_directory(root, data.get("tasks_dir", "projects"))
    return data


def bootstrap(root, tasks_dir=None):
    """Plan new files without writing or replacing existing project conventions."""
    if (root / MARKER).exists() or (root / MARKER).is_symlink():
        data = config(root)
        require(tasks_dir is None or tasks_dir == data.get("tasks_dir", "projects"),
                "existing tasks_dir differs; do not move tasks implicitly")
        return {}, data
    tasks_dir = tasks_dir or "projects"
    task_directory(root, tasks_dir)
    rules = [name for name in ("AGENTS.md", "CLAUDE.md") if (root / name).is_file()]
    data = {"schema": "task-harness.instance/v1", "created_with": catalog()["version"],
            "tasks_dir": tasks_dir, "rules": rules or ["AGENTS.md"]}
    files = {MARKER: json.dumps(data, ensure_ascii=False, indent=2) + "\n"}
    files["WORKSPACE.md"] = f"""# 工作区入口

任务位置：`{tasks_dir}/<任务名>/`。公共 Skill：`task-harness`（从当前运行时定位，勿复制脚本到任务）。
既有工作规则：{', '.join(data['rules'])}；先读这些规则，再按需使用本入口。原项目 README 保持原用途。

| 现在要做什么 | 从哪里开始 |
|---|---|
| 开始或继续任务 | 用 Skill 的 tasks 查看任务总览，再读对应任务 README、最新 handoff 与任务定义 |
| 确认交付 | 对照 request.md/spec.json 的完成标准，查看交付文件与实际检查记录 |
| 复用经验 | 有需要时读 memory/assets.md，仅展开相关入口；个人偏好在 memory/profile.md |
| 保存个人方法 | 需要时建立 playbooks.local/，记录依据、适用范围和失效条件 |
| 留流程故障 | 需要时建立 Inbox/issues/；业务未决问题留在任务内 |

简单问答直接做；同目标同交付沿用原任务，日期或会话变化不另开任务。
任务内按需建立 inputs/（材料）、outputs/（过程）、deliverables/（成果）、tmp/（临时探索）。
已有项目若约定 data/output、src/docs 或日期目录，沿用其位置并记录引用，不重复搬运。
交接用 checkpoint 保存摘要、下一步、真实阻塞与交付依据；它只检查记录完整性，不代替内容判断。
个人文件由本工作区维护，公共包更新不覆盖。一次发现先留任务内，不自动变成公共规则。
"""
    if not rules:
        files["AGENTS.md"] = """# 工作区约定
先读 WORKSPACE.md；续做只展开相关任务的入口和最新交接。
需要建档时使用 task-harness，先查已有任务，再选择流程与场景。
简单问题直接完成；个人资料留在本工作区；不要覆盖来源、旧结果或保存凭证。
公共 Skill 独立安装，本地约定和任务不随其升级覆盖。
"""
    return files, data


def create_files(root, files):
    # Preflight the whole write set, including dangling symlinks, before mutation.
    for name in files:
        raw = root / name
        path = safe_path(root, name)
        require(not raw.is_symlink() and not path.exists(), f"file already exists: {name}")
    for name, content in files.items():
        path = safe_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)


def init(root, tasks_dir=None):
    root = root.resolve()
    files, data = bootstrap(root, tasks_dir)
    create_files(root, files)
    return {"workspace": str(root), "tasks_dir": data.get("tasks_dir", "projects"),
            "created": list(files), "existing_files": "preserved"}


def new_task(root, topic, question, template, scene, files, guide, origin=None):
    """Create a task; callers supply template-specific files relative to the task directory."""
    require(isinstance(topic, str) and re.fullmatch(TOPIC, topic), "topic must be kebab-case")
    require(nonempty(question), "question cannot be empty")
    info = template_info(template)
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        require((root / MARKER).is_file(), "nonempty directory is not a task-harness instance; use init explicitly or choose another directory")
    workspace_files, data = bootstrap(root)
    task = task_directory(root, data.get("tasks_dir", "projects")) / topic
    require(not task.exists() and not task.is_symlink(), "task already exists; resume it or use a new topic")
    require(root in task.resolve().parents, "project path escapes instance")
    prefix, version = task.relative_to(root).as_posix(), catalog()["version"]
    definition = definition_file(template)
    record = {"schema_version": 1, "template": template, "scene": scene, "question": question,
              "created_at": date.today().isoformat(), "created_with": version, **(origin or {})}
    closing = f"\n收尾：done 前先生成检查报告（{info['report']}），checkpoint 时用 --report 引用。" if info.get("report") else ""
    planned = {f"{prefix}/task.json": json.dumps(record, ensure_ascii=False, indent=2) + "\n",
               f"{prefix}/README.md": f"""# {topic}

问题：{question}
入口：先读最新 handoffs/*.json（若无，任务尚未记录交接），再读 [{definition}]({definition})。
新建状态：DRAFT；初始下一步：填写目标、范围、交付与完成条件。进度以最新交接为准。
公共包出生版本：task-harness {version}；流程 {template}，场景 {scene}。
{guide}
资料与结果按实际需要建立 inputs/、outputs/、deliverables/、tmp/；已有项目按其规则放置。
需要追溯时补 sources.md；范围变更与重要决策记 events.md，不覆盖旧结果。
交接时使用 checkpoint 留下摘要、下一步、阻塞和交付依据；同目标续做，不因换会话重建。
已交付文件不原位改写，修订另存新文件名。{closing}
"""}
    planned.update({f"{prefix}/{name}": content for name, content in files.items()})
    planned.update(workspace_files)
    create_files(root, planned)
    return {"task": str(task), "state": "DRAFT", "template": template, "scene": scene,
            "next": "Fill the task definition; create material folders only when needed."}


def task_path(root, topic):
    require(isinstance(topic, str) and re.fullmatch(TOPIC, topic), "topic must be kebab-case")
    directory = task_directory(root, config(root).get("tasks_dir", "projects"))
    task = safe_path(root, str((directory / topic).relative_to(root)))
    require(task.is_dir(), "task not found")
    return task


def metadata(task):
    path = safe_path(task, "task.json")
    if not path.exists():
        require(safe_path(task, "spec.json").is_file(), "unregistered directory; follow its existing entry")
        return {"template": "verify", "legacy": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and data.get("schema_version") == 1, "unknown task schema")
    template_info(data.get("template"))
    return data


def snapshots(task):
    path = safe_path(task, "handoffs")
    if not path.exists():
        return []
    require(path.is_dir(), "handoffs conflicts with a file")
    paths = sorted(path.glob("*.json"))
    require(all(re.fullmatch(r"[0-9]{6}\.json", p.name) for p in paths), "unrecognized handoff filename")
    for p in paths:
        require(not p.is_symlink(), "handoff cannot be a symlink")
    return paths


def validate_handoff(task, data):
    require(isinstance(data, dict) and data.get("schema_version") == 1, "unknown handoff schema")
    require(data.get("status") in {"active", "blocked", "done"}, "invalid handoff status")
    require(nonempty(data.get("summary")), "handoff needs summary")
    if data["status"] != "done":
        require(nonempty(data.get("next_step")), "unfinished task needs next_step")
    if data["status"] == "blocked":
        require(nonempty(data.get("blocker")), "blocked task needs blocker and release condition")
    if data["status"] == "done":
        require(not data.get("blocker"), "done task cannot have an unresolved blocker")
        require(nonempty(data.get("review")), "done task needs actual review details")
        require(data.get("deliverables"), "done task needs a deliverable (text answers may be saved to a file)")
    refs = data.get("deliverables")
    require(isinstance(refs, list) and all(nonempty(p) for p in refs), "deliverables must be paths")
    for ref in refs:
        parts = safe_path(task, ref).relative_to(task.resolve()).parts
        require(parts[0] != "handoffs" and parts not in CONTROL_FILES, f"{ref} is a task control file, not a deliverable")
    hashes = data.get("evidence_fingerprints")
    require(isinstance(hashes, dict) and hashes, "handoff needs evidence fingerprints")
    definition = definition_file(metadata(task)["template"])
    report = data.get("report")
    require(report is None or (nonempty(report) and report in hashes), "handoff report must be a fingerprinted path")
    require({definition, *refs} <= hashes.keys(), "handoff does not bind its definition and deliverables")


def check_report(task, template, ref):
    """A done verify/research task cites the checker's saved report; FAIL is a valid finished outcome."""
    pattern = template_info(template)["report"]
    require(nonempty(ref), f"done {template} task needs --report {pattern}; run the checker first")
    path = safe_path(task, ref)
    relative = PurePosixPath(path.relative_to(task.resolve()).as_posix())
    require(len(relative.parts) == len(PurePosixPath(pattern).parts) and relative.match(pattern), f"report must match {pattern}")
    require(path.is_file(), f"report not found: {ref}")
    saved = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(saved, dict) and saved.get("assessment") in {"PASS", "PARTIAL", "FAIL"}, "report lacks an assessment")
    if template == "verify":
        replay(task, ref)
    hashes = saved.get("evidence_fingerprints")
    require(isinstance(hashes, dict) and hashes, "report lacks evidence fingerprints; regenerate it with the checker")
    for name, value in hashes.items():
        require(matches(task, name, value), f"report evidence changed since the check: {name}; run the checker again")
    return saved["assessment"]


def matches(task, name, saved):
    path = safe_path(task, name)
    return path.is_file() and path.stat().st_size > 0 and fingerprint(path) == saved


def frozen_deliveries(task, paths, pending=None):
    """Files delivered by any done snapshot stay byte-identical; revisions use new names."""
    problems, records = [], [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    labels = [p.name for p in paths]
    if pending is not None:
        records.append(pending)
        labels.append("this checkpoint")
    for index, data in enumerate(records):
        if not isinstance(data, dict) or data.get("status") != "done":
            continue
        for ref in data.get("deliverables", []):
            current = safe_path(task, ref)
            current = fingerprint(current) if current.is_file() else None
            accepted = any(isinstance(x, dict) and x.get("overwritten", {}).get(ref, {}).get("now") == current
                           for x in records[index + 1:])
            message = (f"delivered file changed after {labels[index]}: {ref}; restore it and save the revision under a new name, "
                       f"or record the loss with checkpoint --overwritten {ref} --reason ...")
            if not accepted and not matches(task, ref, data["evidence_fingerprints"].get(ref)) and message not in problems:
                problems.append(message)
    return problems


def handoff_check(task):
    paths = snapshots(task)
    if not paths:
        return {"state": "NO_HANDOFF", "issues": ["No checkpoint; read the task README and definition."]}
    data = json.loads(paths[-1].read_text(encoding="utf-8"))
    changed = []
    try:
        validate_handoff(task, data)
        changed = [name for name, saved in data["evidence_fingerprints"].items() if not matches(task, name, saved)]
        issues = frozen_deliveries(task, paths)
        record_changes = [name for name in changed if name not in data["deliverables"]]
        if data["status"] == "done" and record_changes:
            issues.append(f"changed after delivery: {', '.join(record_changes)}; record the scope change in events.md and save a new checkpoint")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        issues = [str(exc)]
    return {"state": "NEEDS_ATTENTION" if issues else "RECORDED", "recorded_status": data.get("status") if isinstance(data, dict) else None,
            "handoff": str(paths[-1].relative_to(task)), "summary": data.get("summary") if isinstance(data, dict) else None,
            "next_step": data.get("next_step") if isinstance(data, dict) else None,
            "blocker": data.get("blocker") if isinstance(data, dict) else None, "issues": issues,
            "changed_since_checkpoint": changed, "assessment": data.get("assessment") if isinstance(data, dict) else None,
            "claim_limit": "Recorded handoff completeness and file integrity only; no semantic or outcome assessment."}


def checkpoint(root, topic, status, summary, next_step="", blocker="", deliverables=(), review="", overwritten=(), reason="",
               report=None):
    task = task_path(root, topic)
    template = metadata(task)["template"]
    refs = list(deliverables)
    definition = definition_file(template)
    has_checker = bool(template_info(template).get("report"))
    require(not report or has_checker, f"{template} tasks have no checker report")
    assessment = check_report(task, template, report) if report or (status == "done" and has_checker) else None
    evidence = {}
    for ref in [definition, *refs, *([report] if report else [])]:
        path = safe_path(task, ref)
        require(path.is_file() and path.stat().st_size > 0, f"missing or empty handoff evidence: {ref}")
        evidence[ref] = fingerprint(path)
    data = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "status": status,
            "summary": summary, "next_step": next_step, "blocker": blocker, "deliverables": refs,
            "review": review, "evidence_fingerprints": evidence}
    if report:
        data.update(report=report, assessment=assessment)
    validate_handoff(task, data)
    paths = snapshots(task)
    if overwritten:
        require(nonempty(reason), "--overwritten needs --reason explaining why the delivered bytes cannot be restored")
        lost = {}
        for ref in overwritten:
            path = safe_path(task, ref)
            lost[ref] = {"now": fingerprint(path) if path.is_file() else None, "reason": reason}
        data["overwritten"] = lost
    problems = frozen_deliveries(task, paths, data)
    if problems:
        raise ValueError(problems[0])
    sequence = int(paths[-1].stem) + 1 if paths else 1
    require(sequence <= 999999, "handoff sequence exhausted")
    target = safe_path(task, f"handoffs/{sequence:06d}.json")
    write_new(target, data)
    return handoff_check(task)


def inventory(root):
    directory = task_directory(root, config(root).get("tasks_dir", "projects"))
    result = []
    for raw in sorted(directory.iterdir()) if directory.exists() else []:
        if not raw.is_dir() and not raw.is_symlink():
            continue
        row = {"topic": raw.name, "path": str(raw.relative_to(root))}
        try:
            task = safe_path(root, str(raw.relative_to(root)))
            info = metadata(task)
            row.update(template=info["template"], question=info.get("question"), **handoff_check(task))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row.update(state="NEEDS_ATTENTION", issues=[str(exc)])
        result.append(row)
    return {"workspace": str(root), "tasks": result, "index": "derived from task files; no separate registry"}
