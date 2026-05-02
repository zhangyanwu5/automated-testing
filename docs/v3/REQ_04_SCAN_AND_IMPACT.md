# REQ_04_SCAN_AND_IMPACT：扫描与影响分析

## 目标

OpenGuard 必须支持代码和需求的全量扫描、增量扫描、新鲜度校验和影响面分析，同时在 `openguard new` 时建立项目接口知识，为前置路径规划、测试脚本生成和断言提供依据。

## 扫描策略

| 模式 | 触发场景 | 产物 | 目的 |
| --- | --- | --- | --- |
| `init-probe` | `openguard init` 时 | `project_profile.yaml` 初稿 | 轻量探测：识别项目结构、主要子系统、控制通道类型入口，不深度扫描实现细节。 |
| `knowledge-scan` | `openguard new` 时（知识库不存在或目标模块无对应知识条目） | `event_catalog.yaml`、`protocol_catalog.yaml` 等知识条目 | 按需深度扫描目标模块及其前置依赖链，提取游戏接口知识。 |
| `full` | 首次接入、项目测试画像变化、配置变化、分析器升级、索引损坏、发布/夜间门禁 | `snapshot.json`、`full_index.json` | 建立可信基线。 |
| `incremental` | 日常需求/代码变更、本地开发、PR 验证 | `delta.json`、`impact_graph.json` | 降低成本，只分析变化和受影响依赖。 |
| `auto` | 默认模式 | 由系统结合 `project.type`、`scan` 配置和门禁选择 full 或 incremental | 平衡正确性与成本。 |

## 分层扫描策略

OpenGuard 采用**分层按需**策略，不在 `init` 时全量扫描：

```text
init 时（轻量）：
  → 识别项目结构、主要子系统
  → 探测控制通道类型（有 RPC？事件系统？控制台命令？）
  → 写入 project_profile.yaml，作为后续扫描的"地图"

openguard new 时（按需深度）：
  → 扫描目标模块代码、提取接口知识
  → 分析 EARS 前置条件要求
  → 顺着依赖链补扫相关模块（登录、地图切换等）
  → 查 preconditions.yaml：已有路径直接引用，缺失路径写入 unknowns

随着使用（逐渐完整）：
  → 前置路径验证成功后沉淀到 knowledge/
  → 接口知识运行验证后置信度提升
  → 下次同类测试直接复用，不再重新扫描
```

## 游戏接口知识提取

`knowledge-scan` 必须从代码中提取并写入知识库的内容：

| 提取目标 | 典型来源 | 写入知识条目 |
| --- | --- | --- |
| 事件系统 | EventBus 注册、事件类定义 | `event_catalog.yaml` |
| RPC / 网络协议 | Proto 文件、RPC 接口类 | `protocol_catalog.yaml` |
| 控制台命令 | Command 注册表、特性标注 | `control_channels.yaml` |
| 核心状态字段 | Player/Map/Quest 等数据类 | `state_schema.yaml` |
| 日志关键模式 | 日志格式定义、已有日志语句 | `log_patterns.yaml` |
| 测试辅助接口 | 已有的 Debug/Test bridge | `control_channels.yaml` |

每个知识条目必须绑定代码锚点（文件路径 + 符号名 + 哈希），代码变更时触发状态降级（与脚本锚点机制一致）。

## OpenSpec 知识有效性校验

当 `openguard new` 检测到 OpenSpec 时，必须对 OpenSpec 提供的知识进行有效性校验，再写入 `requirements.md` 和知识库：

| 场景 | 判断方式 | 处理 |
| --- | --- | --- |
| OpenSpec specs 描述的接口，代码中能找到对应实现且哈希匹配 | 符号对应 + 哈希比对 | 置信度 `high`，直接使用 |
| OpenSpec specs 存在，但对应代码已被重构或删除 | 符号扫描找不到 | 置信度降低，标记为 `stale`，写入 unknowns |
| OpenSpec 有进行中的 change（未 archive） | OpenSpec change 状态检查 | 提示"规格可能尚未稳定"，置信度 `medium` |
| OpenSpec tasks 已全部完成并 archive | 对应代码有完整实现 | 置信度 `high` |
| OpenSpec 有接口描述但无对应代码实现 | 实现缺失 | 写入 unknowns："规格存在但实现缺失，无法测试" |

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-04-01 | 扫描必须记录文件路径、内容哈希、语言、符号摘要和分析器版本。 |
| REQ-04-02 | 扫描必须记录 `requirements.md` 中 EARS 需求和 OpenSpec specs 的指纹。 |
| REQ-04-03 | 增量扫描必须输出 `delta.json`，包含新增、修改、删除、重命名文件。 |
| REQ-04-04 | 影响分析必须输出 `impact_graph.json`，描述代码、需求、Review 范围、测试类型之间的关系。 |
| REQ-04-05 | 每次 `continue` / `apply` 前必须执行新鲜度校验，输出 `freshness.json`。 |
| REQ-04-06 | 索引过期、需求指纹变化、分析器版本变化或项目测试画像变化时，不得继续使用旧矩阵执行。 |
| REQ-04-07 | 扫描必须遵循 `openguard/config.yaml` 中的 `scan.exclude` 配置，避免依赖、构建产物和隐私目录进入索引。 |
| REQ-04-08 | 扫描入口和符号抽取必须受 `project.type` 影响，例如 Web 侧重路由、组件和端到端入口，Unity / Unreal 侧重场景、资源、脚本、配置和引擎自动化入口。 |
| REQ-04-09 | `openguard init` 的初始探测必须轻量，只识别项目结构、控制通道类型和主要子系统，写入 `project_profile.yaml`，不做全量接口深度扫描。 |
| REQ-04-10 | `openguard new` 时必须对目标模块及其前置依赖链执行 `knowledge-scan`，提取事件、RPC、命令、状态字段、日志模式等游戏接口知识，写入 `openguard/knowledge/` 对应条目。 |
| REQ-04-11 | 游戏接口知识条目必须绑定代码锚点（文件路径 + 符号名 + 哈希）；代码变更时锚点失效，对应知识条目降为 `needs-review` 或 `stale`，并写入 `freshness.json`。 |
| REQ-04-12 | `openguard new` 检测到 OpenSpec 时，必须对 OpenSpec 内容做有效性校验，判断规格与当前代码的一致性，并将校验结果（置信度、状态）写入 `openspec_link.yaml`。 |
| REQ-04-13 | 自动推断出的画像和接口知识证据必须可追溯到具体文件、配置或命令探测结果；冲突或低置信度证据必须进入 unknowns。 |
| REQ-04-14 | 扫描必须同步检查 `test_assets/` 中所有脚本和前置路径的锚点哈希，对比当前代码快照；锚点失效时更新状态并写入 `freshness.json`。 |

## 影响分析范围

- 代码模块、函数、事件、接口、状态面。
- 需求验收项与代码变更映射。
- 需要 Review 的文件与风险点。
- 需要新增、重跑、跳过的测试子图。
- 受影响基线、测试数据、前置路径和宿主环境。
- 知识库中受影响的接口知识条目（事件、RPC、命令、状态字段）。

## 验收标准

- 同一输入下扫描结果可复现。
- 增量扫描结果可追溯到上一份快照。
- 影响图能被 `continue`、`apply`、Review、测试矩阵共同消费。
- `openguard init` 不触发全量接口深度扫描；接口知识随 `openguard new` 按需积累。
- OpenSpec 知识有效性校验结果写入 `openspec_link.yaml`，置信度和状态可被后续步骤查询。

