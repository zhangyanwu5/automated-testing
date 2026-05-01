# REQ_05_TEST_STRATEGY_AND_MATRIX：测试策略与矩阵

## 目标

OpenQA 必须覆盖从快速冒烟到发布全量的测试策略，并通过可执行测试矩阵表达任务。需求验收项优先使用 EARS；矩阵使用 JSON，保证执行器稳定消费。

## 测试套件

| 套件 | 场景 | 覆盖范围 |
| --- | --- | --- |
| `smoke` | 本地快速验证、需求初步可用性检查 | 环境启动、核心 happy path、关键断言、最小数据准备。 |
| `incremental` | PR、日常变更 | 受 `delta.json`、`impact_graph.json`、Review 风险和历史失败影响的子图。 |
| `requirement-full` | 单需求验收或归档 | 需求全部 EARS 验收项、边界、异常、必要回归和兼容性。 |
| `regression` | 合并前、版本分支、重点模块变更 | 高价值历史用例、历史缺陷、核心业务链路。 |
| `full` | 发布、夜间构建、大版本重构 | 全部可执行矩阵、基线、兼容性、长稳、性能门禁。 |

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-05-01 | `test_suite` 必须支持 `smoke`、`incremental`、`requirement-full`、`regression`、`full`。 |
| REQ-05-02 | 测试矩阵必须由 `requirements.md`、`test_knowledge.md`、`impact_graph.json`、`openqa/config.yaml`、历史知识和策略共同生成。 |

| REQ-05-03 | 矩阵必须支持任务依赖 DAG、优先级、超时、重试、并发和失败快停。 |
| REQ-05-04 | 无法执行的测试项必须显式标记 `skipped` 和原因，不得静默省略。 |
| REQ-05-05 | 单需求完整测试必须覆盖全部 EARS 验收项；无法覆盖项必须进入 `unknowns.md` 或人工豁免。 |
| REQ-05-06 | 增量测试必须说明选择依据：代码 delta、影响图、Review 风险、历史失败或 flaky 规则。 |
| REQ-05-07 | 冒烟测试失败时，默认阻止进入更大规模测试。 |
| REQ-05-08 | 矩阵生成必须结合 `project.type`、`runtime`、配置来源和置信度选择测试形态、前置条件、证据类型和执行器 hints。 |
| REQ-05-09 | 当真实执行所需配置缺失或低置信度时，矩阵必须把相关任务标记为 `blocked`、`skipped` 或 `needs-confirmation`，并说明缺失配置或不确定证据。 |
| REQ-05-10 | 对自动决策出的执行模式，矩阵必须记录选择依据；当存在多个合理执行模式时，应优先使用推荐模式生成矩阵，并把替代模式列为候选或 unknowns。 |
| REQ-05-11 | 矩阵生成时必须优先引用 `test_assets/` 中状态为 `verified` 的稳定脚本；`needs-review` 脚本可引用但须标注；`stale` 和 `broken` 脚本不得引用，只能生成新草稿。 |
| REQ-05-12 | 矩阵中每个引用稳定脚本的任务必须记录脚本路径、锚点状态和锚点哈希快照，保证执行报告可追溯到具体脚本版本。 |
| REQ-05-13 | 矩阵任务必须显式声明所需前置状态标签（如 `[logged_in, map_a, level_gte_10]`），并引用 `preconditions.yaml` 中对应的已验证前置路径；无匹配前置路径时任务标记为 `blocked` 并写入 unknowns。 |
| REQ-05-14 | 矩阵生成时必须查询 `openqa/knowledge/` 中的接口知识（事件、RPC、命令、状态字段），用于推断断言方式、前置设置方法和证据采集策略；接口知识为 `inferred` 状态时只能生成候选，不得直接用于执行矩阵。 |



## 格式要求

| 产物 | 格式 | 原因 |
| --- | --- | --- |
| `requirements.md` | Markdown + EARS | 人和 Agent 易读，验收句受控。 |
| `test_knowledge.md` | Markdown 表格 | 适合 Agent 补充断言、前置、风险和 unknowns。 |
| `test_matrix.json` | JSON | 执行器稳定消费，便于 schema 校验。 |
| `run_report.junit.xml` | JUnit XML | CI 系统通用消费。 |

## 测试类型

矩阵应支持：单元、集成、契约、功能、业务流程、回归、状态校验、端到端、UI 自动化、玩家路径、探索式、体验、兼容性、长稳、性能和基线检查。

## 项目类型映射

| 项目类型 | 默认矩阵关注点 |
| --- | --- |
| `web` / `h5` | 页面路由、组件状态、表单、接口 mock、浏览器兼容、console / network 证据。 |
| `web-game` / `webgl` | 浏览器外壳、加载完成、引擎桥接、玩家路径、帧率 / 资源 / 状态基线。 |
| `unity` | scene 启动、PlayMode / EditMode、输入管线、引擎状态、日志、崩溃和性能基线。 |
| `unreal` | map / level、Automation Spec、console command、客户端/服务器组合、日志、crash dump 和性能统计。 |
| `backend` / `api` | 服务健康检查、契约、接口链路、测试数据、依赖服务和错误分支。 |
| `mixed` | 子项目矩阵组合、跨项目依赖、端到端链路和影响子图裁剪。 |

## 验收标准

- 同一策略和输入生成的矩阵稳定可复现。
- 同一需求在不同 `project.type` 下生成的矩阵能体现宿主、运行方式和证据类型差异。
- 每个测试项可追溯到 EARS 需求、代码影响或历史风险。
- 执行报告能反向标注矩阵项的结果、证据和归因。
