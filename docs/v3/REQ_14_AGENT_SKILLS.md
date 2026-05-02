# REQ_14_AGENT_SKILLS：Agent Skills

## 目标

OpenGuard 必须向 AI 宿主安装结构化的操作手册（Skill），告诉 AI 在每个高层指令下该调用哪些 CLI、读哪些文件、输出什么、何时追问用户。Skill 是 OpenGuard 与 AI 宿主之间的协议层，保证 AI 每次操作都有确定性的流程依据，而不依赖聊天历史或临时推测。

---

## Skill 与 Slash Command 的关系

| 概念 | 作用 |
| --- | --- |
| Slash Command（`/opg:*`） | 触发入口，用户在 AI 宿主聊天框中输入，通知 AI 开始某个操作。 |
| Skill（`SKILL.md`） | 操作手册，AI 宿主加载后知道完整的执行步骤、CLI 调用顺序、产物读写方式和判断规则。 |

两者配合：Slash Command 是"门"，Skill 是"门后的流程"。

---

## 驱动循环协议

这是所有 Skill 共享的核心执行模式。AI 宿主加载 Skill 后必须理解并遵守此协议。

### AI 的两种模式

**自主推进模式**（默认）：在 `state.yaml` 的 `agent_action` 不是 `wait_user` 时，AI 自主推进，不等待用户。

**等待用户模式**：遇到以下情况时，AI 必须停下来向用户呈现信息并等待回答：
- `state.yaml` 的 `agent_action: wait_user`
- 存在无法从代码库自主解答的 unknown（需要领域知识，如"生产服务器地址"）
- CLI 命令报错

### 驱动循环表

每次执行 CLI 或生成产物后，读取 `state.yaml`，根据 `agent_action` 和 `next_cli` 决定下一步：

| `agent_action` | AI 行动 |
| --- | --- |
| `generate` | 生成 `missing` 列出的产物文件，完成后调用 `next_cli` |
| `run_cli` | 直接调用 `next_cli`，等结果，继续循环 |
| `resolve` | 读取 `unknowns.md`；能自主解答的逐条解答；需要用户输入的追问用户，得到答案后继续循环 |
| `wait_user` | **停止**，向用户呈现需要决策的内容，等待回答 |
| `done` | **停止**，向用户汇报完成摘要 |

### 不得停下来的情况

- 生成一个文件（直接生成）
- 调用 `openguard _advance`（直接调用）
- 能从代码库找到答案的 unknown（直接解答后继续）

---

## Skill 安装方式

`openguard init` / `openguard update` 根据检测到的 AI 宿主，将 Skill 文件安装到对应目录：

| AI 宿主 | Skill 目录 |
| --- | --- |
| Cursor | `.cursor/skills/openguard-<name>/SKILL.md` |
| CodeBuddy / WorkBuddy | `.codebuddy/skills/openguard-<name>/SKILL.md` |
| Claude Code | `.claude/skills/openguard-<name>/SKILL.md` |
| Windsurf | `.windsurf/skills/openguard-<name>/SKILL.md` |
| Gemini CLI | `.gemini/skills/openguard-<name>/SKILL.md` |
| Codex CLI | `.codex/skills/openguard-<name>/SKILL.md` |
| 其他 / 未知 | `openguard/commands/<name>.md`（通用 fallback） |

Skill 文件由 OpenGuard 工具生成，不需要用户手写；`openguard update` 可刷新 skill 内容而不影响已有产物。

---

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-14-01 | `openguard init` 必须让用户选择 AI 宿主，向对应 skill 目录安装 `openguard-run`、`openguard-apply`、`openguard-archive` 三个核心 Skill，以及 `openguard-continue`（手动恢复 Skill）。 |
| REQ-14-02 | `openguard update` 必须能刷新已安装的 Skill 内容，且不覆盖已有 `openguard/` 产物。 |
| REQ-14-03 | 每个 Skill 必须是自包含的 Markdown 文件，包含：触发条件、驱动循环协议引用、执行步骤（含 CLI 调用）、输出格式、何时停下来和 guardrails。 |
| REQ-14-04 | Skill 中引用的 CLI 命令必须是真实可执行的 `openguard` 子命令；内部命令 `openguard _advance` 可在 Skill 中出现，但不得出现在用户文档中。 |
| REQ-14-05 | `openguard-run` Skill 必须包含驱动循环协议，AI 在 `openguard run` 执行后自动进入循环，无需用户触发 `/opg:continue`。 |
| REQ-14-06 | `openguard-apply` Skill 必须包含报告解读和 overlay 生成指南。 |
| REQ-14-07 | Skill 必须说明 AI 宿主与 OpenGuard 的通信协议：通过文件产物和 CLI 通信，不在执行过程中直接调用大模型或操作目标应用。 |
| REQ-14-08 | 安装了多个 AI 宿主时，同一套 Skill 内容应安装到所有检测到的宿主目录。 |
| REQ-14-09 | `openguard-run` Skill 必须定义**确认门槛**：`phase: ready_for_apply` 时 AI 必须停下来向用户呈现准备摘要（用例数、Review 问题数、预计执行时间），等待用户明确确认后才允许执行 `openguard apply`。 |
| REQ-14-10 | `openguard-continue`（手动恢复 Skill）触发后，AI 必须读取 `state.yaml` 的 `agent_action` 和 `next_cli`，从当前状态继续驱动循环，不重置已有进度。 |

---

## Skill 内容协议

以下描述每个 Skill 文件必须涵盖的内容约定。

---

### `openguard-run` Skill 协议

**触发**：用户输入 `/opg:run <目标>` 或明确要开始一次新的测试任务。

**执行模式**：**自主驱动模式**——执行后自动进入驱动循环，无需用户再次触发，直到 `wait_user` 门槛点。

**行为协议**：

1. 若目标描述不明确，追问用户"这次要验证什么？"，不猜测。这是唯一允许的前置停止点。
2. 调用 `openguard run "<目标>" [参数]`，创建 change 工作区并执行初始扫描。
3. 读取 `state.yaml`，进入**驱动循环**（见驱动循环协议）。
4. 在循环中：
   - `generate`：读代码/需求，生成对应产物，然后调用 `openguard _advance`
   - `run_cli`：直接调用 `next_cli`，继续循环
   - `resolve`：处理 unknowns，能自主解答就解答，否则追问用户后继续
   - `wait_user`：**停止**，向用户呈现确认摘要，等待确认
5. 用户确认后，提示执行 `/opg:apply`。

**生成 `test_knowledge.md` 时**，必须包含：
- YAML front matter 的 `external_preconditions`（仅列出本 change 内任何用例都无法产出的状态，其余填 `[]`）
- `## Cases` JSON 块，声明每个用例的 `produces_tags` 和 `required_precondition_tags`

**约束**：
- 若已有同名 change，询问用户是否继续还是新建，不静默覆盖。
- 生成的测试脚本只写入 `openguard/changes/<id>/test_scripts/`，不写入目标项目代码目录。
- `phase: ready_for_apply` 时**必须**停下来等用户确认，不得自动执行 `apply`。

---

### `openguard-continue`（手动恢复 Skill）协议

**触发**：用户输入 `/opg:continue`，用于 AI 中断后手动恢复，或用户想查看当前进度。

**说明**：正常流程中用户无需触发此命令，`/opg:run` 会自动驱动。此命令仅用于恢复和调试。

**行为协议**：

1. 读取最新 change 的 `state.yaml`，获取 `agent_action`、`next_cli`、`missing`。
2. 向用户简报当前进度（phase、已完成产物、缺失产物）。
3. 根据 `agent_action` 进入**驱动循环**，从当前状态继续推进。

**约束**：不重置已有进度；不重新生成已存在且新鲜的产物。

---

### `openguard-apply` Skill 协议

**触发**：用户输入 `/opg:apply` 或明确要执行测试。**必须在用户确认后才能执行。**

**输入**：可选 `--suite <name>`、`--test-suite`、`--gate`、`--review-level`。

**行为协议**：

1. 调用 `openguard apply [参数]`，OpenGuard 执行器负责启动应用、调度脚本、采集证据。
2. 执行期间 AI 宿主不操作目标应用，等待执行器完成。
3. 执行完成后，读取 `run_report.md`、`timeline.md`、`run_report.json` 进行分析。
4. 区分失败类型（环境 / 前置 / 脚本 / 产品 / 未知）；`UNKNOWN` 结果输出需补充证据的建议，不当 PASS 处理。
5. 若有归因建议，生成 `report_overlay.yaml` 并合并。
6. 输出执行结论、Run ID、失败摘要和建议下一步（`/opg:archive` 或重新 `apply`）。

**约束**：
- AI 宿主不直接操作目标应用，执行由 OpenGuard 执行器负责。
- 低置信度归因只进入 overlay 待确认区，不自动修改代码或产物。
- `UNKNOWN` 不得当 `PASS` 汇报给用户。

---

### `openguard-archive` Skill 协议

**触发**：用户输入 `/opg:archive` 或明确要归档当前 change。

**行为协议**：

1. 调用 `openguard archive --dry-run`，获取归档前检查清单。
2. 检查是否有未解决的 unknowns、blocking Review finding、未通过的门禁报告、不完整的执行报告。
3. 若有阻断项，列出并询问用户是否豁免（必须记录豁免原因）。
4. 输出本次 change 中可晋升的测试脚本列表，说明建议加入的套件。
5. **等待用户确认**后，调用 `openguard archive`，执行归档和脚本晋升。
6. 输出归档位置、晋升脚本列表、沉淀的知识摘要和建议下一步。

**约束**：
- 不自动跳过 blocking Review 和失败门禁，必须人工确认。
- 脚本晋升必须由用户或 AI 确认，不自动执行。
- 单次执行通过的脚本不得直接晋升。

---

## 验收标准

- AI 宿主加载 Skill 后，`/opg:run` 能自主推进所有准备产物直到确认门槛，无需用户手动 `/opg:continue`。
- `openguard-run` 生成的测试脚本只存在于 `openguard/` 目录内。
- `openguard-apply` 执行期间 AI 宿主不直接操作目标应用。
- `phase: ready_for_apply` 时 AI 必须停下来等用户确认，不得自动执行 `apply`。
- `openguard-archive` 晋升脚本必须有对应的 Run ID 历史依据。
- `openguard update` 刷新 Skill 后，已有 change 工作区和 test_assets 不受影响。
- `openguard help` 不展示 `openguard _advance` 内部命令。

