---
name: finance-research
description: 金融研究流程：公司研究、财报分析、同业比较。登记来源与结论，用十进制计算器做可重算的增速/比率，检查追溯与验收清单。用于需要留存来源、计算和报告的研究任务；一句话能答的行情或事实查询不必建档。依赖 task-harness 管工作区与交接；取数用环境里已有的数据工具。
---

# Finance Research

组织研究过程，不自带行情、研报或交易接口。取数用当前环境实际可用的数据工具或 Skill；本包负责范围、来源、计算与复核，交接交给 task-harness。

FR 是本 Skill 目录，TH 是 task-harness 目录（同级安装，或用 TASK_HARNESS_HOME 指定），INSTANCE 是工作区，TASK 是任务目录。

## 流程

1. **判断是否建档。** 能直接回答就直接回答。同一研究对象和交付继续原任务（先跑 `TH/scripts/harness.py tasks --root INSTANCE`）。
2. **建任务并填 request。** 对象与市场、信息截止日、报告期、问题、交付形式、停止条件；验收项写进 `inputs/expected-v1.csv`。
   ```sh
   python3 FR/scripts/research.py new --root INSTANCE --scene company|earnings|peers --topic <kebab> --question '<问题>'
   ```
3. **取材与判断。** 原始材料存 `inputs/`，来源与结论登记 `inputs/research.json`；事实、推断、假设分开写，缺数写 null。
4. **计算与检查。** 输出用新文件名，不覆盖旧结果。
   ```sh
   python3 FR/scripts/finance.py --root TASK --input inputs/metrics.json --out outputs/calculations-01.json
   python3 FR/scripts/research.py check --root TASK --out outputs/research-review-01.json
   ```
5. **交付与交接。** 报告写 `deliverables/report-v1.md`，修订写 v2；done 时 `--report` 引用检查报告（PARTIAL/FAIL 也可交付，如实写明）。

## 按需读

| 什么时候 | 读哪里 |
|---|---|
| 第一次做研究任务，或要写 research.json | [研究流程](references/research.md) |
| 公司研究 / 财报分析 / 同业比较 | [公司](references/finance-company.md) · [财报](references/finance-earnings.md) · [同业](references/finance-peers.md) |
| 涉及增速、比率、单位与口径 | [指标与计算](references/finance-methods.md) |
| 红线、交接规则 | task-harness 的 references/red-lines.md、references/operations.md |

检查器只核对追溯、可重算性和已记录的验收项，不证明披露真实、结论正确或投资有利。不对读者下买卖指令；没有价格或股本就不算估值，没有事前一致预期就不说"超预期"。
