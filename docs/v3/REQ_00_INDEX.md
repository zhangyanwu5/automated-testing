# REQ_00_INDEX：OpenGuard 需求文档索引

本文档汇总 OpenGuard v3 的需求拆分，来源于 `PRODUCT.md`。

| 文档 | 主题 | 说明 |
| --- | --- | --- |
| `REQ_01_COMMANDS_AND_INIT.md` | 指令与初始化 | 用户指令（`init/run/apply/archive/update`）与内部命令（`_advance`）分层设计、AI 驱动循环协议、`/opg:*` Slash Commands、初始化体验、执行过程可见性、调试命令。 |
| `REQ_02_WORKSPACE_AND_ARTIFACTS.md` | 工作区与产物 | `openguard/` 完整目录结构（唯一权威定义）、产物格式选择原则、AI 宿主隐藏目录、`config.yaml` 画像示例。 |
| `REQ_03_CHANGE_STATE_MACHINE.md` | Change 状态机 | change 生命周期状态流（preparing → ready_for_apply → running → done）、`state.yaml` 结构与 `agent_action` 协议、AI 驱动循环推进规则。 |
| `REQ_04_SCAN_AND_IMPACT.md` | 扫描与影响分析 | 全量扫描、增量扫描、knowledge-scan（唯一权威定义）、新鲜度校验、影响图、锚点规则。 |
| `REQ_05_TEST_STRATEGY_AND_MATRIX.md` | 测试策略与矩阵 | 冒烟、增量、单需求完整、回归、全量测试，稳定脚本优先引用。 |
| `REQ_06_CODE_REVIEW.md` | 代码 Review | Review 计划、Review 报告、阻断规则。 |
| `REQ_07_EXECUTION_AND_REPORTING.md` | 执行与报告 | 执行编排、证据采集、脚本状态校验、操作日志与过程记录、suite 执行报告契约。 |
| `REQ_08_QUALITY_GATES.md` | 质量门禁 | 本地、CI、需求验收、发布、夜间构建策略（唯一权威定义）。 |
| `REQ_09_KNOWLEDGE_EVOLUTION.md` | 自我进化 | 知识库、经验沉淀、脚本晋升/降级/过期。 |
| `REQ_10_GOVERNANCE_AND_BOUNDARIES.md` | 治理与边界 | 安全、权限、隐私、侵入策略、脚本晋升边界、工具层稳定性约束（平台无关、超时、不抛异常）。 |
| `REQ_12_OPENSPEC_INTEGRATION.md` | OpenSpec 联动 | OpenSpec change 与 OpenGuard change 的联动工作流和产物关系。 |
| `REQ_13_TEST_ASSET_LIFECYCLE.md` | 测试资产生命周期 | 脚本生成位置、侵入策略、日志采集、锚点绑定、过期状态机、晋升/降级、全局 suite 执行。 |
| `REQ_14_AGENT_SKILLS.md` | Agent Skills | Skill 安装方式、驱动循环协议、四个核心 Skill 的 AI 宿主行为协议（run/apply/archive/continue-恢复）。 |
| `REQ_15_PRECONDITIONS_AND_SETUP_PATHS.md` | 前置路径 | 前置路径定义、白盒/黑盒模式、目录结构、生命周期和跨 change 复用规则。 |
| `REQ_16_RUNTIME_LAUNCHER.md` | 运行时启动与就绪管理 | 各 `project.type` 对应的自主启动协议（Unity Editor、Playwright、WebGL 等）、就绪信号判定规则、场景/URL 自动选择策略、启动超时与进程清理规范。 |



## 设计约束

- **用户指令少且稳定**：用户只需记 `init`、`run`、`apply`、`archive`，内部机制（`_advance`、扫描、矩阵生成）对用户透明。
- **AI 与 CLI 分工明确**：确定性操作（扫描、影响分析、矩阵生成、状态更新）由 CLI 工具完成；需要理解/推理的操作（需求分析、测试知识生成、Review 计划、unknowns 解答）由 AI 完成。
- **通信协议基于文件**：AI 与 CLI 通过 `state.yaml`（机器可读指令）+ stdout hint（人类可读说明）+ Skill 文件（行为规范）三层协作，不在工具进程内调用大模型。
- **所有确定性结果必须落盘为可校验文件**。
- **所有 Agent 推理结果必须通过 overlay 或报告形式进入系统**。
- **所有长期知识必须有来源、置信度、适用范围和过期条件**。

