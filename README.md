# TaskKit

**给 Agent 配好方法、模板和工具，让任务可以验证、复跑和接着做。**

TaskKit 提供一个用户级入口 Skill：`task-harness`。你用自然语言交代目标，Agent 从统一资源目录选择流程、场景卡和模板，运行辅助脚本并保存结果。

当前支持 **API 验证 + 金融研究**。金融研究包括公司研究、财报分析和同业比较，配套来源登记、可溯源计算、报告模板与交付复核。视频制作由其他工具承接，不在本包实现。

## 一段话安装

把下面这段交给支持本地文件读写和命令执行的 Agent：

> 请从 https://github.com/abuttoncc/agent-taskkit/tree/v0.3.0/skills/task-harness 安装 task-harness 到你当前运行时的用户级技能目录，让它在其他项目中也可用。先读安装说明，完成后确认你能发现这个 Skill，并告诉我当前有哪些模板。

也可以下载 [v0.3.0 技能 ZIP](https://github.com/abuttoncc/agent-taskkit/releases/download/v0.3.0/task-harness-0.3.0.zip)，把文件交给 Agent 安装。[校验和](https://github.com/abuttoncc/agent-taskkit/releases/download/v0.3.0/task-harness-0.3.0.zip.sha256) · [全部版本](https://github.com/abuttoncc/agent-taskkit/releases)

需要 Python 3.9+，无第三方 Python 依赖。这里的“用户级”指当前用户的 Agent 环境；不同客户端或机器可能需要分别安装。普通聊天窗口若不能操作本地文件或执行命令，不能仅凭提示词完成安装。

## 装好后这样用

> 用 task-harness 帮我测试这个 API。文档在这里，重点检查它是否返回我需要的数据，并保存过程，方便下次继续。

还可以说：

- “研究这家公司，重点看利润质量和现金流，保留来源与报告。”
- “帮我分析这次财报，说明变化、反证和还缺哪些数据。”
- “比较这几家公司的增长和利润率，先统一会计口径。”
- “继续上次的 API 测试。”
- “检查这个任务还有哪些没完成。”
- “task-harness 现在有哪些模板？”
- “把 task-harness 更新到我提供的新版本。”

Agent 负责选资源、填写任务定义、执行脚本和解释结果。第一次可以明确提到技能名；后续是否自动匹配由宿主 Agent 决定。

## 一个入口，配套资源按需读取

| 内容 | 用途 |
|---|---|
| [SKILL.md](skills/task-harness/SKILL.md) | 从用户目标进入任务 |
| [catalog.json](skills/task-harness/catalog.json) | 集中登记资源与适用场景 |
| [references/](skills/task-harness/references/) | 验证/研究流程、API/公司/财报/同业场景卡与执行手册 |
| [assets/](skills/task-harness/assets/) | 生成任务材料的起始模板 |
| [scripts/](skills/task-harness/scripts/) | 建档、冻结、对账、财务计算、研究复核、重放、安装和更新 |

完整说明见 [安装与使用](skills/task-harness/INSTALL.md)。资源随版本包安装，可离线读取；当前没有在线动态资源服务。

## 工作方式

验证任务先建立验收清单并冻结基线，再执行和对账。研究任务记录问题、信息截止日、来源与结论，按实际研究推进，不强制冻结。

金融计算保存公式、原始输入、报告期、单位和来源 ID；缺数不补猜，非正增长基期不硬算同比。研究复核检查来源引用、计算重放与交付承诺，旧证据改动后重放会报错。失败、漏项和未解决项都会保留。

数据由用户已有的授权工具或可验证公开披露获取。本包不附带行情订阅、研报权限、证券交易接口或自动估值模型。计算器支持增速、差值、比值和百分比；研究场景指导 Agent 判断适用性与反证。

公共包与个人实例分开。公共包升级不修改个人偏好、任务和证据；中央包若有本地改动，自带更新器会拒绝覆盖。通过其他安装渠道获取的 Skill 应沿用原渠道更新。

技能不包含凭证或业务数据，不内置上传、遥测或网络调用。实际 API 请求由 Agent 使用已获授权的工具完成，保存日志前需要脱敏。

## 开发与验证

从仓库根目录运行：

```sh
python3 -B -m unittest discover -s tests -v
python3 scripts/build_release.py --out dist
python3 examples/research_demo.py --root workspace/finance-demo
```

发布脚本只打包明确列出的 Skill 文件，输出 ZIP 与 SHA-256。测试覆盖基线与报告不覆盖、证据篡改、结果分类、路径边界、实例保护和中央包更新。

v0.3.0 新增金融研究资源与完整合成数据演示，28 项本地测试通过。已做本地功能与安装检查；尚未做跨客户端安装验收或真实任务提效 A/B 实验。对账/复核通过只说明记录的覆盖、追溯与显式计算一致，不能证明真实数据无误或投资结论正确。演示数据完全合成，不代表实盘研究验收。
