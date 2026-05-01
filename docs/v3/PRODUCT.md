# OpenQA 产品说明

> **一句话定位：** OpenQA 是面向 AI 编码宿主的自动化测试与代码质量产品。它像 OpenSpec 管理规格变更一样，用轻量指令和文件化产物管理「需求/代码变更 → 测试理解 → 代码 Review → 测试执行 → 报告归因 → 经验沉淀」的闭环。

OpenQA 不在工具进程内调用大模型；Claude Code、CodeBuddy、Cursor 等 Agent 宿主负责推理，OpenQA 负责确定性的 CLI、协议、目录、校验、执行编排和证据落盘。

---

## 1. 产品目标

OpenQA 解决四个问题：

1. **指令少而稳定**：用户只记少数高层指令，底层扫描、规划、代码 Review、矩阵、执行、报告由状态机推进。
2. **功能可验证**：测试结果与代码 Review 结果都落盘为带版本报告，可校验、可回溯、可复现。
3. **迭代可持续**：需求更新、代码修改、测试失败、Review 发现都进入同一个 change 闭环，增量更新而非推倒重来。
4. **越用越聪明**：把稳定的项目知识、Review 规则、断言经验、失败归因和 flaky 规则沉淀为可复用知识。

---

## 2. 指令层：少数高层指令

OpenQA 参考 OpenSpec 的轻量方式，用户只需记 3 个日常指令：`run`（开始任务）、`apply`（执行测试）、`archive`（归档）。AI 驱动循环在后台自主完成所有准备工作，用户只在需要决策时被打断。

### 2.1 用户指令

| 指令 | 定位 | 说明 |
| --- | --- | --- |
| `openqa init` | 初始化 | 在当前项目创建 `openqa/`，生成项目测试画像、配置，向用户选定的 AI 宿主安装 Slash Commands 和 Agent Skills。**只做一次。** |
| `openqa update` | 更新工具指令 | 刷新 `/oqa:*` 指令、Skill、模板和 schema，不改变已有项目产物。 |
| `openqa run <目标>` | 开始一次测试任务 | 创建 change 工作区并触发 AI 驱动循环：AI 自主生成需求、测试知识、Review 计划、测试矩阵，直到准备就绪后呈现确认摘要等待用户确认。 |
| `openqa apply` | 执行与报告 | 用户确认后执行代码 Review、测试矩阵、采集证据、生成报告。支持 `--suite <name>` 直接执行全局测试套件。 |
| `openqa archive` | 归档与沉淀 | 关闭已完成 change，把验证稳定的结论沉淀到 `openqa/knowledge/`，晋升稳定脚本。 |
| `openqa help` | 帮助 | 输出用户指令、参数与当前项目建议下一步（不展示内部命令）。 |

### 2.1a 内部命令（用户不感知）

| 命令 | 说明 |
| --- | --- |
| `openqa _advance` | 状态机推进：执行确定性自动生成（scan/impact/matrix）、更新 `state.yaml`。由 AI 在驱动循环中调用，不出现在 `help` 或用户文档中。 |

### 2.2 Slash Commands

`openqa init` / `openqa update` 向 AI 宿主安装：

| Slash Command | 说明 |
| --- | --- |
| `/oqa:run <目标>` | 开始一次测试任务，AI 自主推进准备阶段，完成后等用户确认执行。 |
| `/oqa:apply` | 用户确认后执行测试，生成报告。 |
| `/oqa:archive` | 归档 change，沉淀可复用知识。 |
| `/oqa:continue` | 手动恢复入口：AI 中断或用户想查看进度时使用，从当前状态继续驱动循环。正常流程无需触发。 |

这组命令的设计原则：**用户描述目标，OpenQA 维护状态；AI 自主推进，只在需要决策时打断用户。**

### 2.3 典型用户流程

```
# 项目首次初始化（只做一次）
openqa init

# 开始一次测试任务
/oqa:run "测试登录流程"
  → AI 内部自主循环（用户不感知）：
      openqa run "测试登录流程"   # 创建 change + 初始扫描
      [AI 分析代码，写 requirements.md]
      openqa _advance             # 影响分析 + 状态更新
      [AI 写 test_knowledge.md + review_plan.md]
      openqa _advance             # 生成 test_matrix.json
      → 准备完成，state=ready_for_apply
  → AI 停下来汇报：
      "准备完成：7 个测试用例，1 个 Review 问题需关注，预计 5 分钟
       是否执行？"

# 用户确认后执行
/oqa:apply

# 归档（可选）
/oqa:archive
```

### 2.4 `openqa init` 体验

```bash
cd your-project
openqa init
```

```text
Welcome to OpenQA / 欢迎使用 OpenQA

? Select language / 选择语言:
  > 中文
    English

正在扫描项目...

检测到 Unity 项目:
  project.type: unity                置信度: high
  unity.version: 2022.3.18f1         from ProjectSettings/ProjectVersion.txt
  test.framework: Unity Test Framework
  tests.detected: PlayMode

  推荐配置:
    runtime.mode: editor-playmode      决策依据: 自动
    evidence: 日志 + 截图 + 状态快照

? 请选择你使用的 AI 编程工具（可多选）:
  ✓ Cursor      [已检测到 .cursor/]
  ✓ CodeBuddy   [已检测到 .codebuddy/]
    Claude Code
    其他 / 跳过

需要补充的信息:
  ? unity.editor_path（Unity 编辑器路径）:

初始化完成:
  openqa/           QA 工作区（建议提交到 Git）
  .cursor/skills/   OpenQA agent skills
  .codebuddy/skills/
  .gitignore        已更新（排除 openqa/reports/*/evidence/）

快速开始:
  /oqa:new       开启一次测试变更
  /oqa:continue  推进下一步
  /oqa:apply     执行 Review 与测试
  /oqa:archive   归档并沉淀经验
```


初始化后目录：

```text
# 项目产出物（显式目录，提交到 Git）
openqa/
  config.yaml              # 项目测试画像：项目类型、AI宿主、扫描、运行、自动化、证据、默认策略
  changes/                 # 每次需求/代码/缺陷变更的 QA 工作区
  artifacts/               # 索引、delta、影响图、矩阵、overlay、schema 校验结果
  reports/                 # 执行报告（含 operation_log、timeline；大型证据建议加入 .gitignore）
  baselines/               # 截图、状态、性能等基线
  knowledge/               # 可复用项目知识与经验
  test_assets/             # 跨 change 稳定复用的测试脚本和前置路径
  suites/                  # 全局可复用的测试套件定义

# AI 宿主配置（各自的隐藏目录）
.cursor/
  skills/openqa-*/         # OpenQA agent skills
  commands/oqa_*.md        # Slash commands
.codebuddy/
  skills/openqa-*/
  commands/oqa_*.md
CLAUDE.md                  # Claude Code：skill 引用
```


### 2.4 策略不是新命令

为避免指令膨胀，OpenQA 不为“全量扫描、增量扫描、完整测试、增量测试、冒烟测试”分别设计一组新命令，而是把它们作为 `new / continue / apply` 的**策略参数**和项目配置：

| 策略维度 | 可选值 | 说明 |
| --- | --- | --- |
| `scan_scope` | `auto` / `full` / `incremental` | `auto` 默认；首次、配置变化、分析器升级走全量，其余走增量。 |
| `test_suite` | `smoke` / `incremental` / `requirement-full` / `regression` / `full` | 控制执行规模，从冒烟到全量逐级扩大。 |
| `review_level` | `off` / `changed` / `risk-based` / `full` | 控制代码 Review 范围，默认对受影响代码做风险驱动 Review。 |
| `gate` | `local` / `ci` / `release` | 不同门禁对应不同默认策略、超时、并发和阻断规则。 |

例如：

```bash
openqa new "验证新手引导奖励" --test-suite smoke
openqa apply --test-suite incremental
openqa apply --scan-scope full --test-suite requirement-full
```

日常用户仍主要使用 `/oqa:new`、`/oqa:continue`、`/oqa:apply`；策略可由 Agent、CI 或 `config.yaml` 自动选择。

---

## 3. 功能层：每个高层指令背后的功能

### 3.1 `openqa init`

**用户感知：** 一次初始化，项目具备 OpenQA 能力。

**背后功能：**

- 第一步询问语言偏好（中文 / English），之后所有交互输出均使用所选语言。
- 扫描项目，自动探测项目类型和已有 AI 宿主目录。
- 通过多选菜单让用户主动选择 AI 宿主（Cursor / CodeBuddy / Claude Code 等）；已检测到宿主目录时预勾选作为推荐，未安装任何宿主的项目也可正常选择。
- 创建 `openqa/` 工作区。

- 自动探测项目特征，识别 `web`、`webgl`、`unity`、`unreal`、`api`、`mixed` 或 `unknown` 项目测试类型。
- 由确定性规则或 AI 宿主基于证据选择默认项目画像、运行方式、执行模式、证据类型和默认策略。
- 只追问无法可靠推断、存在多解且影响执行、涉及本机路径、权限、设备、账号环境或外部服务的信息。
- 生成 `openqa/config.yaml`，记录项目测试画像、证据来源、置信度、决策方式、缺失项和执行策略。
- 无法确认的运行配置写入 `runtime.status=incomplete`、`missing` 或 `unknowns`，不阻塞基础初始化。
- 生成 `.gitignore` 建议规则，排除大型执行证据，保留团队共享产物。
- 检测是否存在 OpenSpec；若存在，提示可通过 `openqa new --from-openspec <change-id>` 建立联动。
- 生成初始 schema 与示例 change 模板。


---

### 3.2 `openqa update`

**用户感知：** 升级 OpenQA 后刷新当前项目的 AI 指令和模板。

**背后功能：**

- 更新 `commands/` 中的 slash command 模板。
- 更新 schema、提示词模板和 artifact 模板。
- 保留已有 `changes/`、`artifacts/`、`reports/`、`knowledge/`。
- 输出兼容性报告：哪些旧产物可继续使用，哪些需要迁移。

---

### 3.3 `openqa new <目标>`

**用户感知：** 开始一次新的 QA 变更，例如：

```bash
openqa new "验证新手引导任务奖励逻辑"
```

**背后功能：**

- 创建 `openqa/changes/<change-id>/`。
- 记录本次目标、来源需求、相关代码变更和人工备注。

- 建立事实快照：代码路径、文件哈希、需求文档指纹、已有测试资产。
- 根据策略选择扫描范围：新项目/发布门禁/索引失效走全量扫描；日常变更走增量扫描。
- 初步判断影响范围：可能受影响模块、Review 范围、测试类型、历史失败模式。
- 生成 `intent.md`、`requirements.md`、`state.yaml`、`snapshot.json`、`delta.json` 和 `impact_graph.json`。

建议目录：

```text
openqa/changes/<change-id>/
  intent.md                # 本次 QA 变更目标

  requirements.md          # EARS 风格需求验收项
  state.yaml               # 当前阶段与下一步建议
  snapshot.json            # 当前需求、代码、测试资产快照
  delta.json               # 相对上次快照的增量变化
  impact_graph.json        # 受影响需求、代码、Review 范围、测试类型
  unknowns.md              # 需要 Agent 或人工补充的不确定项
```

---

### 3.4 `openqa continue`

**用户感知：** 不用记下一条命令，让 OpenQA 根据状态推进。

**背后功能：**

`continue` 是状态机入口，会按当前 change 缺失的产物推进：

| 当前缺什么 | `continue` 做什么 | 产物 |
| --- | --- | --- |
| 缺事实快照 | 按 `scan_scope` 做全量或增量扫描 | `snapshot.json` / `delta.json` |
| 缺影响分析 | 对比需求、代码、历史知识和风险规则 | `impact_graph.json` |
| 缺测试知识 | 生成需求理解、断言线索、测试映射 | `test_knowledge.md` |
| 缺 Review 计划 | 根据影响面生成代码 Review 检查项 | `review_plan.md` |
| 缺测试矩阵 | 将测试知识转为可执行任务 | `test_matrix.json` |
| 存在 unknowns | 明确列出需补充的问题 | `unknowns.md` |
| 可执行 | 提示进入 `/oqa:apply` | `state.yaml` |

`continue` 背后的测试知识需要表达：

- 需求理解与验收点。
- 代码入口、事件、接口、状态面。
- 前置条件、测试数据、断言线索。
- 测试类型映射。
- Review 检查项：变更影响、边界条件、异常处理、并发/性能、安全、可测试性、回归风险。
- 风险、缺口和不确定项。
- 置信度与证据来源。

---

### 3.5 `openqa apply`

**用户感知：** 对当前 change 做代码 Review 与测试执行，并把确认过的结果写回。

**背后功能：**

- 执行前校验：代码哈希、需求指纹、测试知识、Review 计划、矩阵是否新鲜。
- 对受影响代码做结构化 Review：需求一致性、影响面、异常分支、边界条件、可测试性、性能/并发/安全风险。
- 生成 Review findings：`review_findings.sarif.json`（标准机器格式）与 `review_report.md`（人工/Agent 可读摘要）。
- 按测试矩阵 DAG 调度执行，支持同层并行。
- 全程记录操作过程：阶段、命令、策略、输入、输出、耗时、跳过/阻断原因。
- 采集证据：日志、截图、状态快照、RPC 回包、网络摘要、失败上下文。
- 生成测试执行报告和过程时间线：环境、前置、执行、验收、未知分桶，以及用户可读的“如何测试/为何失败”。
- 将 Agent 或人工确认的 overlay 合并到当前 change。
- 低置信度建议只进入待确认区，不直接影响后续执行。

执行链路：

```text
[1] 新鲜度校验 → [2] 代码 Review → [3] 工具链就绪 → [4] 应用就绪 → [5] 前置条件满足 → [6] 验收步骤执行 → [7] 报告归因
```

Review 报告至少包含：

| 字段 | 说明 |
| --- | --- |
| `scope` | 本次 Review 覆盖的文件、函数、变更片段。 |
| `requirements_mapping` | 代码变更与需求/验收项的对应关系。 |
| `findings[]` | 问题列表，含严重级别、位置、证据、建议。 |
| `risk_summary` | 回归、边界、异常、安全、性能、并发、可测试性风险摘要。 |
| `test_impact` | 建议新增、重跑或跳过的测试范围。 |
| `unknowns[]` | 证据不足或需要人工确认的问题。 |

宿主形态：

| 宿主 | 控制方式 |
| --- | --- |
| Unity 原生客户端 | 进程外编排 + Unity Test Framework / 引擎内输入管线 / RPC / WebSocket。 |
| Unreal 原生客户端 | 进程外编排 + Automation Spec / console command / RPC / WebSocket。 |
| WebGL 游戏 | 浏览器外壳 + 引擎内 bridge / JS bridge / WebSocket。 |
| Web / H5 | Playwright 等 DevTools 协议工具。 |
| Backend / API | 服务启动命令 + 健康检查 + API 契约或测试命令。 |

---

### 3.6 操作过程记录

OpenQA 每次执行都必须留下可回溯的过程记录，让用户不用翻原始日志也能知道“怎么测的、在哪失败、为什么失败”。

| 产物 | 格式 | 说明 |
| --- | --- | --- |
| `operation_log.jsonl` | JSONL | 从 `new` 到 `archive` 的机器可读操作事件流。 |
| `timeline.md` | Markdown | 面向用户的测试过程摘要，展示关键步骤、耗时、结果和失败点。 |
| `decision_log.md` | Markdown 表格 | 记录策略选择、跳过、阻断、豁免及原因。 |
| `evidence_index.yaml` | YAML | 统一登记日志、截图、视频、状态快照等证据及引用关系。 |

失败时，报告必须能回溯到：阶段 → 步骤 → 输入 → 输出 → 证据 → 初步原因 → 建议下一步。

---

### 3.7 扫描与测试策略

OpenQA 内部必须同时支持**全量**与**增量**，但由状态机选择，不要求用户手工拼命令。

扫描模式（`init-probe` / `knowledge-scan` / `full` / `incremental` / `auto`）和测试套件（`smoke` / `incremental` / `requirement-full` / `regression` / `full`）的详细定义与触发规则，见 `REQ_04_SCAN_AND_IMPACT.md` 和 `REQ_05_TEST_STRATEGY_AND_MATRIX.md`。

其他必须纳入矩阵的质量维度：代码 Review、测试数据、环境与宿主、基线治理、flaky 治理、成本预算、安全与隐私。



---

### 3.8 `openqa archive`

**用户感知：** 当前 QA change 完成，归档并沉淀经验。

**背后功能：**

- 校验当前 change 的必需产物是否完整。
- 归档 `openqa/changes/<change-id>/`，保留审计链路。
- 将稳定结论晋升到 `openqa/knowledge/`。

- 标记过期或被否定的旧知识。
- 输出本次变更对长期测试资产的影响摘要。

---

## 4. 迭代层：需求更新、代码修改如何演进

OpenQA 的迭代单位是 **change**。一次需求更新、代码修改、缺陷修复、测试策略调整，都应进入一个 change。

### 4.1 标准闭环

```text
NEW → CONTINUE → APPLY → ARCHIVE
```

| 阶段 | 指令 | 关键产物 | 目的 |
| --- | --- | --- | --- |
| NEW | `openqa new <目标>` | `intent.md`、`requirements.md`、`state.yaml`、`snapshot.json`、`delta.json`、`artifact_index.yaml`、`openspec_link.yaml`（可选） | 记录目标并建立工作区；若来自 OpenSpec，则保存关联。 |
| CONTINUE | `openqa continue` | `impact_graph.json`、`test_knowledge.md`、`review_plan.md`、`test_matrix.json` | 自动补齐下一份必要产物；宿主按需读取这些文件组织上下文。 |
| APPLY | `openqa apply` | `review_findings.sarif.json`、`review_report.md`、`run_report.json`、`run_report.junit.xml`、`run_report.md`、`operation_log.jsonl`、`timeline.md`、`evidence_index.yaml`、`report_overlay.yaml` | 按策略做 Review、冒烟/增量/完整测试、采证、归因、过程记录、合并确认结果。 |
| ARCHIVE | `openqa archive` | `archive/`、`knowledge/` 更新 | 归档 change，沉淀经验。 |

### 4.2 变更处理策略

| 变更类型 | 如何识别 | OpenQA 如何处理 |
| --- | --- | --- |
| 需求更新 | 需求文档或 OpenSpec specs 指纹变化 | `continue` 重新生成影响分析和测试知识；可选择 `smoke`、`incremental` 或 `requirement-full`。 |
| 代码修改 | 文件哈希、符号摘要或依赖关系变化 | 更新 `delta.json` 和 `impact_graph.json`，标记受影响模块、Review 范围与测试类型。 |
| Review 发现问题 | `review_findings.sarif.json` 存在 blocking / warning finding | 生成修复建议和测试影响面；blocking 问题默认阻止进入验收执行。 |
| 测试失败 | 报告出现 failed / unknown | `apply` 生成失败分桶与证据包，Agent 输出归因 overlay。 |
| 测试资产变更 | 矩阵、断言、基线或执行器版本变化 | 执行前校验新鲜度，必要时回到 `continue` 重建矩阵。 |
| 项目测试画像变化 | `config.yaml` 中 `project.type`、`runtime` 或 `automation` 改变 | 重建扫描索引、控制通道、前置条件、测试矩阵和执行 hints。 |
| flaky 频发 | 多次报告统计到不稳定 | 进入知识候选，不直接当 PASS；需多轮验证或人工确认。 |

### 4.3 迭代原则

- **状态驱动**：用户只需要 `continue`，OpenQA 根据 `state.yaml` 判断下一步。
- **事实先行**：所有 Agent 输入必须来自最新快照、需求、报告和知识库。
- **增量更新**：需求和代码变更只影响相关测试知识、矩阵和执行子图。
- **overlay 合并**：Agent 不直接改确定性产物，只输出可校验 overlay。
- **可归档**：完成的 change 不是删除，而是成为未来影响分析和自我进化素材。

### 4.4 门禁策略

默认门禁策略（`local` / `ci` / `requirement` / `release` / `nightly`）及其扫描范围、测试套件、Review 严格度和阻断规则，见 `REQ_08_QUALITY_GATES.md`。



---

## 5. 自我进化：如何越用越聪明

OpenQA 的智能来自**可验证经验的持续沉淀**，不是来自工具内部隐藏推理。

### 5.1 进化闭环

```text
Review 发现 + 执行证据 → Agent 归因 → overlay 合并 → 多轮验证 → 知识晋升 → 下一轮 continue/apply 复用
```

### 5.2 知识分层

```text
openqa/knowledge/
  project_profile.yaml       # 项目结构、宿主形态、技术栈、运行方式
  control_channels.yaml      # RPC、bridge、输入通道、入口点
  event_catalog.yaml         # 游戏事件知识（knowledge-scan 生成，绑定锚点）
  protocol_catalog.yaml      # RPC/协议接口知识
  state_schema.yaml          # 核心状态对象字段（Player/Map/Quest 等）
  log_patterns.yaml          # 关键日志模式
  preconditions.yaml         # 已验证前置路径（按状态标签索引，跨 change 复用）
  test_patterns.yaml         # 已验证测试模式
  review_rules.yaml          # 已验证代码 Review 规则与风险模式
  assertion_hints.yaml       # 常用断言与状态检查
  failure_taxonomy.yaml      # 失败类型与归因规则
  flaky_rules.yaml           # flaky 用例与处理策略
  baselines_index.yaml       # 截图/状态/性能基线索引
```



### 5.3 可沉淀内容

| 来源 | 可沉淀内容 |
| --- | --- |
| 成功执行报告 | 稳定路径、稳定前置、有效断言。 |
| 冒烟/增量/完整测试结果 | 哪些场景适合快速验证，哪些必须完整覆盖。 |
| Review 报告 | 高风险代码模式、有效检查项、常见缺陷与修复建议。 |
| 失败报告 | 失败模式、归因规则、补证据建议。 |
| 人工确认 | 置信度提升、规则适用范围。 |
| 多次重跑 | flaky 识别、等待策略、容差策略。 |
| 需求变更历史 | 哪类需求通常影响哪些模块和测试类型。 |
| 代码变更历史 | 哪些目录、接口、事件变更风险更高。 |

### 5.4 防止“越学越错”

- 知识项必须有来源：`source_change`、`source_report` 或 `source_overlay`。
- 知识项必须有置信度、适用范围和过期条件。
- 单次模型输出不能直接晋升为长期知识。
- 失败归因必须保留证据引用，不能只存自然语言结论。
- 路径不存在、接口消失、需求指纹变化时，旧知识要降权或标记过期。
- 支持人工驳回、降权、冻结知识项。

### 5.5 智能提升表现

随着使用次数增加，OpenQA 应逐步做到：

1. 更快判断代码变更影响哪些测试。
2. 更准确选择冒烟、增量、完整、回归或全量测试策略。
3. 更准确识别代码变更中的高风险点。
4. 更准确生成前置条件和断言。
5. 更少重复询问已知项目背景。
6. 更稳定地区分环境问题、脚本问题、产品问题和代码质量问题。
7. 更自动识别 flaky、基线漂移和低价值测试。
8. 更贴合团队自己的项目结构、引擎、运行方式和质量标准。

---

## 6. 与 OpenSpec 的关系

OpenSpec 管**规格驱动开发**，OpenQA 管**质量验证与反馈**。两者联动后形成闭环：

```text
OpenSpec: propose/spec/design/tasks → apply
OpenQA:   new/continue → review/test/gate/report
OpenSpec: archive（在 OpenQA 通过或人工豁免后）
```

| OpenSpec | OpenQA |
| --- | --- |
| 描述要做什么 | 验证做得对不对 |
| 管理需求、设计、任务、实现 | 管理测试知识、代码 Review、矩阵、证据、归因、门禁 |
| `openspec/changes/<id>/proposal.md` | `intent.md` 的来源 |
| `openspec/changes/<id>/specs/` | `requirements.md` / EARS 验收项来源 |
| `openspec/changes/<id>/design.md` | Review 与影响分析输入 |
| `openspec/changes/<id>/tasks.md` | 测试范围和验收阶段输入 |
| `/opsx:apply` | 开发实现 |
| `/oqa:apply` | Review、测试、门禁报告 |

OpenQA 可以独立使用；若检测到 OpenSpec，则可通过 `openqa new --from-openspec <change-id>` 建立关联。OpenQA 默认只读 OpenSpec 产物，不修改 OpenSpec；门禁通过后输出可归档结论，供 `/opsx:archive` 使用。

---

## 7. 设计边界

| 不做 | 原因 |
| --- | --- |
| 工具进程内调用大模型 | 推理由 Agent 宿主负责，OpenQA 保持确定性和可复现。 |
| 默认修改产品代码或 OpenSpec 产物 | 默认只生成测试、Review、门禁报告和建议；写产品代码或 OpenSpec 产物必须显式授权。 |
| 用代码 Review 报告替代人工决策 | Review 报告提供证据、风险和建议；是否修改代码仍由 Agent 宿主或人工确认。 |
| 让用户记大量底层命令 | 扫描、规划、Review、矩阵、报告、知识沉淀应由 `continue/apply/archive` 状态机封装。 |
| 把自然语言当最终产物 | 最终落盘必须是可校验文件。 |
| 将前置失败归类为验收失败 | 两类问题处理路径不同。 |
| 将 UNKNOWN 当 PASS | UNKNOWN 必须补证据或人工确认。 |
| 在产物或知识库中保存密钥 | 安全硬约束。 |

---

## 8. 产品落地优先级

| 优先级 | 能力 | 说明 |
| --- | --- | --- |
| P0 | `init`、`new`、`continue`、`apply`、`archive` | 打通包含 Review、测试、门禁、过程记录的最小可用闭环。 |
| P1 | `/oqa:*`、`openqa/changes/`、状态机、`timeline.md` | 让 Agent 和用户都能自然推进并回溯测试工作流。 |
| P2 | OpenSpec 联动 | 读取 OpenSpec proposal/specs/design/tasks，形成开发与验证闭环。 |
| P3 | `openqa/knowledge/` | 形成长期项目智能。 |

| P4 | 多宿主执行器 | Unity、Unreal、WebGL、Web/H5、Backend/API 分别接入真实执行。 |

---

## 9. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-05-01 | 精简指令体系，参考 OpenSpec 收敛为 `init/update/new/continue/apply/archive`；统一产品命名为 OpenQA / `openqa`；项目产出物目录统一为 `openqa/`（显式目录），slash commands 和 skills 安装到 AI 宿主各自隐藏目录；补充代码 Review、全量/增量扫描、多级测试策略、操作过程记录、失败回溯和 OpenSpec 联动闭环。 |

