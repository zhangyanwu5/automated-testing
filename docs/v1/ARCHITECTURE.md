# 架构设计

本文档描述框架的分层、模块职责、关键接口与解耦策略。目录组织见 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)。**扫描门禁、`.atf/` 落盘与可选 L1 自动化知识包（AKP）** 等流水线契约见 [../v2/ATF_PIPELINE_AND_SCAN_SPEC.md](../v2/ATF_PIPELINE_AND_SCAN_SPEC.md) 与 [../v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](../v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md)。

## 1. 架构分层

```
┌────────────────────────────────────────────────────────┐
│  集成层 (Integration)                                   │
│  CLI · REST/MCP Server · Library Embedding · CI Plugin │
├────────────────────────────────────────────────────────┤
│  流程层 (Workflow)                                      │
│  分析 → 生成 → 规划 → 执行 → 报告，由插件协同完成         │
├────────────────────────────────────────────────────────┤
│  插件层 (Plugins)                                       │
│  AI Providers · Analyzers · Generators · Executors ·   │
│  Oracles · Reporters · Engine Adapters                 │
├────────────────────────────────────────────────────────┤
│  微内核 (Microkernel)                                   │
│  Interfaces · Plugin Loader · Service Registry ·       │
│  Event Bus · Config                                    │
└────────────────────────────────────────────────────────┘
```

每一层只依赖下层的稳定接口：
- 集成层装配流程层与插件，不直接调用微内核
- 流程层编排插件之间的协作
- 插件之间通过服务注册表和事件总线通信，互不直接依赖
- 微内核不依赖任何插件或 AI 服务

## 2. 微内核

微内核是整个框架的最小稳定核，不包含任何业务逻辑。

### 2.1 职责

- **接口定义**：所有跨组件协作的接口都在微内核定义
- **插件加载**：发现、加载、初始化、卸载插件
- **服务注册**：插件向注册表注册实现，消费者按接口查找
- **事件总线**：异步事件发布订阅
- **配置**：插件配置的加载与注入

### 2.2 核心接口

**插件**
```python
class IPlugin(Protocol):
    name: str
    version: str
    def initialize(self, ctx: PluginContext) -> None: ...
    def shutdown(self) -> None: ...
    def dependencies(self) -> list[str]: ...
```

**服务注册表**
```python
class IServiceRegistry(Protocol):
    def register(self, iface: type, impl: Any, name: str = "default") -> None: ...
    def get(self, iface: type, name: str = "default") -> Any: ...
    def list(self, iface: type) -> list[ServiceInfo]: ...
```

**事件总线**
```python
class IEventBus(Protocol):
    async def publish(self, topic: str, payload: dict) -> None: ...
    def subscribe(self, topic: str, handler: Callable) -> Subscription: ...
```

### 2.3 硬约束

- 微内核不得 import 任何具体插件
- 微内核不得依赖任何 AI SDK
- 微内核不得依赖任何游戏引擎相关库

违反上述约束的代码不得合入。

## 3. 插件层

插件按职责分为若干类，每类对应一个接口。同一接口可以有多个实现并存，运行时按配置选择。

### 3.1 AI 提供者 (AI Providers)

对接具体的 AI 服务，向上提供统一能力。

```python
class IAIProvider(Protocol):
    def capabilities(self) -> AICapabilities: ...
    async def analyze_code(self, code: str, ctx: dict) -> CodeAnalysis: ...
    async def generate_code(self, prompt: str, template: str) -> GeneratedCode: ...
    async def plan_test(self, req: TestRequirements) -> TestPlan: ...
    async def judge(self, evidence: Evidence, criteria: dict) -> Verdict: ...
```

**已规划实现**：
- `ClaudeCodeProvider` — 对接 ClaudeCode SDK
- `AnthropicProvider` — 对接 Anthropic API
- `OpenAIProvider` — 对接 OpenAI API
- `LocalLLMProvider` — 对接本地模型（Ollama 等）

不同项目可以启用不同的提供者组合，例如：代码分析走 ClaudeCode，VLM 走 OpenAI，视觉判定走本地模型。

### 3.2 代码分析器 (Analyzers)

扫描项目代码，输出结构化分析结果。

```python
class ICodeAnalyzer(Protocol):
    def supported_languages(self) -> list[str]: ...
    def scan(self, project_path: str) -> ProjectStructure: ...
    def find_test_points(self, structure: ProjectStructure) -> list[TestPoint]: ...
```

分析器按语言/技术栈拆分：C# 分析器、Lua 分析器、C++ 分析器等。分析器自身不调用 AI，它产出客观的代码结构；需要语义理解的部分交给流程层通过 AI Provider 处理。

### 3.3 生成器 (Generators)

根据分析结果和模板生成适配器、测试代码等。

```python
class IAdapterGenerator(Protocol):
    def supported_engines(self) -> list[str]: ...
    def generate(self, analysis: ProjectStructure, template: Template) -> GeneratedCode: ...
    def validate(self, code: GeneratedCode) -> ValidationResult: ...
```

### 3.4 执行器 (Executors)

启动被测游戏、驱动交互、收集证据。

```python
class IExecutor(Protocol):
    def supported_engines(self) -> list[str]: ...
    async def launch(self, build: BuildRef) -> Session: ...
    async def step(self, session: Session, action: Action) -> StepResult: ...
    async def terminate(self, session: Session) -> None: ...
```

### 3.5 Oracle (判定器)

判断测试是否通过。一个用例可以叠加多个 Oracle，任一失败即失败。

```python
class IOracle(Protocol):
    name: str
    def on_start(self, ctx: RunContext) -> None: ...
    def on_step(self, step: Step) -> OracleVerdict: ...
    def on_finish(self, ctx: RunContext) -> OracleVerdict: ...
    def collect_evidence(self) -> Evidence: ...
```

**已规划实现**：`CrashOracle`、`LogOracle`、`InvariantOracle`、`BusinessRuleOracle`、`LLMJudgeOracle`、`VisualOracle`。

### 3.6 引擎适配器 (Engine Adapters)

实现引擎特定的通信与能力。适配器本身包括两部分：
- **Host 侧**：运行在测试进程中，实现上述 `IExecutor` 接口
- **Runtime 侧**：运行在游戏进程中的 SDK，负责 UI 采集、输入注入、反射调用等

两侧通过 JSON-RPC（默认）或 gRPC（高性能场景）通信。

### 3.7 报告器 (Reporters)

输出不同格式的测试报告：HTML、JSON、JUnit XML、Markdown 等。

## 4. 流程层

流程层编排插件协作，完成从输入到输出的完整流程。流程本身不写死在代码里，而是由配置驱动。

### 4.1 标准流程

```
PRD + 代码
   │
   ▼
[Analyzer]         ─── 扫描代码，输出 ProjectStructure
   │
   ▼
[AI Provider]      ─── 语义理解，识别业务逻辑与测试点
   │
   ▼
[Generator]        ─── 生成适配器代码
   │
   ▼
[Validator]        ─── 编译检查、集成测试
   │
   ▼
[AI Provider]      ─── 基于 PRD 合成测试用例
   │
   ▼
[Executor + Oracle] ─── 执行用例、收集证据、判定
   │
   ▼
[Reporter]         ─── 产出报告
```

### 4.2 事件驱动

流程中的每一步都会发布事件，其他插件可以订阅响应：

```
project.analyzed        # 代码分析完成
adapter.generated        # 适配器生成完成
adapter.validated        # 适配器验证通过
testcase.synthesized     # 测试用例合成完成
run.started / run.finished
case.started / case.finished
defect.found
```

这让"主流程 + 插件扩展"成为可能：审计日志、成本统计、缺陷分发等横切关注点都以订阅者身份接入，不侵入主流程。

## 5. 集成层

同一套核心支持三种装配方式。

### 5.1 独立 CLI / 服务

作为独立工具运行，典型入口：

```bash
autotest run --prd prd.md --code ./project --ai claudecode
```

CLI 负责解析参数，加载配置，初始化核心与插件，启动流程。

### 5.2 作为库嵌入

宿主框架（如公司内部的游戏开发平台）直接 import 框架的 Library API：

```python
from autotest import TestingLibrary

class HostFramework:
    def __init__(self):
        self.testing = TestingLibrary(config=...)
        self.testing.bind_to(self)  # 订阅宿主的项目/代码变更事件
```

`TestingLibrary` 是对核心与流程层的薄封装，暴露稳定 API。宿主框架通过事件或直接调用触发测试流程，框架的插件系统照常工作。

### 5.3 REST / MCP 服务

面向外部系统（CI/CD、DevAgent）的远程调用入口：

- REST API：`POST /runs`、`GET /runs/{id}`、`POST /regression`
- MCP Server：将能力暴露为 MCP tools

服务层是流程层的薄壳，请求进来 → 启动流程 → 返回结果。

## 6. 解耦关键点

把"解耦"具体化为几条可以检查的规则：

### 6.1 AI 能力可替换

- 所有 AI 调用必须通过 `IAIProvider` 接口
- 禁止在分析器、生成器、执行器中直接 import AI SDK
- 配置文件切换 provider 不需要改任何代码

**检查方式**：在 CI 中扫描非 `plugins/ai-providers/` 目录下是否出现 `anthropic`、`openai` 等直接 import。

### 6.2 插件间不直接依赖

- 插件 A 需要插件 B 的能力时，从服务注册表按接口查找，不能 import B
- 插件之间通过事件总线异步通信

**检查方式**：每个插件的 `requirements.txt` 只能依赖微内核和 shared，不能依赖其他插件包。

### 6.3 引擎无关性

- 流程层不得出现 `if engine == "unity"` 之类的分支
- 引擎差异全部收敛在对应的适配器插件中
- 所有引擎适配器必须通过统一契约测试套件

### 6.4 核心可嵌入

- 核心启动不强制依赖 CLI 框架或 Web 框架
- 核心的生命周期可以被外部管理（start/stop 是显式调用）
- 核心的配置可以通过程序注入，不强制读文件

## 7. 通信协议

### 7.1 Host ↔ Runtime

默认协议：WebSocket + JSON-RPC 2.0。选择理由：跨语言支持好（C# / C++ / GDScript / Python 都有成熟库），调试友好。

高性能场景（如高频截图传输）可切换到 gRPC。协议抽象在 `packages/protocol` 中，上层不感知。

### 7.2 组件间

微内核内部：直接函数调用。
跨进程：通过服务注册表的代理实现 + 事件总线。
跨节点（分布式部署）：通过消息队列（Redis / RabbitMQ）。

## 8. 配置

配置分三层，从高到低覆盖：

1. **框架默认**：`config/defaults/`
2. **项目配置**：项目根的 `autotest.config.yaml`
3. **运行时参数**：CLI 参数或 API 调用参数

配置驱动插件的启用与参数，例如：

```yaml
ai:
  primary: claudecode
  fallback: [anthropic, openai]

analyzers:
  - csharp
  - lua

engines:
  - unity

oracles:
  - crash
  - log
  - business_rule
  - llm_judge
```

## 9. 安全

- 游戏内 SDK 必须通过条件编译/构建预设从正式发布包中剔除
- Cheat 接口白名单机制，未注册的方法拒绝调用
- 敏感数据（账号、支付）进入 AI Prompt 前必须脱敏
- 远程调用鉴权基于 JWT + 签名

## 10. 可观测性

- Agent 推理链全量 trace（OpenTelemetry 兼容）
- 结构化 JSON 日志，分级输出
- 指标按 Prometheus 格式暴露：运行次数、耗时、LLM token 消耗、失败率
- 所有 AI 调用记录 prompt / response / token / cost
