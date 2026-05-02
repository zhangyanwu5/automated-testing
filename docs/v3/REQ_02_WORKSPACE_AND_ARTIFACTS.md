# REQ_02_WORKSPACE_AND_ARTIFACTS：工作区、产物与格式

## 目标

OpenGuard 的产物必须同时满足：**Agent 易读、工具可校验、CI 可消费、人可审阅**。不假设 OpenGuard 自己管理大模型上下文；上下文组织由 CodeBuddy、Claude Code、Cursor 等宿主负责，OpenGuard 只提供清晰、稳定、可引用的文件化产物。

## 格式选择原则

| 产物类型 | 推荐格式 | 原因 |
| --- | --- | --- |
| 人/Agent 共同编辑的意图、需求、计划 | Markdown + YAML Front Matter | 易读、易改、适合 Agent 生成；结构字段放 front matter。 |
| 需求验收句 | EARS Markdown | 用受控自然语言表达触发、条件、系统响应，降低歧义。 |
| 项目配置、策略、长期知识 | YAML | 人可维护，适合规则、阈值、知识项。 |
| 工具事实、索引、delta、影响图 | JSON | 稳定、确定性、易 schema 校验。 |
| 操作过程、命令审计、事件流 | JSONL | 流式写入，便于失败回溯和长流程追加。 |
| 代码 Review findings | SARIF JSON + Markdown 摘要 | 兼容代码扫描生态，支持文件/行号定位。 |
| 测试执行报告 | JSON + JUnit XML + Markdown 摘要 | JSON 给 Agent/工具，JUnit 给 CI，Markdown 给人。 |
| 截图、视频、原始日志 | 原文件 + YAML/JSON metadata | 不内嵌大二进制，只保存引用、哈希和摘要。 |
| Agent 写回建议 | YAML/JSON overlay | Agent 易生成，工具校验后归一化合并。 |

## 目录需求

```text
openguard/
  config.yaml

  changes/
    <change-id>/
      artifact_index.yaml       # 本 change 产物清单
      openspec_link.yaml        # 可选：关联 OpenSpec change
      intent.md                 # 本次变更目标
      requirements.md           # EARS 验收项
      state.yaml                # 当前阶段与下一步建议
      unknowns.md               # 待补充的不确定项
      snapshot.json             # 代码/需求事实快照
      delta.json                # 相对上次快照的增量
      impact_graph.json         # 影响关系图
      freshness.json            # 新鲜度校验结果
      test_knowledge.md         # 需求理解、断言线索、测试映射
      review_plan.md            # Review 范围与检查项
      test_matrix.json          # 可执行测试任务矩阵
      review_findings.sarif.json
      review_report.md
      gate_report.yaml          # 门禁结论
      report_overlay.yaml       # Agent/人工归因写回
      test_scripts/             # 本次 change 生成的测试脚本草稿
      test_fixtures/            # 本次 change 专用的测试数据和前置状态

  artifacts/                    # 工具生成的索引、全量快照等

  reports/
    suites/
      <suite-name>/
        suite_index.yaml        # 套件执行历史索引
        <run-id>/               # 每次执行独立目录，run-id = run-<ISO8601>
          run_report.json
          run_report.junit.xml
          run_report.md
          events.jsonl
          operation_log.jsonl
          timeline.md
          decision_log.md
          evidence_index.yaml
          evidence/
    changes/
      <change-id>/
        change_run_index.yaml   # 该 change 执行历史索引
        <run-id>/
          run_report.json
          run_report.junit.xml
          run_report.md
          events.jsonl
          operation_log.jsonl
          timeline.md
          decision_log.md
          evidence_index.yaml
          evidence/

  baselines/                    # 截图、状态、性能等基线资产

  knowledge/                    # 可复用项目知识（提交到 Git）
    project_profile.yaml        # 项目画像
    control_channels.yaml       # 控制通道（含运行时验证状态）
    event_catalog.yaml          # 游戏事件知识（knowledge-scan 生成，绑定锚点）
    protocol_catalog.yaml       # RPC/协议接口知识
    state_schema.yaml           # 核心状态对象字段
    log_patterns.yaml           # 关键日志模式
    preconditions.yaml          # 已验证前置路径索引（跨 change 复用）
    test_patterns.yaml
    assertion_hints.yaml
    failure_taxonomy.yaml
    flaky_rules.yaml
    review_rules.yaml
    baselines_index.yaml

  test_assets/                  # 项目维度：跨 change 稳定复用的测试脚本和测试数据
    scripts/
    setup_paths/                # 已验证的前置路径脚本（含 .meta.yaml 锚点）
    fixtures/

  suites/                       # 项目维度：稳定可复用的测试套件定义
    smoke/
    regression/
    requirement/
    full/
```



| 编号 | 需求 |
| --- | --- |
| REQ-02-01 | `openguard/config.yaml` 必须保存项目测试画像，包括项目类型、AI 宿主列表、扫描范围、需求入口、运行方式、自动化控制方式、证据采集、执行策略和默认门禁。 |
| REQ-02-02 | `openguard/changes/` 必须保存每次 QA change 的工作区，包括 `test_scripts/`（草稿脚本）和 `test_fixtures/`（专用测试数据）子目录。 |
| REQ-02-03 | `openguard/artifacts/` 必须保存工具生成的索引、delta、影响图、矩阵和 overlay。 |
| REQ-02-04 | `openguard/reports/` 必须按 `suites/<name>/<run-id>/` 和 `changes/<id>/<run-id>/` 结构保存执行报告；每次执行必须独立存储，不覆盖历史。 |
| REQ-02-05 | `openguard/baselines/` 必须保存截图、状态、性能等基线资产及 metadata。 |
| REQ-02-06 | `openguard/knowledge/` 必须保存可复用项目知识与经验。 |
| REQ-02-07 | `openguard/config.yaml` 中未补齐的运行配置必须显式记录为 incomplete、missing 或 unknowns，不得让后续执行阶段隐式猜测。 |
| REQ-02-08 | `openguard/config.yaml` 只能保存可共享配置或环境变量引用，不得保存密钥、账号口令和隐私数据。 |
| REQ-02-09 | `openguard/config.yaml` 中自动推断或 Agent 决策的关键字段必须记录 `confidence`、`detected_from`、`decided_by` 或 `evidence`，便于后续校验和纠错。 |
| REQ-02-10 | `openguard/test_assets/` 必须保存跨 change 稳定复用的测试脚本和测试数据；每个脚本必须有对应的 `.meta.yaml` 锚点文件，记录绑定符号、置信度和状态。 |
| REQ-02-11 | `openguard/suites/` 必须保存全局可复用的测试套件定义，引用 `test_assets/` 中的脚本，不直接引用 change 工作区内的草稿。 |
| REQ-02-12 | `openguard/config.yaml` 必须支持 `reports.retention` 配置，定义各类报告的保留策略（最大保留次数或天数）；change 维度的执行记录跟随 change 归档保留，不受 suite 保留策略影响。 |
| REQ-02-13 | Slash commands 和 skill 文件必须安装到 AI 宿主对应的隐藏目录（`.cursor/`、`.codebuddy/` 等），不存放在 `openguard/` 目录内。 |
| REQ-02-14 | `openguard init` 必须生成 `.gitignore` 建议规则，推荐排除 `openguard/reports/*/evidence/` 等大型证据目录，保留团队共享的 changes、test_assets、suites、knowledge。 |




## `config.yaml` 配置画像

`openguard init` 生成的 `openguard/config.yaml` 应作为后续扫描、矩阵和执行的统一项目画像入口：


```yaml
project:
  type: unity        # web / webgl / unity / unreal / api / mixed / unknown
  confidence: high
  detected_from:
    - Assets/
    - ProjectSettings/ProjectVersion.txt
    - Packages/manifest.json
  root: "."
  languages: [csharp]
  frameworks: [unity]

ai_hosts:
  - codebuddy
  - cursor

scan:
  scope: auto
  include: [Assets/, Packages/, ProjectSettings/]
  exclude: [Library/, Temp/, Logs/]

runtime:
  status: incomplete
  mode: editor-playmode
  confidence: medium
  decided_by: auto
  evidence:
    - Packages/manifest.json contains com.unity.test-framework
    - PlayMode tests detected
  missing:
    - unity.editor_path
  startup_timeout_seconds: 120
  health_check:
    type: log-pattern
    pattern: null

automation:
  control_channel:
    type: websocket
    url_env: OPENGUARD_CONTROL_WS_URL
    confidence: low
  fallback: manual-or-blackbox
  missing:
    - control_channel.url_or_env

evidence:
  collect: [logs, screenshots, video, state_snapshot]
  log_paths: [Logs/]
  decided_by: auto

defaults:
  gate: local
  test_suite: smoke
  review_level: changed
```

## 核心产物

change 工作区内的完整产物列表及每个产物的生成阶段，见 `REQ_03_CHANGE_STATE_MACHINE.md`；执行报告产物（`run_report.*`、`events.jsonl`、`operation_log.jsonl`、`timeline.md`、`decision_log.md`、`evidence_index.yaml`）见 `REQ_07_EXECUTION_AND_REPORTING.md`。

各产物的**格式选择理由**见本文档"格式选择原则"表；各产物的**内容字段规范**见对应的专项需求文档。



## EARS 使用规则

OpenGuard 应在 `requirements.md` 中引入 EARS，但只用于**需求行为与验收项**，不强行用于报告、矩阵或日志。

常用句式：

```text
WHEN <触发事件> THEN <系统> SHALL <响应>
IF <前置条件> THEN <系统> SHALL <响应>
WHILE <状态> THE <系统> SHALL <持续行为>
WHERE <特性> IS <条件> THE <系统> SHALL <响应>
```

每条 EARS 需求必须有稳定 ID，并能被测试矩阵、Review finding、执行报告引用。

## AI 友好要求

- 文件名、ID、路径必须稳定，便于宿主按需读取。
- 大日志、截图、视频和全量索引不得内嵌到报告正文，只保存引用、哈希、摘要和关键窗口。
- 工具事实与 Agent 推理必须分离；Agent 写回只通过 `report_overlay.yaml`。
- 代码引用必须包含路径、行号/符号和文件哈希，避免编造路径。
- Markdown 文档必须结构稳定，避免长篇散文；优先使用标题、表格、列表和短段落。

## 验收标准

- 产物格式选择能解释：为何用 Markdown/YAML/JSON/JSONL/SARIF/JUnit。
- `openguard/config.yaml` 能稳定表达项目测试画像，且关键推断字段包含证据来源、置信度、决策方式；缺失配置以 incomplete、missing 或 unknowns 明示。
- Agent 宿主可直接读取 `openguard/changes/<id>/` 下的文件自行组织上下文，不依赖 OpenGuard 生成专用 context 文件。
- 每个报告结论都能追溯到 EARS 需求、代码引用、证据或人工豁免。
- 所有机器可读产物必须有 schema 或标准格式约束。

