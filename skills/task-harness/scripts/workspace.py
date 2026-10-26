"""Workspace initialization, derived task inventory and append-only handoffs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from contract import fingerprint, nonempty, require, safe_path, write_new

PACKAGE = Path(__file__).resolve().parents[1]
MARKER = ".task-harness.json"


def catalog():
    return json.loads((PACKAGE / "catalog.json").read_text(encoding="utf-8"))


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


def task_path(root, topic):
    require(isinstance(topic, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic), "topic must be kebab-case")
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
    require(data.get("template") in {x["name"] for x in catalog()["templates"]}, "unknown task template")
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
    hashes = data.get("evidence_fingerprints")
    require(isinstance(hashes, dict) and hashes, "handoff needs evidence fingerprints")
    definition = "spec.json" if metadata(task)["template"] == "verify" else "request.md"
    require({definition, *refs} <= hashes.keys(), "handoff does not bind its definition and deliverables")
    for name, saved in hashes.items():
        path = safe_path(task, name)
        require(path.is_file() and path.stat().st_size > 0, f"missing or empty handoff evidence: {name}")
        require(fingerprint(path) == saved, f"handoff evidence changed: {name}; save a new checkpoint")


def handoff_check(task):
    paths = snapshots(task)
    if not paths:
        return {"state": "NO_HANDOFF", "issues": ["No checkpoint; read the task README and definition."]}
    data = json.loads(paths[-1].read_text(encoding="utf-8"))
    try:
        validate_handoff(task, data)
        issues = []
    except (ValueError, OSError, KeyError, TypeError) as exc:
        issues = [str(exc)]
    return {"state": "NEEDS_ATTENTION" if issues else "RECORDED", "recorded_status": data.get("status") if isinstance(data, dict) else None,
            "handoff": str(paths[-1].relative_to(task)), "summary": data.get("summary") if isinstance(data, dict) else None,
            "next_step": data.get("next_step") if isinstance(data, dict) else None,
            "blocker": data.get("blocker") if isinstance(data, dict) else None, "issues": issues,
            "claim_limit": "Recorded handoff completeness and file integrity only; no semantic or outcome assessment."}


def checkpoint(root, topic, status, summary, next_step="", blocker="", deliverables=(), review=""):
    task = task_path(root, topic)
    info = metadata(task)
    refs = list(deliverables)
    definition = "spec.json" if info["template"] == "verify" else "request.md"
    evidence = {}
    for ref in [definition, *refs]:
        path = safe_path(task, ref)
        require(path.is_file() and path.stat().st_size > 0, f"missing or empty handoff evidence: {ref}")
        evidence[ref] = fingerprint(path)
    data = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "status": status,
            "summary": summary, "next_step": next_step, "blocker": blocker, "deliverables": refs,
            "review": review, "evidence_fingerprints": evidence}
    validate_handoff(task, data)
    paths = snapshots(task)
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
