# 指标、口径与可溯源计算

原始金额注明币种及倍数单位，例如 `CNY million`；同一计算内 unit、entity、basis 必须一致。除增速/差值外，两个输入还须属于同一 period。单位换算、汇率转换、财年匹配、并表调整由 Agent 先核实并记录，计算器不自动猜测。

| operation | 输入顺序 | 公式 | 结果单位 |
|---|---|---|---|
| growth_pct | 本期、前期 | (本期 / 前期 − 1) × 100 | % |
| change | 本期、前期 | 本期 − 前期 | 输入单位 |
| ratio | 分子、分母 | 分子 / 分母 | multiple |
| percentage | 分子、分母 | 分子 / 分母 × 100 | % |

输入用十进制字符串，避免在入库前被二进制浮点舍入；运算使用 Decimal、28 位精度。输入缺失写 null，返回 MISSING。NaN/Infinity、未知 ID、重复 ID、单位/主体/会计口径不一致被拒绝。分母或增长基期非正时返回 NOT_MEANINGFUL，不能把扭亏用普通同比百分比表达。

适用例子：收入/净利润同比、净利润率、经营现金流/净利润、有息负债减现金。比率不替用户解释会计含义：经营现金流与净利润的差异需要看营运资本、税项和非现金项目；利润改善不必然代表现金改善。财务报表分别反映时点或期间数据，不能无说明地混用。[SEC 财务报表入门](https://www.sec.gov/investor/pubs/begfinstmtguide.htm)

```json
{
  "schema_version": 1,
  "metrics": [
    {"id":"rev-current","value":"125","entity":"Example Co","period":"FY2025","unit":"CNY million","basis":"consolidated; restated series","source_id":"S1"},
    {"id":"rev-previous","value":"100","entity":"Example Co","period":"FY2024","unit":"CNY million","basis":"consolidated; restated series","source_id":"S1"}
  ],
  "calculations": [
    {"id":"revenue-growth","operation":"growth_pct","inputs":["rev-current","rev-previous"],"comparability":"两期均为全年、同币种和单位，已核对重述口径；合成示例。"}
  ]
}
```

结果会得到 25%，同时保存公式和两条完整输入。comparability 是执行者的说明，脚本不会自动证明其真实性或验证两个任意 period 标签恰好构成同比；周期长度、并购影响和政策变更仍需审阅。

多家公司分别计算各自指标，再做对照表；不要将不同主体直接塞进同一增速计算。股价/每股收益等量纲不同的估值模型、DCF、组合归因没有包含在这个简明计算器中；任务需要时用已验证的工具或显式保存独立模型和输入，不为了套脚本篡改单位。
