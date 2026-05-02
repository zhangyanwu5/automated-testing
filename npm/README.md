# OpenGuard

> OpenGuard 是面向 AI 编码宿主的自动化测试与代码质量框架。
> 像 OpenSpec 管理规格变更一样，用轻量指令和文件化产物管理「需求/代码变更 → 测试理解 → 代码 Review → 测试执行 → 报告归因 → 经验沉淀」的闭环。

## 安装

```bash
npm install -g @yanwuzhang/openguard
```

安装后自动检测本机 Python 环境并安装 `openguard-agent` Python 包。

**前提条件**：本机需有 Python 3.10+。

---

## 快速开始

```bash
cd your-project
openguard init          # 初始化，探测项目类型，安装 /opg:* slash commands
openguard new "验证某功能"   # 开始一次 QA change
openguard continue      # 状态机自动推进：扫描→影响分析→测试知识→矩阵
openguard apply         # 代码 Review + 测试执行 + 报告
openguard archive       # 归档，沉淀经验到 .openguard/knowledge/
```

---

## 指令

| 指令 | 说明 |
|------|------|
| `openguard init` | 在当前项目创建 `.openguard/`，生成项目测试画像、配置、slash commands 和 skills |
| `openguard update` | 刷新 /opg:* 指令和模板，不改变已有产物 |
| `openguard new <目标>` | 开始一次 QA change（需求、代码修改或缺陷修复） |
| `openguard continue` | 根据当前状态自动推进：补扫描、影响分析、测试知识、Review 计划、测试矩阵 |
| `openguard apply` | 代码 Review + 测试矩阵执行 + 证据采集 + 报告生成 |
| `openguard archive` | 归档已完成 change，晋升稳定知识 |
| `openguard help` | 输出所有命令和当前项目建议下一步 |

---

## 策略参数

```bash
openguard new "验证新手引导" --test-suite smoke
openguard apply --test-suite incremental
openguard apply --scan-scope full --gate release
```

| 参数 | 可选值 |
|------|--------|
| `--scan-scope` | `auto` / `full` / `incremental` |
| `--test-suite` | `smoke` / `incremental` / `requirement-full` / `regression` / `full` |
| `--review-level` | `off` / `changed` / `risk-based` / `full` |
| `--gate` | `local` / `ci` / `release` |

---

## 与 OpenSpec 配合

```bash
openguard new --from-openspec <change-id>   # 从 OpenSpec change 创建 QA change
```

OpenGuard 读取 OpenSpec 的 proposal/specs/design/tasks，OpenGuard 门禁通过后可执行 `/opsx:archive`。

---

## 手动安装 Python 包

如果 postinstall 未能自动安装，可手动执行：

```bash
pip install openguard-agent
```

---

## 许可证

MIT
