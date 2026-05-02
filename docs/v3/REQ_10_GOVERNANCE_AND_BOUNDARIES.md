# REQ_10_GOVERNANCE_AND_BOUNDARIES：治理与边界

## 目标

OpenGuard 必须明确安全、权限、隐私、模型边界和外部系统协作方式，避免自动化测试产品失控。

## 设计边界

| 边界 | 要求 |
| --- | --- |
| 模型调用 | OpenGuard 工具进程不直接调用大模型，推理由 Agent 宿主负责。 |
| 产品代码修改 | 默认不修改产品代码，只生成 Review 报告、测试报告和建议。 |
| 测试脚本位置 | 测试脚本只存放于 `openguard/` 目录内，不写入目标项目的源码目录。 |

| 侵入策略 | 默认 `external-only`；`build-time-bridge` 或 `runtime-patch` 必须显式授权并记录。 |
| 人工决策 | Review 报告不替代人工或 Agent 决策，只提供证据、风险和建议。 |
| 最终产物 | 自然语言不能作为唯一最终产物，必须有可校验文件。 |
| UNKNOWN | UNKNOWN 不得当 PASS，必须补证据或人工确认。 |
| 密钥隐私 | 产物和知识库不得保存密钥、账号口令、隐私数据。 |


## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-10-01 | 写产品代码必须显式授权，并记录授权策略和写入范围。 |
| REQ-10-02 | `openguard init` 写入 `openguard/config.yaml` 时不得保存密钥、账号口令、个人隐私数据或一次性 token；需要凭证的配置只能保存环境变量名、凭证别名或待补充占位符。 |

| REQ-10-03 | `build-time-bridge` 注入必须限制在 debug build；`runtime-patch` 必须有可验证的还原步骤，还原失败时必须阻断后续流程。 |
| REQ-10-04 | 日志增强建议只能作为 Agent 输出建议，不得自动修改目标项目代码；开发者采纳后重跑属于正常开发流程。 |
| REQ-10-05 | 所有 overlay 合并必须保留 generator、generated_at、source_change、source_report 和 confidence。 |
| REQ-10-06 | 敏感信息扫描失败时，必须拒绝写入报告、overlay 或知识库。 |
| REQ-10-07 | 操作日志、时间线和证据索引必须经过敏感信息过滤，不得记录密钥、口令和隐私数据。 |
| REQ-10-08 | 低置信度建议只能进入待确认区，不得自动影响执行或归档。 |
| REQ-10-09 | 所有 schema 版本变化必须有兼容策略或迁移报告。 |
| REQ-10-10 | 与 OpenSpec 联动时，只读取 proposal、specs、tasks 作为需求输入，不修改 OpenSpec 产物，除非显式授权。 |
| REQ-10-11 | 人工豁免必须记录原因、范围、时间和责任人，并出现在门禁报告和时间线中。 |
| REQ-10-12 | 测试脚本晋升必须经过真实执行验证；脚本锚点状态为 `broken` 或 `stale` 时不得参与任何真实执行，相关决策必须有记录。 |
| REQ-10-13 | OpenGuard 内部工具调用（文件读写、哈希计算、可执行文件搜索、运行时探测等）必须对调用方屏蔽平台差异（Windows / macOS / Linux），不得要求各命令模块自行处理平台兼容问题。 |
| REQ-10-14 | 内部工具调用发生错误时，必须以结构化错误结果返回给调用方，不得向上层抛出未捕获异常；错误信息必须可读，便于报告和日志记录。 |
| REQ-10-15 | 耗时较长的工具操作（如目录搜索、可执行文件探测）必须支持超时配置，超时后中止并返回错误结果，不得无限阻塞命令执行。 |


## OpenSpec 联动边界

详细联动流程见 `REQ_12_OPENSPEC_INTEGRATION.md`。治理侧只约束边界：OpenGuard 默认只读 OpenSpec 的 proposal、specs、design、tasks；只有用户显式授权时，才允许写回 OpenSpec 产物或触发 archive。

## 验收标准

- 安全和隐私规则在 `apply`、报告生成、overlay 合并、知识晋升时均生效。
- 所有自动化建议可追溯来源。
- OpenGuard 能独立使用，也能安全读取 OpenSpec 需求输入。
