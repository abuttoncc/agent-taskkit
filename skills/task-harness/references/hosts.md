# 宿主派工

四席的分工、顺序和停止条件在 [固定四席](team.md)。本页只回答一件事：当前运行时怎样把 search 和 analysis 派出去。

先用 [SKILL.md](../SKILL.md) 的认宿主表选定一节，只执行那一节。定义文件的路径是去读宿主已经有的配置。用户没有明确要求长期复用时，本轮不新建代理定义。

## 共同

- leader 是当前会话，负责分发和最终交付，不另起进程。
- structure 由 leader 在收口时完成，不单开进程。它检查交付还缺什么，以及现在能不能停。
- search 只核仓库外的现行事实。analysis 只对照仓库、架构和风险。两边都只把摘要交回：核过的问题、出处、冲突、缺失。
- 两个派工都发出之后，leader 立刻做自己的那份核对，再用该宿主的等待方式取回摘要。
- 子任务使用宿主已经给它的工具。定义文件里不替它开关工具，也不替它改沙箱或权限。
- 外部事实的链接仍由 leader 写入任务的 `sources.md`。
- 派工事实写入 `outputs/workflow.md`。并行一节写清用了哪个机制；走单代理时写明没有并行进程，以及缺的是哪个工具或哪个开关。

## Grok Build

认宿主表命中 `spawn_subagent` 时走这一节。

1. search 调用一次 `spawn_subagent`。`description` 用 `search 外部事实`。`prompt` 写清要核的问题、仓库路径，并要求只返回摘要、不再派子任务。`run_in_background` 保持默认。
2. analysis 再调用一次。`description` 用 `analysis 仓库对照`。`prompt` 写清要对照的路径和风险，同样只返回摘要、不再派子任务。
3. 不填 `subagent_type`。省略时宿主使用 `general-purpose`。内置的 `explore`、`plan` 不能按名字点选。
4. 不在这次调用里写 persona。人格由宿主从 `~/.grok/config.toml` 的 `[subagents.personas]`、项目 `.grok/personas/*.toml`、用户 `~/.grok/personas/*.toml` 解析。
5. `isolation` 用 `none`。这轮要改代码且必须与主会话的工作树分开时，用 `worktree`。
6. leader 同时做自己的核对。然后用 `get_command_or_subagent_output` 取回两个子任务的摘要。
7. 嵌套深度默认是 1。子任务自己没有 `spawn_subagent`。

这些开关打开时改为 [单代理](#单代理)：命令行 `--no-subagents`，环境变量 `GROK_SUBAGENTS=0`，或 `~/.grok/config.toml` 里 `[subagents] enabled = false`。

已有自定义代理是带 YAML frontmatter 的 markdown：

- 项目：`.grok/agents/*.md`
- 用户：`~/.grok/agents/*.md`

## Claude Code

认宿主表命中 Agent 工具时走这一节。

1. search 调用 Agent 工具，`subagent_type` 填 `general-purpose`。任务说明写要核的外部问题，只要摘要，不改文件。
2. analysis 调用 Agent 工具，`subagent_type` 填 `Explore`。Explore 是只读的仓库对照。环境有 `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS=1` 时，analysis 改用 `general-purpose`，任务说明里写明不改文件。
3. `subagent_type` 必填。会话里没有 `general-purpose` 可回退时，省略会直接失败。
4. 两次都发出后，leader 做自己的核对。主会话发起的子代理默认在后台跑；向宿主取这两次的结果，取回前继续做 leader 自己的材料。
5. Agent 工具被权限规则关掉时，改为单代理。

已有子代理定义是 markdown，frontmatter 必填 `name` 和 `description`：

- 项目：`.claude/agents/**/*.md`，从当前目录向上扫描到仓库根
- 用户：`~/.claude/agents/**/*.md`

身份来自 frontmatter 的 `name`，不要求文件名相同。用户明确要求把某席做成长期子代理时才新建，`description` 写清何时委托。

## Codex

认宿主表命中 `CODEX_THREAD_ID` 或 `CODEX_SESSION_ID` 时走这一节。

1. 在本轮明确派出两个子代理，并等待两边的摘要。search 只核仓库外的现行事实。analysis 点名内置的 `explorer`，只读对照仓库、架构和风险。
2. 当前 Codex 会执行 Skill 里写明的派工。子代理继承本会话的模型、沙箱和工具。
3. leader 在等待期间做自己的核对，收齐摘要后再收口。
4. 项目 `.codex/config.toml` 或用户 `~/.codex/config.toml` 里 `[agents] enabled = false` 时，改为单代理。并发上限看 `agents.max_concurrent_threads_per_session`；本模板只派 search 和 analysis 两个。

已有自定义代理是 TOML，必填 `name`、`description`、`developer_instructions`：

- 项目：`.codex/agents/*.toml`
- 用户：`~/.codex/agents/*.toml`

文件里的 `name` 是身份。沙箱、审批和 MCP 跟随父会话，不在这个文件里覆盖。用户明确要求长期复用时才新建。

## 单代理

Grok、Claude Code、Codex 三节的工具都不在当前会话，或该节写明的开关已关掉时：

按 search、analysis、structure 的顺序自己做完。leader 仍写最终交付。`outputs/workflow.md` 的「并行」写明这次没有并行进程，并写上依据：缺 `spawn_subagent`、缺 Agent 工具、缺 Codex 会话环境，或写上关掉派工的那个开关。「谁在等」写明没有另一边在跑。
