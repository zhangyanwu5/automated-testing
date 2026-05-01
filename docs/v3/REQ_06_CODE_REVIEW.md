# REQ_06_CODE_REVIEW：代码 Review

## 目标

OpenQA 必须对受影响代码做结构化 Review，输出标准化 findings 与可读摘要，并将 Review 结果纳入测试影响面和质量门禁。

## Review 策略

| `review_level` | 范围 |
| --- | --- |
| `off` | 不执行 Review。 |
| `changed` | 仅 Review 变更文件/片段。 |
| `risk-based` | 基于影响图、历史风险、需求重要性选择范围。 |
| `full` | 对目标范围内代码做完整 Review。 |

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-06-01 | `continue` 必须能生成 `review_plan.md`，描述 Review 范围、检查项和阻断策略。 |
| REQ-06-02 | `apply` 必须生成 `review_findings.sarif.json` 与 `review_report.md`。 |
| REQ-06-03 | Review 必须检查需求一致性、影响面、边界条件、异常处理、并发/性能、安全、可测试性和可维护性。 |
| REQ-06-04 | Review finding 必须包含严重级别、代码位置、证据、风险说明和建议。 |
| REQ-06-05 | blocking finding 默认阻止进入验收执行，除非有显式豁免。 |
| REQ-06-06 | Review 结果必须反向影响测试矩阵，用于新增、重跑或跳过测试。 |
| REQ-06-07 | Review 报告不得直接修改产品代码，只能生成建议和 overlay。 |

## 格式要求

| 产物 | 格式 | 原因 |
| --- | --- | --- |
| `review_plan.md` | Markdown + YAML Front Matter | Agent 易读易改，结构字段可解析。 |
| `review_findings.sarif.json` | SARIF JSON | 标准代码扫描格式，支持 IDE/CI 展示。 |
| `review_report.md` | Markdown | 给人和 Agent 阅读的摘要、风险和建议。 |
| `report_overlay.yaml` | YAML overlay | 写回确认后的归因、豁免或修正建议。 |

## SARIF finding 要求

每个 finding 必须包含：规则 ID、严重级别、文件路径、行号/符号、消息、证据、建议、关联 EARS 需求 ID、是否 blocking。

## 验收标准

- Review finding 能定位到具体代码区域。
- Review 报告可独立阅读，SARIF 可被工具消费。
- Review 经验可沉淀到 `knowledge/review_rules.yaml`。
