# 验证底座 v0.1

实例只放个人材料和任务。公共流程、脚本不复制进实例。`ROOT` 是某一个任务目录，例如 `/work/projects/api-check`；下面所有证据、输入和输出路径均相对该目录，命令的执行位置不影响解释。

## 开工与交接

从任务 README 找当前问题、基线、最近结果、下一步和阻塞解除条件。填 `spec.json`：问题与截止日、纳入/排除范围、总体与分母依据、环境、采样、停止条件、可复跑命令。命令从任务目录执行；注明需要的依赖和环境变量名称，不填凭证值。

- `closed`：有明确有限全集；`bounded`：只针对指定日期、权限或目录；`open`：总体未知，不能声称总体召回率或全集覆盖率。
- 正式观察前定清单用 `prospective`。已看过本轮结果才补建的清单用 `retrospective`，不能换个时间戳冒充事前验证。
- `revision.reason` 写首版理由或变更理由。首版 `previous_baseline=null`；后续指向前版基线。`revision.event` 可省略，如填写则指向任务内已有文件。
- `expected` 与 `baseline` 是 `inputs/` 直属文件。基线名称用 `YYYY-MM-DD-baseline-v1.json`，下一版换 v2。

预期 CSV 必填五列：`id,requirement,description,basis,acceptance`。ID 稳定唯一，依据和通过条件不能空。三类 requirement：`required` 本轮承诺；`investigate` 尚待查明但必须保留；`not_applicable` 在本轮边界不适用且有依据。模板故意只有表头，防止把通用示例误当作用户需求。

```sh
python3 PACKAGE/scripts/contract.py freeze --root ROOT
```

冻结保存清单、spec、时间和 hash，不执行 `run_command`。按用户已授权范围执行任务脚本，保存脱敏证据。普通读操作可继续；写操作或重试遵循已有授权与 API 幂等语义，不因本模板增加审批流程，也不扩张授权。

## 观测格式

`outputs/run-01-observations.json` 示例（hash 和时间由本轮实际值替换）：

```json
{
  "baseline_sha256": "冻结命令返回的 sha256",
  "observed_at": "2026-10-25T10:00:00+00:00",
  "rows": [{
    "id": "response-schema",
    "status": "PASS",
    "evidence_level": "实际响应与字段核验",
    "detail": "该样本中的 id 和 value 字段满足合同；未验证其他数据段。",
    "evidence": ["outputs/run-01-response.json"]
  }]
}
```

状态：`PASS / FAIL / PARTIAL / SKIP / NOT_RUN`。每条写 detail、evidence_level、evidence；仅 NOT_RUN 可无证据。外部 URL 先保存本地来源摘录或脱敏响应，再引用路径。路径不能越出任务目录，也不能引用 `.env*`、`.git` 等排除目录。不要为生成一个 PASS 而写占位证据；脚本只能检查存在性和 hash，不能证明证据内容支持断言。

```sh
python3 PACKAGE/scripts/contract.py compare --root ROOT --observations outputs/run-01-observations.json --out outputs/run-01-comparison.json
python3 PACKAGE/scripts/contract.py replay --root ROOT --report outputs/run-01-comparison.json
```

退出码：0 本清单 PASS；1 已生成/复核对账但为 FAIL 或 PARTIAL；2 输入、基线、路径或证据错误。`check --root ROOT` 只验证冻结合同完整性。`replay` 重算当前基线的报告，并核对证据 hash；它发现更改时拒绝，不修改历史报告。改版后重放旧基线需另建隔离目录，从旧基线恢复当时 spec、清单和证据。

总评规则：required 有 FAIL 或出现重复观测 ID → FAIL；required 非 PASS、investigate 非 PASS、计划外 ID、不适用项被执行 → PARTIAL；否则 PASS。不适用项省略或 SKIP，单列且不进入 required 分母。重复尝试分别存文件，按预先声明规则汇总，不能静默去重。

达停止条件后保存未完成 ID 与原因。更换范围、环境或判据需改 spec、新基线及前版引用；同一合同下重试用新 observations/comparison。观测时间与“事前/事后”由执行者如实填写，本地 hash 不构成可信第三方预注册。

## 收尾

交付结论、证据层级、适用边界、未解决 ID；再更新 README 的最近结果与下一步。来源记入 `sources.md`，按追加方式记录 `events.md`。不要为了全绿删除失败或降低验收条件。需要跨任务复用的材料先写入个人资产索引；当前只有一次发现的经验留在任务内。
