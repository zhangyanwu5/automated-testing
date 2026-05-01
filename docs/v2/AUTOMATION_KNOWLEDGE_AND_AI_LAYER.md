# 自动化知识包（AKP）与 AI 语义层 — 规格说明（v2）

本文档把两件事**写进可工程化契约**：

1. **第二条（AI / Agent）**：在「全项目路径 + 策划案（Markdown）」之上，如何用 Agent / 大模型**系统性地抽取**后续自动化所需认知，而不是把「扫描」误解为仅文件哈希。  
2. **第三条（产物形态）**：这些认知以何种**结构化、版本化、可校验**的形式落盘，并被**整跑、宿主执行器、脚本生成**消费，以支撑**全自动化**终态。

**与下列文档的关系：**

- [ATF_PIPELINE_AND_SCAN_SPEC.md](./ATF_PIPELINE_AND_SCAN_SPEC.md)：流水线阶段、门禁、`.atf/` 落盘；本文在 **阶段 2（生成）** 与 **artifacts** 语义上对其细化。  
- [TECHNICAL_OVERVIEW.md](./TECHNICAL_OVERVIEW.md)：逻辑部件与数据流；本文将 **「语义认知生成」** 明确定位为 **扫描与索引之后、可选、可替换** 的一层。  
- [AI_AUTOMATED_TESTING_SYSTEM.md](./AI_AUTOMATED_TESTING_SYSTEM.md)：双视角与能力分层；本文描述 **如何把体系说明里的「理解需求与实现」落到机器可读 JSON**。  
- [ATF_DIRECTORY.md](./ATF_DIRECTORY.md)：`.atf/artifacts/` 下建议文件名与 Git 策略。

**实现状态：** 本文档为**规格与工程指导**；具体 CLI / 服务名、调用哪个模型 API 可在实现阶段命名，**须遵守**《技术总览》§7（密钥不进索引 JSON）、G4 敏感键策略与《流水线规格》契约。

---

## 1. 问题陈述：两种「扫描」不要混为一谈

| 层次 | 回答的问题 | 典型产物 | 是否依赖 AI |
| --- | --- | --- | --- |
| **L0 文件级扫描与索引** | 哪些路径在范围内、内容变没变、规则版本是否一致、策划案指纹是否最新 | `scan_index.json`、freshness 门禁 | **否**（可选语言分析器插件仍属确定性规则范畴） |
| **L1 语义认知与自动化知识** | 需求如何拆成可验点、与代码/Lua 表层的候选关联、用例与断言线索、环境与风险 | **自动化知识包 AKP**（本文 §4） | **是（Agent + 可选检索）** |

**产品目标对齐：** 团队期望的「扫描是为了后面自动化省事」，在工程上应表述为：**L0 提供事实锚与变更感知；L1 在 L0 + PRD 之上生成「自动化所需认知包」**。全自动化 = L0 →（可选 L1）→ 矩阵/计划 → 编排执行 → 判定与报告，且 L1 可迭代增强。

---

## 2. 第二条如何工程化：AI / Agent 层的设计原则

下列原则用于把「让模型读整个项目」从口号变成**可上线、可审计、可回滚**的流水线能力。

### 2.1 分阶段交付（避免一口吃掉全仓）

| 阶段 | 目标 | 说明 |
| --- | --- | --- |
| **P0** | 最小可用 | 仅输入：`scan_index` 路径摘要 + PRD 全文（或分块）→ 输出 **AKP v0** 骨架字段 + `unknowns[]` 显式列出不确定项 |
| **P1** | 检索增强 | 以 `scan_index.files[]` 为**候选路径集合**，按扩展名/目录规则分批读入上下文；禁止模型**编造**不在索引中的路径 |
| **P2** | 深度分析 | 对命中文件做 AST / 正则 / 项目自定义提取器（可非 AI），Agent 只负责**综合与写 AKP** |
| **P3** | 闭环验证 | AKP 中每条「可执行假设」尽量链接到 **已有测试入口** 或 **`-executeMethod` 草案`**；执行失败回写 `last_run_feedback`（见 §4.3） |

### 2.2 输入契约（Agent 的「地面真相」）

- **项目根**：与 `scan_index` 解析规则一致；所有路径**必须**能解析为项目根下的相对路径，禁止 `..` 逃逸。  
- **策划案**：参与门禁的 Markdown 路径与指纹以 `scan_index.prd` / freshness 为准；Agent 使用的正文版本**应与门禁一致**（先门禁再 L1，或显式版本号）。  
- **`scan_index.json`**：提供**文件集合与哈希**；Agent **不得**声称某文件存在若不在索引中（除非标注为「建议新增」类提案并单独分桶）。

### 2.3 输出契约（必须可机器消费）

- 单一根对象，含 **`schema_version`**（整数，从 1 递增）与 **`generator`**（工具名 + 版本 + 可选模型标识）。  
- 所有「建议」类字段须带 **`confidence`** 或等价枚举（`high|medium|low`），低置信度**不得**静默当作执行依据。  
- 提供 **`unknowns[]`** / **`assumptions[]`**：模型不确定处必须显式列出，供人或规则补全。

### 2.4 确定性与可复现（CI 友好）

- 记录 **`prompt_bundle_id`** 或等价：模板版本、检索策略版本、是否启用思维链等。  
- 对同一 `(scan_index 内容哈希, prd 哈希, prompt_bundle_id)` 的生成物，应能 **幂等覆盖写** 或 **版本并存**（由项目策略选择）；禁止无版本号的「静默覆盖」导致无法 diff。  
- **成本与超时**：Agent 调用须可配置全局超时、单轮 token 上限、重试策略；失败须进入报告可解析字段，而非仅 stderr 文本。

### 2.5 安全与合规

- **密钥**：仅环境变量或密钥管理系统；**不**写入 `scan_index.json`、**不**写入 AKP 的持久化字段（与 G4 一致）。  
- **脱敏**：日志、截图路径、账号样例等进入 AKP 前须过项目策略（可占位符化）。  
- **写回产品树**：任何由 AKP 触发的代码/脚本生成，须遵守 **product_write_policy**（《流水线规格》5.5），默认 forbid / dry_run。

### 2.6 人机回环（全自动化前的缓冲）

- **默认建议**：CI 中 AKP 生成 → **schema 校验通过**即可落盘；**是否**自动触发生成脚本 / 自动改产品，由策略开关控制。  
- **高敏变更**（如支付、反作弊）：AKP 中标记 `requires_human_ack`，编排器可拒绝无人值守执行直至 ack 文件存在。

---

## 3. 第三条：自动化知识包（AKP）— 建议结构

**落盘位置（默认约定）：** 被测项目 `.atf/artifacts/` 下，文件名建议：

- `automation_knowledge.v{schema_version}.json` — 主包（单文件优先，便于传递）  
- 若体积过大，可拆分为 `akp_prd_digest.json`、`akp_code_surface.json` 等，**主文件须含 `includes[]` 引用相对路径**，并在 `schema_version` 上保持兼容策略。

### 3.1 顶层字段（最小集）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | AKP 自身版本 |
| `generator` | string | 生成器标识（含模型/Agent 框架版本） |
| `generated_at` | string | ISO8601 UTC |
| `inputs` | object | `project_root`、`prd_path`、`scan_index_path` 或内容哈希摘要 |
| `prd_understanding` | object | 策划结构化：功能点、验收点、术语、与测试类型的建议映射 |
| `code_surface` | object | 系统表层：模块、事件/消息、协议/API 候选、配置与 Lua/C# 锚点路径 |
| `test_blueprint` | object | 用例草案、前置条件、数据、期望、断言线索、推荐 `type_id` |
| `execution_hints` | object | 宿主侧：建议 `-executeMethod`、环境变量、日志关键字、超时建议 |
| `evidence_plan` | object | 跑测时应采集的日志/截图/状态路径模式 |
| `risks_and_gaps` | array | 风险、缺口、需人工补全项 |
| `unknowns` | array | 模型明确不确定的命题 |
| `confidence_policy` | object | 可选：何种置信度以下禁止自动执行 |

### 3.2 `test_blueprint` 建议子结构（与矩阵 `type_id` 对齐）

- `cases[]`：每项含 `case_id`、`title`、`requirement_refs[]`、`recommended_type_id`、`steps[]`、`preconditions`、`assertion_hints[]`、`data_requests[]`。  
- `matrix_overlay`（可选）：对现有 `test_matrix.v1.json` 的**增量建议**（仅填需要 override 的字段），须可校验、可拒绝合并。

### 3.3 消费方（全自动化链条中的读者）

| 消费者 | 用法 |
| --- | --- |
| **矩阵填充 / 二次 fill** | 将 AKP 中 `recommended_case_refs` 或 `cases[]` 映射进 `types[].runtime.recommended_case_refs`（策略可控） |
| **Unity / `-executeMethod`** | 读取 `execution_hints` 与 `test_blueprint` 选择入口场景与断言 |
| **报告器** | 将 AKP 版本写入 `execution_flags` 或报告扩展字段，便于追溯「本次跑测依据哪版认知」 |
| **卡点分析** | 对照 `unknowns` / `risks_and_gaps` 提升归因准确率 |

### 3.4 与流水线阶段的挂钩（对齐《流水线规格》§5）

建议在**阶段 2 — 生成各类型测试所需内容**中，将 AKP 视为**可选子阶段**：

```text
扫描门禁通过
  →（可选）L1：生成 / 更新 automation_knowledge.*.json（AKP）
  → 生成 / 更新 test_matrix 与其它 JSON（可读取 AKP）
  → 运行时编排 …
```

**硬约束：** AKP **不能**替代 freshness；AKP 生成失败时，须有明确策略（阻断 / 降级为无 AKP 的 stub 填充 / 仅警告），并在实现文档中写死。

---

## 4. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-04-30 | 初版：区分 L0/L1；AKP 字段与工程化原则；与流水线阶段挂钩。 |
