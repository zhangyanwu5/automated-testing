# REQ_03_CHANGE_STATE_MACHINE：Change 状态机

## 目标

OpenQA 以 change 作为迭代单位，把一次需求更新、代码修改、缺陷修复、测试策略调整纳入同一个闭环。change 工作区本身必须适合 Agent 宿主直接读取；上下文组织由宿主负责，OpenQA 不额外生成专用 context 文件。

**核心设计：AI 驱动循环**

`openqa run` 完成初始化扫描后，通过 `state.yaml` 的 `agent_action` 字段驱动 AI 自主推进，直到到达需要用户确认的门槛点。CLI 工具（`openqa _advance`）负责确定性操作，AI 负责需要理解/推理的操作，两者通过文件和 `state.yaml` 协作。

## 状态流

```text
PREPARING → READY_FOR_APPLY → RUNNING → DONE
```

| 阶段 | 含义 |
| --- | --- |
| `preparing` | AI 正在生成准备产物（requirements/test_knowledge/review_plan/matrix），或 CLI 正在执行确定性扫描 |
| `ready_for_apply` | 所有产物就绪，AI 已向用户呈现确认摘要，等待用户确认执行 |
| `running` | `openqa apply` 执行中 |
| `done` | apply 完成，等待 archive 或下一轮 |
| `archived` | change 已归档 |

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-03-01 | `openqa run <目标>` 必须创建 `openqa/changes/<change-id>/`，执行初始扫描，并将 `state.yaml` 的 `agent_action` 设为 `generate`，触发 AI 驱动循环。 |
| REQ-03-02 | change 必须记录目标、来源需求、相关代码变更、人工备注和当前状态。 |
| REQ-03-03 | `openqa _advance` 必须读取 `state.yaml` 并自动执行确定性产物生成（scan/impact/matrix），更新 `agent_action` 反映下一步行动类型。 |
| REQ-03-04 | `openqa apply` 必须只在 `phase: ready_for_apply` 且必要产物新鲜时运行。 |
| REQ-03-05 | `openqa archive` 必须在产物完整、报告处理完毕后归档 change。 |
| REQ-03-06 | 未解决 unknowns、blocking Review、失败门禁不得被静默跳过。 |
| REQ-03-07 | `openqa archive` 必须输出可晋升的测试脚本列表，由 Agent 或人工确认后晋升到 `openqa/test_assets/` 并建立锚点文件。 |
| REQ-03-08 | 归档时必须同步更新受影响的 `openqa/suites/` 套件定义。 |
| REQ-03-09 | `openqa run` 时必须对目标模块执行 `knowledge-scan`；触发条件、提取内容和锚点规则见 `REQ_04_SCAN_AND_IMPACT.md`。 |
| REQ-03-10 | `openqa run` 时必须查询 `preconditions.yaml`，为当前 change 的外部前置需求匹配已有路径；外部前置标签由 AI 在 `test_knowledge.md` 的 `external_preconditions` 字段中填写，CLI 不做关键词推断。 |
| REQ-03-11 | `openqa run --from-openspec` 时必须对 OpenSpec 内容做有效性校验，并将结果写入 `openspec_link.yaml`。 |

## change 工作区

change 工作区位于 `openqa/changes/<change-id>/`，完整目录结构见 `REQ_02_WORKSPACE_AND_ARTIFACTS.md`。

## `state.yaml` 结构

```yaml
schema_version: "openqa/state/v1"
change_id: "chg-20260501-login-fix"
phase: "preparing"           # preparing | ready_for_apply | running | done | archived
created_at: "2026-05-01T10:00:00Z"
updated_at: "2026-05-01T10:05:00Z"
scan_scope: "auto"

# AI 驱动循环指令（CLI 写入，AI 读取）
agent_action: "generate"     # generate | run_cli | resolve | wait_user | done
next_cli: "openqa _advance"  # AI 下一步应调用的命令（明确不歧义）

missing: []                  # 当前尚未生成的必需产物列表
blockers: []                 # 阻断项列表

# phase=ready_for_apply 时填充，供 AI 向用户呈现确认摘要
summary:
  cases: 7
  review_issues: 1
  estimated_minutes: 5
  notes: []                  # 需要用户关注的事项

strategy:
  test_suite: "smoke"
  review_level: "changed"
  gate: "local"
```

### `agent_action` 枚举定义

| 值 | 含义 | AI 行动 |
| --- | --- | --- |
| `generate` | 需要 AI 生成 `missing` 中的产物 | 读代码/需求，生成文件，然后调 `next_cli` |
| `run_cli` | 直接执行 CLI 命令 | 调 `next_cli`，等结果，继续循环 |
| `resolve` | 需要 AI 处理 unknowns.md | 逐条解决，能自主解答就解答，不行则问用户 |
| `wait_user` | 需要用户决策 | **停止循环**，呈现决策内容给用户等待回答 |
| `done` | 全部完成 | **停止循环**，向用户汇报完成摘要 |

### `next_cli` 约定

CLI 每次更新 `state.yaml` 时必须填写 `next_cli`，直接告知 AI 下一步调用什么命令，消除歧义：

| 情况 | `next_cli` |
| --- | --- |
| 有缺失产物需 AI 生成 | `"openqa _advance"` （AI 生成后调此命令打卡） |
| 产物已生成，需继续扫描 | `"openqa _advance"` |
| 准备就绪，等用户确认 | `null`（wait_user，不需要 CLI） |
| 用户确认后 | `"openqa apply"` |

## 状态机推进规则

| 当前状态 | 触发者 | 行动 | 产物 |
| --- | --- | --- | --- |
| `run` 刚执行 | CLI | 创建 change 骨架 + 初始扫描 | `intent.md`、`snapshot.json`、`delta.json` |
| `agent_action: run_cli` | AI | 调用 `openqa _advance` | 触发影响分析 |
| 缺 `impact_graph.json` | CLI（`_advance`） | 自动生成影响图 | `impact_graph.json` |
| `agent_action: generate`，缺 `requirements.md` | AI | 读代码，写 EARS 验收项 | `requirements.md` |
| `agent_action: generate`，缺 `test_knowledge.md` | AI | 读代码+需求，写测试知识+Cases 契约 | `test_knowledge.md` |
| `agent_action: generate`，缺 `review_plan.md` | AI | 生成 Review 范围和检查项 | `review_plan.md` |
| `agent_action: run_cli` | AI | 调用 `openqa _advance` | 生成 `test_matrix.json` |
| 产物全部就绪 | CLI（`_advance`） | 写 `summary`，设 `agent_action: wait_user` | `state.yaml` 更新 |
| `agent_action: wait_user` | AI | **停止**，向用户呈现确认摘要 | — |
| 用户确认 | AI | 调用 `openqa apply` | — |
| 存在 unknowns | CLI（`_advance`）| 设 `agent_action: resolve` | `state.yaml` 更新 |
| `agent_action: resolve` | AI | 逐条解决 unknowns，不行则问用户 | `unknowns.md` 更新 |

## 验收标准

- Agent 不依赖聊天历史判断进度，必须以 `state.yaml` 的 `agent_action` 和 `missing` 为准。
- `requirements.md` 中的 EARS ID 必须可被矩阵、Review 和报告引用。
- change 可暂停、恢复、归档。
- `state.yaml` 的 `agent_action` 必须在每次 `openqa _advance` 执行后正确更新。
- AI 生成产物后调用 `openqa _advance`，CLI 验证产物存在并更新状态，不做内容解读。
- `phase: ready_for_apply` 时 `summary` 字段必须有值，供 AI 向用户呈现确认摘要。
