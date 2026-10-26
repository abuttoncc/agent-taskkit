# TaskKit

**给 Agent 一套工作秩序：工作区有统一约定，任务按需建目录，过程和成果各有归处。**

安装名为 `task-harness`。公共 Skill 提供流程、提示词框架与脚本；个人规则、材料和任务留在自己的工作区。

## 怎么工作

1. **先认工作区**：读已有规则与入口。可以先初始化工作区，不必虚构任务；已有文件和目录约定保留。
2. **再判断任务**：简单问题直接做，同目标继续原任务，需要留存的新目标再建目录。
3. **用框架承接**：明确目标、范围、材料与方法、执行与交付、完成和停止条件。Agent 负责填写，用户只需交代目标。
4. **按需收纳与交接**：输入、过程和成果用到时再建目录，阶段结束留下结果、下一步与阻塞，方便下次接着做。

新建的通用任务只有三个文件：

```text
工作区/
├── AGENTS.md                 # 新工作区的简短规则；已有规则保留
├── WORKSPACE.md              # 工作区导航与收纳约定
└── projects/<任务名>/        # 默认位置，也可沿用自定义任务目录
    ├── README.md            # 任务入口
    ├── request.md           # 本次任务的提示词框架
    └── task.json            # 类型、目标和创建版本
```

需要时再增加 `inputs/`、`outputs/`、`deliverables/` 和来源记录；交接快照放 `handoffs/`。任务总览从实际记录生成。个人偏好与方法也按需积累，公共包升级不覆盖它们。

内置**通用任务、API 验证、金融研究（公司、财报、同业）**三类流程，从同一个[资源目录](skills/task-harness/catalog.json)按需选用。其他具体能力交给环境中已有工具。

## 安装与使用

把这段话交给能读写本地文件、执行命令的 Agent（Python 3.9+，无第三方 Python 依赖）：

> 请从 https://github.com/abuttoncc/agent-taskkit/tree/v0.4.0/skills/task-harness 安装 task-harness。先读 INSTALL.md，安装到当前运行时的用户级技能目录，并确认安装成功。

装好后可以说：

> 给这个工作区建立统一秩序，保留已有规则。后续任务按需建目录，保存过程与交接。

> 用 task-harness 开始这项方案设计，明确完成条件；如果已有对应任务就接着做。

> 看看这个工作区有哪些未完成任务，从上次的下一步继续。

检查器核对交接字段、文件完整性及专门流程的记录；内容质量由 Agent 实际核验。它没有后台服务或强制 hook。

[详细安装与使用](skills/task-harness/INSTALL.md) · [工作区规则](skills/task-harness/references/workspace.md) · [版本下载](https://github.com/abuttoncc/agent-taskkit/releases)
