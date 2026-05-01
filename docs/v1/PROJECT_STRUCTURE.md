# 项目目录结构

本文档描述代码目录组织与依赖方向约定。架构原则见 [ARCHITECTURE.md](./ARCHITECTURE.md)。被测项目侧 **`.atf/`** 目录与产物约定见 [../v2/ATF_DIRECTORY.md](../v2/ATF_DIRECTORY.md)。

目录结构服从架构：微内核 / 插件 / 集成层 的分离在目录上必须可见，不允许跨层或跨插件的直接依赖。

## 1. 顶层布局

```
automated-testing/
├── core/                    # 微内核：接口、插件加载、服务注册、事件总线
├── plugins/                 # 可插拔功能模块
│   ├── ai-providers/        # AI 能力提供者
│   ├── analyzers/           # 代码分析器
│   ├── generators/          # 代码/用例生成器
│   ├── executors/           # 执行器
│   ├── oracles/             # 判定器
│   ├── reporters/           # 报告器
│   └── engine-adapters/     # 引擎适配器（含 Host 与 Runtime 两侧）
├── integration/             # 集成层：CLI / 库嵌入 / 服务化
│   ├── cli/
│   ├── library/
│   └── server/
├── shared/                  # 所有层都可用的纯工具与类型
├── config/                  # 默认配置与示例配置
├── contract-tests/          # 跨插件的契约测试
├── tests/                   # 框架自身的单元与集成测试
├── docs/
├── examples/                # 示例项目与使用案例
└── scripts/                 # 构建、发布、诊断脚本
```

## 2. core/ — 微内核

```
core/
├── interfaces/              # 所有跨组件接口
│   ├── plugin.py            # IPlugin
│   ├── service_registry.py  # IServiceRegistry
│   ├── event_bus.py         # IEventBus
│   ├── ai_provider.py       # IAIProvider
│   ├── analyzer.py          # ICodeAnalyzer
│   ├── generator.py         # IAdapterGenerator
│   ├── executor.py          # IExecutor
│   ├── oracle.py            # IOracle
│   └── reporter.py          # IReporter
├── plugin_system/           # 插件发现、加载、依赖解析
├── service_registry/        # 服务注册表实现
├── event_bus/               # 事件总线实现
├── config/                  # 配置加载与注入
└── lifecycle/               # 核心启动 / 停止
```

**硬约束**：
- `core/` 不得 import 任何 `plugins/*`、`integration/*`
- `core/` 不得依赖任何 AI SDK、游戏引擎库、Web 框架
- 违反此规则的 PR 不合入

## 3. plugins/ — 插件

每个插件是一个独立的包：独立的 `pyproject.toml` / `requirements.txt`，独立的测试目录。

### 3.1 ai-providers/

```
plugins/ai-providers/
├── claudecode/              # ClaudeCode SDK 提供者
│   ├── src/
│   │   ├── provider.py      # 实现 IAIProvider
│   │   └── client.py        # ClaudeCode SDK 封装
│   ├── tests/
│   └── pyproject.toml
├── anthropic/               # Anthropic API 提供者
├── openai/                  # OpenAI API 提供者
└── local-llm/               # 本地模型提供者（Ollama 等)
```

**硬约束**：AI SDK 的 import 只允许出现在 `plugins/ai-providers/*` 中。

### 3.2 analyzers/

按语言划分，每个语言一个分析器。分析器不调用 AI，只做客观的结构提取。

```
plugins/analyzers/
├── csharp/
├── lua/                     # 用于 XLua 等混合架构
├── cpp/
├── gdscript/
└── universal/               # 基于 tree-sitter 的通用分析器
```

### 3.3 generators/

```
plugins/generators/
├── adapter-generator/       # 根据分析结果生成引擎适配器
│   ├── src/
│   │   ├── generator.py
│   │   └── templates/       # 模板文件（非代码）
│   └── tests/
├── testcase-synthesizer/    # 根据 PRD + 分析结果合成测试用例
└── code-validator/          # 生成代码的编译/语法校验
```

生成器需要 AI 能力时，从服务注册表获取 `IAIProvider`，不直接依赖任何 AI SDK。

### 3.4 executors/

```
plugins/executors/
├── local/                   # 本地单机执行
├── distributed/             # 分布式执行（调度到 worker 节点）
└── ci/                      # CI 环境执行
```

### 3.5 oracles/

```
plugins/oracles/
├── crash/
├── log/
├── invariant/
├── business-rule/
├── llm-judge/               # 通过 AI Provider 进行语义判定
├── visual/                  # 通过 VLM 进行视觉判定
└── regression/              # 版本间行为差分
```

### 3.6 reporters/

```
plugins/reporters/
├── html/
├── json/
├── junit/
└── markdown/
```

### 3.7 engine-adapters/

引擎适配器是"对"出现的：Host 侧（Python）+ Runtime 侧（引擎原生语言）。

```
plugins/engine-adapters/
├── unity/
│   ├── host/                # Python
│   │   ├── src/
│   │   │   ├── executor.py  # 实现 IExecutor
│   │   │   ├── rpc.py       # WebSocket / JSON-RPC 客户端
│   │   │   └── selector.py
│   │   └── tests/
│   └── runtime/             # C# UPM 包
│       ├── Runtime/
│       │   ├── AutoTestRuntime.cs
│       │   ├── UiTreeCollector.cs
│       │   ├── InputSimulator.cs
│       │   ├── LogHook.cs
│       │   └── CheatDispatcher.cs
│       └── package.json
├── unity-xlua/              # Unity + XLua 混合架构专用
│   ├── host/
│   └── runtime/
│       ├── Runtime/
│       └── Lua/             # Lua 侧测试桥接脚本
├── unreal/
│   ├── host/
│   └── runtime/             # UE Plugin
│       └── Source/AutoTestRuntime/
└── godot/
    ├── host/
    └── runtime/             # Godot Addon
```

**硬约束**：适配器之间不得相互依赖（unity 不能 import unreal，反之亦然）。

## 4. integration/ — 集成层

```
integration/
├── cli/                     # 独立命令行工具
│   └── src/
│       ├── commands/
│       └── main.py
├── library/                 # 作为库嵌入
│   └── src/
│       └── testing_library.py
└── server/                  # REST / MCP 服务
    └── src/
        ├── rest/
        └── mcp/
```

每种集成形态共用同一份核心与插件，区别只在入口装配。

## 5. shared/ — 共享工具

```
shared/
├── types/                   # 跨模块的数据结构
├── utils/                   # 纯函数工具
└── errors/                  # 统一异常定义
```

**硬约束**：
- `shared/` 不得依赖 `core/`、`plugins/`、`integration/` 中的任何东西
- `shared/` 只能依赖 Python 标准库和少量基础第三方库（pydantic、pathlib 等）

## 6. config/ — 配置

```
config/
├── defaults/                # 框架默认配置
│   ├── core.yaml
│   ├── plugins.yaml
│   └── engines.yaml
├── profiles/                # 预设配置档
│   ├── local-dev.yaml
│   ├── ci.yaml
│   └── production.yaml
└── schemas/                 # 配置 JSON Schema
```

## 7. contract-tests/ — 契约测试

用于保证同一接口的不同实现语义一致。

```
contract-tests/
├── ai_provider_contract/    # 所有 IAIProvider 实现必须通过
├── executor_contract/       # 所有 IExecutor 实现必须通过
├── oracle_contract/
└── engine_adapter_contract/
```

每个插件在 CI 中都要跑对应的契约套件。契约不通过的实现不允许注册。

## 8. examples/ — 示例项目

```
examples/
├── unity-xlua-slg/          # Unity + XLua 的 SLG 项目示例
│   ├── project/             # Unity 工程
│   ├── prd/                 # 对应的需求文档
│   └── expected/            # 期望产出（适配器代码、用例、报告）
├── unreal-demo/
└── embedded-in-devframework/ # 作为库嵌入到其他开发框架的示例
```

## 9. 依赖方向约束

### 9.1 允许的依赖

```
integration/* ─┬─▶ core/
               ├─▶ plugins/*（通过接口，由配置决定加载哪些）
               └─▶ shared/

plugins/* ────┬─▶ core/interfaces/
              └─▶ shared/

core/ ────────▶ shared/

shared/ ──────▶ (仅标准库 + 基础第三方库)
```

### 9.2 禁止的依赖

| 禁止 | 原因 |
| --- | --- |
| `core/` → `plugins/*` | 核心不能知道具体实现 |
| `core/` → `integration/*` | 核心不能绑定集成形态 |
| `plugins/a/` → `plugins/b/` | 插件间必须通过接口 + 服务注册表通信 |
| `plugins/*` → AI SDK（除 `ai-providers/` 外） | 强制 AI 能力走抽象接口 |
| `plugins/*` → 游戏引擎库（除 `engine-adapters/` 外） | 引擎差异必须收敛在适配器 |
| `shared/` → 任何上层 | 工具层不能反向依赖 |

### 9.3 检查手段

- **静态检查**：在 CI 中用 `import-linter` 或等价工具声明依赖规则
- **循环检查**：开启 `import/no-cycle`
- **构建隔离**：每个插件在自己的 pyproject 中声明依赖，上述跨层引用会在安装时直接失败

## 10. 新增模块 Checklist

### 新增一个插件

1. 在 `plugins/<category>/<name>/` 下创建目录
2. 独立的 `pyproject.toml`，只声明对 `core/` 和 `shared/` 的依赖
3. 实现对应接口（在 `core/interfaces/` 中）
4. 通过契约测试（`contract-tests/<category>_contract/`）
5. 在 `config/defaults/plugins.yaml` 中注册元信息（不开启，由项目自己决定）

### 新增一个引擎适配器

1. 在 `plugins/engine-adapters/<engine>/` 下创建 `host/` + `runtime/`
2. Host 侧实现 `IExecutor`
3. Runtime 侧实现 RPC Server 与基础能力
4. 通过 `engine_adapter_contract` 契约测试
5. 在 `examples/` 下补一个最小示例

### 新增一种集成形态

1. 在 `integration/<form>/` 下创建目录
2. 只调用 `integration/library` 暴露的 API 或通过 `core/` 装配
3. 不重复实现流程逻辑——流程逻辑在核心与插件中，集成层只是入口

## 11. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v2.0 | 2026-04-22 | 对齐解耦架构：微内核 + 插件 + 集成层三层结构，明确依赖方向约束 |
| v1.0 | 2026-04-22 | 初版 |
