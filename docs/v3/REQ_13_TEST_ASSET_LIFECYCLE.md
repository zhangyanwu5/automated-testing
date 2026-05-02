# REQ_13_TEST_ASSET_LIFECYCLE：测试资产生命周期

## 目标

OpenGuard 的测试脚本和测试套件必须有明确的生命周期管理：从 change 工作区生成，到跨 change 稳定复用，再到过期检测与修复。必须避免测试脚本静默跑错、积累腐化脚本、或每次 change 重复生成相同脚本的问题。

---

## 目录结构

```text
openguard/
  changes/<change-id>/

    test_scripts/           # 本次 change 生成的测试脚本草稿
    test_fixtures/          # 本次 change 专用的测试数据和前置状态
    test_matrix.json        # 引用 test_scripts/ 或 test_assets/ 中的脚本

  test_assets/              # 项目维度：跨 change 稳定复用的测试资产
    scripts/                # 已验证的可复用测试脚本
      <script>.py           # 脚本本体
      <script>.meta.yaml    # 锚点、置信度、状态、变更历史
    fixtures/               # 通用测试数据和前置状态

  suites/                   # 项目维度：稳定可复用的测试套件
    smoke/
      suite.yaml            # 套件定义：包含哪些脚本、依赖、执行顺序
    regression/
      suite.yaml
    requirement/
      <req-id>/
        suite.yaml
    full/
      suite.yaml
```

---

## 两个维度

| 维度 | 位置 | 说明 |
| --- | --- | --- |
| 变更维度 | `openguard/changes/<id>/test_scripts/` | 因本次 change 生成，生命周期跟随 change。 |
| 项目维度 | `openguard/test_assets/` / `openguard/suites/` | 跨 change 稳定积累，归档时从 change 晋升。 |


---

## 测试脚本生成位置

| 编号 | 需求 |
| --- | --- |
| REQ-13-01 | 测试脚本必须生成在 `openguard/` 内，不得写入目标项目的源码目录。 |
| REQ-13-02 | change 工作区内生成的脚本位于 `openguard/changes/<id>/test_scripts/`，作为草稿。 |

| REQ-13-03 | 稳定脚本通过 `archive` 晋升到 `test_assets/scripts/`，并建立 `.meta.yaml` 锚点文件。 |
| REQ-13-04 | `suites/` 中的套件定义引用 `test_assets/scripts/` 内的脚本路径，不得直接引用 change 工作区内的草稿。 |
| REQ-13-05 | 矩阵生成时应优先引用 `test_assets/` 中已有的稳定脚本；无对应稳定脚本时，生成草稿并记录来源。 |

---

## 侵入策略

OpenGuard 对目标项目的侵入分三档，在 `config.yaml` 中通过 `runtime.intrusion_strategy` 声明。

| 策略 | 含义 | 适用场景 |
| --- | --- | --- |
| `external-only` | 完全不侵入目标项目代码，只通过外部协议控制 | Web/H5、已内置 bridge 的项目 |
| `build-time-bridge` | 注入仅在 debug build 构建流程中完成，不改主分支代码 | Unity/Unreal 需要 RPC/WebSocket bridge 的项目 |
| `runtime-patch` | 运行时注入，用完还原；需显式授权并有可验证还原步骤 | 极少数无法用前两种方式的场景 |

| 编号 | 需求 |
| --- | --- |
| REQ-13-06 | 默认侵入策略为 `external-only`；使用 `build-time-bridge` 或 `runtime-patch` 必须在 `config.yaml` 中显式声明且记录授权。 |
| REQ-13-07 | `build-time-bridge` 注入必须限制在 debug build，不得影响生产构建配置，且 bridge 代码来源必须可追溯。 |
| REQ-13-08 | `runtime-patch` 必须有可验证的还原步骤；还原失败时必须阻断后续 `apply` 流程并报警，不得继续执行或归档。 |
| REQ-13-09 | 侵入策略变化视为项目测试画像变化，必须触发全量扫描和矩阵重建。 |

---

## 日志采集与增强策略

| 层次 | 方式 | 说明 |
| --- | --- | --- |
| 第一层：已有日志 | 采集目标应用正常输出的日志 | 不修改项目代码；只需配置日志路径和格式。 |
| 第二层：协商增强 | Agent 建议在特定位置增加日志或开启 debug 模式 | 输出建议，不自动写入代码；由开发者决定是否采纳。 |
| 第三层：debug build 开关 | 生成带额外日志开关的 debug 构建配置 | 不修改主分支代码；debug 配置与生产配置隔离。 |

| 编号 | 需求 |
| --- | --- |
| REQ-13-10 | OpenGuard 必须优先使用目标应用已有的日志输出，采集、过滤、摘要后写入 `events.jsonl`。 |
| REQ-13-11 | 当已有日志不足以支撑特定断言分析时，Agent 应输出日志增强建议（文件/符号/日志级别），不得自动修改目标项目代码。 |
| REQ-13-12 | debug build 模式的额外日志配置必须与生产配置隔离，测试完成后不需要手动还原（因为主分支未被修改）。 |

---

## 脚本锚点绑定

脚本晋升到 `test_assets/` 时，必须生成 `.meta.yaml` 记录锚点信息：

```yaml
# test_assets/scripts/login_flow.meta.yaml
script: scripts/login_flow.py
status: verified                      # verified / needs-review / stale / broken
confidence: high
created_from_change: change-2026-001
created_at: 2026-05-01
last_verified_at: 2026-05-01
last_verified_change: change-2026-001

bound_to:
  - type: code_symbol
    path: Assets/Scripts/Login/LoginManager.cs
    symbol: LoginManager.HandleLogin
    hash: a3f2c1b4
  - type: code_symbol
    path: Assets/Scripts/Login/LoginUI.cs
    symbol: LoginUI.OnSubmitClick
    hash: b7e9d4a2
  - type: requirement
    id: REQ-LOGIN-001
    fingerprint: c2a8f1e3

suite_membership:
  - smoke
  - requirement/REQ-LOGIN-001
```

| 编号 | 需求 |
| --- | --- |
| REQ-13-13 | 脚本晋升时必须记录绑定的代码符号路径和哈希、需求 ID 和指纹、所属套件，以及创建来源 change。 |
| REQ-13-14 | 锚点文件必须与脚本本体同名（`.meta.yaml` 后缀），且路径稳定，便于新鲜度校验直接查找。 |

---

## 脚本过期状态机

```text
verified
  │ 锚点代码符号哈希变化（但未消失）
  ▼
needs-review        ← 可以参与本地/CI 执行，但不能用于 release/nightly gate
  │ Agent 或人工确认仍有效，更新锚点哈希
  ▼
verified（锚点更新）

verified / needs-review
  │ 绑定的代码符号消失或需求指纹变化
  ▼
stale               ← 等待 Agent 重新对齐需求；不参与执行
  │ 需求对齐后重新验证通过
  ▼
verified（锚点更新）

stale
  │ 接口/符号完全断裂（无法映射）
  ▼
broken              ← 自动禁用；必须修复后才能参与任何执行
  │ 修复并重新通过验证
  ▼
verified
```

| 编号 | 需求 |
| --- | --- |
| REQ-13-15 | 每次 `continue` / `apply` / `openguard apply --suite` 前，必须对矩阵引用的脚本执行锚点新鲜度检查。 |
| REQ-13-16 | 锚点代码符号哈希变化时，脚本状态更新为 `needs-review`，并在 `freshness.json` 中列出变化详情。 |
| REQ-13-17 | 绑定的代码符号消失或需求指纹变化时，脚本状态更新为 `stale`，并从当前执行矩阵中移除（标记为 `skipped`，说明原因）。 |
| REQ-13-18 | 符号完全断裂时，脚本状态更新为 `broken`，从所有套件的可执行列表中移除，必须人工或 Agent 修复。 |
| REQ-13-19 | `needs-review` 状态的脚本不得用于 `release` 或 `nightly` gate；`stale` 和 `broken` 状态的脚本不得参与任何真实执行。 |
| REQ-13-20 | Agent 对 `needs-review` 脚本可生成修复建议（分析 delta，判断测试意图是否仍有效，生成更新版本作为 overlay）；用户或 Agent 确认后更新锚点，恢复为 `verified`。 |

---

## 脚本晋升与降级

| 操作 | 触发条件 | 结果 |
| --- | --- | --- |
| 晋升 | change `archive` 时，脚本多次 `apply` 通过，无 flaky，且人工或 Agent 确认稳定 | 脚本复制到 `test_assets/`，生成锚点文件，加入指定套件 |
| 更新锚点 | `needs-review` 脚本经 Agent/人工确认仍有效 | 更新锚点哈希，恢复 `verified` |
| 降级 | 锚点变化未及时确认，或多次 flaky | 状态降为 `needs-review`，从高级别 gate 移除 |
| 过期 | 符号消失或需求变更 | 状态变为 `stale`，从执行矩阵移除 |
| 禁用 | 断裂无法映射 | 状态变为 `broken`，必须显式修复 |

| 编号 | 需求 |
| --- | --- |
| REQ-13-21 | `archive` 阶段必须输出本次 change 中可晋升的脚本列表，包含晋升依据（历史 Run ID 列表、通过次数）和目标套件建议，由 Agent 或人工确认后执行晋升。 |
| REQ-13-22 | 脚本多次重跑 flaky 时，不得晋升；已晋升的脚本出现 flaky 时，状态降为 `needs-review` 并进入 flaky 治理流程。 |
| REQ-13-23 | 单次模型输出生成的脚本不得直接晋升；必须至少经过一次真实执行验证（有对应 Run ID 的通过记录）。 |


---

## 全局 suite 执行

`openguard apply --suite <name>` 在无 change 上下文时直接执行对应全局套件。

```bash
openguard apply --suite smoke
openguard apply --suite regression
openguard apply --suite requirement/REQ-LOGIN-001
openguard apply --suite full --gate release
openguard apply --suite smoke --review-level off   # 纯执行，不做 Review
```

| 编号 | 需求 |
| --- | --- |
| REQ-13-24 | `openguard apply --suite <name>` 必须在无 change 上下文时可独立执行对应套件，产出执行报告和证据。 |
| REQ-13-25 | 全局 suite 执行前必须对引用的脚本执行锚点新鲜度检查；`broken` 或 `stale` 脚本不参与执行，结果以 `skipped` 记录。 |
| REQ-13-26 | 全局 suite 执行报告必须标注套件名、脚本版本、锚点哈希和执行时的代码版本，保证可回溯。 |

---

## 验收标准

- 测试脚本不会出现在目标项目的源码目录中。
- `test_assets/` 中每个脚本都有对应的 `.meta.yaml` 锚点文件。
- `continue` / `apply` 在使用脚本前能明确报告每个脚本的锚点状态和新鲜度。
- `broken` 和 `stale` 脚本不参与任何真实执行，且执行报告中有明确说明。
- `needs-review` 脚本不出现在 `release` 和 `nightly` 门禁的执行矩阵中。
- 脚本晋升需要真实执行验证，不允许纯模型输出直接晋升。
- 全局 suite 执行结果可追溯到脚本版本、锚点和代码版本。
- 已验证的前置路径在 `preconditions.yaml` 中按状态标签索引，跨 change 直接复用，不重复建立。


---

## 前置路径（Setup Path）

前置路径的定义、实现模式、目录结构、生命周期和功能需求已独立为 `REQ_15_PRECONDITIONS_AND_SETUP_PATHS.md`。

矩阵任务必须显式引用前置路径（通过状态标签），不得把前置步骤隐式嵌入测试脚本正文（见 REQ-15-06）。


