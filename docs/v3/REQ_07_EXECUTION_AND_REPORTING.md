# REQ_07_EXECUTION_AND_REPORTING：执行与报告

## 目标

OpenQA 必须按矩阵执行测试，采集证据，区分失败类型，并生成适合 Agent、CI 和人工审阅的报告组合。

## 执行链路

```text
新鲜度校验 → 脚本状态校验 → 代码 Review → 工具链就绪 → 应用就绪 → 前置条件满足 → 验收步骤执行 → 报告归因
```

## 执行器职责边界

OpenQA 执行器是确定性的本地流程编排器，负责按矩阵调度、启动目标应用、采集证据和落盘报告，不在执行过程中调用大模型。

AI 宿主（CodeBuddy / Claude Code / Cursor 等）与 OpenQA 的分工：

| 角色 | 职责 |
| --- | --- |
| AI 宿主 | 生成测试脚本、读取执行报告、推理归因、输出 `report_overlay.yaml` |
| OpenQA 执行器 | 校验新鲜度与脚本状态、启动目标应用、按矩阵调度运行测试脚本、采集证据、写入报告 |
| 测试脚本 | 通过各项目类型对应的控制通道（Playwright / WebSocket / RPC 等）操控目标应用，断言结果以约定格式输出供执行器采集 |

AI 宿主与 OpenQA 之间只通过文件产物和 CLI 通信（`state.yaml`、`run_report.md`、`report_overlay.yaml` 等），不在执行过程中直接操作目标应用。



## 执行报告存储模型

每次执行必须生成独立的 Run ID，报告存入独立目录，不覆盖历史记录：

```text
openqa/reports/
  suites/

    <suite-name>/
      suite_index.yaml              # 套件执行历史索引
      <run-id>/                     # 每次执行独立目录，run-id = run-<ISO8601>
        run_report.json
        run_report.junit.xml
        run_report.md
        events.jsonl
        timeline.md
        evidence_index.yaml
        evidence/
  changes/
    <change-id>/
      change_run_index.yaml         # 该 change 执行历史索引
      <run-id>/
        run_report.json
        run_report.junit.xml
        run_report.md
        events.jsonl
        timeline.md
        evidence_index.yaml
        evidence/
```

`suite_index.yaml` 格式示例：

```yaml
suite: smoke
runs:
  - id: run-2026-05-01T090000Z
    timestamp: 2026-05-01T09:00:00Z
    result: passed
    script_count: 12
    code_version: abc123
    gate: ci
  - id: run-2026-05-01T210000Z
    timestamp: 2026-05-01T21:00:00Z
    result: failed
    script_count: 12
    code_version: def456
    gate: nightly
latest_run_id: run-2026-05-01T210000Z
retention:
  max_runs: 30
```

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-07-01 | `apply` 执行前必须校验代码哈希、需求指纹、Review 计划、测试知识和矩阵新鲜度。 |
| REQ-07-02 | 执行器必须按矩阵 DAG 调度，支持并行、失败快停、重试、超时和预算控制。 |
| REQ-07-03 | 执行必须区分环境失败、前置失败、脚本失败、验收失败、产品失败和未知。 |
| REQ-07-04 | 执行必须采集日志、截图、状态快照、RPC 回包、网络摘要和失败上下文。 |
| REQ-07-05 | 报告必须生成 `run_report.json`、`run_report.junit.xml` 和 `run_report.md`。 |
| REQ-07-06 | 报告必须能关联 `test_matrix.json` 中的任务、EARS 需求 ID、代码影响和证据路径。 |
| REQ-07-07 | 报告必须允许 Agent 通过 `report_overlay.yaml` 写回归因或修正建议。 |
| REQ-07-08 | 执行过程中的大量事件必须写入 `events.jsonl`，而不是塞入单个巨大 JSON。 |
| REQ-07-09 | 从 `new`、`continue`、`apply` 到 `archive` 的关键操作必须写入 `operation_log.jsonl`。 |
| REQ-07-10 | 测试结束后必须生成 `timeline.md`，让用户清晰看到测试如何执行、在哪里失败、失败原因是什么。 |
| REQ-07-11 | 所有证据必须登记到 `evidence_index.yaml`，并与操作步骤、报告结论建立引用关系。 |
| REQ-07-12 | `apply` 必须根据 `project.type`、`runtime`、`automation`、配置来源和置信度做执行前校验；只有真实执行必需配置缺失或低置信度会影响结果时，才阻断真实测试并输出缺失项和下一步建议。 |
| REQ-07-13 | `apply` 和 `apply --suite` 执行前必须校验矩阵引用的所有脚本状态；`broken` 和 `stale` 脚本不得参与执行，必须在报告中标记为 `skipped` 并说明原因；`needs-review` 脚本不得参与 `release` 和 `nightly` gate 执行。 |
| REQ-07-14 | 每次执行必须生成唯一 Run ID（格式：`run-<ISO8601时间戳>`），报告和证据写入独立的 `<run-id>/` 目录，不得覆盖历史执行记录。 |
| REQ-07-15 | 每个套件和每个 change 必须维护执行历史索引（`suite_index.yaml` / `change_run_index.yaml`），记录所有 Run ID、时间戳、结果摘要、代码版本和门禁类型；`latest_run_id` 字段指向最新一次执行。 |
| REQ-07-16 | 执行历史记录必须遵循 `config.yaml` 中配置的保留策略（`reports.retention`）；超出保留数量的旧记录可清理，但 `change` 维度的执行记录跟随 change 归档保留，不受 suite 保留策略影响。 |
| REQ-07-17 | 执行器必须通过 subprocess 调用测试脚本（`.py` / `.js` 等），不在执行器进程内直接调用大模型；AI 宿主通过读取执行报告参与归因和修复建议，不直接操作目标应用。 |
| REQ-07-18 | `operation_log.jsonl` 每条事件必须包含：`event_id`、`change_id`、`phase`（`new` / `continue` / `review` / `test` / `report` / `archive`）、`step`、`started_at` / `ended_at`、`inputs`、`outputs`、`decision`、`status`（`passed` / `failed` / `skipped` / `blocked` / `unknown`）、`evidence_refs`、`error`。 |
| REQ-07-19 | 失败必须区分：环境、前置、Review、脚本、产品、数据、未知七种类型，并在 `failure_buckets` 中体现。 |
| REQ-07-20 | `timeline.md` 必须展示失败前后的关键步骤，不要求用户阅读原始日志；用户只读 `timeline.md` 就能理解本次测试过程。 |
| REQ-07-21 | `decision_log.md` 必须解释为什么选择冒烟 / 增量 / 完整测试、为什么跳过或阻断某些项，以及所有人工豁免记录。 |
| REQ-07-22 | 操作记录不得保存密钥、账号口令或隐私数据；敏感信息扫描失败时必须拒绝写入。 |

## 格式要求

| 产物 | 格式 | 用途 |
| --- | --- | --- |
| `run_report.json` | JSON | Agent/工具消费的主报告。 |
| `run_report.junit.xml` | JUnit XML | CI 平台展示测试结果。 |
| `run_report.md` | Markdown | 人工阅读摘要。 |
| `events.jsonl` | JSONL | 流式记录步骤、日志窗口、状态变化。 |
| `operation_log.jsonl` | JSONL | 从 `new` 到 `archive` 的机器可读操作事件流，支持失败中断恢复。 |
| `timeline.md` | Markdown | 面向用户的过程摘要，展示关键步骤、耗时、结果和失败点。 |
| `decision_log.md` | Markdown 表格 | 记录策略选择、跳过、阻断、豁免及原因。 |
| `evidence_index.yaml` | YAML | 统一登记日志、截图、视频、状态快照等证据及引用关系。 |
| `evidence/*.metadata.yaml` | YAML | 截图、视频、原始日志等证据 metadata。 |
| `suite_index.yaml` | YAML | 套件执行历史索引，含 Run ID 列表和 latest 指针。 |
| `change_run_index.yaml` | YAML | change 执行历史索引，含 Run ID 列表和 latest 指针。 |

## 宿主形态

执行器必须根据 `openqa/config.yaml` 中的 `project.type`、`runtime` 和 `automation` 选择启动、连接、前置校验和证据采集方式。


| 宿主 | 控制方式 | 关键执行配置 |
| --- | --- | --- |
| Unity 原生客户端 | 进程外编排 + Unity Test Framework / 引擎内输入管线 / RPC / WebSocket。 | Unity Editor 或构建产物路径、执行模式、scene、日志路径、启动完成判定。 |
| Unreal 原生客户端 | 进程外编排 + Automation Spec / console command / RPC / WebSocket。 | `.uproject`、Editor 或 packaged build 路径、map / level、测试过滤器、crash dump 路径。 |
| WebGL 游戏 | 浏览器外壳 + 引擎内 bridge / JS bridge / WebSocket。 | 构建目录或 URL、浏览器、加载完成判定、桥接方式、性能和资源基线。 |
| Web / H5 | Playwright 等 DevTools 协议工具。 | 启动命令、访问 URL、浏览器、console / network / screenshot 采集。 |
| Backend / API | 服务启动命令 + 健康检查 + API 契约或测试命令。 | 启动命令、健康检查、OpenAPI / gRPC / Postman 入口、依赖服务和测试数据。 |

若真实执行必需的 `runtime` 或 `automation` 配置缺失、低置信度或与当前矩阵冲突，`apply` 必须在执行前阻断真实测试，并在报告或 `openqa/changes/<id>/unknowns.md` 中说明缺失项、证据和下一步建议。


## 报告字段

| 字段 | 说明 |
| --- | --- |
| `run_id` | 本次执行的唯一 ID，格式 `run-<ISO8601时间戳>`。 |
| `suite` | 执行的套件名（全局 suite 执行时）或 change ID（change 维度执行时）。 |
| `code_version` | 执行时的代码版本（Git commit hash 或快照哈希）。 |
| `runtime` | 工具链、应用启动和连接状态。 |
| `precondition` | 前置条件结果和耗时。 |
| `acceptance` | 验收任务结果、证据引用、关联 EARS ID。 |
| `failure_buckets` | 环境、前置、脚本、产品、数据、未知分桶。 |
| `evidence_refs` | 日志、截图、状态、网络、RPC 证据引用。 |
| `attribution_hints` | 供 Agent 归因的结构化线索。 |
| `trace_refs` | 指向 `operation_log.jsonl`、`timeline.md`、`events.jsonl` 中相关步骤。 |

## 验收标准

- 前置失败不得被归类为验收失败。
- UNKNOWN 不得默认当 PASS。
- 报告中的证据引用必须存在且可追踪。
- 失败报告必须能回溯到具体阶段、命令、输入、输出和证据。
- 大型证据只以引用和摘要进入报告正文。
- 同一套件的每次执行结果独立存储，不覆盖历史；历史记录可通过索引查询。
- AI 宿主与执行器之间只通过文件产物和 CLI 通信，不在执行过程中调用大模型。
- 测试中断后，可根据 `operation_log.jsonl` 最后一条事件恢复或安全重跑。
- Agent 读取 `operation_log.jsonl` 和 `evidence_index.yaml` 能做失败归因。

