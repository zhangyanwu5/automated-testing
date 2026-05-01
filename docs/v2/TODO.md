# ATF 详细实现 Todo（v2）

本文档将 [ROADMAP.md](./ROADMAP.md) 中的里程碑 **M0–M14** 拆解为可勾选、可排期的实现任务；**产品语义**以 [ATF_PIPELINE_AND_SCAN_SPEC.md](./ATF_PIPELINE_AND_SCAN_SPEC.md)（《流水线规格》）、[AI_AUTOMATED_TESTING_SYSTEM.md](./AI_AUTOMATED_TESTING_SYSTEM.md)（《体系说明》）为准；**逻辑边界**对齐 [TECHNICAL_OVERVIEW.md](./TECHNICAL_OVERVIEW.md)（《技术总览》）。

**用法建议：** 将下列 `- [ ]` 项迁入 issue / 看板时，保留里程碑标签（如 `M3`）便于过滤；完成一项即勾选，并在 PR 中引用对应小节编号。

---

## 0. 跨里程碑全局清单

在任意里程碑并行推进时仍应持续满足：

- [x] **G1** 测试计划 / 任务 JSON 中 [ROADMAP §2](./ROADMAP.md#2-测试类型全量矩阵) 所列全部 `type_id` 均有条目；未实现为 `skipped` + `reason`（《流水线规格》5.2）。实现：`ALL_MATRIX_TYPE_IDS`、`validate_test_matrix_document`、`schemas/test_matrix.v1.json`；单测 `tests/test_matrix/test_m4_validate.py`、`test_g_global_invariants.py`。
- [x] **G2** 报告 schema 自始区分 **runtime / precondition / acceptance**（或等价分栏），与《体系说明》2.3、《流水线规格》5.3、6 一致。实现：`schemas/run_report.v1.json`、`build_run_report` / `validate_run_report_document`、`RUN_REPORT_CHANGELOG`；单测 `tests/test_matrix/test_m7_full_run.py`。
- [x] **G3** 宿主与控制面：原生引擎路径不默认假设 DOM；Web/WebGL 在矩阵或配置中显式声明后再使用浏览器侧能力（《体系说明》2.4）。实现：`runtime/host_capabilities.py`（默认 `matrix/fill_from_scan` 写入 `native_engine_host` + `browser_side_capabilities: not_declared`）、`browser_side_capabilities_declared` / `assert_browser_side_capabilities_declared`；单测 `test_g_global_invariants.py`。
- [x] **G4** 密钥与模型配置经环境或密钥管理注入，**不**写入 `.atf/` 下索引 JSON（《技术总览》§7）。实现：`index_secret_guard.reject_sensitive_keys_in_index`，在 `validate_index_dict` 与 `python -m core.test_matrix fill` 路径执行；单测 `tests/atf_scan_index/test_g4_index_secrets.py`。
- [x] **G5** 写被测产品源码或自动应用补丁仅在**显式策略**下启用；默认 dry-run 或仅建议（《流水线规格》5.5、《技术总览》§7）。实现：`analysis/product_write_policy.py`（`assert_may_apply_product_writes`）、`FullRunConfig.product_write_policy` 与报告 `execution_flags`（默认 `forbid`）、CLI `--product-write-policy`；单测 `test_g_global_invariants.py`、`test_m7_full_run.py`。
- [x] **G6** `schema_version` / `rule_version` 变更策略有文档与单测，避免静默破坏历史对比（含回归基线等消费方）。实现：`matrix/schema_policy.py`（矩阵）、`migrate.INDEX_FORMAT_CHANGELOG` / `RULE_VERSION_BUMP_POLICY`（索引）；单测 `test_g_global_invariants.py`。

---

## M0 — `.atf/` 与索引 Schema

**目标：** 《流水线规格》§3.4–3.6；《Roadmap》M0。

- [x] **M0.1** 文档化 `.atf/` 下建议子结构（`scan_index`、可选 `artifacts/`、`reports/`），并说明与 `.gitignore` 的推荐策略（[ROADMAP §6](./ROADMAP.md#6-风险与缓解)）。
- [x] **M0.2** 定义并实现 `scan_index`（或等价名）JSON schema：`version`、`rule_version`、`files[]`（至少含 `path`、内容哈希、`size`、可选 `last_analyzed_at` 等）。
- [x] **M0.3** 可选 `prd` 段：`path`、内容哈希（为 M2 预留字段或占位）。
- [x] **M0.4** 版本迁移策略：索引 `version` 升级时的读取/重写/全量失效规则（单测覆盖）。
- [x] **M0.5** 验收：**不启动被测应用**即可用单元测试校验 schema 与迁移（对齐 Roadmap M0 验收）。

> **M0 实现位置（本仓库）：** JSON Schema `schemas/scan_index.v1.json`；Python 包 `src/core/atf_scan_index/`（`pytest`：`tests/atf_scan_index/`）；目录约定文档 `docs/v2/ATF_DIRECTORY.md`。

---

## M1 — 增量扫描器

**目标：** 《流水线规格》3.1；依赖 M0。

- [x] **M1.1** 配置项：扫描根（C# / Lua 或多语言）、包含/排除 glob、并发或批大小（可选）。
- [x] **M1.2** 首次 / 强制全量：遍历 → 逐文件哈希 → 调用分析器 → 写索引。
- [x] **M1.3** 增量：读旧索引 → diff 路径与哈希 → 仅对变更/新增/删除文件调用分析 → 合并回索引。
- [x] **M1.4** `rule_version`（或分析器版本）变化时：失效范围、部分重扫或全量重扫策略 + 测试。
- [x] **M1.5** 验收 fixture：修改单文件后二次扫描，分析调用量或耗时相对全量显著下降（Roadmap M1）。

> **M1 实现位置（本仓库）：** `ScanConfig` 与 `run_scan` 见 `src/core/atf_scan_index/scan_config.py`、`scanner.py`；导出 `core.atf_scan_index`；单测 `tests/atf_scan_index/test_m1_scanner.py`。`rule_version` 变更策略：**对磁盘仍存在路径全量重跑分析器**（仍逐文件重算哈希）；`force_full` 在不改 `rule_version` 时也可强制全量重分析。

---

## M2 — 需求 Markdown Freshness

**目标：** 《流水线规格》第 4 节；依赖 M0、M1。

- [x] **M2.1** 将需求路径 + 内容哈希写入索引或独立指纹文件（与代码侧对称策略）。
- [x] **M2.2** API / 函数语义：「项目 + 需求是否仍最新」的判定入口，供门禁复用。
- [x] **M2.3** 边界：仅改需求不改代码时门禁行为；仅改未纳入扫描范围的文件的边界行为（与设计说明一致并文档化）。
- [x] **M2.4** 单测覆盖上述边界。

> **M2 实现位置（本仓库）：** `fingerprint_prd` / `resolve_safe_project_file`（`src/core/atf_scan_index/prd_fingerprint.py`）；`check_freshness` / `FreshnessResult` / `refresh_prd_fingerprint` / `merge_prd_into_index`（`freshness.py`）；`run_scan(..., prd_rel_path=...)` 写入 `prd`；单测 `tests/atf_scan_index/test_m2_freshness.py`；规格边界 §4.1 见 `docs/v2/ATF_PIPELINE_AND_SCAN_SPEC.md`。

---

## M3 — 扫描入口与门禁 API

**目标：** 《流水线规格》第 2 节「仅扫描」；依赖 M1、M2。

- [x] **M3.1** 可被 CI 与「一体化执行」复用的扫描 API（语言层模块，不绑定具体 CLI 名）。
- [x] **M3.2** 对外入口：CLI 子命令或等价（实现自定），行为符合「仅扫描」。
- [x] **M3.3** `--help` / dry-run（或等价）行为有自动化测试。
- [x] **M3.4** 与 M2 门禁组合：执行流调用前可单独跑「扫描 + freshness」自检。

> **M3 实现位置（本仓库）：** `run_scan(..., dry_run=...)`（`scanner.py`）；`run_scan_only` / `run_scan_then_check_freshness` / `ScanWithFreshnessResult`（`scan_api.py`）；``python -m core.atf_scan_index`` / 控制台入口 ``atf-scan``（`cli.py`、`__main__.py`）；单测 `tests/atf_scan_index/test_m3_scan_api.py`、`test_m3_cli.py`。

---

## M4 — 测试矩阵 JSON v1（全类型占位）

**目标：** 《流水线规格》5.2；依赖 M2；可不依赖真实游戏。

- [x] **M4.1** 定义 `test_matrix.v1.json`（名称可配置）schema：`schema_version`、`types[]`。
- [x] **M4.2** `types[]` 覆盖 Roadmap §2.1、§2.2 全部 `type_id`；每项含 `status`、`reason`、`depends_on`（可空）、`artifacts_ref`（可空）。
- [x] **M4.3** 为 **runtime / preconditions** 预留顶层或每类型字段（键存在，可为空对象）。
- [x] **M4.4** CI 或本地校验脚本：生成 JSON 缺任一枚举 `type_id` 即失败。
- [x] **M4.5** 样例 fixture：全 `skipped` + 合法 `reason` 的 golden 文件。

> **M4 实现位置（本仓库）：** JSON Schema `schemas/test_matrix.v1.json`；`src/core/test_matrix/matrix/`（`constants`、`validate`：`ALL_MATRIX_TYPE_IDS`、`validate_test_matrix_document` / `load_and_validate_test_matrix`）；``python -m core.test_matrix`` / ``atf-validate-test-matrix``；golden `tests/fixtures/test_matrix_all_skipped.v1.json`；单测 `tests/test_matrix/test_m4_validate.py`。

---

## M5 — 扫描 + 需求 → 填充生成物

**目标：** Roadmap M5；依赖 M4、分析管线（与 M1 衔接）。

- [x] **M5.1** 映射层：管线输出 → 各 `type_id` 的摘要、推荐用例引用等字段契约。
- [x] **M5.2** 无法生成某类型内容时写入明确 `reason`，**不**静默省略类型条目。
- [x] **M5.3** AI 为可选加速路径；**无外部模型 / stub 模型**下仍产出合法、枚举完整的 JSON（Roadmap 验收）。
- [x] **M5.4** 与 M2 需求指纹输入衔接（生成物可引用需求版本）。
- [ ] **M5.5** **AKP JSON Schema 与校验**：对齐 [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md) 的字段与 `schema_version`；落盘默认路径与命名约定对齐 [ATF_DIRECTORY.md](./ATF_DIRECTORY.md)；单测覆盖合法 / 非法样例。
- [ ] **M5.6** **管线集成**：在 L0 门禁通过后，可选子命令或 `full_run` 阶段调用 Agent / 模型网关生成或增量更新 AKP；`fill` / 矩阵映射可读入最新 `automation_knowledge*.json`（路径由配置或 CLI 指定）；AKP 缺失或失败时的 **阻断 / 降级** 策略可配置并写入报告 `execution_flags` 或等价字段。
- [ ] **M5.7** **Agent 可观测与确定性**（对照 [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md) §2.4）：生成流程记录 `prompt_bundle_id`（或等价：模板版本、检索策略、是否 CoT）；对 `(scan_index 内容哈希, prd 哈希, prompt_bundle_id)` 支持**幂等覆盖写**或**版本并存**（可配置）；调用可配置**全局超时、单轮 token 上限、重试**，失败进入报告**可解析字段**（非仅 stderr）。
- [ ] **M5.8** **AKP 契约扩展**（对照同文档 §2.3、§3.1–3.2）：Schema / 校验覆盖 `assumptions[]`；建议类字段带 `confidence`（或 `high|medium|low`）及可选 `confidence_policy`；大文件分包时主文件 `includes[]` 相对路径引用与兼容策略；`test_blueprint.matrix_overlay` 对 `test_matrix.v1` 的增量建议须**可校验、可拒绝合并**（单测含接受/拒绝路径）。
- [ ] **M5.9** **AKP 安全与人机门禁**（对照 §2.5–2.6）：落盘前对 AKP JSON 走与 G4 **同源**的敏感键拒绝（密钥不进 AKP 持久化字段）；日志/截图路径/账号样例等**脱敏或占位**策略（可配置钩子）；`requires_human_ack` 与编排器：无人值守执行前检查 ack 文件或等价闸门（与 `product_write_policy` 文档交叉引用）。
- [ ] **M5.10** **AKP 消费方与闭环**（对照 §3.3、§2.1 P3）：报告 `execution_flags` 或顶层扩展写入本次依据的 **AKP `schema_version` 与路径或内容哈希**；矩阵/宿主侧从 `execution_hints`、`test_blueprint` 映射 `recommended_case_refs` / `-executeMethod` 草案（与现有 Unity CLI 字段策略对齐）；卡点分析（M13）**可选**并入 AKP 的 `unknowns` / `risks_and_gaps` 以提升归因；P3：`last_run_feedback`（或等价）在执行失败后回写 AKP 或 sidecar 并文档化策略。

> **M5 实现位置（本仓库）：** `src/core/test_matrix/matrix/pipeline_mapping.py`（摘要与每类型 `runtime` 契约键）、`matrix/fill_from_scan.py`（`build_test_matrix_from_scan_index`）；CLI ``python -m core.test_matrix fill --scan-index … --out …``；单测 `tests/test_matrix/test_m5_fill_from_scan.py`。**M5.5–M5.10** 为 L1 / AKP 待实现项（总契约见 [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md)）。

---

## M6 — DAG 调度与并行

**目标：** 《流水线规格》5.4；依赖 M5。

- [x] **M6.1** 从 JSON 读取 `depends_on`，构建有向图；环检测与清晰错误信息。
- [x] **M6.2** 拓扑分层；同层并行（进程或异步），可配置并发上限。
- [x] **M6.3** 为各 `type_id` 定义执行适配接口（每类型一执行器或统一 runner 分支均可）。
- [x] **M6.4** fixture：验证顺序、最大并行度、成环配置失败报告。

> **M6 实现位置（本仓库）：** `src/core/test_matrix/execution/dag.py`（`validate_matrix_dag` / `topological_layers` / `MatrixDagError`）、`execution/scheduler.py`（`MatrixTypeExecutor` / `run_matrix_scheduled`）；单测 `tests/test_matrix/test_m6_dag.py`、`test_m6_scheduler.py`。

---

## M6R — 运行时编排（工具链 / 应用 / 前置）

**目标：** 《体系说明》2.3、《流水线规格》5.3；依赖 M6。

- [x] **M6R.1** 抽象四段：`toolchain_launch` → `app_launch` → `world_preconditions` → `readiness_gate`（命名对齐 [ROADMAP §2.4](./ROADMAP.md#24-运行时能力与类型矩阵正交)）。
- [x] **M6R.2** 前置清单 schema：超时、重试、结构化错误码；失败可映射到「脚本 / 环境 / 产品」分桶（初版可粗粒度）。
- [x] **M6R.3** 与 M6 集成：默认编排链为根节点或整图唯一前驱链。
- [x] **M6R.4** mock/stub：无真实服务器时跑通链路与报告字段。
- [x] **M6R.5** 真实项目 smoke：至少「工具链 + 应用 + 一条简单前置（如进入主界面）」。
- [x] **M6R.6** 阅读并对照 [Playwright原理与Web游戏自动化对照.md](../Playwright原理与Web游戏自动化对照.md)：进程外编排 + 双向通道；原生宿主不默认 DOM 定位。

> **实现位置：** ``schemas/preconditions.v1.json``；``src/core/test_matrix/runtime/runtime_orchestration.py``、``runtime/preconditions_validate.py``、``execution/integrated_run.py``；单测 ``tests/test_matrix/test_m6r_runtime.py``；示例烟测 ``examples/aoe3d/smoke_atf_pipeline.py``（默认 stub）。

---

## M7 — 一体化执行与报告骨架

**目标：** 《流水线规格》5.1–5.5、第 6 节；依赖 M3、M6R。

- [x] **M7.1** 「执行自动化测试」主路径：项目根 + 需求路径 → 门禁扫描 → 生成 JSON → M6R → DAG 执行。
- [x] **M7.2** 落盘 `.atf/reports/run_<id>.json`（及可选 Markdown）；含 runtime / precondition / acceptance 分段。
- [x] **M7.3** 各 `type_id` 状态、耗时、证据路径占位；卡点占位（深内容由 M13 增强）。
- [x] **M7.4** dry-run 或 mock 执行器端到端跑通；报告能区分前置失败与验收失败。
- [x] **M7.5** 与《流水线规格》阶段顺序自检清单（团队内可用 checklist 勾一遍）。

> **实现位置：** ``schemas/run_report.v1.json``；``src/core/test_matrix/full_run.py``、``reporting/run_report.py``；CLI ``python -m core.test_matrix run ...`` / ``atf-run``；单测 ``tests/test_matrix/test_m7_full_run.py``。

---

## M8 — 计划 → 可执行用例与执行器集成

**目标：** 《体系说明》Phase 1；依赖 M7。

- [x] **M8.1** 将矩阵中 `executable` 项转为用例中间表示或最终格式（ID、步骤、期望摘要）。
- [x] **M8.2** 显式 **preconditions / environment** 并与 M6R 对接。
- [x] **M8.3** 报告字段稳定化（版本化与变更说明）。
- [x] **M8.4** 至少 `functional` 与 `e2e` 或 `ui_automation` 在 mock 或真实环境跑通；样例含一条依赖前置的用例。

> **实现位置：** ``src/core/test_matrix/execution/executable_plan.py``、``execution/stub_executors.py``；``reporting/run_report.RUN_REPORT_SCHEMA_VERSION`` / ``RUN_REPORT_CHANGELOG``；单测 ``tests/test_matrix/test_m8_executable.py``。

---

## M9 — 需求追溯与覆盖报告

**目标：** 《体系说明》Phase 1 扩展；依赖 M8。

- [x] **M9.1** 数据模型：`requirement_id → test_point_id → test_case_id → run_result`。
- [x] **M9.2** 需求 Markdown 解析规则（可先约定标题/列表格式）与版本说明。
- [x] **M9.3** 报告区块：覆盖数、未覆盖列表、每条需求最近一次结果。
- [x] **M9.4** 样例需求文档 + golden 报告片段测试。

---

## M10 — 语义判定 Oracle

**目标：** 《体系说明》3.3、Phase 2；依赖 M8。

- [x] **M10.1** 判定插件契约：输入（意图、步骤、画面、日志、状态、期望摘要）；输出 PASS / FAIL / UNKNOWN、理由、置信度、疑似问题、建议补充证据。
- [x] **M10.2** 步骤级可挂载；UNKNOWN 不得当 PASS（策略与单测）。
- [x] **M10.3** mock 判定器 + 契约测试；输出字段与《体系说明》一致。
- [x] **M10.4** 认知网关（可选）：配额、超时、审计、stub（与《技术总览》「Cognitive Gateway」对齐）。

---

## M11 — 视觉判定（两阶段）

**目标：** Roadmap M11、《体系说明》3.3；依赖 M10、执行侧画面采集。

- [x] **M11.1** 阶段 1（规则）：元素存在/可见/越界、黑屏、弹窗状态等；**像素/区域 diff + 容差/掩膜**（帧缓冲或截图管线由宿主提供）。
- [x] **M11.2** 阶段 2（可选）：多模态语义插件；与 M10 共用证据管道与报告；特性开关默认关。
- [x] **M11.3** 阶段 1 离线单测；阶段 2 可关闭时行为明确。

---

## M12 — 回归基线、Diff、趋势

**目标：** 《体系说明》Phase 3；依赖 M9、稳定报告 schema。

- [x] **M12.1** `.atf/baselines/`（或等价）：状态快照、日志摘要、Approved 参考帧与像素指纹、历史 run 索引。
- [x] **M12.2** 报告：新增失败、与历史同类失败、影响面（初版可简化字段）。
- [x] **M12.3** 截图基线策略文档：入库范围、人工审批门槛（项目约定模板）。
- [x] **M12.4** 验收：两次运行间人为注入 diff 可被检出。

> **实现位置：** `src/core/test_matrix/analysis/regression_baseline.py`；报告顶层 `regression`；`full_run.FullRunConfig.enable_regression_baseline`；`docs/v2/BASELINE_STRATEGY.md`、`docs/v2/ATF_DIRECTORY.md`；单测 `tests/test_matrix/test_m12_regression.py`。

---

## M13 — 卡点 AI、归因、脚本优先修复

**目标：** 《流水线规格》5.5；依赖 M7+；可与 M10 共用模型网关。

- [x] **M13.1** 硬 / 软 / 质量卡点分类写入报告。
- [x] **M13.2** 归因：脚本 / 环境 / 产品标签 + 置信度（规则 + 可选 LLM）。
- [x] **M13.3** 脚本类：补丁建议生成；**可选**自动应用（仅限测试资产等策略）→ 受影响子图重跑。
- [x] **M13.4** 产品类：缺陷记录 + 证据链；禁止改断言假通过。
- [x] **M13.5** 黄金样例：错误测试资产 vs 错误产品行为，归因方向符合预期（stub 可起步）。

> **实现位置：** `src/core/test_matrix/reporting/stall_analysis.py`；报告 `stall_analysis` / `stall_placeholder`；`full_run.FullRunConfig.enable_stall_analysis`；单测 `tests/test_matrix/test_m13_stall.py`。

---

## M14 — 产品侧自动修复原型

**目标：** 《体系说明》3.4、Phase 4；依赖 M12、M13、M10。

- [x] **M14.1** 失败证据聚合 → 相关源码定位 → Patch 草案（默认 dry-run 或人审）。
- [x] **M14.2** 目标用例重跑 + 相关回归子集调度。
- [x] **M14.3** 审计日志与路径越权防护；显式策略开启才允许写产品工程。
- [x] **M14.4** 验收：默认不静默写盘；策略开启时行为有单测或集成测。

> **实现位置：** `src/core/test_matrix/analysis/product_fix_loop.py`；报告 `product_fix`；`full_run.FullRunConfig.enable_product_fix_prototype`；审计 `.atf/baselines/product_fix_audit.jsonl`；单测 `tests/test_matrix/test_m14_product_fix.py`。

---

## 附录 A — 体系阶段与 Todo 范围对照

| 《体系说明》阶段 | 主要 Todo 章节 |
| --- | --- |
| Phase 1 可执行闭环 | M4–M9（核心 M7–M8） |
| Phase 2 体验与智能判定 | M10–M11 |
| Phase 3 回归运营 | M12 |
| Phase 4 闭环加深 | M13–M14 |

**规格闭环 Beta（对外表述）** 对应完成度：**M0–M6R–M7** 及全局清单 G1–G4。

---

## 附录 B — 逻辑部件与首个落地映射（提醒）

实现时可按 [TECHNICAL_OVERVIEW.md](./TECHNICAL_OVERVIEW.md) §3 自检是否遗漏：**Entry、Scan & Index、Freshness Gate、（可选）AKP / AI 语义层、Artifact Generator、Runtime Orchestrator、Scheduler、Execution Adapters、Evidence Collector、Oracles、Reporter、Stall Analyzer（可选）、Cognitive Gateway（可选）**。编排与扩展点可采用过程式流水线或字典分发，并随实现种类增多向注册机制演进（《技术总览》§2、§6）。

---

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-04-30 | 初版：从 Roadmap M0–M14 拆解可勾选任务，附全局清单与附录。**M0 已勾选完成**：实现见 `src/core/atf_scan_index/`、`schemas/scan_index.v1.json`、`docs/v2/ATF_DIRECTORY.md`、`tests/atf_scan_index/`。 |
| 2026-04-30 | **M1 已勾选完成**：增量扫描 `run_scan` / `ScanConfig`、单测含 M1.5 与 `rule_version` 变更全量重分析。 |
| 2026-04-30 | **M2 已勾选完成**：需求指纹、`check_freshness` / `refresh_prd_fingerprint`、`run_scan(prd_rel_path=...)`、§4.1 边界与 `test_m2_freshness.py`。 |
| 2026-04-30 | **M3、M4 已勾选完成**：`scan_api` + `dry_run` + ``python -m core.atf_scan_index``；`core.test_matrix` 校验与 golden；`test_m3_*`、`test_m4_validate.py`。 |
| 2026-04-30 | **M5、M6 已勾选完成**：`build_test_matrix_from_scan_index`、`pipeline_mapping`、`dag`/`scheduler` 与 `test_m5_*`、`test_m6_*`。 |
| 2026-04-30 | **M6R、M7、M8 已勾选完成**：`runtime_orchestration`、`integrated_run`、`full_run`、`run_report`、`executable_plan`、`stub_executors`、schema `preconditions.v1`/`run_report.v1`；单测 `test_m6r_*`、`test_m7_*`、`test_m8_*`；示例 `examples/aoe3d/smoke_atf_pipeline.py`。 |
| 2026-04-30 | **M9、M10、M11 已勾选完成**：`prd_parse`、`traceability`、`oracle`、`cognitive_gateway`、`visual_oracle`；矩阵 `runtime.requirement_ids` / `test_point_ids`；报告 `acceptance.traceability`；单测 `test_m9_*`、`test_m10_*`、`test_m11_*`；样例 PRD `tests/fixtures/prd_trace_sample.md`。 |
| 2026-04-30 | **M12、M13、M14 已勾选完成**：`regression_baseline`、`stall_analysis`、`product_fix_loop`；报告段 `regression` / `stall_analysis` / `product_fix`；`schemas/run_report.v1.json` 与 `RUN_REPORT_CHANGELOG` v1.2；`BASELINE_STRATEGY.md`；单测 `test_m12_*`、`test_m13_*`、`test_m14_*`。 |
| 2026-04-30 | 附录 B 表述与《技术总览》§2、§6 对齐（编排与扩展点的演进式实现，不再写「首版允许代替插件系统」）。 |
| 2026-04-30 | 各节「实现位置」路径与 `core.test_matrix` 子包布局对齐（`matrix` / `runtime` / `execution` / `reporting` / `analysis`）；G3/G5/G6 行内文件路径同步。 |
| 2026-04-30 | M0 目标节号对齐《流水线规格》§3.4–3.6；新增 **M5.5–M5.6**（AKP schema 与管线集成）待办；附录 B 增加可选 AKP 层。 |
| 2026-04-30 | 对照《自动化知识包与 AI 语义层》全文查漏补缺：新增 **M5.7–M5.10**（Agent 确定性、AKP 扩展字段与 matrix_overlay、安全/脱敏/`requires_human_ack`、报告与宿主消费及 `last_run_feedback` 闭环）。 |
