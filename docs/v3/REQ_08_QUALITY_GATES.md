# REQ_08_QUALITY_GATES：质量门禁

## 目标

OpenQA 必须针对不同阶段提供默认质量门禁策略，决定当前 change 是否允许继续推进。

## 门禁定义

门禁是“继续下一步前必须通过的质量检查”。同样执行 `openqa apply`，不同门禁会选择不同扫描范围、测试套件、Review 严格度和阻断规则。

## 默认策略

| 门禁 | 默认策略 | 目的 |
| --- | --- | --- |
| `local` | `scan_scope=incremental` + `test_suite=smoke` + `review_level=changed` | 快速发现明显问题。 |
| `ci` | `scan_scope=auto` + `test_suite=incremental` + `review_level=risk-based` | 验证 PR 或日常变更，控制成本。 |
| `requirement` | `test_suite=requirement-full` + `review_level=risk-based` | 确保单个需求验收闭环。 |
| `release` | `scan_scope=full` + `test_suite=regression/full` + `review_level=risk-based` | 发布前质量确认。 |
| `nightly` | `scan_scope=full` + `test_suite=full` | 发现慢问题、长稳问题、基线漂移。 |

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-08-01 | 系统必须支持按 `gate` 自动选择默认策略。 |
| REQ-08-02 | 门禁必须定义阻断条件，包括 blocking Review、冒烟失败、验收失败、证据缺失、敏感信息泄漏。 |
| REQ-08-03 | 门禁必须支持人工豁免，但豁免必须记录原因、人员、时间和范围。 |
| REQ-08-04 | 门禁必须输出 `gate_report.yaml`，说明通过、失败、跳过和豁免项。 |
| REQ-08-05 | 发布和夜间门禁必须优先正确性，不得为了成本跳过高风险项。 |
| REQ-08-06 | 门禁决策可基于 `suite_index.yaml` 中的历史执行记录，例如"连续 N 次通过才标记稳定"或"最近 N 次中出现 M 次失败则阻断"；具体阈值在 `config.yaml` 中配置。 |


## 验收标准

- 不同门禁下策略选择可解释、可追踪。
- 阻断与豁免均写入报告。
- 门禁失败时，Agent 和用户能从报告、时间线和证据索引中知道下一步应该修代码、补测试、补证据还是人工确认。
