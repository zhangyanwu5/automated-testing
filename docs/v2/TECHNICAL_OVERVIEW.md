# ATF 技术总览（从零视角）

本文说明**逻辑部件、数据流、扩展边界**（可写细、可写全）。**工程上**以可维护、可演进为目标：规格与契约可写全写细；实现按边界分层、控制依赖与测试覆盖，避免与问题规模脱节的过度设计，也避免在稳定边界上长期缺乏抽象而导致难以替换或并行演进。产品语义与阶段以 [AI_AUTOMATED_TESTING_SYSTEM.md](./AI_AUTOMATED_TESTING_SYSTEM.md)、[ATF_PIPELINE_AND_SCAN_SPEC.md](./ATF_PIPELINE_AND_SCAN_SPEC.md) 为准；交付顺序以 [ROADMAP.md](./ROADMAP.md) 为准。

---

## 1. 文档角色

| 文档 | 技术总览中的位置 |
| --- | --- |
| 体系说明 | **为何**测、双视角、能力分层、原则 |
| 流水线规格 | **何时写盘、何种门禁、何种阶段契约** |
| Roadmap | **按何顺序交付** |
| 本文 | **由哪些逻辑块组成、块之间如何传数据** |

---

## 2. 工程原则（合理性）

下列原则用于在**规格已定义**的前提下，约束实现如何分层、何时收紧边界，使仓库结构与技术债可控；与文档篇幅、规格粗细 **无**「写少才算对」的关系。

| 原则 | 说明 |
| --- | --- |
| **分层与依赖方向** | 按数据流划清：扫描与索引 → 新鲜度门禁 → 生成物（矩阵等 JSON）→ 运行时编排 → 调度与执行 → 报告与可选卡点分析。模块依赖宜**单向**（上游产物驱动下游），避免核心路径上出现难测的环依赖。 |
| **抽象与问题规模匹配** | 「逻辑部件」表是**能力边界**；在**多实现、多宿主或跨团队契约**处（分析器、执行适配器、Oracle、对外 API）应有清晰接口或注册点，便于替换与测试替身。单一路径、变更稀少的内部逻辑允许集中实现，以降低误用面与跳转成本。 |
| **编排可观测** | 流水线须能在日志与报告中还原阶段顺序与失败落点；实现形态可为显式函数链、状态机或 DAG 驱动，以**可读、可调试、与《流水线规格》阶段一致**为准。 |
| **依赖与栈选型** | 第三方库按能力缺口引入；涉及安全、序列化、进程与网络控制时，优先成熟、可审计、团队可运维的方案，而非默认「最少行数」。 |
| **契约优先** | `.atf/` 写盘规则、freshness、报告 runtime/precondition/acceptance 分栏、测试矩阵全类型占位等，实现与 schema 一致；`schema_version` / 迁移策略见 Roadmap 与矩阵/索引变更说明，避免静默破坏历史对比。 |

**本仓库 Python 布局（与上表对应）：** `core.atf_scan_index` 承担扫描、索引校验与 freshness API；`core.test_matrix` 在包根保留 **一体化入口**（`full_run.py`、`cli.py`、`__main__.py`），其余按子包划分——`matrix`（矩阵 JSON、校验、从索引填充）、`runtime`（M6R 编排与前置）、`execution`（DAG、调度、可执行计划、占位执行器）、`reporting`（运行报告、PRD、追溯、卡点分析）、`analysis`（Oracle、视觉规则、回归基线、产品修复与写盘策略）。对外仍优先 `from core.test_matrix import …`（根 `__init__.py` 聚合导出），子包路径供深入阅读与定向 `import`。

下文各表仍是**能力分解**。

---

## 3. 逻辑部件（概念）

以下为**能力边界**命名，实现时可映射为进程、库或服务。

| 部件 | 职责 |
| --- | --- |
| **入口（Entry）** | CLI / CI 任务 / API：解析参数、加载项目级配置、选择模式（仅扫描 / 完整执行）。 |
| **扫描与索引（Scan & Index）** | 遍历配置范围内的源码；计算哈希；调用语言分析器；读写 `.atf/` 下索引与 `artifacts/`。 |
| **新鲜度门禁（Freshness Gate）** | 比较索引、规则版本与需求文档指纹；决定是否需要增量扫描或阻断执行。 |
| **语义认知生成器（AKP / AI 层，可选）** | 在 L0 索引与 PRD 已门禁通过的前提下，由 Agent 生成 **自动化知识包**（JSON，落盘 `artifacts/`）；为矩阵、宿主执行与报告提供**可版本化**的认知输入；契约见 [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md)。 |
| **生成器（Artifact Generator）** | 输入：最新索引 + 需求（**可选**再并入 AKP）；输出：带 schema 版本的 JSON（测试矩阵、计划摘要、前置声明等），满足「全类型占位」契约。 |
| **运行时编排器（Runtime Orchestrator）** | 工具链就绪 → 被测应用就绪 → 控制通道建立 → 前置条件谓词满足；超时、重试、结构化错误码。 |
| **调度器（Scheduler）** | 读取任务依赖（DAG）；分层并行或串行；将节点分派给对应执行适配器。 |
| **执行适配器（Execution Adapters）** | 按 `type_id` 或宿主类型执行：单元/集成运行器、引擎内测试、E2E 驱动、长稳任务等；**一个宿主一类适配契约**，禁止混用 DOM 假设于原生宿主。 |
| **观测与证据（Evidence Collector）** | 统一采集日志路径、截图、状态快照、RPC 回包摘要等；写入报告可引用字段。 |
| **判定（Oracles）** | 断言、规则检查、崩溃/日志判定、像素 diff、可选语义判定；输出须可序列化进报告。 |
| **报告器（Reporter）** | 聚合各阶段与任务结果；区分前置 / 验收失败；归因分桶；落盘 `.atf/reports/`。 |
| **卡点分析（Stall Analyzer，可选 AI）** | 消费报告与证据；输出脚本/环境/产品标签与修复建议；**不**改写产品断言语义。 |
| **外部认知网关（Cognitive Gateway，可选）** | 隔离对大模型或视觉服务的调用；统一配额、超时、审计与 stub 策略。 |

---

## 4. 数据流（一次完整执行）

```text
Entry
  → Freshness Gate ──否──→ Scan & Index ──┐
  → Freshness Gate ──是──────────────────┘
  →（可选）AKP / AI 语义层 → 落盘 .atf/artifacts/automation_knowledge*.json
  → Artifact Generator（JSON）
  → Runtime Orchestrator（《流水线规格》5.3 四段）
  → Scheduler（DAG）→ Execution Adapters（多节点）
        ↘ Evidence Collector / Oracles 贯穿
  → Reporter
  → Stall Analyzer（可选）
```

与《流水线规格》阶段一一对应；调度器仅在编排器报告「可进入验收」后对验收类任务放闸（或按契约将部分任务仅依赖「应用已启动」等细粒度门）。

---

## 5. 控制面与宿主适配

- **编排进程**与**被测应用**宜分离；之间通过 **长连接或等价双向通道**（如 WebSocket、命名管道、引擎插件暴露的 RPC）传递命令与事件。  
- **宿主适配层**封装：如何启动、如何注入输入、如何读取 UI 树或游戏状态、如何抓帧。Web、WebGL、原生 Player 使用不同适配，共享上层「步骤 / 前置 / 证据」语义。  
- 与 [Playwright原理与Web游戏自动化对照.md](../Playwright原理与Web游戏自动化对照.md) 对齐：**不**默认全局 OS 键鼠为唯一路径；原生优先引擎内输入管线。

---

## 6. 扩展点（实现时遵守的接口思想）

1. **分析器插件**：按语言或框架注册；输出合并进索引；`rule_version` 变更触发失效。  
2. **执行适配器注册表**：`type_id` + 宿主 → 适配器；未实现返回 skipped + reason，由生成器或调度前置写死。  
3. **Oracle 链**：步骤级可挂载多个判定器；语义类 Oracle 须支持 UNKNOWN 与置信度。  
4. **报告 schema 版本化**：字段演进通过 `schema_version` 迁移，避免静默破坏历史对比（Roadmap M12）。  

「扩展点」是**行为契约**；具体实现可为显式分支、字典分发或注册表，随分析器/适配器/Oracle 实现数量增加，再统一为注册与发现机制，使新增种类不修改核心编排的中央开关文件。

---

## 7. 配置与安全（最小集）

- **项目根路径、扫描根、需求路径、引擎路径、并发上限、超时**等应由项目级配置提供，**不**硬编码在工具仓库内。  
- 任何「写被测产品源码」或「自动应用补丁」须在**显式策略**下开启；默认 dry-run 或仅生成建议。  
- 密钥与模型 API **不**写入索引 JSON；经环境变量或密钥管理注入认知网关。

---

## 8. 相关文档

- [AI_AUTOMATED_TESTING_SYSTEM.md](./AI_AUTOMATED_TESTING_SYSTEM.md)  
- [ATF_PIPELINE_AND_SCAN_SPEC.md](./ATF_PIPELINE_AND_SCAN_SPEC.md)  
- [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md)  
- [ROADMAP.md](./ROADMAP.md)  
- [Playwright原理与Web游戏自动化对照.md](../Playwright原理与Web游戏自动化对照.md)  

---

## 9. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-04-30 | 初版：逻辑部件、数据流、§6 扩展点。**§2** 定名为「工程原则（合理性）」：分层与依赖方向、抽象与问题规模匹配、编排可观测、依赖与栈选型、契约优先；物理映射可为少数包或多包以边界清晰为准。**§6** 扩展点与显式分发→注册机制的演进表述对齐。 |
| 2026-04-30 | §2 增补「本仓库 Python 布局」：`core.test_matrix` 拆为 `matrix` / `runtime` / `execution` / `reporting` / `analysis` 子包，根级保留 `full_run` 与 `cli`。 |
| 2026-04-30 | §3 逻辑部件表与 §4 数据流：增加可选 AKP / AI 语义层；§8 增加 AKP 文链接。 |
