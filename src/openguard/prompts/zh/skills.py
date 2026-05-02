"""Skill SKILL.md content — 中文。

格式遵循 CodeBuddy Skill 规范：
  - YAML frontmatter：name + description（必填）
  - Markdown 正文：指令性语言，动词开头，< 5k 词
"""
from __future__ import annotations


SKILL_RUN = """\
---
name: openguard-run
description: >
  当用户输入 /opg:run 或明确要开始一次测试任务时使用此 Skill。
---

# openguard-run

## 触发条件
用户输入 `/opg:run <目标>` 或明确表示要开始一次需求/代码修改/缺陷修复对应的测试任务。

## 执行模式
此 Skill 采用**自主驱动模式**：创建 change 后，无需等待用户，持续推进所有产物，
直到遇到 `wait_user` 门槛点或需要人类输入的真正 unknown。
用户说的是 `/opg:run`，不是 `/opg:run 然后停下来等待`。

## 步骤

**1. 确认目标**
若描述不清，追问"这次要验证什么？"，不猜测意图。

**2. 创建 change**
在终端执行：
```
openguard run "<目标>" [--from-openspec <id>] [--test-suite <suite>]
```

**3. 进入驱动循环**
命令完成后，读取 `state.yaml`，进入驱动循环（见驱动循环表格）。
持续循环直到满足停止条件。

**4. 向用户汇报**
仅在驱动循环停止时汇报。汇报：change ID、已生成内容、当前状态、用户需要决策的事项（如有）。

## 驱动循环

每次执行 CLI 命令或生成产物后，读取 `state.yaml`，根据 `agent_action` 决定下一步：

| `agent_action` | 行动 |
| --- | --- |
| `run_cli` | 调用 `next_cli`，然后循环 |
| `generate` | 生成 `missing` 中列出的产物，写入后调用 `next_cli`，然后循环 |
| `resolve` | 读取 `unknowns.md`；能自主解决的逐条解决；需要用户输入的追问用户，得到答案后继续循环 |
| `wait_user` | **停止。** 向用户呈现需要决策的内容，等待回答 |
| `done` | **停止。** 向用户汇报完成摘要 |

**必须停下来的情况：**
- `agent_action: wait_user`（特别是 `phase: ready_for_apply`，需要呈现摘要等用户确认）
- 无法从代码库自主解答的真正 unknown（如"生产服务器地址是什么？"）
- 需要先修复代码的 blocker
- CLI 命令报错

**不必停下来的情况：**
- 生成文件（直接生成）
- 调用 `openguard _advance`（直接调用）
- 能从代码库找到答案的 unknown（直接解答后继续）

## 生成 test_knowledge.md 时

必须包含两个机器可读部分：

**a) YAML front matter：**
```yaml
external_preconditions:
  - some_state   # 仅当本 change 内没有任何用例能产出此状态；否则填 []
scene_map:        # Unity 项目专用：执行器据此自动选择入口场景
  login: Assets/Scenes/Login.unity   # key = 逻辑名称，value = 场景路径
  main: Assets/Scenes/Main.unity
```

**b) `## Cases` JSON 块：**
```json
[
  {
    "id": "AC-001",
    "title": "正常登录",
    "produces_tags": ["logged_in"],
    "required_precondition_tags": []
  },
  {
    "id": "AC-005",
    "title": "断线重连",
    "produces_tags": [],
    "required_precondition_tags": ["logged_in"]
  }
]
```

填写规则：
- `produces_tags`：该用例通过后系统所处的状态标签
- `required_precondition_tags`：该用例运行前系统必须处于的状态标签
- 若 B 需要 `logged_in` 而 A 能产出 `logged_in`，矩阵自动将 A 排在 B 前面，不要加入 `external_preconditions`
- 只有当本 change 内没有任何用例能产出所需状态时，才加入 `external_preconditions`
- 必须基于用例实际语义，不得用关键词猜测

## 生成测试脚本时
- 读取 `config.yaml` 中的 `project.type`、`runtime`、`automation`
- `verified` → 直接引用
- `needs-review` → 可引用但须标注
- `stale`/`broken` → 在 `openguard/changes/<id>/test_scripts/` 生成新草稿
- 控制通道选择：
  - `web`/`h5`：Playwright
  - `webgl`/`web-game`：Playwright + JS bridge / WebSocket
  - `unity`：Unity Test Framework / WebSocket RPC
  - `unreal`：Automation Spec / console command
  - `backend`/`api`：HTTP API / gRPC

## Guardrails
- 若已有同名 change，询问用户是继续还是新建，不自动覆盖——这是一个停止条件。
- 目标描述为空时必须追问，不默认。
- 脚本只写入 `openguard/` 目录，不写入目标项目源码目录。
- `phase: ready_for_apply` 时**必须**停下来向用户呈现确认摘要，不得自动执行 apply。
"""

# 向后兼容别名
SKILL_NEW = SKILL_RUN

SKILL_CONTINUE = """\
---
name: openguard-continue
description: >
  手动恢复：当 AI 驱动循环中断、对话重置或需要查看当前进度时使用此 Skill。
  正常流程中 /opg:run 会自动驱动循环，无需手动触发此命令。
---

# openguard-continue

## 触发条件
用户输入 `/opg:continue` 或要求恢复/查看当前进度。
正常流程中 `/opg:run` 自动驱动循环，仅在中断后手动恢复时使用此命令。

## 驱动循环

每次执行 CLI 命令或生成产物后，读取 `state.yaml`，根据 `agent_action` 决定下一步：

| `agent_action` | 行动 |
| --- | --- |
| `run_cli` | 再次执行 `openguard continue`，然后循环 |
| `generate` | 生成 `missing_artifacts` 中列出的缺失产物，写入后再执行 `openguard continue`，然后循环 |
| `resolve` | 读取 `unknowns.md`；能自主解决的逐条解决；需要人类输入的追问用户，得到答案后继续循环 |
| `wait_user` | **停止。** 把需要决策的内容呈现给用户，等待回答 |
| `done` | **停止。** 向用户汇报完成摘要 |

**必须停下来的情况（暂停并询问用户）：**
- `state.yaml` 中 `agent_action: wait_user`
- 无法通过代码库自主解答的真正 unknown（如"生产服务器地址是什么？"）
- 需要先修复代码才能继续的 blocker
- CLI 命令报错

**不需要停下来的情况：**
- 生成文件（直接生成）
- 再次执行 `openguard continue`（直接执行）
- 能从代码库中找到答案的 unknown（直接解答）

## 步骤

**1. 执行 CLI**
```
openguard continue [--change <id>]
```

**2. 读取状态**
读取 `state.yaml`，查看 `agent_action` 和 `missing_artifacts`。

**3. 按驱动循环表格执行**

**4. 生成 test_knowledge.md 时**

必须包含两个机器可读部分：

**a) YAML front matter：**
```yaml
external_preconditions:
  - some_state   # 仅当本 change 内没有任何用例能产出此状态；否则填 []
```

**b) `## Cases` JSON 块：**
```json
[
  {
    "id": "AC-001",
    "title": "正常登录",
    "produces_tags": ["logged_in"],
    "required_precondition_tags": []
  },
  {
    "id": "AC-005",
    "title": "断线重连",
    "produces_tags": [],
    "required_precondition_tags": ["logged_in"]
  }
]
```

填写规则：
- `produces_tags`：该用例通过后系统所处的状态标签
- `required_precondition_tags`：该用例运行前系统必须处于的状态标签
- 若 B 需要 `logged_in` 而 A 能产出 `logged_in`，矩阵自动将 A 排在 B 前面，不要加入 `external_preconditions`
- 只有当本 change 内没有任何用例能产出所需状态时，才加入 `external_preconditions`
- 必须基于用例实际语义，不得用关键词猜测

**5. 生成测试脚本时**
- 读取 `config.yaml` 中的 `project.type`、`runtime`、`automation`
- `verified` → 直接引用
- `needs-review` → 可引用但须标注
- `stale`/`broken` → 在 `openguard/changes/<id>/test_scripts/` 生成新草稿
- 控制通道选择：
  - `web`/`h5`：Playwright
  - `webgl`/`web-game`：Playwright + JS bridge / WebSocket
  - `unity`：Unity Test Framework / WebSocket RPC
  - `unreal`：Automation Spec / console command
  - `backend`/`api`：HTTP API / gRPC

## Guardrails
- 已存在且新鲜的产物不得重复生成。
- 不引用 `stale`/`broken` 脚本。
- 脚本只写入 `openguard/changes/<id>/test_scripts/`，不写入项目源码。
- unknowns 未解决时不推进到 apply。
- 填写 `produces_tags` 和 `required_precondition_tags` 时必须基于用例实际语义，不得用关键词猜测。
"""

SKILL_APPLY = """\
---
name: openguard-apply
description: >
  当用户输入 /opg:apply 或要求执行测试时使用此 Skill。
  支持 change 上下文模式（默认）和套件模式（--suite）。
---

# openguard-apply

## 触发条件
用户输入 `/opg:apply` 或要求执行代码 Review 和测试。

## Change 上下文模式（默认）

**1. 执行**
```
openguard apply [--change <id>] [--test-suite <suite>] [--gate <gate>] [--review-level <level>]
```
执行链路：`新鲜度校验 → 代码 Review → 工具链就绪 → 应用就绪 → 前置条件 → 验收步骤 → 报告`

**2. 等待**
执行期间不操作目标应用，等待执行器完成。

**3. 读取报告**
- `run_report.md` — 人可读摘要
- `timeline.md` — 过程时间线
- `run_report.json` — 结构化详情（深度分析用）

**4. 分析失败**
分类失败类型：
- **env**：工具链未就绪或应用未启动
- **precondition**：测试数据或前置状态准备失败
- **script**：测试脚本本身错误
- **product**：被测系统行为不符合预期
- **unknown**：无法分类（需补充证据）

UNKNOWN 结果：提出需要补充哪些证据，不得当 PASS 处理。
产品失败：生成初步归因线索。

**5. 生成 overlay（如有归因建议）**
写入 `report_overlay.yaml`，然后执行：
```
openguard apply --merge-overlay <path>
```

**6. 向用户汇报**
汇报：执行结论、Run ID、pass/fail/unknown 统计、失败摘要、建议下一步。

## 套件模式（--suite <name>）

执行：
```
openguard apply --suite <name> [--gate <gate>]
```
读取 `run_report.md`、`timeline.md`。
汇报：套件名、脚本锚点哈希、代码版本、执行结论。

## Guardrails
- 不直接操作目标应用，执行由 OpenGuard 执行器负责。
- 低置信度归因只进入 overlay 待确认区，不修改代码或产物。
- UNKNOWN 不得当 PASS 汇报给用户。
- `needs-review` 脚本不得参与 `release`/`nightly` gate。
"""

SKILL_ARCHIVE = """\
---
name: openguard-archive
description: >
  当用户输入 /opg:archive 或要求归档当前 QA change 时使用此 Skill。
---

# openguard-archive

## 触发条件
用户输入 `/opg:archive` 或要求关闭已完成的 change。

## 步骤

**1. 归档前检查（dry-run）**
```
openguard archive [--change <id>] --dry-run
```
检查：
- 是否有未解决 unknowns（必须先解决）
- 是否有 blocking Review finding（必须修复或人工豁免）
- 门禁报告是否通过
- 执行报告是否完整

**2. 处理阻断项**
列出阻断项，询问用户是否豁免。
必须记录豁免原因，不得静默跳过。

**3. 确认可晋升脚本**
晋升条件：多次执行通过、无 flaky 历史、有 Run ID 依据。
说明每个脚本建议加入的套件（smoke/regression/requirement/full）。
单次通过的脚本不得晋升。

**4. 等待用户确认**
等待用户或 AI 确认晋升列表后再执行，不自动晋升。

**5. 执行归档**
```
openguard archive [--change <id>]
```
执行：脚本晋升到 `test_assets/`（含 `.meta.yaml`）、更新 `suites/`、沉淀知识。

**6. 向用户汇报**
汇报：归档位置、晋升脚本列表（含锚点路径）、知识摘要、更新的套件、建议下一步。

## Guardrails
- 不自动跳过 blocking Review 和失败门禁，必须人工确认。
- 不自动晋升脚本，等待确认。
- 单次通过的脚本不得直接晋升。
- 归档后保留 change 目录（审计链路）。
"""


_SKILL_CONTENT_MAP: dict[str, str] = {
    "openguard-run":      SKILL_RUN,
    "openguard-continue": SKILL_CONTINUE,
    "openguard-apply":    SKILL_APPLY,
    "openguard-archive":  SKILL_ARCHIVE,
}

SKILL_NAMES: list[str] = list(_SKILL_CONTENT_MAP.keys())


def get_skill_content(skill_name: str) -> str:
    return _SKILL_CONTENT_MAP[skill_name]
