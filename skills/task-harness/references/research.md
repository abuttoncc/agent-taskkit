# 金融研究流程

先按用户问题选择公司研究、财报分析或同业比较场景。只读对应场景卡；涉及计算时再读 [指标与计算口径](finance-methods.md)。本流程组织研究，不自带行情、研报订阅、交易接口或凭证。

## 形成任务

由 Agent 新建 `research` 任务，填写 request.md：对象与市场、信息截止日、报告期、要回答的问题、交付形式、验收标准和停止条件。当前问题能直接回答时无需建档。已有材料足够就继续，只有影响结论的信息缺口才询问用户。

```sh
python3 PACKAGE/scripts/harness.py new --root INSTANCE --template research --scene company --topic company-review --question '用户问题'
```

scene 可选 company、earnings、peers。同一实例可以同时保存 API 和研究任务；根据每个任务的 task.json 定位类型。旧 verify 任务无需迁移。

Agent 根据本轮目标填写 `inputs/expected-v1.csv`。列为 `id,requirement,description,basis,acceptance`，requirement 为 required/investigate/not_applicable。研究流程不强制冻结；有事前对照实验要求时另建 verify 子任务，不把事后研究伪装成事前验证。任务范围变化需留事件和前版材料；用新 expected-v2.csv，并让 research.json 的 expected 字段指向它（省略时默认 inputs/expected-v1.csv）。不能为了通过检查删除未完成承诺。

## 获取材料

| 需要什么 | 优先入口 | 实际检查 |
|---|---|---|
| 财务与经营数据 | 交易所/监管披露、公司年报季报、投资者关系页面 | 报告期、币种、金额单位、合并口径、重述版本 |
| 最新价格、股本、汇率 | 用户已授权的数据工具或可验证公开行情 | 时间戳、时区、复权、总股本/流通股本、报价币种 |
| 市场预期 | 用户提供或已授权的一致预期/券商材料 | 形成日期、样本、预测年度与实际口径是否相同 |
| 行业与同业 | 原始统计、公司披露、可验证行业材料 | 样本差异、商业模式、地域和财年差异 |

先读取当前环境实际可用工具的自述，再选择具体入口。来源不足时用可获得的原始公开披露完成能完成的部分，并说明缺口。没有一致预期不能说“超市场预期”；没有价格或股本就不计算当前估值。不把搜索摘要直接当作完整原文，不自动安装付费连接或索要用户把密钥写入任务文件。

`sources.md` 作人读索引；`inputs/research.json` 作机器检查的来源、结论与复核记录。保存原始摘录或脱敏响应到任务 inputs/；最终报告里也给读者来源链接或文件页码。

## 做判断并复核

在 findings.md 区分事实、推断、假设。每个核心判断登记到 research.json 的 claims；写明来源 ID，需要计算的再写 calculation_ids。推断和假设需说明 reasoning。处理与主论点矛盾的材料；缺数用 null/缺失，不用零或经验补齐。

计算由 finance.py 或已有经过验证的工具完成。finance.py 输出公式、完整输入、单位、报告期、来源 ID、输入文件 hash；支持增速、差值、比值和百分比。它不会查行情、自动换汇、统一财年或推断调整项。额外模型须单独保存公式、假设、脚本和来源，不能冒充本脚本已验收的计算。

按 request 和 expected 写 `deliverables/report-v1.md`，可从 inputs/report-template.md 起稿。复核时更新 review.md，以及 research.json 的 review。复核记录必须描述实际检查，不能只因文件存在就标通过。

```sh
python3 PACKAGE/scripts/finance.py --root TASK --input inputs/metrics.json --out outputs/calculations-01.json
python3 PACKAGE/scripts/research.py check --root TASK --out outputs/research-review-01.json
python3 PACKAGE/scripts/research.py replay --root TASK --report outputs/research-review-01.json
```

退出码 0 为本地记录检查 PASS；1 为已输出的 PARTIAL/FAIL；2 为格式、路径、来源引用或重算不一致。输出必须用新名字，replay 不修改旧报告。没有计算时 calculation_files 可为空；有缺失计算的交付允许解释后给出部分结论，检查仍保留 PARTIAL。

研究完成与投资对象好坏无关。给出负面结论也可以完整交付。检查器不证明披露真实、结论正确或投资有利，只核对追溯、可重算性和已记录的验收项。

## research.json 格式

```json
{
  "schema_version": 1,
  "as_of": "2026-10-25",
  "sources": [{
    "id": "S1", "citation": "用户提供的示例财报（合成数据）",
    "locator": "收入和利润表", "published_at": "2026-01-15", "accessed_at": "2026-10-25",
    "evidence": ["inputs/source-example.json"]
  }],
  "claims": [{
    "id": "F1", "kind": "inference", "statement": "示例收入同比增长 25%。",
    "source_ids": ["S1"], "calculation_ids": ["revenue-growth"],
    "reasoning": "统一口径后的本期与前期收入相除减一。"
  }],
  "calculation_files": ["outputs/calculations-01.json"],
  "review": [{
    "id": "growth", "status": "PASS", "detail": "比对输入与来源，并重算增长率。",
    "evidence": ["outputs/calculations-01.json", "deliverables/report-v1.md"]
  }],
  "deliverables": ["deliverables/report-v1.md"],
  "limitations": ["示例数据，仅用于演示工作流。"]
}
```

所有路径相对 TASK，不支持跨任务或敏感配置路径。来源发布日期不得晚于 as_of；未知日期用 null，检查会保留 PARTIAL。source_ids 必须存在；所有计算文件都会按原输入重算，每个计算输入的 source_id 必须登记。

review 的 ID 对应 expected；required 有 FAIL 总评 FAIL；缺项、待核实、计划外项、缺失计算或来源日期未知为 PARTIAL。不适用项可省略或 SKIP。结果记录中包含证据 hash，原始材料、交付物或复核记录改动后，旧报告 replay 将拒绝。

## 继续与交付

先读任务 README、request、findings 与最近复核；确认来源是否仍满足时点，再补缺项。改报告写新版本，保留旧结果。交付核心判断、证据、计算和关键限制；再更新 README 的结果与下一步。个人偏好和方法进入本实例，真实研究材料不提交到公共技能仓库。
