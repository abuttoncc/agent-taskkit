# TaskKit

一个让 Agent 按流程完成任务、保存证据、方便下次继续的 Skill。安装名为 `task-harness`，流程说明、模板和辅助脚本随包提供，由 Agent 按需使用。

## 能做什么

- **通用验证与 API 测试**：建立验收清单、检查结果、保存证据并复跑。
- **金融研究**：公司研究、财报分析、同业比较，配套来源记录、可溯源计算和报告复核。

## 安装

把下面这段话发给能读写本地文件、执行命令的 Agent：

> 请从 https://github.com/abuttoncc/agent-taskkit/tree/v0.3.0/skills/task-harness 安装 task-harness。先读 INSTALL.md，安装到当前运行时的用户级技能目录，并确认安装成功。

需要 Python 3.9+，无第三方 Python 依赖。也可下载 [技能 ZIP](https://github.com/abuttoncc/agent-taskkit/releases/download/v0.3.0/task-harness-0.3.0.zip) 交给 Agent 安装。

## 使用

直接用自然语言交代任务，例如：

> 用 task-harness 测试这个 API，检查返回数据是否符合要求，并保存过程。

> 用 task-harness 分析这家公司最新财报，重点看利润质量和现金流，保留来源与报告。

> 继续上次的研究，列出尚未验证的问题。

金融数据由你已有的授权工具或公开披露提供；本包不含数据订阅。复核检查记录与计算的一致性，不保证投资结论正确。

[详细安装与使用](skills/task-harness/INSTALL.md) · [资源目录](skills/task-harness/catalog.json) · [版本下载](https://github.com/abuttoncc/agent-taskkit/releases)
