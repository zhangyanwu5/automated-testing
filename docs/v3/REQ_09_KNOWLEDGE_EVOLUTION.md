# REQ_09_KNOWLEDGE_EVOLUTION：自我进化

## 目标

OpenGuard 必须通过可验证经验沉淀，让项目越用越聪明，而不是依赖工具内部隐藏推理。知识库包含两大类：**测试执行经验**（由执行报告驱动沉淀）和**项目接口知识**（由代码扫描驱动建立）。

## 进化闭环

```text
代码扫描 → 接口知识建立 → 前置路径生成 → 执行验证 → 知识晋升 → 下次直接复用
Review 发现 + 执行证据 → Agent 归因 → overlay 合并 → 多轮验证 → 知识晋升 → 下一轮复用
```

## 知识分层

```text
openguard/knowledge/
  # 项目画像与运行环境
  project_profile.yaml     # 项目结构、宿主形态、技术栈、运行方式
  control_channels.yaml    # RPC、bridge、输入通道、入口点（含运行时验证状态）

  # 游戏接口知识（由 knowledge-scan 建立，绑定代码锚点）
  event_catalog.yaml       # 所有可观察的事件名、参数、触发条件
  protocol_catalog.yaml    # 网络协议/RPC 接口定义
  state_schema.yaml        # 核心状态对象（Player/Map/Quest 等）字段和类型
  log_patterns.yaml        # 关键日志模式、关键字和含义

  # 前置路径（由首次验证建立，跨 change 复用）
  preconditions.yaml       # 已验证的前置准备路径，按状态标签索引

  # 测试执行经验
  test_patterns.yaml       # 已验证测试模式
  assertion_hints.yaml     # 常用断言与状态检查
  failure_taxonomy.yaml    # 失败类型与归因规则
  flaky_rules.yaml         # flaky 用例与处理策略
  review_rules.yaml        # 已验证代码 Review 规则与风险模式
  baselines_index.yaml     # 截图/状态/性能基线索引
```

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-09-01 | 成功执行报告可沉淀稳定路径、稳定前置和有效断言。 |
| REQ-09-02 | Review 报告可沉淀高风险代码模式、有效检查项和常见修复建议。 |
| REQ-09-03 | 失败报告可沉淀失败模式、归因规则和补证据建议。 |
| REQ-09-04 | 冒烟、增量、完整测试结果可沉淀测试策略选择经验。 |
| REQ-09-05 | 多次重跑结果可沉淀 flaky 规则、等待策略和容差策略。 |
| REQ-09-06 | 需求和代码变更历史可沉淀高风险模块、接口和测试影响规律。 |
| REQ-09-07 | 单次模型输出不得直接晋升为长期知识。 |
| REQ-09-08 | `openguard init` 生成的项目测试画像可作为 `project_profile.yaml` 的初始来源，但只有经过执行或人工确认的运行、控制和断言经验才能晋升为长期知识。 |
| REQ-09-09 | 测试脚本必须经过至少一次真实执行验证后，才能晋升到 `openguard/test_assets/`；单次模型生成的草稿不得直接晋升。 |
| REQ-09-10 | 晋升到 `test_assets/` 的脚本必须持续跟踪锚点有效性；绑定符号哈希变化时降为 `needs-review`，符号消失或需求变更时降为 `stale`，断裂无法映射时降为 `broken`。 |
| REQ-09-11 | 脚本出现 flaky 时不得晋升；已晋升脚本出现 flaky 时降为 `needs-review` 并进入 flaky 治理流程，不得直接当 PASS。 |
| REQ-09-12 | 脚本状态降级不得影响正在运行的 change；降级结果应在下一次 `continue` / `apply` 前的新鲜度校验中体现。 |
| REQ-09-13 | 历史执行记录（`suite_index.yaml` / `change_run_index.yaml`）可被知识进化消费，用于 flaky 统计、稳定路径识别、测试策略选择经验沉淀和脚本晋升依据。 |
| REQ-09-14 | `knowledge-scan` 提取的游戏接口知识必须绑定代码锚点，代码变更时降级触发规则见 `REQ_04_SCAN_AND_IMPACT.md`（REQ-04-11）。 |
| REQ-09-15 | 知识条目状态降级后，Agent 可通过分析 `delta.json` 判断变更是"纯重构（接口不变）"还是"行为变更"；若是纯重构，可生成 overlay 更新锚点哈希待确认；若是行为变更，生成"需要重新验证"的提示。 |
| REQ-09-16 | 前置路径（`preconditions.yaml`）必须经过至少一次真实执行验证后才能沉淀；沉淀后按"所需状态标签"（如 `logged_in`、`map_a`、`level_10`）索引，供后续 change 直接查找复用。 |
| REQ-09-17 | `openguard new` 时必须查询 `preconditions.yaml`，为当前 change 的前置需求匹配已有路径；无匹配时写入 `unknowns.md`，并提示需要补充或建立新的前置路径。 |

## 知识条目要求

每条知识必须包含：来源、证据、置信度、适用范围、状态（`inferred` / `verified` / `needs-review` / `stale` / `broken`）、过期条件、创建时间、最后验证时间。

接口知识条目还必须包含：代码锚点（文件路径 + 符号名 + 哈希）、锚点最后检查时间。

## 防错要求

- 路径不存在、接口消失、需求指纹变化时，相关知识必须降权或过期。
- 支持人工驳回、降权和冻结知识项。
- 低置信度知识只能作为建议，不得自动阻断或放行。
- `inferred`（仅代码分析）状态的接口知识不得用于生成执行测试，只能用于生成候选矩阵和建议。

## 验收标准

- 后续 change 能复用历史前置路径，不重复询问已知前置步骤。
- 知识库能解释"为什么选择这些测试/Review 规则/前置路径"。
- 代码变更后，受影响的接口知识条目自动降级，不会静默污染新的测试计划。
- 知识失效时不会污染新的测试计划。
