# OpenQA

> **一句话定位：** OpenQA 是面向 AI 编码宿主的自动化测试与代码质量框架。它像 OpenSpec 管理规格变更一样，用轻量指令和文件化产物管理「需求/代码变更 → 测试理解 → 代码 Review → 测试执行 → 报告归因 → 经验沉淀」的闭环。

OpenQA 不在工具进程内调用大模型；Claude Code、CodeBuddy、Cursor 等 Agent 宿主负责推理，OpenQA 负责确定性的 CLI、协议、目录、校验、执行编排和证据落盘。

---

## 安装

### 推荐方式（与 OpenSpec 一致）

```bash
npm install -g @yanwuzhang/openqa
```

安装时自动检测本机 Python 3.10+ 并安装 `openqa-agent`。**前提：本机已安装 Python 3.10+。**

### 直接用 pip 安装

```bash
pip install openqa-agent
```

---

## 快速开始

```bash
cd your-project
openqa init                      # 初始化：探测项目类型，生成配置，安装 slash commands 和 skills
openqa new "验证新手引导奖励逻辑"  # 开始一次 QA change
openqa continue                  # 状态机自动推进：扫描 → 影响分析 → 测试知识 → 矩阵
openqa apply                     # 代码 Review + 测试执行 + 证据采集 + 报告
openqa archive                   # 归档，沉淀经验到 openqa/knowledge/
```

---

## 核心指令

| 指令 | 说明 |
|------|------|
| `openqa init` | 在当前项目创建 `openqa/`，生成项目测试画像、配置、忽略规则、slash commands 和 Agent Skills |
| `openqa update` | 刷新 `/oqa:*` 指令和模板，不改变已有产物 |
| `openqa new <目标>` | 开始一次 QA change（需求、代码修改或缺陷修复） |
| `openqa continue` | 根据当前状态自动推进：补扫描、影响分析、测试知识、Review 计划、测试矩阵 |
| `openqa apply` | 代码 Review + 测试矩阵执行 + 证据采集 + 报告生成；支持 `--suite <name>` 直接执行全局套件 |
| `openqa archive` | 归档已完成 change，晋升稳定知识 |
| `openqa help` | 输出所有命令和当前项目建议下一步 |

### 策略参数

```bash
openqa new "验证新手引导" --test-suite smoke
openqa apply --test-suite incremental --gate ci
openqa apply --scan-scope full --test-suite regression --gate release
openqa apply --suite smoke                  # 不需要 change 上下文，直接执行全局套件
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
openqa new <目标>
    │
    ▼
openqa continue  ──► 自动推进：snapshot → delta → impact_graph
    │                           → test_knowledge → review_plan → test_matrix
    ▼
openqa apply     ──► [1] 新鲜度校验 → [2] 代码 Review → [3] 工具链就绪
    │                → [4] 应用就绪 → [5] 前置条件 → [6] 验收执行 → [7] 报告归因
    ▼
openqa archive   ──► 归档 change，晋升稳定脚本到 test_assets/，沉淀知识
```

---

## openqa/ 目录结构

```
openqa/
  config.yaml          # 项目测试画像：类型、宿主、扫描、运行、自动化、证据、默认策略
  ignore               # 扫描忽略规则
  commands/            # /oqa:* slash command 模板（AI 宿主）
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
openqa new --from-openspec <change-id>
```

```
OpenSpec: propose → spec → design → tasks → /opsx:apply（实现）
OpenQA:   new → continue → /oqa:apply（Review + 测试 + 门禁）
OpenSpec: /opsx:archive（OpenQA 门禁通过后）
```

OpenQA 默认只读 OpenSpec 产物，不修改；门禁通过后输出可归档结论供 `/opsx:archive` 使用。

---

## 与 AI 宿主集成

`openqa init` 向检测到的 AI 宿主安装：

- **Slash Commands**（`/oqa:new` / `/oqa:continue` / `/oqa:apply` / `/oqa:archive`）— 对话框触发入口
- **Agent Skills**（`openqa-new` / `openqa-continue` / `openqa-apply` / `openqa-archive`）— 完整操作手册，含执行步骤、CLI 调用顺序、产物读写和 guardrails

支持宿主：**CodeBuddy** / **Cursor** / **Claude Code**

---

## 本地开发

### 环境要求

- Python 3.10+
- Node.js 18+
- pnpm（可选，用于快捷脚本）

### 克隆与安装

```bash
git clone https://github.com/yanwuzhang/openqa.git
cd openqa

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
openqa/
  src/
    openqa/          # Python 主包
      cli/           # CLI 入口（main.py / dispatch.py）
      commands/      # 命令处理器（init / new / continue / apply / archive / update / help）
      init/          # 项目探测、config 生成、slash commands、skills 安装
      workspace/     # 工作区布局、change 管理
      scan/          # 扫描器、新鲜度校验、影响分析
      matrix/        # 测试矩阵生成
      review/        # Review 计划、SARIF findings
      executor/      # 执行编排、报告生成、Run ID
      gates/         # 质量门禁引擎
      knowledge/     # 知识库管理、脚本晋升
      assets/        # 测试资产生命周期（锚点状态机、suite 管理）
      openspec/      # OpenSpec 联动
      governance/    # 治理边界、决策日志
      log/           # 日志采集策略
    tests/           # 测试套件（305 个测试）
  npm/               # npm 包壳（@yanwuzhang/openqa）
    bin/openqa.js    # CLI 入口（透传到 Python）
    scripts/postinstall.js
  scripts/
    rebuild.mjs      # 本地开发重建脚本（跨平台）
  docs/
    v3/              # 需求文档（REQ_01~14）
  pyproject.toml     # Python 包配置（openqa-agent）
  package.json       # 根 package.json（pnpm 快捷指令）
```

---

## 发布

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
