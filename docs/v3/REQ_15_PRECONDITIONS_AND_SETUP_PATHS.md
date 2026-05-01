# REQ_15_PRECONDITIONS_AND_SETUP_PATHS：前置路径

## 目标

前置路径（Setup Path）是"把目标系统从初始状态带到可测试目标功能的状态"的步骤序列。它是独立于当前 change 的测试资产，跨 change 复用，避免每次测试重复建立相同的前置条件。

---

## 定义与示例

```text
示例：测试"任务奖励逻辑"的前置路径
  step 1: login               → 登录服务器，账号来自环境变量
  step 2: change_map_a        → 切换到地图 A
  step 3: set_level_10        → 设置等级到 10（白盒）或升级到 10（黑盒）
  状态标签: [logged_in, map_a, level_gte_10]
```

---

## 两种实现模式

| 模式 | 含义 | 优点 | 缺点 |
| --- | --- | --- | --- |
| `white-box` | 直接通过 RPC / console command / API 设置目标状态，跳过游戏内操作 | 快、稳定、不受 UI 变化影响 | 需要游戏提供调试接口 |
| `black-box` | 模拟真实玩家操作走完前置流程（点击、等待、交互） | 不需要调试接口，贴近真实 | 慢、容易 flaky、受 UI 变化影响大 |

`openqa/config.yaml` 中通过 `automation.precondition_mode` 声明优先使用哪种模式；两种都支持时优先使用 `white-box`。

---

## 目录结构

```text
openqa/knowledge/
  preconditions.yaml          # 已验证前置路径索引（按状态标签索引）

openqa/test_assets/
  setup_paths/                # 已验证的前置路径脚本（与测试脚本平级）
    login_server.py
    login_server.meta.yaml    # 锚点：绑定登录相关代码符号和 RPC
    change_map_a.py
    change_map_a.meta.yaml
    set_level.py
    set_level.meta.yaml
```

`preconditions.yaml` 按状态标签索引，引用 `setup_paths/` 中的脚本：

```yaml
# openqa/knowledge/preconditions.yaml
preconditions:
  - tags: [logged_in]
    setup_path: openqa/test_assets/setup_paths/login_server.py
    status: verified
    mode: white-box
    last_verified: 2026-05-01
    last_verified_run: run-2026-05-01T090000Z

  - tags: [logged_in, map_a]
    setup_path:
      - openqa/test_assets/setup_paths/login_server.py
      - openqa/test_assets/setup_paths/change_map_a.py
    status: verified
    mode: black-box
    last_verified: 2026-05-01

  - tags: [logged_in, map_a, level_gte_10]
    setup_path:
      - openqa/test_assets/setup_paths/login_server.py
      - openqa/test_assets/setup_paths/change_map_a.py
      - openqa/test_assets/setup_paths/set_level.py
    status: needs-review
    mode: white-box
    last_verified: 2026-04-10
```

---

## 前置路径生命周期

```text
openqa new 时：
  → AI 分析 EARS 前置条件 + 代码前置检查，推断所需状态标签
  → 查 preconditions.yaml：
      ├─ 找到匹配标签 → 直接引用，写入 test_matrix.json
      └─ 未找到 → 写入 unknowns.md，AI 生成候选步骤供用户确认

首次执行验证成功后：
  → 前置路径晋升到 test_assets/setup_paths/
  → preconditions.yaml 中状态改为 verified

代码变更时：
  → 扫描检查 setup_paths/ 的锚点哈希
  → 失效时降为 needs-review 或 stale
  → freshness.json 列出变化，下次 new/continue 时提示
```

---

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-15-01 | 前置路径必须存放在 `openqa/test_assets/setup_paths/`，每个路径脚本有对应的 `.meta.yaml` 锚点文件。 |
| REQ-15-02 | `preconditions.yaml` 必须按状态标签索引已验证的前置路径，供 `openqa new` 时查找复用。 |
| REQ-15-03 | 前置路径的实现模式（`white-box` / `black-box`）必须在 `preconditions.yaml` 中记录；`white-box` 模式优先。 |
| REQ-15-04 | 前置路径必须经过至少一次真实执行验证后才能沉淀到 `preconditions.yaml`；AI 生成的候选步骤需要用户或 AI 确认。 |
| REQ-15-05 | 前置路径的锚点失效（绑定的接口消失或变更）时，状态降为 `needs-review` 或 `stale`，并在 `freshness.json` 中标注；`stale` 状态的前置路径不得参与任何真实执行。 |
| REQ-15-06 | 矩阵任务必须显式引用前置路径（通过状态标签或路径引用），不得把前置步骤隐式嵌入测试脚本正文，以保证前置路径可独立复用和维护。 |
| REQ-15-07 | `openqa new` 时必须查询 `preconditions.yaml`，为当前 change 的前置需求匹配已有路径；无匹配时写入 `unknowns.md`，并提示需要补充或建立新的前置路径。 |
| REQ-15-08 | 已验证的前置路径在 `preconditions.yaml` 中按状态标签索引，跨 change 直接复用，不重复建立。 |

---

## 验收标准

- 后续 change 能复用历史前置路径，不重复询问已知前置步骤。
- `stale` 状态的前置路径不参与任何真实执行，且执行报告中有明确说明。
- 前置路径的锚点失效自动降级，不会静默污染新的测试计划。
- 矩阵中每个测试任务的前置状态标签明确，与 `preconditions.yaml` 可对应。
