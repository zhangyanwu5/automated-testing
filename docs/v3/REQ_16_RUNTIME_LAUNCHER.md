# REQ_16_RUNTIME_LAUNCHER：运行时启动与就绪管理

## 目标

OpenGuard 执行器必须能够**自主启动目标应用、等待其就绪、选择正确的入口场景/URL，并在测试结束后可靠清理进程**，无需用户手动操作。这是"全自主执行"的前提。

本文档定义各 `project.type` 对应的启动协议、就绪判定规则、场景选择策略和健康检查方式。

---

## 设计原则

| 原则 | 说明 |
| --- | --- |
| **自主启动** | `openguard apply` 触发后，执行器必须自动拉起目标应用，不依赖用户手动操作 |
| **确定性就绪判定** | 必须有可检测的信号（日志模式、端口、文件、HTTP 响应）来判断应用已就绪，不依靠固定等待时间 |
| **场景感知** | 执行器根据测试矩阵的前置条件自动选择入口场景/URL，不硬编码 |
| **超时与清理** | 所有等待必须有超时上限；执行结束后必须清理残留进程 |
| **幂等性** | 若目标应用已在运行，执行器必须能识别并复用，或先关闭再重启 |

---

## Unity Editor PlayMode（`runtime.mode: editor-playmode`）

### 启动流程

```
1. 检查 Unity Editor 进程是否已在运行（通过进程名 Unity.exe / Unity）
   ├─ 已运行 → 检查是否打开了正确项目（通过日志或进程参数）
   │           ├─ 正确项目 → 跳过启动，直接进入场景选择
   │           └─ 错误项目 → 关闭并重启
   └─ 未运行 → 启动 Unity Editor
        命令：<unity_editor_path> -projectPath <project_root> -logFile <openguard/logs/editor.log>
        等待就绪信号（见下）

2. 等待编辑器就绪（最长 startup_timeout_seconds，默认 120s）
   就绪信号（任一满足）：
   ├─ editor.log 出现 "Compilation finished" 或 "All assemblies are up to date"
   └─ editor.log 出现 "Reloading assemblies after finished compiling" 完成

3. 场景选择（见场景选择策略）

4. 进入 PlayMode
   方式一（优先）：通过 Unity Editor 菜单接口或 EditorApplication.isPlaying=true
   方式二（fallback）：通过 Unity Test Framework CLI 模式启动
   等待就绪信号：
   ├─ editor.log 出现 "Entering Play Mode" 或 "Start Play Mode"
   └─ 或脚本可通过控制通道查询 Application.isPlaying == true
```

### 就绪信号规范

| 阶段 | 信号类型 | 匹配规则 |
| --- | --- | --- |
| 编辑器启动 | 日志文件 | `editor.log` 中出现 `"Compilation finished"` 或 `"All assemblies are up to date"` |
| PlayMode 启动 | 日志文件 | `editor.log` 中出现 `"Start Play Mode"` 或 `"Entering Play Mode"` |
| 场景加载完成 | 日志文件 | `editor.log` 中出现 `"Loaded scene"` 或 `"Finished loading scene"` |
| 游戏逻辑就绪 | 自定义信号（可选）| 测试脚本通过 RPC/WebSocket 查询，或日志中出现约定的 ready marker |

`config.yaml` 可覆盖默认就绪信号：
```yaml
runtime:
  health_check:
    type: log-pattern
    pattern: "LoginScene loaded"   # 自定义就绪信号（可选，缺省用内置规则）
    timeout_seconds: 120
```

### 场景选择策略

执行器根据测试矩阵第一个 P0 用例的 `precondition` 字段自动选择入口场景：

1. **从 `test_knowledge.md` 读取场景映射**（AI 在生成 test_knowledge 时填写）：
   ```yaml
   scene_map:
     login: Assets/Scenes/Login.unity
     main: Assets/Scenes/Main.unity
   ```
2. **从 `config.yaml` 的 `runtime.entry_scene` 读取**（用户手动配置）
3. **从项目 `ProjectSettings/EditorBuildSettings.asset` 推断**（取 index=0 的场景）
4. **fallback**：不指定场景，使用 Unity 编辑器当前已打开的场景

优先级：`test_knowledge.scene_map` > `config.yaml.runtime.entry_scene` > `EditorBuildSettings[0]` > 当前场景

---

## Web / H5（`runtime.mode: playwright`）

### 启动流程

```
1. 执行 runtime.start_command（若配置）
2. 等待 runtime.health_check.url 返回 HTTP 200（或自定义条件）
3. 启动 Playwright 浏览器，导航到 runtime.base_url
4. 等待页面加载完成（networkidle 或自定义 selector 出现）
```

### 就绪信号

| 信号类型 | 说明 |
| --- | --- |
| HTTP 健康检查 | `GET <health_check.url>` 返回 2xx |
| 页面元素 | Playwright 等待指定 selector 出现 |
| 网络静默 | `networkidle` 事件（500ms 内无新请求） |

---

## WebGL 游戏（`runtime.mode: playwright+js-bridge`）

### 启动流程

```
1. 启动静态文件服务器（若本地 build）或直接访问 runtime.webgl_url
2. Playwright 导航到 URL
3. 等待 WebGL Canvas 出现且 JS bridge 可用
   信号：window.__openguard_bridge_ready === true（脚本注入后查询）
4. 注入测试驱动代码
```

---

## Backend / API（`runtime.mode: http-api` / `grpc`）

### 启动流程

```
1. 执行 runtime.start_command 启动服务（若配置）
2. 轮询 runtime.health_check.url 直到返回 2xx（间隔 1s，最多 runtime.startup_timeout_seconds）
3. 验证 API 版本（若配置 runtime.api_version_endpoint）
```

---

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-16-01 | 执行器必须在 `openguard apply` 时根据 `config.yaml` 的 `runtime.mode` 自动选择对应的启动器，无需用户手动启动目标应用。 |
| REQ-16-02 | Unity editor-playmode 启动器必须先检查 Unity Editor 进程是否已在运行；若已运行且项目正确，直接复用；若项目不符，先关闭再重启。 |
| REQ-16-03 | Unity editor-playmode 启动器必须通过实时监听 `editor.log` 的日志模式判断编辑器和 PlayMode 的就绪状态，不使用固定等待时间。 |
| REQ-16-04 | 场景选择必须按优先级自动推断：`test_knowledge.scene_map` > `config.yaml runtime.entry_scene` > `EditorBuildSettings[0]` > 当前场景。 |
| REQ-16-05 | 所有等待（编辑器启动、PlayMode 进入、场景加载）必须有超时上限（由 `runtime.startup_timeout_seconds` 配置，默认 120s）；超时后必须写入 `env` 类型失败并终止执行。 |
| REQ-16-06 | 执行结束后（无论成功或失败），执行器必须清理由自己启动的目标应用进程；若应用是用户手动打开的，不得强制关闭。 |
| REQ-16-07 | Playwright 启动器必须等待 HTTP 健康检查通过后再开始测试；无健康检查配置时等待服务端口可达。 |
| REQ-16-08 | WebGL 启动器必须等待 JS bridge 注入完成且 `window.__openguard_bridge_ready === true` 后再执行测试步骤。 |
| REQ-16-09 | 启动过程中的所有步骤（启动命令、日志匹配、超时重试）必须写入 `events.jsonl`，失败时写入 `env` 类型错误和日志摘要。 |
| REQ-16-10 | `config.yaml` 的 `runtime.health_check.pattern` 必须支持自定义日志就绪信号，覆盖内置默认规则。 |
| REQ-16-11 | 执行器必须能区分"应用未启动"（`env` 失败）和"应用启动后崩溃"（`product` 失败），两者对应不同的失败类型和处置建议。 |
| REQ-16-12 | `test_knowledge.md` 必须支持 `scene_map` 结构化字段，由 AI 在生成 test_knowledge 时根据项目代码自动填写；执行器读取此字段做场景选择。 |

---

## `config.yaml` runtime 字段扩展

在现有 `runtime` 节下新增以下可选字段：

```yaml
runtime:
  mode: editor-playmode          # 已有
  unity_editor_path: ...         # 已有
  startup_timeout_seconds: 120   # 已有（默认值从 60 改为 120）
  health_check:
    type: log-pattern            # log-pattern | http | port
    pattern: null                # 自定义就绪日志模式（null 时用内置规则）
    url: null                    # HTTP 健康检查 URL（http 类型时）
    timeout_seconds: 120         # 健康检查超时（可独立配置）
  entry_scene: null              # Unity 入口场景路径（null 时自动推断）
  base_url: null                 # Web/WebGL 访问 URL
  start_command: null            # 应用启动命令（null 时不自动启动，要求应用已运行）
  auto_start: true               # 是否自动启动（false 时要求用户手动启动）
  auto_close: true               # 执行结束后是否自动关闭
  log_file: null                 # 日志文件路径（null 时用项目默认路径）
```

---

## `test_knowledge.md` 新增字段

AI 在生成 `test_knowledge.md` 时必须填写 `scene_map`（如果能从代码推断）：

```markdown
---
external_preconditions: []
scene_map:
  login: Assets/Scenes/Login.unity
  main: Assets/Scenes/Main.unity
  battle: Assets/Scenes/Battle.unity
---
```

执行器读取此字段选择入口场景，无需用户手动配置。

---

## 验收标准

- `openguard apply` 执行后，若 `runtime.auto_start: true`（默认），执行器自动启动 Unity Editor，无需用户手动操作。
- Unity Editor 启动后，执行器通过日志模式（非固定等待）判断就绪，误判率为零。
- 场景选择符合优先级规则，日志中记录选择依据。
- 超时后报告明确区分"启动超时"（env 失败）而非"测试失败"（product 失败）。
- 执行结束后 Unity Editor 进程状态符合 `auto_close` 配置。
- AI 生成的 `test_knowledge.md` 包含 `scene_map` 字段时，执行器正确使用；缺失时 fallback 到 `EditorBuildSettings`。

