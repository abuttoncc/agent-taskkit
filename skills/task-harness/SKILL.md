---
name: task-harness
description: 给工作区建立任务秩序：按需建任务目录与提示词框架，接续旧任务，用交接快照记录状态、下一步和交付，已交付文件不被原位改写。用于初始化工作区、需要分步推进或留存成果的新任务、继续上次的任务、查看未完成任务、API 与明确承诺的验证；简单问答无需建档。金融研究另用 finance-research。
---

# Task Harness

先认工作区规则与已有任务，再按需建档，执行后留下可接续的交接。用户只交代目标；你选流程、填材料、跑脚本，不要求用户学目录术语或手填 JSON/CSV。

TH 是本 Skill 目录，INSTANCE 是工作区，TOPIC 是 kebab-case 任务名。命令从任意目录运行，路径按当前 shell 引用。

## 先定位

读当前项目生效的 AGENTS.md/CLAUDE.md 与 WORKSPACE.md，确认可写范围和已有约定。用户指定路径优先；不把项目规则写到共享父目录，不扫描其他用户的工作区。

| 情况 | 动作 |
|---|---|
| 简单问答、单次查证、小修改 | 直接做，不建档 |
| 已有任务的补充、修订、下一阶段 | 续做原任务；换日、换会话不新建 |
| 新的独立目标，要分步推进或留存成果 | 新建任务，有关联时在 request 中引用旧任务 |
| 已有成熟目录与任务入口 | 沿用原规则，只借本框架，不搬家 |

## 核心命令

```sh
python3 TH/scripts/harness.py tasks --root INSTANCE          # 总览：最新状态、下一步、需关注项
python3 TH/scripts/harness.py init  --root INSTANCE          # 只建立秩序；已有规则保留，可加 --tasks-dir 相对目录
python3 TH/scripts/harness.py new   --root INSTANCE --topic TOPIC --question '用户的具体目标'
python3 TH/scripts/harness.py checkpoint --root INSTANCE --topic TOPIC --status active --summary '已完成…' --next '下一步…'
python3 TH/scripts/harness.py checkpoint --root INSTANCE --topic TOPIC --status blocked --summary '…' --next '…' --blocker '缺什么；什么条件解除'
python3 TH/scripts/harness.py checkpoint --root INSTANCE --topic TOPIC --status done --summary '…' --deliverable deliverables/x.md --review '实际做过的检查'
```

- new 默认 general，生成 README.md、request.md、task.json。创建后是 DRAFT：先按 request 的五节填目标、范围、材料、交付、完成与停止条件，再执行。
- 验证类任务加 `--template verify`，流程见 [验证](references/verify.md)；done 时还要 `--report outputs/<run>-comparison.json`。
- 说明要写真实内容，不能为通过检查填示例话。done 需要非空交付文件、实查说明、无阻塞；控制文件（request/README/task.json/handoffs）不算交付。

## 交接规则

- 阶段结束、阻塞或交付时存 checkpoint，快照追加到 handoffs/，最新一份就是当前入口。
- 进行中改 request 或草稿属正常，tasks 只列出变动。
- **已交付文件冻结。** done 之后可以回到 active 继续，但交付过的文件不能原位改；修订另存新文件名（report-v2.md）。原字节确实找不回时，用 `--overwritten 路径 --reason 原因` 记入新快照，不能悄悄覆盖。
- done 之后又改了任务定义，要在 events.md 记范围变化，再存新快照。
- 检查器只核对字段与文件指纹，不判断内容语义。验证对象 FAIL 也可以是一项完成的交付，不要把"任务结束"说成"对象通过"。

## 按需读

| 什么时候 | 读哪里 |
|---|---|
| 填 general 任务的 request | [通用任务框架](references/general.md) |
| 初始化已有项目、个人偏好与方法放哪 | [工作区秩序](references/workspace.md) |
| API 测试、验证承诺 | [验证](references/verify.md)、[API 场景卡](references/api.md) |
| 体检、安装与更新、可选会话 hook | [执行手册](references/operations.md) |
| 报告结论前 | [五条红线](references/red-lines.md) |

公司研究、财报分析、同业比较用 finance-research Skill 创建任务，交接仍用这里的 checkpoint。具体取数、成稿等能力交给环境中已有的工具或 Skill，不冒称本包内置了它们。

给用户结论与交付入口，收尾记录保持简短。经验先留在任务里，确认可复用后再放进个人方法；不自动把个人材料回传公共 Skill。
