# OpenGuard

> **一句话定位：** OpenGuard 是面向 AI 编码宿主的自动化测试与代码质量框架。它像 OpenSpec 管理规格变更一样，用轻量指令和文件化产物管理「需求/代码变更 → 测试理解 → 代码 Review → 测试执行 → 报告归因 → 经验沉淀」的闭环。

OpenGuard 不在工具进程内调用大模型；Claude Code、CodeBuddy、Cursor 等 Agent 宿主负责推理，OpenGuard 负责确定性的 CLI、协议、目录、校验、执行编排和证据落盘。

---

## 安装

### 推荐方式（npm 全局安装）

```bash
npm install -g @yanwuzhang/openguard
```

安装时自动检测本机 Python 3.10+ 并安装 `openguard-agent`。**前提：本机已安装 Python 3.10+。**

### 直接用 pip 安装

```bash
pip install openguard-agent
```

---

## 快速开始

```bash
cd your-project
openguard init              # 初始化：探测项目类型，生成配置，安装 slash commands 和 skills
/opg:run "验证登录流程"   # 开始一次测试任务（AI 自主推进准备，完成后等你确认执行）
/opg:apply               # 用户确认后执行：代码 Review + 测试 + 证据采集 + 报告
/opg:archive             # 归档，沉淀经验到 openguard/knowledge/
```

---

## 核心指令

| 指令 | 说明 |
|------|------|
| `openguard init` | 在当前项目创建 `openguard/`，生成项目测试画像、配置，向 AI 宿主安装 Slash Commands 和 Agent Skills |
| `openguard update` | 刷新 `/opg:*` 指令、Skill、schema 和模板，不改变已有产物 |
| `openguard run <目标>` | 开始一次测试任务（需求/代码修改/缺陷修复），AI 自主推进准备阶段，准备完成后呈现摘要等待用户确认 |
| `openguard apply` | 用户确认后：代码 Review + 测试矩阵执行 + 证据采集 + 报告生成；支持 `--suite <name>` 直接执行全局套件 |
| `openguard archive` | 归档已完成 change，晋升稳定脚本到 `test_assets/`，沉淀经验到 `knowledge/` |
| `openguard help` | 输出所有用户指令和当前项目建议下一步 |

### Slash Commands

`openguard init` 向检测到的 AI 宿主安装以下 Slash Commands：

| Slash Command | 说明 |
|---|---|
| `/opg:run <目标>` | 开始一次测试任务，AI 自主推进准备阶段，完成后等待用户确认执行 |
| `/opg:apply` | 用户确认后执行测试，生成报告 |
| `/opg:archive` | 归档 change，沉淀可复用知识 |
| `/opg:continue` | 手动恢复入口：AI 中断或用户想查看进度时使用；正常流程无需触发 |

### 策略参数

```bash
openguard run "验证新手引导" --test-suite smoke
openguard apply --test-suite incremental --gate ci
openguard apply --scan-scope full --test-suite regression --gate release
openguard apply --suite smoke          # 不需要 change 上下文，直接执行全局套件
```

| 参数 | 可选值 | 说明 |
|------|--------|------|
| `--scan-scope` | `auto` / `full` / `incremental` | 默认 auto；首次/配置变化/发布门禁走全量 |
| `--test-suite` | `smoke` / `incremental` / `requirement-full` / `regression` / `full` | 控制执行规模 |
| `--review-level` | `off` / `changed` / `risk-based` / `full` | 控制 Review 范围 |
| `--gate` | `local` / `ci` / `release` | 门禁级别，影响阻断规则和超时 |

---

## 工作流

```
openguard init
    │
    ▼
openguard run <目标>  ──► AI 自主循环：snapshot → delta → impact_graph
    │                            → requirements.md → test_knowledge.md
    │                            → review_plan.md → test_matrix.json
    │                  ──► 准备完成，呈现摘要，等待用户确认
    ▼
openguard apply       ──► [1] 新鲜度校验 → [2] 代码 Review → [3] 工具链就绪
    │                → [4] 应用就绪 → [5] 前置条件 → [6] 验收执行 → [7] 报告归因
    ▼
openguard archive     ──► 归档 change，晋升稳定脚本到 test_assets/，沉淀知识
```

### 典型用户流程

```bash
# 1. 项目首次初始化（只做一次）
openguard init

# 2. 开始一次测试任务（AI 自主推进准备阶段）
/opg:run "测试登录流程"
# → AI 内部自主循环（用户不感知）：
#     openguard run "测试登录流程"   # 创建 change + 初始扫描
#     [AI 生成 requirements.md]
#     openguard _advance             # 确定性产物生成 + 状态更新
#     [AI 生成 test_knowledge.md + review_plan.md]
#     openguard _advance             # 生成 test_matrix.json + 状态更新
# → AI 停下来汇报：
#     "准备完成：7 个测试用例，1 个 Review 问题需关注，预计 5 分钟。是否执行？"

# 3. 用户确认后执行
/opg:apply

# 4. 归档（可选）
/opg:archive
```

---

## openguard/ 目录结构

```
openguard/
  config.yaml          # 项目测试画像：类型、宿主、扫描、运行、自动化、证据、默认策略
  changes/             # 每次 QA change 的工作区
    <change-id>/
      intent.md        # 本次变更目标
      requirements.md  # EARS 风格验收项
      state.yaml       # 当前阶段与下一步建议
      snapshot.json    # 代码/需求/资产快照
      delta.json       # 相对上次快照的增量
      impact_graph.json # 影响范围分析
      test_knowledge.md # 需求理解、断言线索、测试映射
      review_plan.md   # 代码 Review 检查项
      test_matrix.json # 可执行任务 DAG
      test_scripts/    # 本次 change 生成的测试脚本草稿
  test_assets/         # 跨 change 稳定复用的测试脚本（归档后晋升）
    scripts/           # 已验证脚本 + .meta.yaml 锚点
    fixtures/          # 通用测试数据
  suites/              # 全局可复用测试套件定义
    smoke/
    regression/
    requirement/
    full/
  artifacts/           # 索引、delta、矩阵、overlay
  reports/             # 执行报告（按 change / suite 分层）
  traces/              # 操作日志、时间线、决策记录
  baselines/           # 截图、状态、性能基线
  knowledge/           # 可复用项目知识与经验
    project_profile.yaml
    preconditions.yaml
    test_patterns.yaml
    review_rules.yaml
    failure_taxonomy.yaml
    flaky_rules.yaml
```

---

## 支持的项目类型

| 类型 | 控制方式 | 说明 |
|------|---------|------|
| `unity` | 进程外编排 + Unity Test Framework / RPC / WebSocket | Unity 原生客户端 |
| `unreal` | 进程外编排 + Automation Spec / console command / RPC | Unreal 原生客户端 |
| `webgl` / `web-game` | 浏览器外壳 + JS bridge / WebSocket | WebGL 游戏 |
| `web` | Playwright 等 DevTools 协议 | Web / H5 |
| `backend` / `api` | 服务启动 + 健康检查 + API 契约 | 后端服务 |
| `mixed` | 多子项目联动，含执行顺序和依赖关系 | 复合项目 |

---

## 与 OpenSpec 配合

```bash
# 从 OpenSpec change 创建 QA change（读取 proposal/specs/tasks）
openguard run --from-openspec <change-id>
```

```
OpenSpec: propose → spec → design → tasks → /opsx:apply（实现）
OpenGuard:   run → /opg:apply（Review + 测试 + 门禁）
OpenSpec: /opsx:archive（OpenGuard 门禁通过后）
```

OpenGuard 默认只读 OpenSpec 产物，不修改；门禁通过后输出可归档结论供 `/opsx:archive` 使用。

---

## 与 AI 宿主集成

`openguard init` 向检测到的 AI 宿主安装：

- **Slash Commands**（`/opg:run` / `/opg:apply` / `/opg:archive` / `/opg:continue`）— 对话框触发入口
- **Agent Skills**（`openguard-run` / `openguard-apply` / `openguard-archive`）— 完整操作手册，含执行步骤、CLI 调用顺序、产物读写和 guardrails

| AI 宿主 | Slash Commands 目录 | Skill 目录 |
|---|---|---|
| CodeBuddy | `.codebuddy/commands/` | `.codebuddy/skills/openguard-*/` |
| Cursor | `.cursor/rules/` | `.cursor/skills/openguard-*/` |
| Claude Code | `.claude/commands/` | `.claude/skills/openguard-*/` |
| Windsurf | `.windsurf/rules/` | `.windsurf/skills/openguard-*/` |

---

## 本地开发

### 环境要求

- Python 3.10+
- Node.js 18+
- pnpm（可选，用于快捷脚本）

### 克隆与安装

```bash
git clone https://github.com/yanwuzhang/openguard.git
cd openguard

# 安装 Python 包（editable 模式）+ npm 全局链接
node scripts/rebuild.mjs
```

### 开发快捷指令

```bash
# 重新安装（改了 Python 代码或 npm 文件后执行）
node scripts/rebuild.mjs
pnpm rebuild          # 等价写法

# 完整模拟发布流程（npm pack + npm install -g）
node scripts/rebuild.mjs --pack
pnpm rebuild:pack

# 只重装 Python 包（只改了 Python 代码时）
node scripts/rebuild.mjs --py-only
pnpm rebuild:py
```

### 运行测试

```bash
python -m pytest src/tests/ -v
python -m pytest src/tests/ -q   # 简洁模式
```

### 项目结构

```
openguard/
  src/
    openguard/          # Python 主包
      cli/              # CLI 入口（main.py / dispatch.py）
      commands/         # 命令处理器（init / run / apply / archive / update / debug / report）
      setup/            # 项目探测、config 生成、slash commands、skills 安装
      workspace/        # 工作区布局、change 管理、测试资产生命周期
      scan/             # 扫描器、新鲜度校验、影响分析
      matrix/           # 测试矩阵生成
      review/           # Review 计划、SARIF findings
      executor/         # 执行编排、报告生成、Run ID
      launcher/         # 应用运行时启动器（Unity / Web）
      gates/            # 质量门禁引擎
      knowledge/        # 知识库管理、脚本晋升
      integrations/     # 外部工具集成（OpenSpec / 未来：Jira / Notion）
      governance/       # 治理边界、敏感信息扫描
      prompts/          # Agent 提示词模板（zh / en）
      diag/             # 诊断日志（CLI 调用记录、_advance 推进轨迹）
      log_collection/   # 目标应用日志采集（执行期间证据收集）
      tools/            # 原子工具函数（fs / analysis / runtime）
    tests/              # 测试套件
  npm/                  # npm 包壳（@yanwuzhang/openguard）
  scripts/
    rebuild.mjs         # 本地开发重建脚本（跨平台）
  docs/
    v3/                 # 需求文档（REQ_01~16）
  pyproject.toml
  package.json
```

---

## 开发者调试工具

`openguard debug` 是面向开发者的单点调试命令，**不出现在用户帮助中**。可以单独触发任意内部步骤，无需走完整流程。

### 子命令一览

| 子命令 | 说明 |
|--------|------|
| `debug detect` | 执行项目类型探测，打印结果（等同于 `init` 的探测阶段） |
| `debug preflight` | 执行 `apply` 前校验，打印每项结果 |
| `debug launcher` | 启动目标应用（Unity/Web）并等待就绪 |
| `debug scan` | 对当前 change 执行代码/需求扫描 |
| `debug impact` | 执行影响分析，生成 `impact_graph.json` |
| `debug matrix` | 生成测试矩阵，打印用例摘要 |

### Unity 启动流程调试（推荐顺序）

```bash
# 1. 确认项目探测正确（project_type=unity，editors found 有路径）
openguard debug detect

# 2. 确认 preflight 配置校验通过（所有项 [✓]）
openguard debug preflight

# 3. 验证完整启动流程：启动 Editor → 编译就绪 → 选场景 → 进入 PlayMode → 立即停止
openguard debug launcher --stop-after 0

# 4. 验证 PlayMode 稳定性：进入后保持 30 秒
openguard debug launcher --stop-after 30

# 5. 保持运行直到 Ctrl+C（手动观察游戏状态）
openguard debug launcher
```

**`--stop-after` 参数说明：**
- `0`：进入 PlayMode 后立即停止（只验证启动流程，速度最快）
- `N`：保持 N 秒后自动停止
- 不传（默认 `-1`）：持续保持，按 `Ctrl+C` 停止

### 场景说明

`debug launcher` 没有 `test_knowledge.md` 时，按以下优先级选择入口场景：

1. `config.yaml` 的 `runtime.entry_scene`（手动指定）
2. `ProjectSettings/EditorBuildSettings.asset` 的第一个 enabled 场景
3. Editor 当前打开的场景（不切换）

**调试时指定场景**：在 `config.yaml` 里临时加 `runtime.entry_scene: Assets/Scenes/xxx.unity`，调试完再删掉。

### 其他调试命令

```bash
# 扫描（强制全量）
openguard debug scan --scope full

# 影响分析
openguard debug impact

# 测试矩阵生成（指定套件）
openguard debug matrix --suite smoke

# preflight 指定门禁级别
openguard debug preflight --gate ci

# 探测指定路径的项目
openguard debug detect --path /path/to/project
```

---

## 问题上报

遇到 bug 或非预期行为时，执行以下命令一键生成上报文件：

```bash
openguard report
```

输出示例：
```
上报文件已生成：/your/project/openguard-report-20260502-221800.txt
请将此文件发送给开发者进行分析。
```

上报文件包含：最近 CLI 调用记录、`_advance` 推进轨迹、执行报告、事件流、失败任务脚本输出。所有内容在写入前自动脱敏（token/password → `***REDACTED***`）。

```bash
# 指定 change
openguard report --change <change-id>

# 指定输出路径
openguard report --out /tmp/my-report.txt
```



### 发布 Python 包到 PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

### 发布 npm 包

```bash
cd npm
npm login           # 只需一次
npm publish --access public
```

---

## 许可证

MIT
