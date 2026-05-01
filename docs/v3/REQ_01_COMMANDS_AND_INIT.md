# REQ_01_COMMANDS_AND_INIT：指令与初始化

## 目标

OpenQA 应提供极少量、稳定、易记的高层指令，参考 OpenSpec 的轻量交互方式，让用户只感知业务语义，底层扫描、产物生成、状态推进由 AI 驱动循环自主完成。

**核心设计原则：**
- 用户只暴露**业务动作**指令，不暴露工具内部机制
- **确定性操作**由 CLI 工具完成，**需要理解/推理**的由 AI 完成
- AI 多轮交互对用户透明，用户只感知"正在准备"和"需要你决策"两种状态
- 内部工具命令（如 `_advance`）不出现在用户文档、Slash Commands 和帮助信息中

## 范围

包含 CLI 指令、Slash Commands、初始化体验、项目测试画像、策略参数、驱动循环协议。不包含具体扫描器、执行器实现。

## 指令分层

### 用户指令（用户可见、可记忆）

| 指令 | 用户语义 | 说明 |
| --- | --- | --- |
| `openqa init` | 初始化项目 | 在当前项目初始化 `openqa/` 工作区，生成项目测试画像，向 AI 宿主安装 Skill 和 Slash Commands。**只在项目首次配置时执行一次。** |
| `openqa run <目标>` | 开始一次测试任务 | 为一次需求/代码修改/缺陷修复创建 change 工作区，并自动触发 AI 驱动循环推进所有准备产物，直到需要用户确认。 |
| `openqa apply` | 执行测试 | 用户确认准备就绪后，执行代码 Review、测试矩阵、证据采集、报告生成。 |
| `openqa archive` | 归档并沉淀经验 | 关闭已完成 change，晋升稳定脚本，沉淀知识。 |
| `openqa update` | 刷新工具指令 | 刷新已安装的 Skill 和 Slash Commands，不改变已有产物。 |
| `openqa help` | 帮助 | 输出用户指令、参数和当前项目建议下一步。 |

### 内部命令（AI 调用，用户不感知）

| 命令 | 用途 |
| --- | --- |
| `openqa _advance` | 状态机推进：检查产物就绪状态、执行确定性自动生成（scan/impact/matrix）、更新 `state.yaml`。由 AI 在驱动循环中调用，不出现在用户文档和帮助信息中。 |

> `openqa continue` 重命名为 `openqa _advance`，下划线前缀约定为内部命令，`help` 不展示。`/oqa:continue` Slash Command 保留作为手动恢复入口（见下方）。

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-01-01 | 系统必须提供 `openqa init`，在当前项目初始化 `openqa/` 工作区、配置，并向用户选定的 AI 宿主安装 Slash Commands 和 Skill。 |
| REQ-01-02 | 系统必须提供 `openqa update`，刷新 Slash Commands、Skill、schema、模板，且不得破坏已有产物。 |
| REQ-01-03 | 系统必须提供 `openqa run <目标>`，用于开始一次需求、代码修改或缺陷修复对应的 QA change，并自动触发 AI 驱动循环推进准备阶段。 |
| REQ-01-04 | 系统必须提供内部命令 `openqa _advance`，由 AI 在驱动循环中调用，执行确定性产物生成和状态推进；该命令不出现在 `help` 输出、Slash Commands 和用户文档中。 |
| REQ-01-05 | 系统必须提供 `openqa apply`，执行代码 Review、测试、采证、报告生成和确认结果合并。 |
| REQ-01-06 | `openqa apply` 必须支持 `--suite <name>` 参数，在无 change 上下文时直接执行 `openqa/suites/<name>/` 中定义的全局测试套件。 |
| REQ-01-07 | 系统必须提供 `openqa archive`，归档已完成 change 并沉淀稳定知识。 |
| REQ-01-08 | 系统必须提供 `openqa help`，输出**用户指令**（不含内部命令）、参数、策略和当前项目下一步建议。 |
| REQ-01-09 | 系统必须根据用户选定的 AI 宿主，将 `/oqa:*` Slash Commands 安装到对应宿主目录。 |
| REQ-01-10 | `scan_scope`、`test_suite`、`review_level`、`gate` 必须作为策略参数或配置项存在，而不是新增一线命令。 |
| REQ-01-11 | 测试脚本必须生成在 `openqa/` 目录内，不得写入目标项目的源码目录；change 工作区内的脚本为草稿，稳定后经 `archive` 晋升到 `openqa/test_assets/`。 |
| REQ-01-12 | `openqa init` 必须生成项目测试画像，至少包含 `project.type`、AI 宿主、扫描范围、运行方式、自动化控制方式、证据采集和默认门禁。 |
| REQ-01-13 | `openqa init` 必须采用"探测优先、必要追问"策略：能通过扫描、工具链探测或 Agent 基于证据决策确定的配置，不应要求用户手工选择。 |
| REQ-01-14 | `openqa init` 必须支持 `web`、`web-game` / `webgl`、`unity`、`unreal`、`backend` / `api`、`mixed`、`unknown` 等项目类型画像。 |
| REQ-01-15 | `openqa init` 只应追问无法可靠推断、存在多解且影响执行、涉及本机环境路径、权限、设备、账号环境或外部服务的信息。 |
| REQ-01-16 | `openqa init` 必须支持非交互参数，例如 `--lang <zh\|en>`、`--profile <type>`、`--host <ai-host>`、`--gate <gate>`、`--yes`，用于 CI、模板工程和脚本化初始化。 |
| REQ-01-17 | `openqa init --reconfigure` 必须允许重新配置项目测试画像和 AI 宿主，并保留已有 changes、reports、knowledge 和人工维护配置。 |
| REQ-01-18 | 自动推断或 Agent 决策生成的画像字段必须记录来源、置信度、决策方式和缺失项；低置信度结果不得静默当作确定配置。 |
| REQ-01-19 | `openqa init` 必须通过多选菜单让用户主动选择 AI 宿主（Cursor / CodeBuddy / Claude Code 等，可多选）；探测到已有宿主目录时预勾选对应项作为推荐，但最终安装以用户选择为准。 |
| REQ-01-20 | `openqa update` 必须能刷新已安装的 Skill 内容，且不覆盖已有 `openqa/` 产物、changes、reports 和 knowledge。 |
| REQ-01-21 | `openqa init` 必须生成 `.gitignore` 建议规则，推荐排除大型执行证据，保留 `openqa/changes/`、`openqa/test_assets/`、`openqa/suites/`、`openqa/knowledge/`。 |
| REQ-01-22 | `openqa init` 必须支持中文和英文两种语言；第一步询问用户语言偏好，之后所有交互输出均使用所选语言。 |
| REQ-01-23 | 所有用户指令（`init`、`run`、`apply`、`archive`、`update`）在执行期间必须向终端实时输出当前步骤状态，不得出现无任何输出的静默等待。 |
| REQ-01-24 | 耗时操作开始时必须显示 spinner 动画；操作完成后替换为 `✓`（成功）或 `✗`（失败）加步骤描述的固定行。 |
| REQ-01-25 | 每个顶层步骤完成后必须以独立一行打印最终结果，使用户能清楚区分"已完成"、"进行中"、"已跳过"三种状态。 |
| REQ-01-26 | 步骤输出必须包含步骤名称；耗时超过 3 秒的步骤还应在该行末尾追加实际耗时。 |
| REQ-01-27 | 在非交互模式（`--yes` 参数或检测到非 TTY 环境）下，必须禁用 spinner 动画，改为逐行打印纯文本进度。 |
| REQ-01-34 | `openqa run` 在创建 change 工作区并完成确定性初始扫描后，必须向 AI 输出 `state.yaml` 路径和 `agent_action: generate`，触发 AI 驱动循环，无需用户额外输入。 |
| REQ-01-35 | AI 驱动循环必须在以下情况下**自动停止**并等待用户输入：`state.yaml` 中 `agent_action: wait_user`；存在无法从代码库自主解答的 unknown；CLI 命令报错。 |
| REQ-01-36 | AI 驱动循环在以下情况下**不得停止**，必须自主推进：生成产物文件；调用 `openqa _advance`；解答可从代码库确定的 unknown。 |
| REQ-01-37 | `openqa run` 完成准备阶段（`phase: ready_for_apply`）时，AI 必须向用户呈现确认摘要（用例数、Review 问题数、预计执行时间），等待用户明确确认后才允许执行 `openqa apply`。 |
| REQ-01-38 | `/oqa:continue` Slash Command 作为**手动恢复入口**保留，供 AI 中断/对话超长/用户想手动干预时使用；正常流程无需用户主动触发。 |

## AI 宿主安装约定

| AI 宿主 | Slash Commands 目录 | Skill 目录 |
| --- | --- | --- |
| Cursor | `.cursor/rules/` | `.cursor/skills/openqa-<name>/SKILL.md` |
| CodeBuddy | `.codebuddy/commands/` | `.codebuddy/skills/openqa-<name>/SKILL.md` |
| Claude Code | `.claude/commands/` | `.claude/skills/openqa-<name>/SKILL.md` |
| Windsurf | `.windsurf/rules/` | `.windsurf/skills/openqa-<name>/SKILL.md` |
| Gemini CLI | `.gemini/commands/` | `.gemini/skills/openqa-<name>/SKILL.md` |
| Codex CLI | `.codex/commands/` | `.codex/skills/openqa-<name>/SKILL.md` |
| 通用 fallback | `openqa/commands/` | `openqa/commands/<name>.md` |

## 典型用户流程

```
# 1. 项目首次初始化（只做一次）
openqa init

# 2. 开始一次测试任务（AI 自主推进准备阶段）
/oqa:run "测试登录流程"
  → AI 内部循环（用户不感知）：
      openqa run "测试登录流程"   # 创建 change + 初始扫描
      [AI 生成 requirements.md]
      openqa _advance             # 确定性产物生成 + 状态更新
      [AI 生成 test_knowledge.md + review_plan.md]
      openqa _advance             # 生成 test_matrix.json + 状态更新
  → AI 停下来汇报：
      "准备完成：7 个测试用例，1 个 Review 问题需关注，预计 5 分钟
       是否执行？"

# 3. 用户确认后执行
/oqa:apply

# 4. 归档（可选）
/oqa:archive
```

## 初始化体验

`openqa init` 流程：**选择语言 → 扫描项目 → 展示检测结果与推荐决策 → 补充缺失信息**。

```text
Welcome to OpenQA / 欢迎使用 OpenQA

? Select language / 选择语言:
  > 中文
    English
```

**中文模式示例：**

```text
欢迎使用 OpenQA
面向 AI 编码宿主的自动化测试框架

正在扫描项目...

检测到 Unity 项目:
  project.type:    unity                置信度: high
  detected_from:   Assets/, ProjectSettings/, ProjectSettings/ProjectVersion.txt
  unity.version:   2019.4.41f1
  test.framework:  Unity Test Framework
  tests.detected:  PlayMode
  scenes.detected: 12

推荐配置:
  runtime.mode:    editor-playmode      决策依据: 自动
  evidence:        日志 + 截图 + 视频 + 状态快照

? 请选择你使用的 AI 编程工具（可多选）:
  ✓ CodeBuddy   [已检测到 .codebuddy/]
  ✓ Cursor      [已检测到 .cursor/]
    Claude Code
    其他 / 跳过

✓ 已创建 openqa/ 工作区
✓ 已写入 openqa/config.yaml
✓ 已安装 openqa-* skills
✓ 已更新 .gitignore

快速开始:
  /oqa:run    开始一次测试任务（AI 自主推进准备，完成后等你确认执行）
  /oqa:apply  确认后执行测试
```

## 执行过程可见性

所有命令在执行期间必须持续向终端输出进度，杜绝无任何输出的静默等待。采用两层反馈机制：

- **Spinner**：耗时步骤进行中时显示旋转动画，完成后原地替换为 `✓` / `✗` + 步骤名（TTY 模式）。
- **Step 逐行确认**：每个顶层步骤完成后独立打印一行最终状态，形成完整的执行记录。

非 TTY 或 `--yes` 模式下禁用 spinner，改为逐行纯文本输出。

## 初始化决策原则

`openqa init` 不应被设计成传统配置问卷。它应先扫描项目和工具链，生成候选画像，再由确定性规则或 AI 宿主基于证据选择默认决策，最后只询问必要信息。

| 信息类型 | 处理方式 |
| --- | --- |
| 可通过文件结构、manifest、配置文件、已有测试框架、构建产物推断的信息 | 自动写入画像，并记录 `detected_from` 和 `confidence`。 |
| 可由规则或 Agent 基于证据选择的默认策略 | 自动决策，并记录 `decided_by`、`evidence` 和置信度。 |
| 存在多个合理选择且会影响执行成本或结果的信息 | 给出推荐值和理由，仅让用户确认差异项。 |
| 本机环境路径、设备、权限、账号环境、外部服务地址或无法扫描的信息 | 询问用户；涉及敏感信息时只保存环境变量名、凭证别名或占位符。 |
| 低置信度或互相冲突的信息 | 写入 `unknowns` 或 `missing`，不静默生成确定结论。 |

## 项目测试画像

`openqa init` 应把用户确认或自动决策后的画像写入 `openqa/config.yaml`，供后续 `run`、`_advance`、`apply` 统一消费。

| 画像字段 | 说明 |
| --- | --- |
| `project.type` | 项目测试类型，例如 `web`、`webgl`、`unity`、`unreal`、`api`、`mixed`。 |
| `ai_hosts` | 需要安装 `/oqa:*` 指令的 AI 宿主。 |
| `scan` | 默认扫描范围、包含/排除目录、语言和分析器提示。 |
| `runtime` | 应用启动方式、构建路径、健康检查、超时和运行模式。 |
| `automation` | 控制通道，例如 Playwright、引擎内 bridge、RPC、WebSocket、命令行或黑盒 UI。 |
| `evidence` | 默认采集的日志、截图、视频、状态快照、网络或 RPC 证据。 |
| `defaults` | 默认 `gate`、`test_suite`、`review_level`、超时和并发预算。 |
| `confidence` / `detected_from` / `decided_by` / `missing` | 每个关键推断字段的置信度、证据来源、决策方式和待补充项。 |

## 验收标准

- 用户完成初始化后，可以通过 `/oqa:run` 开启一个测试任务。
- `/oqa:run` 后 AI 自主推进所有准备产物，无需用户手动触发 `/oqa:continue`。
- AI 驱动循环中遇到无法自主解答的问题时，自动停下来向用户追问，用户回答后继续，无需用户显式"继续"。
- 准备完成后 AI 必须呈现确认摘要并等待用户确认，用户不确认不得自动执行 `apply`。
- 初始化后的 `openqa/config.yaml` 能说明当前项目按哪种测试画像运行，后续扫描、矩阵和执行不得仅依赖聊天历史猜测项目类型。
- `openqa help` 不展示内部命令（`_advance` 等）。
- 更新指令模板或重新配置画像时，已有 `openqa/changes/`、`openqa/reports/`、`openqa/knowledge/` 不被覆盖。

---

## 调试命令

`openqa debug` 是仅在**调试构建**中可用的命令入口，正式发布包中完全屏蔽。

### 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-01-28 | 系统必须提供 `openqa debug` 命令作为调试命令入口，支持子命令扩展；该命令仅在调试构建中可用，正式发布包中必须完全屏蔽。 |
| REQ-01-29 | `openqa debug clean` 必须将项目还原到 `openqa init` 执行前的状态，清除范围包括：`openqa/` 目录、已安装到各 AI 宿主目录的 `/oqa:*` slash commands 和 `openqa-*` skill 文件、`.gitignore` 中由 openqa 追加的规则块。 |
| REQ-01-30 | `openqa debug clean` 执行前必须显示确认提示，列出将被删除的内容摘要；用户输入 `y` 或 `yes` 后才执行；支持 `--yes` 参数跳过确认。 |
| REQ-01-31 | 确认提示的语言必须跟随 `openqa/config.yaml` 中记录的语言偏好；若 config 不存在，默认使用英文。 |
| REQ-01-32 | `openqa debug clean` 执行时必须遵循过程可见性要求，逐步输出每项删除结果。 |
| REQ-01-33 | `openqa debug` 的所有子命令必须在帮助文本中标注 `[debug build only]`；正式构建中 `openqa help` 不展示任何 `debug` 子命令。 |






## 初始化体验

`openqa init` 流程分四步：**选择语言 → 扫描项目 → 展示检测结果与推荐决策 → 补充缺失信息**。

第一步询问语言偏好（在所有其他输出之前）：

```text
Welcome to OpenQA / 欢迎使用 OpenQA

? Select language / 选择语言:
  > 中文
    English
```

选择语言后，后续所有输出切换为所选语言。

**中文模式示例：**

```text
欢迎使用 OpenQA
面向 AI 编码宿主的自动化测试框架

正在扫描项目...

检测到 Unity 项目:
  project.type:    unity                置信度: high
  detected_from:   Assets/, ProjectSettings/, ProjectSettings/ProjectVersion.txt
  unity.version:   2019.4.41f1
  test.framework:  Unity Test Framework
  tests.detected:  PlayMode
  scenes.detected: 12

推荐配置:
  runtime.mode:    editor-playmode      决策依据: 自动
  evidence:        日志 + 截图 + 视频 + 状态快照

? 请选择你使用的 AI 编程工具（可多选）:
  ✓ CodeBuddy   [已检测到 .codebuddy/]
  ✓ Cursor      [已检测到 .cursor/]
    Claude Code
    其他 / 跳过

需要补充的信息:

  ? unity.editor_path（Unity 编辑器路径）:
  ? control_channel.url_or_env（控制通道地址或环境变量名）:

✓ 已创建 openqa/ 工作区: D:\Work\SLG\AOEX\AOE3D\openqa
✓ 已写入 openqa/config.yaml
✓ 已安装 openqa-* skills
✓ 已更新 .gitignore

快速开始:
  /oqa:new       开启一次测试变更
  /oqa:continue  推进下一步
  /oqa:apply     执行 Review 与测试
  /oqa:archive   归档并沉淀经验
```

**英文模式示例：**

```text
Scanning project...

Detected Unity project:
  project.type:    unity                confidence: high
  detected_from:   Assets/, ProjectSettings/, ProjectSettings/ProjectVersion.txt
  unity.version:   2019.4.41f1
  test.framework:  Unity Test Framework
  tests.detected:  PlayMode
  scenes.detected: 12

Recommended decisions:
  runtime.mode:    editor-playmode      decided_by: auto
  evidence:        logs + screenshots + video + state_snapshot

? Select AI coding tools to install skills into (multi-select):
  ✓ CodeBuddy   [detected .codebuddy/]
  ✓ Cursor      [detected .cursor/]
    Claude Code
    Other / Skip

Required input before real execution:

  ? unity.editor_path:
  ? control_channel.url_or_env:

✓ Created openqa/ workspace at D:\Work\SLG\AOEX\AOE3D\openqa
✓ Written openqa/config.yaml
✓ Installed openqa-* skills
✓ Updated .gitignore

Quick start:
  /oqa:new       Start a QA change
  /oqa:continue  Next artifact
  /oqa:apply     Review, run and merge results
  /oqa:archive   Close and learn
```


## 执行过程可见性

所有命令在执行期间必须持续向终端输出进度，杜绝无任何输出的静默等待。采用两层反馈机制：

- **Spinner**：耗时步骤进行中时显示旋转动画，完成后原地替换为 `✓` / `✗` + 步骤名（TTY 模式）。
- **Step 逐行确认**：每个顶层步骤完成后独立打印一行最终状态，形成完整的执行记录。

非 TTY 或 `--yes` 模式下禁用 spinner，改为逐行纯文本输出。

**终端输出示例（`openqa init`，TTY 模式）：**

```text
⠸ Scanning project...
✓ Scanning project...                                          1.2s

⠼ Installing /oqa:* commands for codebuddy...
✓ Installed /oqa:* commands for codebuddy (12 files)

⠴ Installing /oqa:* commands for cursor...
✓ Installed /oqa:* commands for cursor (12 files)

⠦ Installing openqa-* skills...
✓ Installed openqa-* skills for codebuddy (3 files)

⠧ Writing openqa/config.yaml...
✓ Written openqa/config.yaml

⠇ Updating .gitignore...
✓ Updated .gitignore
```

**终端输出示例（`openqa apply`，TTY 模式）：**

```text
⠸ Running code review...
✓ Code review complete — 2 findings (0 blocking)             3.4s

⠼ Executing test suite: smoke...
  ✓ login_flow                                               0.8s
  ✓ home_page_load                                           1.1s
  ✗ checkout_button [failed]                                 2.0s
✓ Test suite done — 2 passed, 1 failed                       4.1s

⠴ Collecting evidence...
✓ Evidence collected — logs + 3 screenshots

⠦ Generating report...
✓ Report written: openqa/reports/r-20260501-001/report.md
```

**非 TTY / CI 模式（`--yes` 或管道输出）：**

```text
[init] Scanning project...
[init] Scanning project... done (1.2s)
[init] Installing /oqa:* commands for codebuddy... done
[init] Installing openqa-* skills... done
[init] Written openqa/config.yaml
[init] Updated .gitignore
```







## 初始化决策原则

`openqa init` 不应被设计成传统配置问卷。它应先扫描项目和工具链，生成候选画像，再由确定性规则或 AI 宿主基于证据选择默认决策，最后只询问必要信息。

| 信息类型 | 处理方式 |
| --- | --- |
| 可通过文件结构、manifest、配置文件、已有测试框架、构建产物推断的信息 | 自动写入画像，并记录 `detected_from` 和 `confidence`。 |
| 可由规则或 Agent 基于证据选择的默认策略，例如执行模式、默认测试套件、证据类型 | 自动决策，并记录 `decided_by`、`evidence` 和置信度。 |
| 存在多个合理选择且会影响执行成本或结果的信息 | 给出推荐值和理由，仅让用户确认差异项。 |
| 本机环境路径、设备、权限、账号环境、外部服务地址或无法扫描的信息 | 询问用户；涉及敏感信息时只保存环境变量名、凭证别名或占位符。 |
| 低置信度或互相冲突的信息 | 写入 `unknowns` 或 `missing`，不静默生成确定结论。 |

## 项目测试画像

`openqa init` 应把用户确认或自动决策后的画像写入 `openqa/config.yaml`，供后续 `new`、`continue`、`apply` 统一消费。


| 画像字段 | 说明 |
| --- | --- |
| `project.type` | 项目测试类型，例如 `web`、`webgl`、`unity`、`unreal`、`api`、`mixed`。 |
| `ai_hosts` | 需要安装 `/oqa:*` 指令的 AI 宿主。 |
| `scan` | 默认扫描范围、包含/排除目录、语言和分析器提示。 |
| `runtime` | 应用启动方式、构建路径、健康检查、超时和运行模式。 |
| `automation` | 控制通道，例如 Playwright、引擎内 bridge、RPC、WebSocket、命令行或黑盒 UI。 |
| `evidence` | 默认采集的日志、截图、视频、状态快照、网络或 RPC 证据。 |
| `defaults` | 默认 `gate`、`test_suite`、`review_level`、超时和并发预算。 |
| `confidence` / `detected_from` / `decided_by` / `missing` | 每个关键推断字段的置信度、证据来源、决策方式和待补充项。 |

## 分类型自动探测与必要追问

| 项目类型 | 应自动探测或决策 | 仅在缺失或多解时询问 |
| --- | --- | --- |
| `web` / `h5` | `package.json`、启动脚本、框架、Playwright / Cypress 配置、默认端口、已有测试命令、浏览器证据类型。 | 多个启动脚本同等合理、无法确认访问 URL、登录环境或外部服务选择。 |
| `web-game` / `webgl` | WebGL 构建目录、浏览器外壳、资源目录、加载完成线索、JS bridge / WebSocket 痕迹、性能和资源基线候选。 | 构建目录不标准、桥接端口未知、多个入口页面或运行环境并存。 |
| `unity` | `Assets/`、`ProjectSettings/`、Unity 版本、包依赖、Unity Test Framework、EditMode / PlayMode 测试、scene 列表、常规日志和忽略目录、已有构建产物。 | Unity Editor 路径、多个执行模式都合理、目标平台、真机设备、非标准构建路径、内部 RPC / WebSocket 端口。 |
| `unreal` | `.uproject`、`Config/`、`Content/`、`Source/`、Automation Spec、map / level、packaged build 候选、日志和 crash dump 约定。 | Unreal Editor 路径、Editor automation 与 packaged build 取舍、dedicated server / client 组合、非标准构建路径。 |
| `backend` / `api` | 语言和框架、服务启动脚本、OpenAPI / gRPC / Postman 入口、测试命令、健康检查候选、依赖服务线索。 | 多个服务入口、环境选择、不可扫描的依赖服务地址、测试账号或数据来源。 |
| `mixed` | 子项目列表、每个子项目类型、依赖关系、默认影响子图和候选执行顺序。 | 默认 change 入口、跨项目端到端环境、多个子项目执行优先级。 |
| `unknown` | 已知文件结构、语言、测试框架和可用命令。 | 项目类型、运行方式、控制通道等无法由证据确认的信息。 |

## 验收标准

- 用户完成初始化后，可以通过 `/oqa:new` 开启一个 change。
- 若项目安装 OpenSpec，初始化后应提示可使用 `openqa new --from-openspec <change-id>`。
- 初始化后的 `openqa/config.yaml` 能说明当前项目按哪种测试画像运行，后续扫描、矩阵和执行不得仅依赖聊天历史猜测项目类型。
- 可自动探测或决策的信息不应反复询问用户；用户只需补充无法可靠推断的必要信息。
- 项目运行方式未配置完整时，`continue` 可以继续生成需求、Review 和矩阵；只有真实执行必需配置缺失时，`apply` 才应提示补齐必要 runtime 配置。
- 更新指令模板或重新配置画像时，已有 `openqa/changes/`、`openqa/reports/`、`openqa/knowledge/` 不被覆盖。
- 日常交互不要求用户直接理解底层扫描、矩阵、报告命令。

---

## 调试命令

`openqa debug` 是仅在**调试构建**中可用的命令入口，正式发布包中完全屏蔽。它不承担任何生产功能，仅用于开发阶段的状态重置和验证。

### 终端示例（`openqa debug clean`，中文模式）

```text
openqa debug clean

警告：此操作将清除以下内容：
  • openqa/ 目录（含所有 changes、reports、knowledge、config）
  • .cursor/commands/ 中的 /oqa:* 命令文件
  • .cursor/skills/ 中的 openqa-* skill 文件
  • .codebuddy/commands/ 中的 /oqa:* 命令文件
  • .codebuddy/skills/ 中的 openqa-* skill 文件
  • .gitignore 中由 openqa 追加的规则块

执行后项目将还原到 openqa init 之前的状态，此操作不可撤销。

确认清除？[y/N] y

⠸ 删除 openqa/ 目录...
✓ 已删除 openqa/

⠸ 删除 AI 宿主目录中的 openqa 文件...
✓ 已删除 .cursor/commands/ 中的 /oqa:* 文件（12 个）
✓ 已删除 .cursor/skills/ 中的 openqa-* 目录（3 个）
✓ 已删除 .codebuddy/commands/ 中的 /oqa:* 文件（12 个）
✓ 已删除 .codebuddy/skills/ 中的 openqa-* 目录（3 个）

⠸ 清理 .gitignore 中的 openqa 规则...
✓ 已清理 .gitignore

已还原到初始化前状态。运行 openqa init 重新初始化。
```

### 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-01-28 | 系统必须提供 `openqa debug` 命令作为调试命令入口，支持子命令扩展；该命令仅在调试构建（debug build）中可用，正式发布包中必须完全屏蔽，不得以报错形式存在。 |
| REQ-01-29 | `openqa debug clean` 必须将项目还原到 `openqa init` 执行前的状态，清除范围包括：`openqa/` 目录、已安装到各 AI 宿主目录的 `/oqa:*` slash commands 和 `openqa-*` skill 文件、`.gitignore` 中由 openqa 追加的规则块。 |
| REQ-01-30 | `openqa debug clean` 执行前必须显示确认提示，列出将被删除的内容摘要；用户输入 `y` 或 `yes` 后才执行；支持 `--yes` 参数跳过确认（仅用于自动化测试场景）。 |
| REQ-01-31 | 确认提示的语言必须跟随 `openqa/config.yaml` 中记录的语言偏好；若 config 不存在，默认使用英文。 |
| REQ-01-32 | `openqa debug clean` 执行时必须遵循 REQ-01-23 ~ 27 的过程可见性要求，逐步输出每项删除结果，最终输出"已还原到初始化前状态"（中文）或"Restored to pre-init state."（英文）。 |
| REQ-01-33 | `openqa debug` 的所有子命令必须在帮助文本中标注 `[debug build only]`；正式构建中 `openqa help` 不展示任何 `debug` 子命令。 |


